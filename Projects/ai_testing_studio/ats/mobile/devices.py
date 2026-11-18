"""Android devices: running emulators and connected phones (``adb devices -l``) and installed AVD names (``emulator -list-avds``)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ats.mobile.models import RUN_ON
from ats.mobile.tools import Toolbox, default_tools

SERIAL = re.compile(r"^[A-Za-z0-9:._\-]+$")


@dataclass
class Device:
    serial: str
    state: str = "device"  # device | offline | unauthorized | no permissions ...
    kind: str = "device"  # emulator | device
    model: str = ""
    manufacturer: str = ""
    avd: str = ""
    android_version: str = ""
    label: str = field(default="")

    @property
    def ready(self) -> bool:
        return self.state == "device"

    @property
    def title(self) -> str:
        """What the picker shows. The tester never types or sees a UDID for a phone; an emulator shows its port to tell instances apart."""
        if self.label:
            return self.label
        if self.kind == "emulator":
            return f"{self.avd or self.model or 'Android Emulator'} ({self.serial})"
        name = f"{self.manufacturer} {self.model}".strip() if self.model and self.manufacturer and not self.model.lower().startswith(self.manufacturer.lower()) else self.model
        return (name or self.serial).strip()

    def picker_label(self) -> str:
        extra = f" - Android {self.android_version}" if self.android_version else ""
        problem = "" if self.ready else f" [{self.state}]"
        return f"{self.title}{extra}{problem}"


def parse_adb_devices(text: str) -> list[Device]:
    """Parse the output of ``adb devices -l``. Headers, daemon notices and malformed lines are ignored."""
    devices: list[Device] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith(("List of devices", "*", "adb server")):
            continue
        parts = line.split()
        if len(parts) < 2 or not SERIAL.match(parts[0]):
            continue
        serial, rest = parts[0], parts[1:]
        state = rest[0]
        if state == "no" and len(rest) > 1 and rest[1] == "permissions":
            state = "no permissions"
        attributes = dict(item.split(":", 1) for item in rest if ":" in item)
        devices.append(
            Device(serial=serial, state=state, kind="emulator" if serial.startswith("emulator-") else "device", model=attributes.get("model", "").replace("_", " "))
        )
    return devices


def _getprop(tools: Toolbox, adb: str, serial: str, name: str) -> str:
    result = tools.run([adb, "-s", serial, "shell", "getprop", name], 10)
    return result.stdout.strip().splitlines()[0].strip() if result.ok and result.stdout.strip() else ""


def _avd_name(tools: Toolbox, adb: str, serial: str) -> str:
    result = tools.run([adb, "-s", serial, "emu", "avd", "name"], 10)
    lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip() and ln.strip().upper() != "OK"] if result.ok else []
    return lines[0] if lines else _getprop(tools, adb, serial, "ro.boot.qemu.avd_name")


def list_devices(tools: Toolbox | None = None) -> list[Device]:
    """Every device adb can see, with friendly names. Never raises; without adb the list is empty."""
    tools = tools or default_tools()
    adb = tools.adb()
    if not adb:
        return []
    result = tools.run([adb, "devices", "-l"], 15)
    if not result.ok:
        return []
    devices = parse_adb_devices(result.stdout)
    for device in devices:
        if not device.ready:
            continue
        model = _getprop(tools, adb, device.serial, "ro.product.model")
        device.model = model or device.model
        device.android_version = _getprop(tools, adb, device.serial, "ro.build.version.release")
        if device.kind == "emulator":
            device.avd = _avd_name(tools, adb, device.serial)
        else:
            device.manufacturer = _getprop(tools, adb, device.serial, "ro.product.manufacturer").title()
    unique_titles(devices)
    return devices


def unique_titles(devices: list[Device]) -> None:
    """Two phones of the same model get their serial appended so the picker stays unambiguous."""
    counts: dict[str, int] = {}
    for device in devices:
        counts[device.title] = counts.get(device.title, 0) + 1
    for device in devices:
        if counts[device.title] > 1 and device.kind == "device":
            device.label = f"{device.title} ({device.serial})"


def list_avds(tools: Toolbox | None = None) -> list[str]:
    """Names of the installed Android Virtual Devices (empty when the emulator tool is not available)."""
    tools = tools or default_tools()
    emulator = tools.emulator()
    if not emulator:
        return []
    result = tools.run([emulator, "-list-avds"], 15)
    if not result.ok:
        return []
    return [ln.strip() for ln in result.stdout.splitlines() if ln.strip() and re.match(r"^[A-Za-z0-9_.\-]+$", ln.strip())]


def devices_for(run_on: str, devices: list[Device]) -> list[Device]:
    """The devices that fit the 'Run On' choice."""
    wanted = "emulator" if run_on == "emulator" else "device"
    return [d for d in devices if d.kind == wanted]


def run_on_label(run_on: str) -> str:
    return RUN_ON.get(run_on, RUN_ON["emulator"])
