"""Right panel: the AI agent chat, model picker, live activity timeline, approvals and the keep/revert review."""

from __future__ import annotations

import json
import time
from html import escape
from typing import Any

import streamlit as st

from studio.chat import ChangeSet, ChatMessage, TextBlock, ToolCall, add_notice, apply_event
from studio.config import settings
from studio.models import available_models, get_model

from .dialogs import ensure_folder
from .state import AgentRun, S, attempt, broker, coding_agent, conversations, log, reload_paths, repo, sync_after_change

POLL_SECONDS = 0.4
SUGGESTIONS = [
    "Explain how this repository is structured",
    "Find likely bugs in this repository",
    "Plan unit tests for the main modules",
]
MODES = ["ASK", "PLAN", "AGENT"]
MODE_HELP = {
    "ASK": "Read-only answers about the repository.",
    "PLAN": "Read-only implementation plan.",
    "AGENT": "Edits files. You keep or revert every change.",
}
STATUS_LETTER = {"added": "A", "modified": "M", "deleted": "D"}

# tool name -> (present tense, past tense)
VERBS: dict[str, tuple[str, str]] = {
    "list_files": ("Listing", "Listed"),
    "get_repository_tree": ("Scanning tree", "Scanned tree"),
    "read_file": ("Reading", "Read"),
    "read_files": ("Reading", "Read"),
    "search_code": ("Searching", "Searched"),
    "search_filename": ("Finding file", "Found file"),
    "find_references": ("Finding references", "Found references"),
    "get_file_metadata": ("Inspecting", "Inspected"),
    "write_file": ("Writing", "Wrote"),
    "create_file": ("Creating", "Created"),
    "edit_file": ("Editing", "Edited"),
    "delete_file": ("Deleting", "Deleted"),
    "rename_file": ("Renaming", "Renamed"),
    "run_command": ("Running", "Ran"),
}
WRITE_TOOLS = {"write_file", "create_file", "edit_file", "delete_file", "rename_file"}


def _running() -> bool:
    return st.session_state.get("run") is not None


# ------------------------------------------------------------------ run lifecycle
def _start_run(prompt: str) -> None:
    current = repo()
    if current is None:
        st.toast("Connect a repository first.", icon=":material/error:")
        return
    if not settings.nvidia_api_key:
        st.toast("Set NVIDIA_API_KEY in .env or in Settings before using the agent.", icon=":material/key:")
        return
    mode = (S.mode or "ASK").lower()
    if mode == "agent" and not ensure_folder():
        return
    current = repo()
    model = get_model(S.model)
    user = ChatMessage(role="user", text=prompt[:8000], mode=mode)
    answer = ChatMessage(role="assistant", mode=mode, model=model.label, streaming=True, status="Starting")
    S.messages = [*S.messages, user, answer]
    S.cursor = 0
    S.approvals = {}
    run = AgentRun(coding_agent, broker, conversations, current, prompt[:8000], mode, S.conversation_id, model=model.id)
    S.run = run
    run.start()
    log(f"Agent ({mode.upper()}, {model.label}): {prompt[:80]}")


def _drain() -> bool:
    """Applies new agent events to the transcript. Returns True when the run has ended."""
    run: AgentRun | None = st.session_state.get("run")
    if run is None:
        return False
    finished = run.finished.is_set()  # read first: every event is emitted before this flag is set
    events, cursor = run.events_since(S.cursor)
    answer = next((m for m in reversed(S.messages) if m.role == "assistant"), None)
    if answer is not None:
        for event in events:
            apply_event(answer, event, S.approvals)
        if finished:
            if answer.streaming:  # the run ended without telling us why: never leave the user guessing
                add_notice(answer, "The agent ended unexpectedly before finishing. Click Continue to try again.")
                answer.incomplete = True
            answer.streaming, answer.status = False, ""
            answer.finished = answer.finished or time.time()
    S.cursor = cursor
    if finished:
        modified = list(answer.modified) if answer is not None else []
        S.run = None
        S.approvals = {}
        current = repo()
        if modified and current is not None:
            current.reindex()
            sync_after_change(modified)
        log("Agent run finished")
        return True
    return False


# ------------------------------------------------------------------ activity timeline
def _target(tool: ToolCall) -> str:
    args = tool.args if isinstance(tool.args, dict) else {}
    paths = args.get("paths")
    if isinstance(paths, str):  # list arguments arrive as a JSON string
        try:
            paths = json.loads(paths)
        except ValueError:
            paths = [paths]
    if isinstance(paths, list) and paths:
        shown = ", ".join(str(p) for p in paths[:3])
        return shown + (f" +{len(paths) - 3} more" if len(paths) > 3 else "")
    if args.get("from_path"):
        return f"{args.get('from_path')} to {args.get('to_path', '')}"
    for key in ("path", "query", "command", "symbol", "name", "branch", "message"):
        if args.get(key):
            return str(args[key])[:120]
    return ""


def _timeline(tools: list[ToolCall]) -> str:
    rows = []
    for tool in tools:
        present, past = VERBS.get(tool.name, (tool.name.replace("_", " ").capitalize(), tool.name.replace("_", " ").capitalize()))
        state = "run" if not tool.done else ("ok" if tool.ok else "fail")
        kind = "write" if tool.name in WRITE_TOOLS else ("exec" if tool.name == "run_command" else "read")
        elapsed = (tool.ended or time.time()) - tool.started
        result = escape(tool.summary[:90]) if tool.done and tool.summary else ""
        rows.append(
            f"<div class='act {state} {kind}'><span class='ic'></span>"
            f"<span class='verb'>{present if not tool.done else past}</span>"
            f"<code class='tgt'>{escape(_target(tool))}</code>"
            f"<span class='res'>{result}</span><span class='dur'>{elapsed:.1f}s</span></div>"
        )
    return "<div class='timeline'>" + "".join(rows) + "</div>"


def _blocks(message: ChatMessage) -> None:
    group: list[ToolCall] = []
    for block in message.blocks:
        if isinstance(block, ToolCall):
            group.append(block)
            continue
        if group:
            st.markdown(_timeline(group), unsafe_allow_html=True)
            group = []
        if isinstance(block, TextBlock) and block.text.strip():
            st.markdown(block.text)
    if group:
        st.markdown(_timeline(group), unsafe_allow_html=True)


def _tool_details(message: ChatMessage) -> None:
    tools = [t for t in message.tools if t.args or t.output]
    if not tools:
        return
    with st.expander(f"Tool details ({len(tools)})", icon=":material/terminal:"):
        for tool in tools:
            st.markdown(f"**{tool.name}** {'ok' if tool.ok else 'failed'}" + (f" - {escape(tool.summary)}" if tool.summary else ""))
            if tool.args:
                st.code(json.dumps(tool.args, indent=2, default=str)[:1500], language="json")
            if tool.output:
                st.code(tool.output[-2500:], language=None, line_numbers=False)


def _runbar(message: ChatMessage) -> None:
    now = time.time()
    elapsed = int(now - message.started)
    steps = f"step {message.step}/{message.max_steps}" if message.step else ""
    status = message.status or "Working"
    running_tool = next((t for t in reversed(message.tools) if not t.done), None)
    if running_tool is not None:  # say exactly what is running right now
        present = VERBS.get(running_tool.name, (running_tool.name.replace("_", " ").capitalize(),))[0]
        status = f"{present} {_target(running_tool)}".strip()
    elif status in {"Thinking", "Continuing"} or status.startswith("Running "):
        status = "Thinking" if message.reasoning else "Waiting for the model"
    idle = int(now - message.last_event)
    if idle >= 8:
        status += f" ({idle}s, still working)"
    meta = " | ".join(x for x in (steps, f"{elapsed}s") if x)
    st.markdown(
        f"<div class='runbar'><span class='spin'></span><span class='st'>{escape(status)}</span>"
        f"<span class='meta'>{escape(meta)}</span></div>",
        unsafe_allow_html=True,
    )
    if message.reasoning:
        tail = message.reasoning.strip().replace("\n", " ")[-260:]
        st.markdown(f"<div class='think'>Thinking: {escape(tail)}</div>", unsafe_allow_html=True)


# ------------------------------------------------------------------ keep / revert
def _pending(changes: ChangeSet) -> list[str]:
    done = set(changes.kept) | set(changes.reverted)
    return [item["path"] for item in changes.files if item["path"] not in done]


def _refresh_state(changes: ChangeSet) -> None:
    if _pending(changes):
        changes.state = "pending"
    elif changes.kept and changes.reverted:
        changes.state = "mixed"
    else:
        changes.state = "rejected" if changes.reverted else "accepted"


def _keep(message: ChatMessage, paths: list[str]) -> None:
    current, changes = repo(), message.changes
    if current is None or changes is None:
        return
    for path in paths:
        current.tracker.keep_file(changes.change_id, path)
        changes.kept.append(path)
    _refresh_state(changes)
    if changes.state == "accepted":
        current.tracker.accept(changes.change_id)
    log("Kept " + ", ".join(paths))


def _revert(message: ChatMessage, paths: list[str]) -> None:
    current, changes = repo(), message.changes
    if current is None or changes is None:
        return
    restored: list[str] = []
    with current.lock:
        for path in paths:
            ok, done = attempt(current.tracker.revert_file, changes.change_id, current.workspace, path)
            if ok and done:
                current.index.refresh_file(path)
                changes.reverted.append(path)
                restored.append(path)
    _refresh_state(changes)
    if restored:
        reload_paths(restored)
        log("Reverted " + ", ".join(restored))
        st.toast(f"Reverted {len(restored)} file(s).", icon=":material/undo:")


def _changes_card(message: ChatMessage, changes: ChangeSet) -> None:
    live = message.streaming
    pending = _pending(changes)
    adds = sum(int(i.get("additions", 0)) for i in changes.files)
    dels = sum(int(i.get("deletions", 0)) for i in changes.files)
    count = len(changes.files)
    with st.container(border=True, key=f"review_{message.id}"):
        title = "Changes so far" if live else ("Review changes" if pending else "Changes reviewed")
        st.markdown(
            f"<div class='rev-head'><b>{title}</b><span>{count} file{'s' if count != 1 else ''} "
            f"<i class='add'>+{adds}</i> <i class='del'>-{dels}</i></span></div>",
            unsafe_allow_html=True,
        )
        if not live and pending:
            keep_all, revert_all = st.columns(2)
            if keep_all.button("Keep all", key=f"keepall:{message.id}", type="primary", icon=":material/check:", width="stretch"):
                _keep(message, pending)
                st.rerun()
            if revert_all.button("Revert all", key=f"revertall:{message.id}", icon=":material/undo:", width="stretch"):
                _revert(message, pending)
                st.rerun()
            st.caption("The edits are already in your working copy. Keep them, or revert to the previous version.")
        for item in changes.files:
            path = item["path"]
            decided = "kept" if path in changes.kept else "reverted" if path in changes.reverted else ""
            label = f"`{STATUS_LETTER.get(item['status'], '?')}` {path}  :green[+{item['additions']}] :red[-{item['deletions']}]"
            if decided:
                label += f"  :gray[{decided}]"
            with st.expander(label, expanded=bool(not live and not decided and len(pending) <= 3)):
                st.code(changes.diffs.get(path) or "(no textual diff)", language="diff", line_numbers=False)
                if not live and not decided:
                    keep, revert = st.columns(2)
                    if keep.button("Keep", key=f"keep:{message.id}:{path}", icon=":material/check:", width="stretch"):
                        _keep(message, [path])
                        st.rerun()
                    if revert.button("Revert", key=f"revert:{message.id}:{path}", icon=":material/undo:", width="stretch"):
                        _revert(message, [path])
                        st.rerun()
        if not live and not pending:
            st.caption({"accepted": "All changes kept. Commit them from Source Control.", "rejected": "All changes reverted; the files were restored.",
                        "mixed": "Some changes kept, some reverted."}.get(changes.state, ""))


# ------------------------------------------------------------------ messages
def _render_message(message: ChatMessage) -> None:
    if message.role == "user":
        with st.chat_message("user"):
            st.markdown(message.text)
        return
    with st.chat_message("assistant"):
        head = message.mode.upper() + (f"  |  {message.model}" if message.model else "")
        st.caption(head)
        if message.context_files:
            with st.expander(f"Context ({len(message.context_files)} files)", icon=":material/folder_open:"):
                st.markdown("\n".join(f"- `{p}`" for p in message.context_files[:40]))
        if message.streaming:
            _runbar(message)
        elif message.reasoning:
            with st.expander("Reasoning", icon=":material/psychology:"):
                st.markdown(message.reasoning[-6000:])
        _blocks(message)
        if message.error:
            st.error(message.error)
        if message.changes is not None:
            _changes_card(message, message.changes)
        validation = message.validation
        if validation is not None:
            passed = validation.get("passed")
            (st.success if passed else st.warning if passed is None else st.error)(
                "Validation passed" if passed else "Nothing could be validated" if passed is None else "Validation failed"
            )
            if validation.get("steps"):
                st.caption("; ".join(f"{s.get('name')}: {s.get('status')}" for s in validation["steps"]))
        if not message.streaming:
            _tool_details(message)
            if message.inspected or message.modified:
                took = f"  |  {int(message.finished - message.started)}s" if message.finished else ""
                with st.expander(f"Inspected {len(message.inspected)}  |  modified {len(message.modified)}{took}", icon=":material/fact_check:"):
                    if message.inspected:
                        st.markdown("**Inspected**\n" + "\n".join(f"- `{p}`" for p in message.inspected[:60]))
                    if message.modified:
                        st.markdown("**Modified**\n" + "\n".join(f"- `{p}`" for p in message.modified[:60]))


def _render_approvals() -> None:
    for approval_id, approval in list(S.approvals.items()):
        with st.container(border=True):
            st.markdown(f"**Approval needed: {approval.get('title', 'Action')}**")
            st.caption(approval.get("reason", ""))
            for key, value in (approval.get("details") or {}).items():
                st.markdown(f"{key}: `{value}`")
            yes, no = st.columns(2)
            decided: bool | None = None
            if yes.button("Approve", key=f"ok:{approval_id}", type="primary", width="stretch"):
                decided = True
            if no.button("Deny", key=f"no:{approval_id}", width="stretch"):
                decided = False
            if decided is not None:
                broker.resolve(approval_id, decided)
                S.approvals.pop(approval_id, None)
                st.rerun(scope="fragment")


# ------------------------------------------------------------------ panel
def _transcript() -> None:
    ended = _drain()
    with st.container(key="chat"):
        if not S.messages:
            _intro()
        for message in S.messages:
            _render_message(message)
        _render_approvals()
        last = S.messages[-1] if S.messages else None
        if last is not None and last.role == "assistant" and not last.streaming and last.incomplete:
            if st.button("Continue", key="agent_continue", icon=":material/play_arrow:", disabled=_running()):
                _start_run("Continue where you left off and finish the task.")
                st.rerun()
    if ended:
        st.rerun()


def _intro() -> None:
    st.markdown(
        "<div class='intro'><div class='orb'>RK</div><h4>Ask. Plan. Build.</h4>"
        "<p>Ask about the repository, request a plan, or switch to AGENT to make changes. You review every edit before it stays.</p></div>"
        "<div class='suggest-title'>Try</div>",
        unsafe_allow_html=True,
    )
    with st.container(key="suggest"):
        for index, text in enumerate(SUGGESTIONS):
            if st.button(text, key=f"suggest_{index}", icon=":material/bolt:", disabled=repo() is None):
                _start_run(text)
                st.rerun()


def _pending_banner() -> None:
    if _running():
        return
    for message in reversed(S.messages):
        if message.role == "assistant" and message.changes is not None:
            count = len(_pending(message.changes))
            if count:
                st.markdown(
                    f"<div class='pending-banner'>{count} file{'s' if count != 1 else ''} awaiting review. Keep or revert them above.</div>",
                    unsafe_allow_html=True,
                )
            break


def _stop_run() -> None:
    run: AgentRun | None = st.session_state.get("run")
    if run is None:
        return
    run.cancel()
    answer = next((m for m in reversed(S.messages) if m.role == "assistant"), None)
    if answer is not None and answer.streaming:
        answer.status = "Stopping"
    log("Agent stop requested")


def _run_input() -> None:
    """While the agent works the message box is locked and its send arrow becomes a Stop button."""
    with st.container(key="runinput"):
        text, stop = st.columns([8, 1.3], vertical_alignment="center", gap="small")
        text.markdown("<div class='runinput-text'><span class='spin'></span>Agent is working... press stop to cancel</div>", unsafe_allow_html=True)
        stop.button("", icon=":material/stop:", key="agent_stop_input", help="Stop the agent", on_click=_stop_run, width="stretch")


def render_agent_panel() -> None:
    running = _running()
    key_ok = bool(settings.nvidia_api_key)
    models = available_models()
    ids = [m.id for m in models]
    labels = {m.id: m.label for m in models}
    if S.model not in ids:
        S.model = ids[0]

    head, picker, clear = st.columns([3, 6, 1.3], vertical_alignment="center")
    head.markdown(f"<div class='agent-head'><span class='pulse{'' if key_ok else ' off'}'></span><b>RK AGENT</b></div>", unsafe_allow_html=True)
    picker.selectbox("Model", ids, key="model", format_func=lambda i: labels.get(i, i), disabled=running, label_visibility="collapsed")
    if running:
        clear.button("", icon=":material/stop_circle:", key="agent_stop", help="Stop", on_click=_stop_run)
    elif clear.button("", icon=":material/delete_sweep:", key="agent_clear", help="Clear conversation"):
        conversations.clear(S.conversation_id)
        S.messages = []
        S.approvals = {}
        st.rerun()

    with st.container(key="modebar"):
        st.segmented_control("Mode", MODES, key="mode", disabled=running, label_visibility="collapsed", width="stretch")
    st.markdown(f"<div class='mode-note' title='{escape(MODE_HELP[S.mode or 'ASK'])}'>{escape(MODE_HELP[S.mode or 'ASK'])}</div>", unsafe_allow_html=True)

    st.fragment(run_every=POLL_SECONDS if running else None)(_transcript)()
    _pending_banner()

    if running:
        _run_input()
        return
    prompt = st.chat_input("Message the agent", disabled=repo() is None, key="agent_input")
    if prompt and prompt.strip():
        _start_run(prompt.strip())
        st.rerun()
