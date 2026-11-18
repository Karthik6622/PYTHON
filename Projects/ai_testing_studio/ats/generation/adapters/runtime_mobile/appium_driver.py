"""Appium driver factory for the mobile tests.

Reads what to test from the environment (APP_PATH or APP_PACKAGE, APP_ACTIVITY, ANDROID_SERIAL, APPIUM_SERVER_URL) and the non-secret
capabilities from mobile_config/android.json. When APPIUM_SERVER_URL is not set a local Appium server is started and stopped again.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "mobile_config" / "android.json"
START_TIMEOUT = float(os.environ.get("APPIUM_START_TIMEOUT", "90"))
DEFAULTS = {"platformName": "Android", "appium:automationName": "UiAutomator2", "appium:newCommandTimeout": 300}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def load_capabilities() -> dict:
    """The session capabilities: the committed defaults plus what this run needs from the environment."""
    caps = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.is_file() else dict(DEFAULTS)
    app, package = os.environ.get("APP_PATH", ""), os.environ.get("APP_PACKAGE", "")
    activity, serial = os.environ.get("APP_ACTIVITY", ""), os.environ.get("ANDROID_SERIAL", "")
    if app:
        caps["appium:app"] = app
    if package:
        caps["appium:appPackage"] = package
    if activity:
        caps["appium:appActivity"] = activity
        caps.setdefault("appium:appWaitActivity", "*")
    if serial:
        caps["appium:udid"] = serial
        caps["appium:deviceName"] = serial
    if not (caps.get("appium:app") or caps.get("appium:appPackage")):
        raise RuntimeError("No application to test: set APP_PATH (path of the APK) or APP_PACKAGE (an installed application).")
    caps["appium:systemPort"] = free_port()  # keeps parallel sessions on one machine apart
    return caps


def server_ready(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/status", timeout=timeout) as response:  # noqa: S310 - local server
            body = json.loads(response.read().decode("utf-8", "replace") or "{}")
    except (OSError, ValueError, urllib.error.URLError):
        return False
    value = body.get("value", body) if isinstance(body, dict) else {}
    return bool(value.get("ready", True)) if isinstance(value, dict) else True


def _kill_tree(process: subprocess.Popen) -> None:
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


def start_server() -> tuple[str, Callable[[], None]]:
    """``(server URL, stop function)``. An APPIUM_SERVER_URL given in the environment is used as is and never stopped."""
    configured = os.environ.get("APPIUM_SERVER_URL", "").strip()
    if configured:
        return configured.rstrip("/"), lambda: None
    command = shutil.which("appium")
    if command:
        argv = [command]
    else:
        npx = shutil.which("npx")
        if npx is None:
            raise RuntimeError("Appium is not available in the current execution environment. Install Node.js, then run: npm install -g appium")
        argv = [npx, "--no-install", "appium"]
    port = free_port()
    log_path = ROOT / "reports" / "appium.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("w", encoding="utf-8", errors="replace")
    process = subprocess.Popen(  # noqa: S603 - argument list, no shell
        [*argv, "--address", "127.0.0.1", "--port", str(port), "--log-no-colors"], stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL
    )
    url = f"http://127.0.0.1:{port}"

    def stop() -> None:
        _kill_tree(process)
        log.close()

    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stop()
            raise RuntimeError(f"Appium stopped right after it was started. See {log_path}")
        if server_ready(url):
            return url, stop
        time.sleep(0.5)
    stop()
    raise RuntimeError(f"Appium did not become ready in {START_TIMEOUT:.0f}s. See {log_path}")


def create_driver(url: str, capabilities: dict):  # noqa: ANN201 - an Appium WebDriver
    from appium import webdriver
    from appium.options.android import UiAutomator2Options

    options = UiAutomator2Options().load_capabilities(capabilities)
    return webdriver.Remote(url, options=options)
