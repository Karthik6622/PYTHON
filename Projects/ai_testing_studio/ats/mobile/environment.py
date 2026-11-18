"""Environment validation for mobile testing. Never raises into the UI: every problem becomes a check with a message and a fix hint."""

from __future__ import annotations

import importlib.util
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ats.mobile import apk as apk_tools
from ats.mobile.devices import Device, devices_for, list_devices
from ats.mobile.models import RUN_ON, MobileConfig
from ats.mobile.tools import Toolbox, default_tools

OK, WARN, FAIL = "ok", "warn", "fail"
MSG_NO_DEVICE = "No Android device detected. Start an Android emulator or connect an Android device with USB debugging enabled."
MSG_NO_APPIUM = "Appium is not available in the current execution environment."
MSG_NO_DRIVER = "UiAutomator2 driver is not installed."
MSG_NO_APK = "Selected APK could not be found."


@dataclass
class Check:
    key: str
    title: str
    status: str
    message: str
    fix: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"key": self.key, "title": self.title, "status": self.status, "message": self.message, "fix": self.fix}


@dataclass
class EnvReport:
    checks: list[Check] = field(default_factory=list)
    devices: list[Device] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(c.status == FAIL for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]

    def get(self, key: str) -> Check | None:
        return next((c for c in self.checks if c.key == key), None)

    def problem(self) -> str:
        """One sentence for the first thing that blocks testing ('' when everything needed is in place)."""
        first = self.failures[0] if self.failures else None
        return f"{first.message} {first.fix}".strip() if first else ""

    def as_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "checks": [c.as_dict() for c in self.checks]}


def _version(text: str) -> str:
    match = re.search(r"\d+(?:\.\d+){1,3}", text or "")
    return match.group(0) if match else ""


def _check_client() -> Check:
    if importlib.util.find_spec("appium") is None:
        return Check("client", "Appium Python client", FAIL, "The Appium Python client is not installed.", "Run: python -m pip install Appium-Python-Client")
    return Check("client", "Appium Python client", OK, "The Appium Python client is installed.")


def _check_adb(tools: Toolbox) -> tuple[Check, str | None]:
    adb = tools.adb()
    if not adb:
        return Check("adb", "Android Debug Bridge (adb)", FAIL, "adb was not found.", "Install the Android SDK platform-tools and add them to PATH, or set ANDROID_HOME."), None
    result = tools.run([adb, "version"], 15)
    if not result.ok:
        return Check("adb", "Android Debug Bridge (adb)", FAIL, "adb was found but did not run.", "Check the Android SDK platform-tools installation."), None
    version = _version(result.stdout)
    return Check("adb", "Android Debug Bridge (adb)", OK, f"adb {version} is available." if version else "adb is available."), adb


def _check_sdk(tools: Toolbox) -> Check:
    root = tools.sdk_root()
    if root:
        return Check("sdk", "Android SDK", OK, f"Android SDK found at {root}.")
    return Check("sdk", "Android SDK", FAIL, "The Android SDK was not found.", "Install the Android SDK and set the ANDROID_HOME environment variable to its folder.")


def _check_appium(tools: Toolbox) -> tuple[Check, list[str] | None]:
    command = tools.appium_command()
    if not command:
        return Check("appium", "Appium server", FAIL, MSG_NO_APPIUM, "Install Node.js, then run: npm install -g appium"), None
    result = tools.run([*command, "--version"], 60)
    version = _version(result.stdout) if result.ok else ""
    if not version:
        return Check("appium", "Appium server", FAIL, MSG_NO_APPIUM, "Install Node.js, then run: npm install -g appium"), None
    return Check("appium", "Appium server", OK, f"Appium {version} is available."), command


def _installed_drivers(text: str) -> set[str] | None:
    """Names of the installed Appium drivers from ``appium driver list --installed --json`` (None when the output cannot be read)."""
    start = text.find("{")
    if start < 0:
        return None
    try:
        data = json.loads(text[start:])
    except ValueError:
        return None
    return {name.lower() for name, info in data.items() if isinstance(info, dict) and info.get("installed", True)} if isinstance(data, dict) else None


def _check_driver(tools: Toolbox, command: list[str] | None) -> Check:
    title = "UiAutomator2 driver"
    if command is None:
        return Check("driver", title, WARN, "Not checked because Appium is not available.")
    result = tools.run([*command, "driver", "list", "--installed", "--json"], 90)
    names = _installed_drivers(result.text) if result.ok else None
    if names is None:
        found = result.ok and "uiautomator2" in result.text.lower()
    else:
        found = "uiautomator2" in names
    if not found:
        return Check("driver", title, FAIL, MSG_NO_DRIVER, "Run: appium driver install uiautomator2")
    return Check("driver", title, OK, "The UiAutomator2 driver is installed.")


def _check_device(config: MobileConfig, devices: list[Device], adb_ok: bool) -> Check:
    title = "Device"
    if not adb_ok:
        return Check("device", title, WARN, "Not checked because adb is not available.")
    ready = [d for d in devices if d.ready]
    if not ready:
        blocked = [d for d in devices if not d.ready]
        if blocked:
            first = blocked[0]
            hint = "Accept the USB debugging prompt on the device." if first.state == "unauthorized" else "Reconnect the device or restart the emulator."
            return Check("device", title, FAIL, f"{first.title} is {first.state}.", hint)
        return Check("device", title, FAIL, MSG_NO_DEVICE, "Start an emulator from Android Studio (Device Manager) or plug in a phone and enable USB debugging.")
    fitting = devices_for(config.run_on, ready)
    if not fitting:
        if config.run_on == "emulator":
            return Check("device", title, FAIL, "No running Android emulator was found, but a connected device is available.", "Start an emulator from Android Studio (Device Manager), or switch 'Run On' to Connected Android Device.")
        return Check("device", title, FAIL, "No connected Android device was found, but an emulator is running.", "Connect a phone with USB debugging enabled, or switch 'Run On' to Android Emulator.")
    if config.device_serial:
        chosen = next((d for d in fitting if d.serial == config.device_serial), None)
        if chosen is None:
            return Check("device", title, FAIL, f"The selected device ({config.device_label or config.device_serial}) is no longer available.", "Press Refresh and choose a device again.")
        return Check("device", title, OK, f"{chosen.title} is ready.")
    return Check("device", title, WARN, f"{len(fitting)} {RUN_ON[config.run_on].lower()}(s) available. Choose one.", "Pick a device in the Device list.")


def _check_app(config: MobileConfig, tools: Toolbox, serial: str) -> Check:
    title = "Application"
    if config.uses_apk:
        if not config.apk_path:
            return Check("app", title, FAIL, "No APK is selected.", "Upload an APK or enter the path of a local APK.")
        path = Path(config.apk_path)
        if not path.is_file():
            return Check("app", title, FAIL, MSG_NO_APK, "Upload it again or correct the path.")
        try:
            apk_tools.validate_apk(path)
        except Exception as exc:  # noqa: BLE001 - MobileError carries a clean message
            return Check("app", title, FAIL, getattr(exc, "user_message", "The APK is not valid."), "Choose a different APK.")
        return Check("app", title, OK, f"{config.apk_name or path.name} is ready.")
    if not config.package:
        return Check("app", title, FAIL, "No application package name is set.", "Enter the package name of the installed application (for example com.example.app).")
    if not apk_tools.is_valid_package(config.package):
        return Check("app", title, FAIL, "The package name is not valid.", "Use a name like com.example.app.")
    if serial and not apk_tools.is_installed(tools, serial, config.package):
        return Check("app", title, FAIL, f"{config.package} is not installed on the selected device.", "Install the application or use an APK instead.")
    return Check("app", title, OK, f"{config.package} will be started on the device.")


def check_environment(config: MobileConfig | None = None, *, tools: Toolbox | None = None, need_device: bool = True, need_app: bool = True) -> EnvReport:
    """Everything mobile testing needs, as a list of ok/warn/fail checks. Never raises."""
    config = config or MobileConfig()
    tools = tools or default_tools()
    report = EnvReport()
    try:
        adb_check, adb = _check_adb(tools)
        appium_check, command = _check_appium(tools)
        report.checks += [_check_client(), adb_check, _check_sdk(tools) if adb else Check("sdk", "Android SDK", WARN, "Not checked because adb is not available."), appium_check, _check_driver(tools, command)]
        if need_device:
            report.devices = list_devices(tools) if adb else []
            device_check = _check_device(config, report.devices, adb is not None)
            report.checks.append(device_check)
        if need_app:
            serial = config.device_serial if config.device_serial else next((d.serial for d in devices_for(config.run_on, report.devices) if d.ready), "")
            report.checks.append(_check_app(config, tools, serial))
    except Exception as exc:  # noqa: BLE001 - the report must always come back
        report.checks.append(Check("unexpected", "Environment check", FAIL, f"The environment check stopped unexpectedly ({exc.__class__.__name__}).", "Try again; if it keeps happening check the studio log."))
    return report
