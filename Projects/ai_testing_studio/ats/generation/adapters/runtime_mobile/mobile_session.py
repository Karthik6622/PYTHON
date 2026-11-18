"""One test's view of the device: records steps, offers the device-level actions (relaunch, back, swipe, rotate, alerts) and writes the
evidence (steps, screenshot, page source, logcat tail, device info, Appium error) that the studio reads after the run."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATTERN = re.compile(r"\{\{env:([A-Za-z_][A-Za-z0-9_]*)\}\}")
LOG_LINES = 30
ERROR_LINE = re.compile(r"(?i)\b(FATAL|AndroidRuntime|ANR in|Exception|crash)\b|\s[EF]/|\s[EF]\s")


class MobileSession:
    def __init__(self, driver, test_case_id: str) -> None:  # noqa: ANN001 - an Appium driver
        self.driver = driver
        self.test_case_id = test_case_id
        self.steps: list[dict] = []
        self.failure: dict = {}
        self.warnings: list[str] = []
        self._secrets: set[str] = set()

    # ------------------------------------------------------------------ values
    def val(self, text: str) -> str:
        """Substitute {{env:NAME}} placeholders from the environment (values never appear in code, steps or reports)."""

        def lookup(match: re.Match) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise AssertionError(f"Environment variable {name} is not set")
            self._secrets.add(os.environ[name])
            return os.environ[name]

        return ENV_PATTERN.sub(lookup, text)

    def _mask(self, text: str) -> str:
        for secret in self._secrets:
            if len(secret) >= 4:
                text = text.replace(secret, "***")
        return text

    # ------------------------------------------------------------------ the app
    @property
    def package(self) -> str:
        caps = getattr(self.driver, "capabilities", None) or {}
        return os.environ.get("APP_PACKAGE") or caps.get("appPackage") or caps.get("appium:appPackage") or getattr(self.driver, "current_package", "") or ""

    def start_test(self) -> None:
        """Every test starts from a freshly launched app."""
        self.relaunch()

    def relaunch(self) -> None:
        package = self.package
        try:
            self.driver.terminate_app(package)
        except Exception:  # noqa: BLE001 - the app may not be running
            pass
        self.driver.activate_app(package)
        time.sleep(1.0)

    # ------------------------------------------------------------------ device actions
    def back(self) -> None:
        self.driver.back()

    def hide_keyboard(self) -> None:
        try:
            self.driver.hide_keyboard()
        except Exception:  # noqa: BLE001 - no keyboard is showing
            pass

    def swipe(self, direction: str) -> None:
        """Move a finger up/down/left/right over the middle of the screen (``up`` scrolls a list down)."""
        size = self.driver.get_window_size()
        width, height = int(size["width"]), int(size["height"])
        self.driver.execute_script(
            "mobile: swipeGesture",
            {"left": int(width * 0.1), "top": int(height * 0.2), "width": int(width * 0.8), "height": int(height * 0.6), "direction": direction, "percent": 0.75},
        )

    def rotate(self, orientation: str) -> None:
        self.driver.orientation = orientation.upper()
        time.sleep(0.8)

    def accept_alert(self) -> None:
        self._alert("accept")

    def dismiss_alert(self) -> None:
        self._alert("dismiss")

    def _alert(self, action: str) -> None:
        try:
            getattr(self.driver.switch_to.alert, action)()
        except Exception:  # noqa: BLE001 - fall back to the UiAutomator2 command
            self.driver.execute_script(f"mobile: {action}Alert", {})

    def wait(self, seconds: float) -> None:
        time.sleep(min(float(seconds), 10.0))

    # ------------------------------------------------------------------ steps and evidence
    @contextmanager
    def step(self, description: str, action: str = "", element: str = ""):
        record = {"index": len(self.steps) + 1, "description": description, "action": action, "element": element, "status": "running"}
        self.steps.append(record)
        try:
            yield
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = self._mask(f"{type(exc).__name__}: {exc}")[:1500]
            self.failure = {"step": record["index"], "action": action, "element": element, "error": record["error"], "error_type": type(exc).__name__}
            raise
        else:
            record["status"] = "passed"

    def _logcat(self) -> list[str]:
        lines: list[str] = []
        try:
            entries = self.driver.get_log("logcat")
            lines = [str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in entries]
        except Exception:  # noqa: BLE001 - not every server exposes the log
            lines = []
        if not lines:
            adb = shutil.which("adb")
            serial = os.environ.get("ANDROID_SERIAL", "")
            if adb and serial:
                try:
                    done = subprocess.run([adb, "-s", serial, "logcat", "-d", "-t", "300"], capture_output=True, text=True, timeout=20, errors="replace")  # noqa: S603
                    lines = done.stdout.splitlines()
                except (OSError, subprocess.TimeoutExpired):
                    lines = []
        errors = [ln for ln in lines if ERROR_LINE.search(ln)]
        return [self._mask(ln)[:300] for ln in (errors[-LOG_LINES:] or lines[-LOG_LINES:])]

    def _device(self) -> dict:
        caps = getattr(self.driver, "capabilities", None) or {}
        pick = lambda *names: next((str(caps[n]) for n in names if caps.get(n)), "")  # noqa: E731
        return {
            "serial": os.environ.get("ANDROID_SERIAL") or pick("deviceUDID", "appium:udid", "udid"),
            "name": pick("deviceName", "appium:deviceName"), "model": pick("deviceModel"), "manufacturer": pick("deviceManufacturer"),
            "platform_version": pick("platformVersion", "appium:platformVersion"), "api_level": pick("deviceApiLevel"),
        }  # fmt: skip

    def finish(self, failed: bool, error: str = "") -> None:
        folder = ROOT / "reports" / "evidence" / self.test_case_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "steps.json").write_text(json.dumps(self.steps, indent=2), encoding="utf-8")
        if not failed:
            return
        message = self.failure.get("error") or self._mask(error)[:1500]
        info = {
            "test_case_id": self.test_case_id, "warnings": self.warnings[-5:], "device": self._device(), "package": self.package,
            "appium_error": {"type": self.failure.get("error_type", ""), "message": message}, "console": self._logcat(), **self.failure,
        }
        info.setdefault("error", message)
        try:
            activity = getattr(self.driver, "current_activity", "") or ""
            info["url"] = f"android-app://{self.package}/{activity}"
            info["title"] = activity
            (folder / "page_source.xml").write_text(self._mask(self.driver.page_source or "")[:500_000], encoding="utf-8")
            (folder / "screenshot.png").write_bytes(self.driver.get_screenshot_as_png())
        except Exception as exc:  # the session may already be gone; evidence is best effort
            info["evidence_error"] = f"{type(exc).__name__}: {self._mask(str(exc))[:200]}"
        (folder / "failure.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
