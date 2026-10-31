"""Runs shell commands inside the repository folder with a time limit, output cap and a scrubbed environment."""

from __future__ import annotations

import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..config import settings
from ..security import PathSecurityError, redact, resolve_in_root
from .git_service import auth_env

_SECRET_NAME = re.compile(r"(?:token|secret|api[_-]?key|password|passwd|credential|private[_-]?key)", re.I)
# Only a single, plain git network command gets the GitHub token (never a chained command or a script that could read it).
_GIT_NETWORK = re.compile(r"^\s*git\s+(?:push|pull|fetch|clone|ls-remote)\b[^;&|<>`$()\r\n]*$", re.I)
MAX_OUTPUT_CHARS = 30_000
RUNAWAY_OUTPUT_CHARS = 300_000
VENV_NAME = ".venv"
BROWSERS_NAME = ".playwright-browsers"
# Commands that need the folder's own Python environment; others (git, ls, ...) never create one.
_NEEDS_ENV = re.compile(r"(?:^|[\s;&|(])(?:pip3?|python3?|py|playwright|pytest|uvicorn|streamlit|jupyter|ipython)(?=$|[\s;&|)])", re.I)
_PLAIN_PYTHON = re.compile(r"^(\s*(?:python(?:\d+(?:\.\d+)*)?|py)(?:\.exe)?\s+)(.+?)\s*$", re.I)


@dataclass
class CommandResult:
    command: str
    exit_code: int | None
    output: str
    timed_out: bool = False
    cancelled: bool = False
    truncated: bool = False
    duration: float = 0.0

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.cancelled

    def public(self) -> dict:
        return {
            "command": self.command, "exit_code": self.exit_code, "output": self.output, "timed_out": self.timed_out,
            "cancelled": self.cancelled, "truncated": self.truncated, "duration": round(self.duration, 2), "ok": self.ok,
        }


def venv_bin(root: Path) -> Path | None:
    """The folder's own environment (<folder>/.venv), when it exists."""
    for sub, exe in (("Scripts", "python.exe"), ("bin", "python")):
        folder = root / VENV_NAME / sub
        if (folder / exe).is_file():
            return folder
    return None


def ensure_environment(root: Path, command: str) -> str:
    """Create <folder>/.venv the first time a Python command runs, so everything installed stays inside the folder.

    Returns a short note for the terminal (empty when nothing was created)."""
    if venv_bin(root) is not None or not _NEEDS_ENV.search(command):
        return ""
    try:
        subprocess.run([sys.executable or "python", "-m", "venv", str(root / VENV_NAME)], capture_output=True, timeout=240, check=True)
    except (OSError, subprocess.SubprocessError):
        shutil.rmtree(root / VENV_NAME, ignore_errors=True)
        return "[Could not create a folder environment; using RK Studio's Python instead]\n"
    exclude = root / ".git" / "info" / "exclude"
    if exclude.parent.is_dir():  # keep the environment out of `git status` without touching the repository's own files
        try:
            with exclude.open("a", encoding="utf-8") as handle:
                handle.write(f"\n{VENV_NAME}/\n{BROWSERS_NAME}/\n")
        except OSError:
            pass
    return f"[Created {VENV_NAME} in this folder: pip installs and Playwright browsers are kept here]\n"


def clean_environment(root: Path | None = None) -> dict[str, str]:
    """The user's environment minus anything that looks like a credential (so repository code cannot read the API keys).

    With a folder that has a `.venv`, `python`, `pip` and `playwright` resolve to that environment, and Playwright
    browsers are stored in the folder. Otherwise they resolve to the Python that runs RK Studio.
    """
    env = {key: value for key, value in os.environ.items() if not _SECRET_NAME.search(key)}
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PIP_PROGRESS_BAR"] = "off"
    env["CI"] = env.get("CI", "1")
    env["GIT_TERMINAL_PROMPT"] = "0"
    if "GIT_CONFIG_COUNT" not in env:  # git commit in the terminal must not start gc (see git_service._run)
        env.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "gc.auto", "GIT_CONFIG_VALUE_0": "0"})
    env["NO_COLOR"] = "1"
    bin_dir = venv_bin(root) if root is not None else None
    if bin_dir is not None and root is not None:
        env.pop("PYTHONHOME", None)
        env["VIRTUAL_ENV"] = str(bin_dir.parent)
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(root / BROWSERS_NAME)
        env["PATH"] = os.pathsep.join([str(bin_dir), env.get("PATH", "")])
        return env
    exe_dir = Path(sys.executable).parent if sys.executable else None
    if exe_dir is not None:
        extra = [str(exe_dir)] + ([str(exe_dir / "Scripts")] if (exe_dir / "Scripts").is_dir() else [])
        env["PATH"] = os.pathsep.join([*extra, env.get("PATH", "")])
    return env


def python_command() -> str:
    """Shell-safe path of the Python that runs this backend (used for tests and compile checks)."""
    exe = sys.executable or "python"
    return f'"{exe}"'


def quote_python_script_path(command: str, cwd: Path, root: Path) -> str:
    """Quote an existing Python script filename with spaces when the command is unambiguous.

    For example, `python test calculator.py` is treated as one script path only when that exact file exists and `test`
    does not. Shell syntax, explicit quoting and commands with further arguments are left untouched.
    """
    match = _PLAIN_PYTHON.fullmatch(command)
    if not match:
        return command
    prefix, script = match.groups()
    if " " not in script or any(char in script for char in "\r\n\"';&|<>`$"):
        return command
    candidate = (cwd / script).resolve()
    first_candidate = (cwd / script.split(None, 1)[0]).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return command
    return f'{prefix}"{script}"' if candidate.is_file() and not first_candidate.exists() else command


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


class TerminalService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def resolve_cwd(self, relative: str = "") -> Path:
        try:
            cwd = resolve_in_root(self.root, relative)
        except PathSecurityError as exc:
            raise ValueError(str(exc)) from exc
        if not cwd.is_dir():
            raise ValueError("The working directory does not exist.")
        return cwd

    def run_streaming(
        self,
        command: str,
        cwd_relative: str = "",
        timeout: int | None = None,
        on_output: Callable[[str], None] | None = None,
        cancel: threading.Event | None = None,
        input_queue: queue.Queue | None = None,
    ) -> CommandResult:
        """Blocking. Call from a worker thread. on_output receives redacted text as it arrives.

        With `input_queue` the command can be answered like in a real terminal: each line put in the queue is typed into the
        program (and echoed in the output); without it the program gets no input at all."""
        cwd = self.resolve_cwd(cwd_relative)
        command = quote_python_script_path(command, cwd, self.root)
        limit = timeout or settings.command_timeout_seconds
        shell = settings.terminal_shell
        note = ensure_environment(self.root, command)
        env = clean_environment(self.root)
        try:
            if settings.workspace_path.resolve() in self.root.resolve().parents:
                # A folder RK Studio keeps under its own workspaces folder is a repository only if it has its own .git. Without this,
                # git would climb into the repository RK Studio itself lives in and act on (or refuse) the wrong project.
                env["GIT_CEILING_DIRECTORIES"] = str(self.root.resolve().parent)
        except OSError:
            pass
        network_git = _GIT_NETWORK.match(command)
        if network_git:
            # Never prompt in the terminal. The connected account's token goes through the environment only (a header scoped to
            # github.com), never into the command line or a remote URL. Hosted GitHub SSH URLs are rewritten to HTTPS because
            # the server has no access to the visitor's SSH agent / known_hosts; local runs retain their normal SSH setup.
            auth = auth_env()
            index = int(env.get("GIT_CONFIG_COUNT", "0"))
            for source_index in range(int(auth.get("GIT_CONFIG_COUNT", "0"))):
                env[f"GIT_CONFIG_KEY_{index}"] = auth[f"GIT_CONFIG_KEY_{source_index}"]
                env[f"GIT_CONFIG_VALUE_{index}"] = auth[f"GIT_CONFIG_VALUE_{source_index}"]
                index += 1
            if index:
                env["GIT_CONFIG_COUNT"] = str(index)
        popen_args: dict = {
            "cwd": str(cwd), "env": env, "stdin": subprocess.PIPE if input_queue is not None else subprocess.DEVNULL,
            "stdout": subprocess.PIPE, "stderr": subprocess.STDOUT, "bufsize": 0,
        }
        if input_queue is not None:
            env["PYTHONUNBUFFERED"] = "1"  # prompts such as input("Enter: ") must appear before the program waits for the answer
        if os.name == "nt":
            popen_args["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_args["start_new_session"] = True
        started = time.monotonic()
        try:
            process = subprocess.Popen([shell, "-c", command] if shell else command, shell=not shell, **popen_args)
        except OSError as exc:
            return CommandResult(command, None, f"Could not start the command: {exc}")

        pieces: list[str] = []
        total = 0
        flooded = False
        if note:
            pieces.append(note)
            total += len(note)
            if on_output:
                on_output(note)

        def reader() -> None:
            nonlocal total, flooded
            assert process.stdout is not None
            decoder = __import__("codecs").getincrementaldecoder("utf-8")(errors="replace")
            while True:
                data = process.stdout.read(4096)
                if not data:
                    break
                text = redact(decoder.decode(data))
                if text:
                    pieces.append(text)
                    total += len(text)
                    if on_output:
                        on_output(text)
                    if total > RUNAWAY_OUTPUT_CHARS:
                        # A program stuck in a loop (for example one that keeps asking for input that cannot arrive) would
                        # otherwise fill memory and freeze the page.
                        flooded = True
                        _kill_tree(process)
                        break

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()

        def typist() -> None:
            assert input_queue is not None and process.stdin is not None
            while process.poll() is None:
                try:
                    line = input_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                try:
                    process.stdin.write((line + "\n").encode("utf-8"))
                    process.stdin.flush()
                except OSError:
                    break  # the program has already ended
                echo = redact(line) + "\n"
                pieces.append(echo)
                if on_output:
                    on_output(echo)
            try:
                process.stdin.close()
            except OSError:
                pass

        if input_queue is not None:
            threading.Thread(target=typist, daemon=True).start()
        timed_out = cancelled = False
        while process.poll() is None:
            if cancel is not None and cancel.is_set():
                cancelled = True
                _kill_tree(process)
                break
            if time.monotonic() - started > limit:
                timed_out = True
                _kill_tree(process)
                break
            time.sleep(0.05)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _kill_tree(process)
        thread.join(timeout=5)
        output = "".join(pieces)
        truncated = False
        if len(output) > MAX_OUTPUT_CHARS:
            truncated = True
            head, tail = MAX_OUTPUT_CHARS // 3, MAX_OUTPUT_CHARS * 2 // 3
            output = output[:head] + "\n... [output truncated] ...\n" + output[-tail:]
        if timed_out:
            output += f"\n[Stopped: exceeded the {limit}s time limit]"
        if flooded:
            output += "\n[Stopped: the command printed too much output. A program that waits for typed input cannot get it here.]"
        if cancelled:
            output += "\n[Cancelled]"
        return CommandResult(command, process.returncode if not (timed_out or cancelled) else None, output, timed_out, cancelled, truncated, time.monotonic() - started)

    def run(self, command: str, cwd_relative: str = "", timeout: int | None = None) -> CommandResult:
        return self.run_streaming(command, cwd_relative, timeout)
