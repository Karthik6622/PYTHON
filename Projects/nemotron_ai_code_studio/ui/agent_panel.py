"""Right panel: the AI agent chat, mode selector, approvals and proposed changes."""

from __future__ import annotations

import json
from html import escape
from typing import Any

import streamlit as st

from studio.chat import ChangeSet, ChatMessage, ToolCall, apply_event
from studio.config import settings

from .state import AgentRun, S, attempt, broker, coding_agent, conversations, log, reload_paths, repo, sync_after_change

POLL_SECONDS = 0.4
SUGGESTIONS = [
    "Explain how this repository is structured",
    "Find likely bugs in this repository",
    "Plan unit tests for the main modules",
]
MODES = ["ASK", "PLAN", "AGENT"]
MODE_HELP = {
    "ASK": "Answers questions about the repository. Read-only.",
    "PLAN": "Produces an implementation plan. Read-only.",
    "AGENT": "Edits files, runs checks and reports. Risky steps ask you first; nothing is committed or pushed.",
}
STATUS_LETTER = {"added": "A", "modified": "M", "deleted": "D"}


def _running() -> bool:
    run = st.session_state.get("run")
    return run is not None


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
    user = ChatMessage(role="user", text=prompt[:8000], mode=mode)
    answer = ChatMessage(role="assistant", mode=mode, streaming=True, status="Starting")
    S.messages = [*S.messages, user, answer]
    S.cursor = 0
    S.approvals = {}
    run = AgentRun(coding_agent, broker, conversations, current, prompt[:8000], mode, S.conversation_id)
    S.run = run
    run.start()
    log(f"Agent ({mode.upper()}): {prompt[:80]}")


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
            answer.streaming, answer.status = False, ""
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


# ------------------------------------------------------------------ message rendering
def _tool(tool: ToolCall) -> None:
    icon = ":material/hourglass_empty:" if not tool.done else (":material/check_circle:" if tool.ok else ":material/error:")
    title = f"{tool.name}" + (f"  -  {tool.summary}" if tool.summary else "")
    with st.expander(title, icon=icon):
        if tool.args:
            st.code(json.dumps(tool.args, indent=2, default=str)[:2000], language="json")
        if tool.output:
            st.code(tool.output[-4000:], language=None, line_numbers=False)


def _apply(message: ChatMessage) -> None:
    current = repo()
    changes = message.changes
    if current is None or changes is None:
        return
    current.tracker.accept(changes.change_id)
    changes.state = "accepted"
    log(f"Accepted {len(changes.files)} changed file(s)")


def _reject(message: ChatMessage) -> None:
    current = repo()
    changes = message.changes
    if current is None or changes is None:
        return
    with current.lock:
        ok, restored = attempt(current.tracker.reject, changes.change_id, current.workspace)
        if ok:
            for path in restored:
                current.index.refresh_file(path)
    if ok:
        changes.state = "rejected"
        reload_paths(list(restored))
        log("Rejected changes; restored " + (", ".join(restored) or "nothing"))
        st.toast("Changes rejected and files restored.", icon=":material/undo:")


def _changes_card(message: ChatMessage, changes: ChangeSet) -> None:
    with st.container(border=True):
        st.markdown(f"**Proposed changes ({len(changes.files)} file{'s' if len(changes.files) != 1 else ''})**")
        for item in changes.files:
            st.markdown(f"`{STATUS_LETTER.get(item['status'], '?')}` {item['path']}  :green[+{item['additions']}] :red[-{item['deletions']}]")
        if changes.state == "pending":
            review, apply_, reject = st.columns(3)
            show_diff = review.toggle("Review Changes", key=f"review:{message.id}")
            if apply_.button("Apply", key=f"apply:{message.id}", type="primary", icon=":material/check:", width="stretch"):
                _apply(message)
                st.rerun()
            if reject.button("Reject", key=f"reject:{message.id}", icon=":material/undo:", width="stretch"):
                _reject(message)
                st.rerun()
            st.caption("The files are already updated on disk. Reject restores them; Apply keeps them. Commit from Source Control.")
            if show_diff:
                st.code(changes.diff or "(no textual diff)", language="diff", line_numbers=False)
        else:
            if changes.state == "accepted":
                st.success("Applied. Review and commit from Source Control.")
            else:
                st.info("Rejected. The files were restored.")
            with st.expander("View diff"):
                st.code(changes.diff or "(no textual diff)", language="diff", line_numbers=False)


def _render_message(message: ChatMessage) -> None:
    if message.role == "user":
        with st.chat_message("user"):
            st.markdown(message.text)
        return
    with st.chat_message("assistant"):
        st.caption(f"{message.mode.upper()}" + (f"  |  {message.status}" if message.status else ""))
        if message.context_files:
            with st.expander(f"Context ({len(message.context_files)} files)", icon=":material/folder_open:"):
                st.markdown("\n".join(f"- `{p}`" for p in message.context_files[:40]))
        if message.reasoning:
            with st.expander("Reasoning", icon=":material/psychology:"):
                st.markdown(message.reasoning[-6000:])
        for tool in message.tools:
            _tool(tool)
        if message.text:
            st.markdown(message.text)
        elif message.streaming:
            st.caption("Working...")
        if message.error:
            st.error(message.error)
        validation = message.validation
        if validation is not None:
            passed = validation.get("passed")
            (st.success if passed else st.warning if passed is None else st.error)(
                "Validation passed" if passed else "Nothing could be validated" if passed is None else "Validation failed"
            )
            if validation.get("steps"):
                st.caption("; ".join(f"{s.get('name')}: {s.get('status')}" for s in validation["steps"]))
        if message.inspected or message.modified:
            with st.expander(f"Files inspected ({len(message.inspected)})  |  modified ({len(message.modified)})", icon=":material/fact_check:"):
                if message.inspected:
                    st.markdown("**Inspected**\n" + "\n".join(f"- `{p}`" for p in message.inspected[:60]))
                if message.modified:
                    st.markdown("**Modified**\n" + "\n".join(f"- `{p}`" for p in message.modified[:60]))
        if message.changes is not None:
            _changes_card(message, message.changes)


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
    if ended:
        st.rerun()


def _intro() -> None:
    st.markdown(
        "<div class='intro'><div class='orb'>N</div><h4>Ask. Plan. Build.</h4>"
        "<p>Ask about the repository, request a plan, or switch to AGENT to make changes. Referenced files appear under each answer.</p></div>"
        "<div class='suggest-title'>Try</div>",
        unsafe_allow_html=True,
    )
    with st.container(key="suggest"):
        for index, text in enumerate(SUGGESTIONS):
            if st.button(text, key=f"suggest_{index}", icon=":material/bolt:", disabled=repo() is None):
                _start_run(text)
                st.rerun()


def render_agent_panel() -> None:
    running = _running()
    key_ok = bool(settings.nvidia_api_key)
    head, clear = st.columns([5, 1], vertical_alignment="center")
    head.markdown(
        f"<div class='agent-head'><span class='pulse{'' if key_ok else ' off'}'></span><b>NEMOTRON AGENT</b></div>",
        unsafe_allow_html=True,
    )
    if running:
        if clear.button("", icon=":material/stop_circle:", key="agent_stop", help="Stop"):
            run = st.session_state.get("run")
            if run is not None:
                run.cancel()
    elif clear.button("", icon=":material/delete_sweep:", key="agent_clear", help="Clear conversation"):
        conversations.clear(S.conversation_id)
        S.messages = []
        S.approvals = {}
        st.rerun()

    with st.container(key="modebar"):
        st.segmented_control("Mode", MODES, key="mode", disabled=running, label_visibility="collapsed", width="stretch")
    st.markdown(f"<div class='mode-note'>{escape(MODE_HELP[S.mode or 'ASK'])}</div>", unsafe_allow_html=True)

    st.fragment(run_every=POLL_SECONDS if running else None)(_transcript)()

    prompt = st.chat_input("Message the agent", disabled=running or repo() is None, key="agent_input")
    if prompt and prompt.strip():
        _start_run(prompt.strip())
        st.rerun()
