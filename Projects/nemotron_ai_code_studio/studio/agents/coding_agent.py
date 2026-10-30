"""Coding agent: the orchestrator.

understand -> plan -> search -> read -> understand dependencies -> propose changes -> apply -> validate -> run tests ->
inspect errors -> fix -> diff -> present. The model drives the loop through structured tool calls; this class supplies the
repository context, enforces mode and approval rules, streams events to the UI and runs automatic validation.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..approvals import ApprovalBroker
from ..config import settings
from ..security import redact
from ..services.nvidia_service import SYSTEM_PROMPT, NvidiaError, NvidiaService
from ..services.repository_service import ActiveRepository
from ..tools.registry import ToolContext, ToolOutcome, execute_tool, tool_schemas
from .debugging_agent import DebuggingAgent
from .planning_agent import PlanningAgent
from .testing_agent import TestingAgent

Emit = Callable[[dict[str, Any]], None]
MODES = ("ask", "plan", "agent")
MAX_FIX_ROUNDS = 2
MAX_REPEATED_CALLS = 3
MAX_NUDGES = 2
FILE_WRITE_TOOLS = {"write_file", "create_file", "edit_file", "delete_file", "rename_file"}
# A reply that only announces what the model is about to do, without having done it.
_INTENT = re.compile(r"\b(i['’]ll|i will|i['’]m going to|i am going to|let me|let['’]s|next,? i|now i|going to|here is (?:the|my) plan|plan:)", re.I)


def _needs_action(text: str) -> bool:
    text = text.strip()
    return not text or text.endswith(":") or bool(_INTENT.search(text[:1500]))


@dataclass
class RunResult:
    message: str = ""
    inspected: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    change_id: str = ""
    ok: bool = True


class ConversationStore:
    """Keeps recent user/assistant turns (text only) so follow-up questions have context without resending tool traces."""

    def __init__(self, max_turns: int = 12) -> None:
        self._turns: dict[str, list[dict[str, str]]] = {}
        self._max = max_turns * 2

    def history(self, conversation_id: str) -> list[dict[str, str]]:
        return [dict(m) for m in self._turns.get(conversation_id, [])]

    def add(self, conversation_id: str, user: str, assistant: str) -> None:
        turns = self._turns.setdefault(conversation_id, [])
        turns.append({"role": "user", "content": user[:8000]})
        turns.append({"role": "assistant", "content": assistant[:8000]})
        del turns[: max(0, len(turns) - self._max)]
        if len(self._turns) > 100:
            self._turns.pop(next(iter(self._turns)))

    def clear(self, conversation_id: str) -> None:
        self._turns.pop(conversation_id, None)


class CodingAgent:
    def __init__(self, nvidia: NvidiaService, broker: ApprovalBroker) -> None:
        self.nvidia = nvidia
        self.broker = broker
        self.planner = PlanningAgent()
        self.tester = TestingAgent()
        self.debugger = DebuggingAgent()

    async def run(self, repo: ActiveRepository, request: str, mode: str, history: list[dict[str, str]], emit: Emit, model: str | None = None) -> RunResult:
        mode = mode if mode in MODES else "ask"
        loop = asyncio.get_running_loop()
        change_id = repo.tracker.begin()
        state = {"call": ""}
        ctx = ToolContext(repo=repo, change_id=change_id, mode=mode)
        ctx.request_approval = lambda req: self.broker.request(req, emit)
        ctx.emit_output = lambda text: loop.call_soon_threadsafe(emit, {"type": "tool_output", "id": state["call"], "text": text})
        result = RunResult(change_id=change_id)

        async def call_tool(call_id: str, name: str, args: dict[str, Any]) -> ToolOutcome:
            state["call"] = call_id
            emit({"type": "tool_start", "id": call_id, "name": name, "args": _short_args(args)})
            outcome = await execute_tool(ctx, name, args)
            emit({"type": "tool_end", "id": call_id, "name": name, "ok": outcome.ok, "summary": outcome.summary, "preview": outcome.content[:1800]})
            emit({"type": "files", "inspected": list(ctx.inspected), "modified": list(ctx.modified)})
            if name in FILE_WRITE_TOOLS and outcome.ok:
                await self._present_changes(repo, ctx, emit)  # live "changes so far" while the agent works
            return outcome

        try:
            emit({"type": "status", "text": "Selecting relevant files"})
            bundle = await asyncio.to_thread(repo.context.build, request)
            for item in bundle.files:
                ctx.note_inspected(item.path)
            emit({"type": "context", "files": bundle.public(), "tokens": bundle.tokens})

            system = f"{SYSTEM_PROMPT}\n\n{self.planner.instructions(mode)}\n\n{bundle.to_prompt()}"
            messages: list[dict[str, Any]] = [{"role": "system", "content": system}, *history, {"role": "user", "content": request}]
            schemas = tool_schemas(mode)
            max_steps = self.planner.max_steps(mode, settings.agent_max_steps)
            seen: dict[str, int] = {}
            fix_rounds = 0
            validated_signature: str | None = None
            empty_replies = 0
            nudges = 0
            final_text = ""

            for step in range(max_steps):
                emit({"type": "step", "n": step + 1, "max": max_steps})
                emit({"type": "status", "text": "Thinking" if step == 0 else "Continuing"})
                turn = None
                async for event in self.nvidia.agent_chat(messages, schemas, model=model):
                    if event["type"] == "content":
                        emit({"type": "token", "text": event["text"]})
                    elif event["type"] == "reasoning":
                        emit({"type": "reasoning", "text": event["text"]})
                    elif event["type"] == "done":
                        turn = event["result"]
                if turn is None:
                    raise NvidiaError("The model returned no response.", 502)

                if turn.tool_calls:
                    empty_replies = 0
                    entries = []
                    for call in turn.tool_calls:
                        entry = call.as_message_entry()
                        if call.error:
                            entry["function"]["arguments"] = "{}"
                        entries.append(entry)
                    messages.append({"role": "assistant", "content": turn.content or None, "tool_calls": entries})
                    for call in turn.tool_calls:
                        if call.error:
                            emit({"type": "tool_start", "id": call.id, "name": call.name, "args": {}})
                            emit({"type": "tool_end", "id": call.id, "name": call.name, "ok": False, "summary": "invalid arguments", "preview": call.error})
                            messages.append({"role": "tool", "tool_call_id": call.id, "content": f"ERROR: {call.error}"})
                            continue
                        signature = f"{call.name}:{json.dumps(call.arguments, sort_keys=True, default=str)}"
                        seen[signature] = seen.get(signature, 0) + 1
                        if seen[signature] > MAX_REPEATED_CALLS and call.name not in {"run_tests", "run_linter"}:
                            outcome = ToolOutcome("ERROR: you already made this exact call several times with the same result. Change your approach.", False, "repeated call")
                        else:
                            outcome = await call_tool(call.id, call.name, call.arguments)
                        messages.append({"role": "tool", "tool_call_id": call.id, "content": outcome.content})
                    continue

                final_text = turn.content.strip()
                if mode == "agent" and not ctx.modified and nudges < MAX_NUDGES and (turn.finish_reason == "length" or _needs_action(final_text)):
                    # The model stopped after reading (or only announced a plan). Push it to actually make the edits.
                    nudges += 1
                    messages.append({"role": "assistant", "content": final_text or "(no reply)"})
                    messages.append({"role": "user", "content": (
                        "You have not modified any files yet. Carry out the requested change now: call edit_file, write_file or create_file. "
                        "Do not describe what you will do; do it. If the request truly needs no file changes, answer in one short paragraph."
                    )})
                    emit({"type": "status", "text": "Asking the model to make the edits"})
                    continue
                if not final_text:
                    empty_replies += 1
                    if empty_replies <= 1:
                        messages.append({"role": "user", "content": "Your last reply was empty. Continue the task or give your final answer."})
                        continue
                    if ctx.modified:
                        final_text = "Changes were made; review them below."
                        emit({"type": "notice", "text": final_text})
                    else:
                        final_text = (
                            f"The agent stopped without finishing: the model returned an empty reply after inspecting {len(ctx.inspected)} file(s) "
                            "and made no changes. Click Continue to try again, rephrase the request, or pick another model."
                        )
                        emit({"type": "notice", "text": final_text, "incomplete": True})
                if turn.finish_reason == "length":
                    final_text += "\n\n(The reply was cut off by the output limit.)"
                    emit({"type": "notice", "text": "The reply was cut off by the model's output limit. Click Continue to go on.", "incomplete": True})
                elif mode == "agent" and not ctx.modified and nudges >= MAX_NUDGES and _needs_action(final_text):
                    emit({"type": "notice", "text": "The agent stopped without changing any files: the model described the work but never made an edit. Click Continue to try again.", "incomplete": True})

                if mode == "agent" and ctx.modified and settings.auto_validate:
                    signature = await asyncio.to_thread(_changes_signature, ctx)
                    if signature != validated_signature and fix_rounds <= MAX_FIX_ROUNDS:
                        validated_signature = signature
                        emit({"type": "status", "text": "Validating changes"})
                        report = await self.tester.validate(ctx, lambda c, cid, name, args: call_tool(f"{cid}-{fix_rounds}", name, args))
                        emit({"type": "validation", **report.public()})
                        if report.passed is False and fix_rounds < MAX_FIX_ROUNDS:
                            fix_rounds += 1
                            brief = await asyncio.to_thread(self.debugger.diagnose, repo, report.failure_output)
                            messages.append({"role": "assistant", "content": final_text or "Changes applied."})
                            messages.append({"role": "user", "content": "Automatic validation failed after your edits. Fix the problems with the smallest correct change, then give your final report.\n\n" + brief.text})
                            emit({"type": "status", "text": f"Fixing validation problems (attempt {fix_rounds})"})
                            continue
                        if report.passed is False:
                            final_text += "\n\nValidation still reports problems after the automatic fix attempts; please review the output."
                            emit({"type": "notice", "text": "Validation still reports problems after the automatic fix attempts; please review the output."})
                break
            else:
                final_text = (final_text or "") + f"\n\nStopped after {max_steps} steps. The work may be incomplete; ask me to continue."
                emit({"type": "notice", "text": f"Stopped after {max_steps} steps. The work may be incomplete; click Continue to go on.", "incomplete": True})

            result.message = redact(final_text)
        except NvidiaError as exc:
            result.ok = False
            result.message = exc.message
            emit({"type": "error", "message": exc.message})
        except asyncio.CancelledError:
            ctx.cancel.set()
            await self._present_changes(repo, ctx, emit)
            emit({"type": "cancelled", "change_id": change_id, "inspected": list(ctx.inspected), "modified": list(ctx.modified)})
            raise
        except Exception as exc:  # never leave the UI hanging
            result.ok = False
            result.message = f"The agent stopped because of an internal error ({exc.__class__.__name__})."
            emit({"type": "error", "message": result.message})
        finally:
            result.inspected, result.modified = list(ctx.inspected), list(ctx.modified)

        await self._present_changes(repo, ctx, emit)
        emit({"type": "done", "message": result.message, "ok": result.ok, "inspected": result.inspected, "modified": result.modified, "change_id": change_id, "mode": mode})
        return result

    async def _present_changes(self, repo: ActiveRepository, ctx: ToolContext, emit: Emit) -> None:
        files = await asyncio.to_thread(repo.tracker.summary, ctx.change_id, repo.workspace)
        if files:
            diffs = {item["path"]: await asyncio.to_thread(repo.tracker.file_diff, ctx.change_id, repo.workspace, item["path"]) for item in files}
            emit({"type": "changes", "change_id": ctx.change_id, "files": files, "diffs": diffs})


def _changes_signature(ctx: ToolContext) -> str:
    return json.dumps(ctx.repo.tracker.summary(ctx.change_id, ctx.repo.workspace), sort_keys=True)


def _short_args(args: dict[str, Any]) -> dict[str, Any]:
    short: dict[str, Any] = {}
    for key, value in list(args.items())[:6]:
        if isinstance(value, str):
            short[key] = redact(value)[:160]
        elif isinstance(value, (int, float, bool)) or value is None:
            short[key] = value
        else:
            short[key] = redact(json.dumps(value, default=str))[:160]
    return short
