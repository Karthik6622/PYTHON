"""Bottom panel: Terminal, Problems, Output, Tests and Git Diff."""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from studio.services.command_policy import classify_command
from studio.tools import devtools

from .state import CommandRun, S, attempt, log, open_file, reload_paths, repo

PANEL_HEIGHT = 300
POLL_SECONDS = 0.5


# ------------------------------------------------------------------ live runs
def _live(attr: str, render: Callable[[Any], None], finish: Callable[[Any], None]) -> None:
    """Shows a background CommandRun; polls while it runs and does one full rerun when it ends."""
    run = st.session_state.get(attr)
    running = run is not None and not run.finished.is_set()

    def body() -> None:
        current = st.session_state.get(attr)
        if current is None:
            return
        render(current)
        if current.finished.is_set():
            finish(current)
            st.session_state[attr] = None
            st.rerun()

    st.fragment(run_every=POLL_SECONDS if running else None)(body)()


def _after_command(changed_files: bool = True) -> None:
    current = repo()
    if current is None or not changed_files:
        return
    current.reindex()  # a command may have created, changed or deleted files
    reload_paths(list(S.tabs))


def _start(attr: str, command: str, kind: str = "") -> None:
    current = repo()
    if current is None:
        return
    st.session_state[attr] = CommandRun(current, command)
    if kind:
        S.job_kind = kind
    log(f"$ {command}")


# ------------------------------------------------------------------ terminal
def _terminal_render(run: CommandRun) -> None:
    state = "running" if not run.finished.is_set() else "finished"
    st.caption(f"$ {run.command}  ({state})")
    st.code(run.output or "(no output yet)", language=None, line_numbers=False, height=160)
    if not run.finished.is_set() and st.button("Stop", icon=":material/stop:", key="term_stop"):
        run.cancel()


def _terminal_finish(run: CommandRun) -> None:
    result = run.result
    code = "" if result is None else ("cancelled" if result.cancelled else "timed out" if result.timed_out else f"exit {result.exit_code}")
    body = result.output if result is not None else run.error or run.output
    S.terminal = (S.terminal + f"$ {run.command}\n{body.rstrip()}\n[{code or 'error'}]\n\n")[-20000:]
    log(f"Command finished ({code or 'error'}): {run.command}")
    _after_command()


def render_terminal() -> None:
    current = repo()
    if current is None:
        st.info("No repository is open.")
        return
    running = st.session_state.get("term_run") is not None and not st.session_state["term_run"].finished.is_set()

    with st.form("term_form", clear_on_submit=True, border=False):
        left, right = st.columns([9, 1.3], vertical_alignment="bottom")
        command = left.text_input("Command", placeholder="Run a command in the repository folder, for example: python -m pytest", label_visibility="collapsed")
        submitted = right.form_submit_button("Run", icon=":material/play_arrow:", width="stretch", disabled=running)
    if submitted and command.strip():
        verdict = classify_command(command)
        if verdict.level == "deny":
            st.error(verdict.reason)
        elif verdict.level == "approve":
            S.term_confirm = {"command": command.strip(), "reason": verdict.reason}
        else:
            _start("term_run", command.strip())
            st.rerun()

    pending = st.session_state.get("term_confirm")
    if pending:
        st.warning(f"{pending['reason']}\n\n`{pending['command']}`")
        yes, no = st.columns(2)
        if yes.button("Run anyway", type="primary", key="term_yes", width="stretch"):
            st.session_state["term_confirm"] = None
            _start("term_run", pending["command"])
            st.rerun()
        if no.button("Cancel", key="term_no", width="stretch"):
            st.session_state["term_confirm"] = None
            st.rerun()

    _live("term_run", _terminal_render, _terminal_finish)
    if S.terminal:
        top = st.columns([8, 1.3])
        top[0].caption("History")
        if top[1].button("Clear", key="term_clear", width="stretch"):
            S.terminal = ""
            st.rerun()
        st.code(S.terminal, language=None, line_numbers=False, height=PANEL_HEIGHT - 120)


# ------------------------------------------------------------------ tests and problems
def _job_render(run: CommandRun) -> None:
    label = "Running tests" if S.job_kind == "tests" else "Checking code"
    st.caption(f"{label}: {run.command}")
    st.code(run.output or "(no output yet)", language=None, line_numbers=False, height=PANEL_HEIGHT - 100)
    if not run.finished.is_set() and st.button("Stop", icon=":material/stop:", key="job_stop"):
        run.cancel()


def _job_finish(run: CommandRun) -> None:
    result = run.result
    output = (result.output if result is not None else run.error or run.output) or ""
    data = {
        "command": run.command, "output": output, "ok": bool(result is not None and result.ok),
        "exit_code": None if result is None else result.exit_code,
        "cancelled": bool(result is not None and result.cancelled), "timed_out": bool(result is not None and result.timed_out),
        "problems": devtools.parse_problems(output),
    }
    if S.job_kind == "tests":
        S.tests_result = data
    else:
        S.lint_result = data
    log(f"{'Tests' if S.job_kind == 'tests' else 'Check'} finished: {'passed' if data['ok'] else 'failed'}")
    _after_command()


def _busy() -> bool:
    run = st.session_state.get("job_run")
    return run is not None and not run.finished.is_set()


def _problem_list(problems: list[dict], prefix: str) -> None:
    for index, problem in enumerate(problems[:100]):
        if st.button(f"{problem['path']}:{problem['line']}  {problem['message'][:110]}", key=f"{prefix}:{index}", width="stretch"):
            open_file(problem["path"])
            S.goto = {"path": problem["path"], "line": problem["line"]}
            st.rerun()


def render_problems() -> None:
    current = repo()
    if current is None:
        st.info("No repository is open.")
        return
    if st.button("Check code", icon=":material/rule:", disabled=_busy(), key="lint_btn"):
        try:
            command = devtools.detect_lint_command(current)
        except devtools.ToolSetupError as exc:
            st.error(str(exc))
            command = None
        else:
            if command is None:
                result = devtools.syntax_check(current)
                S.lint_result = {
                    "command": result.command, "output": result.output, "ok": result.ok, "exit_code": result.exit_code,
                    "cancelled": False, "timed_out": False, "problems": devtools.parse_problems(result.output),
                }
                st.rerun()
            else:
                _start("job_run", command, "lint")
                st.rerun()
    if S.job_kind == "lint":
        _live("job_run", _job_render, _job_finish)
    result = S.lint_result
    if result is None:
        st.caption("Run a check to list problems. Uses ruff, flake8 or npm lint when configured, otherwise a Python syntax check.")
    elif result["problems"]:
        st.markdown(f"**{len(result['problems'])} problem(s)** from `{result['command']}`")
        _problem_list(result["problems"], "prob")
    elif result["ok"]:
        st.success("No problems found.")
        st.caption(result["output"][:300])
    else:
        st.error("The check failed.")
        st.code(result["output"][-3000:], language=None, line_numbers=False)


def render_tests() -> None:
    current = repo()
    if current is None:
        st.info("No repository is open.")
        return
    try:
        suggested = devtools.detect_test_command(current)
        note = ""
    except devtools.ToolSetupError as exc:
        suggested, note = "", str(exc)
    left, right = st.columns([9, 1.6], vertical_alignment="bottom")
    command = left.text_input("Test command", value=suggested, key=f"tests_cmd:{suggested}", placeholder="Test command", help=note or None)
    if right.button("Run tests", icon=":material/science:", type="primary", disabled=_busy() or not command.strip(), key="tests_btn", width="stretch"):
        verdict = classify_command(command)
        if verdict.level == "deny":
            st.error(verdict.reason)
        else:
            _start("job_run", command.strip(), "tests")
            st.rerun()
    if note and not suggested:
        st.caption(note)

    if S.job_kind == "tests":
        _live("job_run", _job_render, _job_finish)
    result = S.tests_result
    if result is None:
        return
    if result["ok"]:
        st.success("Tests passed.")
    elif result["cancelled"] or result["timed_out"]:
        st.warning("The test run was stopped.")
    else:
        st.error(f"Tests failed (exit code {result['exit_code']}).")
    if result["problems"]:
        st.caption("Locations mentioned in the output")
        _problem_list(result["problems"], "tprob")
    with st.expander("Output", expanded=not result["ok"]):
        st.code(result["output"][-8000:], language=None, line_numbers=False)


# ------------------------------------------------------------------ output and git diff
def render_output() -> None:
    top = st.columns([8, 1.3])
    top[0].caption("Activity log")
    if top[1].button("Clear", key="out_clear", width="stretch"):
        S.output_log = []
        st.rerun()
    st.code("\n".join(S.output_log) or "No activity yet.", language=None, line_numbers=False, height=PANEL_HEIGHT - 60)


def render_git_diff() -> None:
    current = repo()
    if current is None or current.git is None:
        st.info("Open a Git repository to see its diff.")
        return
    st.button("Refresh", icon=":material/refresh:", key="gd_refresh")
    ok, unstaged = attempt(current.git.diff, None, False)
    ok2, staged = attempt(current.git.diff, None, True)
    if not (ok and ok2):
        return
    if not unstaged.strip() and not staged.strip():
        st.caption("The working tree is clean.")
    if staged.strip():
        st.caption("Staged")
        st.code(staged, language="diff", line_numbers=False, height=PANEL_HEIGHT - 100)
    if unstaged.strip():
        st.caption("Not staged")
        st.code(unstaged, language="diff", line_numbers=False, height=PANEL_HEIGHT - 100)


def render_bottom() -> None:
    terminal, problems, output, tests, diff = st.tabs(["TERMINAL", "PROBLEMS", "OUTPUT", "TESTS", "GIT DIFF"])
    with terminal:
        render_terminal()
    with problems:
        render_problems()
    with output:
        render_output()
    with tests:
        render_tests()
    with diff:
        render_git_diff()
