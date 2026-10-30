"""Runs shell commands inside the repository folder with a time limit, output cap and a scrubbed environment."""

from __future__ import annotations

import os
import re
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

_SECRET_NAME = re.compile(r"(?:token|secret|api[_-]?key|password|passwd|credential|private[_-]?key)", re.I)
MAX_OUTPUT_CHARS = 30_000


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


def clean_environment() -> dict[str, str]:
    """The user's environment minus anything that looks like a credential (so repository code cannot read the API keys).

    `python`, `pip` and `playwright` in the terminal resolve to the same Python that runs RK Studio, so
    `pip install x` makes `x` importable by the scripts you run next.
    """
    env = {key: value for key, value in os.environ.items() if not _SECRET_NAME.search(key)}
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PIP_PROGRESS_BAR"] = "off"
    env["CI"] = env.get("CI", "1")
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["NO_COLOR"] = "1"
    exe_dir = Path(sys.executable).parent if sys.executable else None
    if exe_dir is not None:
        extra = [str(exe_dir)] + ([str(exe_dir / "Scripts")] if (exe_dir / "Scripts").is_dir() else [])
        env["PATH"] = os.pathsep.join([*extra, env.get("PATH", "")])
    return env


def python_command() -> str:
    """Shell-safe path of the Python that runs this backend (used for tests and compile checks)."""
    exe = sys.executable or "python"
    return f'"{exe}"'


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
    ) -> CommandResult:
        """Blocking. Call from a worker thread. on_output receives redacted text as it arrives."""
        cwd = self.resolve_cwd(cwd_relative)
        limit = timeout or settings.command_timeout_seconds
        shell = settings.terminal_shell
        popen_args: dict = {
            "cwd": str(cwd), "env": clean_environment(), "stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT, "bufsize": 0,
        }
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

        def reader() -> None:
            nonlocal total
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

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
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
        if cancelled:
            output += "\n[Cancelled]"
        return CommandResult(command, process.returncode if not (timed_out or cancelled) else None, output, timed_out, cancelled, truncated, time.monotonic() - started)

    def run(self, command: str, cwd_relative: str = "", timeout: int | None = None) -> CommandResult:
        return self.run_streaming(command, cwd_relative, timeout)
