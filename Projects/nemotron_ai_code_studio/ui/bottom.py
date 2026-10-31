"""Bottom panel: Terminal, Problems, Output, Tests and Git Diff."""

from __future__ import annotations

import os
from html import escape
from typing import Any, Callable

import streamlit as st

from studio.config import settings
from studio.services.command_policy import classify_command
from studio.services.terminal_hints import hint_for
from studio.tools import devtools

from .dialogs import ensure_folder
from .state import CommandRun, S, attempt, log, open_file, reload_paths, repo

PANEL_HEIGHT = 240
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
    if current is None:
        return
    if current.git is not None:
        current.git.invalidate()  # git commit / push / pull typed in the terminal change what Source Control and the status bar show
    if not changed_files:
        return
    current.reindex()  # a command may have created, changed or deleted files
    reload_paths(list(S.tabs))


def _start(attr: str, command: str, kind: str = "", cwd: str = "", timeout: int | None = None) -> None:
    current = repo()
    if current is None:
        return
    run = CommandRun(current, command, cwd, timeout)
    run.prompt = _prompt()
    st.session_state[attr] = run
    if kind:
        S.job_kind = kind
    log(f"$ {command}")


# ------------------------------------------------------------------ terminal
def _prompt() -> str:
    """The full path the terminal process is actually running in, with forward slashes."""
    current = repo()
    if current is None:
        return "PS>"
    base = current.terminal.root
    path = base / S.term_cwd if S.term_cwd else base
    return f"PS {path.as_posix()}>"


def _terminal_html(live: CommandRun | None) -> str:
    """The scrollback. The live prompt with its input box is drawn by render_terminal, on the same line as the prompt."""
    chunks = [S.terminal] if S.terminal else []
    if live is not None:
        chunks.append(f"{live.prompt} {live.command}\n{live.output}")
    body = ""
    for line in "".join(chunks).rstrip("\n").split("\n"):
        if line.startswith("PS ") and ">" in line:
            head, _, rest = line.partition("> ")
            body += f"<span class='ps'>{escape(head)}&gt;</span> <span class='cmd'>{escape(rest)}</span>\n"
        elif line.startswith("hint: "):
            body += f"<span class='hint'>{escape(line)}</span>\n"
        elif not line.strip():
            body += "<span class='gap'></span>\n"  # a truly empty line would end the HTML block and break the layout
        else:
            body += escape(line) + "\n"
    if not S.terminal and live is None:
        if st.session_state.get("_link") is not None:
            body = ("<span class='dim'>Commands run in the hosted working copy; the prompt shows that copy's full path. "
                "The browser does not disclose your computer's folder path. Use quotes around file names with spaces.</span>\n")
        else:
            body = ("<span class='dim'>RK Studio terminal. Type commands right after the prompt: git status, pip install &lt;package&gt;, "
                "python script.py, python -m playwright install chromium. cd and cls work.</span>\n")
    return f"<div class='term'><pre>{body}</pre></div>"


def _terminal_render(run: CommandRun) -> None:
    st.markdown(_terminal_html(run), unsafe_allow_html=True)
    if not run.finished.is_set() and st.button("Stop", icon=":material/stop:", key="term_stop"):
        run.cancel()


def _terminal_finish(run: CommandRun) -> None:
    result = run.result
    code = "" if result is None else ("cancelled" if result.cancelled else "timed out" if result.timed_out else f"exit {result.exit_code}")
    body = result.output if result is not None else run.error or run.output
    status = f"[{code}]\n" if code and code != "exit 0" else ""
    hint = hint_for(run.command, body or "", None if result is None else result.exit_code)
    if "GitHub login cannot be typed" in hint and not settings.github_token:
        st.session_state["_ask_github"] = True  # a git command in the terminal needs the account
    hint = "".join(f"hint: {line}\n" for line in hint.split("\n")) if hint else ""
    S.terminal = (S.terminal + f"{run.prompt} {run.command}\n{body.rstrip()}\n{status}{hint}\n")[-30000:]
    log(f"Command finished ({code or 'error'}): {run.command}")
    _after_command()


def _builtin(command: str) -> bool:
    """cd / cls are handled by the app (each command runs in its own process). Returns True when handled."""
    current = repo()
    if current is None:
        return False
    parts = command.strip().split(None, 1)
    word = parts[0].lower() if parts else ""
    if word in {"cls", "clear"} and len(parts) == 1:
        S.terminal = ""
        return True
    if word in {"cd", "chdir", "set-location", "sl"}:
        target = parts[1].strip().strip("\"'") if len(parts) > 1 else ""
        entry = f"{_prompt()} {command.strip()}\n"
        if not target or target in {"~", "\\", "/"}:
            new = ""
        else:
            new = os.path.normpath(os.path.join(S.term_cwd or ".", target.replace("\\", "/"))).replace("\\", "/")
            new = "" if new == "." else new
        try:
            if new.startswith("..") or os.path.isabs(new):
                raise ValueError("Cannot leave the repository folder.")
            current.terminal.resolve_cwd(new)
        except ValueError as exc:
            S.terminal = (S.terminal + entry + f"cd : {exc}\n\n")[-20000:]
        else:
            S.term_cwd = new
            S.terminal = (S.terminal + entry + "\n")[-20000:]
        return True
    return False


def render_terminal() -> None:
    current = repo()
    if current is None:
        st.info("No repository is open.")
        return
    try:
        current.terminal.resolve_cwd(S.term_cwd)
    except ValueError:
        S.term_cwd = ""  # the folder is gone, or another repository was opened
    running = st.session_state.get("term_run") is not None and not st.session_state["term_run"].finished.is_set()

    with st.container(key="termbox"):
        if not running:
            st.markdown(_terminal_html(None), unsafe_allow_html=True)
            # The prompt and the input share one line, like a real shell. Enter submits (the Run button is visually hidden).
            with st.form("term_form", clear_on_submit=True, border=False):
                st.markdown(f"<span class='ps termps'>{escape(_prompt())}</span>", unsafe_allow_html=True)
                command = st.text_input("Command", label_visibility="collapsed", placeholder="type a command")
                submitted = st.form_submit_button("Run")
            if submitted and command.strip():
                if not ensure_folder():  # the terminal always works in the folder the user chose
                    st.rerun()
                verdict = classify_command(command, user_initiated=True)
                if _builtin(command):
                    st.rerun()
                elif verdict.level == "deny":
                    S.terminal = (S.terminal + f"{_prompt()} {command.strip()}\n{verdict.reason}\n\n")[-30000:]
                    st.rerun()
                elif verdict.level == "approve":
                    S.term_confirm = {"command": command.strip(), "reason": verdict.reason}
                else:
                    _start("term_run", command.strip(), cwd=S.term_cwd, timeout=settings.terminal_timeout_seconds)
                    st.rerun()

        pending = st.session_state.get("term_confirm")
        if pending:
            st.warning(f"{pending['reason']}\n\n`{pending['command']}`")
            yes, no = st.columns(2)
            if yes.button("Run anyway", type="primary", key="term_yes", width="stretch"):
                st.session_state["term_confirm"] = None
                _start("term_run", pending["command"], cwd=S.term_cwd, timeout=settings.terminal_timeout_seconds)
                st.rerun()
            if no.button("Cancel", key="term_no", width="stretch"):
                st.session_state["term_confirm"] = None
                st.rerun()

        _live("term_run", _terminal_render, _terminal_finish)



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
    names = ["TERMINAL", "PROBLEMS", "OUTPUT", "TESTS", "GIT DIFF"]
    try:
        tabs = st.tabs(names, key="bottomtabs", on_change="rerun")  # only the open tab runs: git diff no longer costs time on every click
    except TypeError:
        tabs = st.tabs(names)  # older Streamlit: every tab runs
    renderers = [render_terminal, render_problems, render_output, render_tests, render_git_diff]
    for tab, render in zip(tabs, renderers):
        with tab:
            if getattr(tab, "open", True):
                render()
