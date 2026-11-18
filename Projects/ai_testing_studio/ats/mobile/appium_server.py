"""A local Appium server for app analysis: started on a free port, reused when one already answers, always stopped afterwards."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ats.logging_setup import get_logger
from ats.mobile import settings
from ats.mobile.models import MobileError
from ats.mobile.tools import Toolbox, default_tools
from ats.security import mask

LOGGER = get_logger("mobile.appium")
DEFAULT_URL = "http://127.0.0.1:4723"

Probe = Callable[[str], bool]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def server_ready(url: str, timeout: float = 2.0) -> bool:
    """True when an Appium server answers ``/status`` as ready."""
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/status", timeout=timeout) as response:  # noqa: S310 - http to localhost
            body = json.loads(response.read().decode("utf-8", "replace") or "{}")
    except (OSError, ValueError, urllib.error.URLError):
        return False
    value = body.get("value", body) if isinstance(body, dict) else {}
    return bool(value.get("ready", True)) if isinstance(value, dict) else True


def kill_tree(process: subprocess.Popen[Any]) -> None:
    """Stop Appium and the Node children it started (``appium`` is a Node launcher on every platform)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, timeout=15)  # noqa: S603,S607
        else:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
    except (OSError, subprocess.TimeoutExpired):
        pass


class AppiumServer:
    """Context manager. ``url`` is where sessions are created. A server that was already running is reused and left running."""

    def __init__(self, tools: Toolbox | None = None, log_file: Path | None = None, *, popen: Callable[..., Any] = subprocess.Popen, probe: Probe = server_ready, port: int | None = None, reuse: bool = True) -> None:
        self.tools = tools or default_tools()
        self.log_file = log_file
        self._popen = popen
        self._probe = probe
        self._port = port
        self._reuse = reuse
        self.url = ""
        self.process: Any = None
        self.reused = False
        self._log_handle: Any = None

    def start(self) -> str:
        configured = self.tools.env("APPIUM_SERVER_URL")
        for candidate in [configured, DEFAULT_URL if self._reuse else ""]:
            if candidate and self._probe(candidate):
                self.url, self.reused = candidate.rstrip("/"), True
                return self.url
        command = self.tools.appium_command()
        if not command:
            raise MobileError("Appium is not available in the current execution environment. Install Node.js, then run: npm install -g appium")
        port = self._port or free_port()
        argv = [*command, "--address", "127.0.0.1", "--port", str(port), "--log-no-colors"]
        stdout: Any = subprocess.DEVNULL
        if self.log_file is not None:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = self.log_file.open("w", encoding="utf-8", errors="replace")
            stdout = self._log_handle
        try:
            self.process = self._popen(argv, stdout=stdout, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=self.tools.environment())
        except OSError as exc:
            self._close_log()
            raise MobileError("Appium could not be started. Check that it is installed (npm install -g appium).") from exc
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + settings.appium_start_timeout()
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.stop()
                raise MobileError("Appium stopped right after it was started." + self._log_hint())
            if self._probe(url):
                self.url = url
                return url
            time.sleep(0.5)
        self.stop()
        raise MobileError("Appium did not become ready in time." + self._log_hint())

    def _log_hint(self) -> str:
        tail = self.log_tail(6)
        return f" Last log lines: {tail}" if tail else ""

    def log_tail(self, lines: int = 20) -> str:
        """The end of the Appium log with secrets masked."""
        if self.log_file is None or not self.log_file.is_file():
            return ""
        try:
            return mask(" | ".join(self.log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]))[:600]
        except OSError:
            return ""

    def _close_log(self) -> None:
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except OSError:
                pass
            self._log_handle = None

    def stop(self) -> None:
        if self.process is not None and not self.reused:
            try:
                kill_tree(self.process)
            except Exception:  # noqa: BLE001 - stopping must never raise
                LOGGER.warning("Could not stop the Appium process cleanly", exc_info=True)
        self.process = None
        self._close_log()

    def __enter__(self) -> AppiumServer:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()
