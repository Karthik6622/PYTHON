"""Running external tools (adb, emulator, appium, aapt) safely: argument lists only (no shell), timeouts, and an injectable runner for tests."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ats.mobile import settings


@dataclass
class CommandResult:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    error: str = ""  # the tool is missing, timed out or could not start (returncode is then -1)

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.error

    @property
    def text(self) -> str:
        return (self.stdout or "") + (("\n" + self.stderr) if self.stderr else "")


Runner = Callable[[list[str], float], CommandResult]
Which = Callable[[str], "str | None"]


def run_command(argv: list[str], timeout: float | None = None, env: dict[str, str] | None = None) -> CommandResult:
    """Run one command. Never raises: a missing tool, a timeout or an OS error comes back in ``error``."""
    try:
        done = subprocess.run(  # noqa: S603 - argument list, no shell
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout or settings.command_timeout(), env=env, stdin=subprocess.DEVNULL
        )
    except FileNotFoundError:
        return CommandResult(-1, error=f"{argv[0]} was not found")
    except subprocess.TimeoutExpired:
        return CommandResult(-1, error=f"{Path(argv[0]).name} did not answer in time")
    except OSError as exc:
        return CommandResult(-1, error=f"{Path(argv[0]).name} could not be started: {exc.__class__.__name__}")
    return CommandResult(done.returncode, done.stdout or "", done.stderr or "")


class Toolbox:
    """Finds the Android/Appium tools and runs them. Everything is injectable so tests never touch real tools."""

    def __init__(self, runner: Runner | None = None, which: Which | None = None, environ: dict[str, str] | None = None, is_file: Callable[[Path], bool] | None = None) -> None:
        self._runner = runner or (lambda argv, timeout: run_command(argv, timeout))
        self._which = which or shutil.which
        self._environ = dict(os.environ) if environ is None else environ
        self._is_file = is_file or (lambda path: path.is_file())

    # ------------------------------------------------------------------ plumbing
    def run(self, argv: list[str], timeout: float | None = None) -> CommandResult:
        try:
            return self._runner(argv, timeout or settings.command_timeout())
        except Exception as exc:  # noqa: BLE001 - a misbehaving runner must not reach the UI
            return CommandResult(-1, error=f"{exc.__class__.__name__}")

    def env(self, name: str) -> str:
        return self._environ.get(name, "")

    def environment(self) -> dict[str, str]:
        """The process environment, plus ANDROID_HOME when it can be worked out (Appium needs it)."""
        env = dict(self._environ)
        root = self.sdk_root()
        if root and not (env.get("ANDROID_HOME") or env.get("ANDROID_SDK_ROOT")):
            env["ANDROID_HOME"] = root
        return env

    def which(self, name: str) -> str | None:
        return self._which(name)

    # ------------------------------------------------------------------ Android SDK
    def sdk_root(self) -> str:
        for name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
            value = self.env(name)
            if value and Path(value).is_dir():
                return value
        adb = self.which("adb")
        if adb and Path(adb).parent.name.lower() == "platform-tools":
            return str(Path(adb).parent.parent)
        return ""

    def _sdk_tool(self, name: str, folder: str) -> str | None:
        found = self.which(name)
        if found:
            return found
        for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
            root = self.env(variable)
            if not root:
                continue
            for candidate in (Path(root) / folder / f"{name}.exe", Path(root) / folder / name):
                if self._is_file(candidate):
                    return str(candidate)
        return None

    def adb(self) -> str | None:
        return self._sdk_tool("adb", "platform-tools")

    def emulator(self) -> str | None:
        return self._sdk_tool("emulator", "emulator")

    def aapt(self) -> str | None:
        found = self.which("aapt2") or self.which("aapt")
        if found:
            return found
        root = self.env("ANDROID_HOME") or self.env("ANDROID_SDK_ROOT")
        if root:
            tools = sorted((Path(root) / "build-tools").glob("*"), reverse=True) if Path(root, "build-tools").is_dir() else []
            for folder in tools:
                for name in ("aapt2.exe", "aapt2", "aapt.exe", "aapt"):
                    if self._is_file(folder / name):
                        return str(folder / name)
        return None

    # ------------------------------------------------------------------ Appium
    def appium_command(self) -> list[str] | None:
        """The command that starts Appium: ``appium`` on PATH, else the project-local one through ``npx --no-install``."""
        found = self.which("appium")
        if found:
            return [found]
        npx = self.which("npx")
        if npx:
            return [npx, "--no-install", "appium"]
        return None


def default_tools() -> Toolbox:
    """A toolbox over the real machine (created per use so a changed PATH or ANDROID_HOME is noticed)."""
    return Toolbox()
