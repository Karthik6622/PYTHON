"""The application under test: APK validation and storage, package/launch-activity discovery, and installed-app resolution."""

from __future__ import annotations

import os
import re
import secrets
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ats.config import get_settings
from ats.logging_setup import get_logger
from ats.mobile import settings
from ats.mobile.models import MobileError
from ats.mobile.tools import Toolbox, default_tools

LOGGER = get_logger("mobile.apk")
PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
ACTIVITY = re.compile(r"^[A-Za-z0-9_.$]+$")
DEX = re.compile(r"^classes\d*\.dex$")
MAX_UNCOMPRESSED_FACTOR = 8  # a zip that expands to more than 8x the size limit is treated as a zip bomb


@dataclass
class ApkInfo:
    package: str = ""
    activity: str = ""
    version: str = ""
    note: str = ""  # why something could not be read (shown to the tester)


# ----------------------------------------------------------------------------------------
# validation
# ----------------------------------------------------------------------------------------
def is_valid_package(value: str) -> bool:
    return bool(PACKAGE.match(value or ""))


def is_valid_activity(value: str) -> bool:
    return bool(value) and bool(ACTIVITY.match(value))


def normalize_activity(activity: str, package: str) -> str:
    activity = (activity or "").strip()
    if activity.startswith(".") and package:
        return package + activity
    return activity


def _unsafe_member(name: str) -> bool:
    text = name.replace("\\", "/")
    return "\x00" in text or text.startswith("/") or bool(re.match(r"^[A-Za-z]:", text)) or ".." in PurePosixPath(text).parts


def validate_apk(path: Path, max_bytes: int | None = None) -> Path:
    """Check that ``path`` is a real, reasonably sized APK. Raises ``MobileError`` with a message a tester understands."""
    limit = max_bytes or settings.max_apk_bytes()
    if path.suffix.lower() != ".apk":
        raise MobileError("Only .apk files are supported.")
    if not path.is_file():
        raise MobileError("Selected APK could not be found.")
    size = path.stat().st_size
    if size == 0:
        raise MobileError("The selected APK is empty.")
    if size > limit:
        raise MobileError(f"The APK is {size // (1024 * 1024)} MB, which is over the {limit // (1024 * 1024)} MB limit (MOBILE_MAX_APK_MB).")
    if not zipfile.is_zipfile(path):
        raise MobileError("The file is not a valid APK (it is not a zip archive).")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if any(_unsafe_member(n) for n in names):
                raise MobileError("The APK contains unsafe file paths and was rejected.")
            if "AndroidManifest.xml" not in names:
                raise MobileError("The file is not a valid APK: AndroidManifest.xml is missing.")
            if not any(DEX.match(n) for n in names):
                raise MobileError("The file is not a valid APK: it contains no classes.dex.")
            if sum(i.file_size for i in infos) > limit * MAX_UNCOMPRESSED_FACTOR:
                raise MobileError("The APK expands to an unreasonable size and was rejected.")
    except zipfile.BadZipFile as exc:
        raise MobileError("The file is not a valid APK (the zip archive is damaged).") from exc
    return path


def check_upload_name(name: str) -> str:
    """The display name of an upload. It is never used as a path; a name that tries to be one is refused."""
    text = (name or "").strip()
    if not text or "\x00" in text or "/" in text or "\\" in text or text in {".", ".."} or ".." in PurePosixPath(text).parts:
        raise MobileError("The file name is not allowed.")
    if not text.lower().endswith(".apk"):
        raise MobileError("Only .apk files are supported.")
    return text


def uploads_dir(project_id: str) -> Path:
    """Uploaded APKs live in the secure folder: never in a generated bundle, a ZIP, a report or Git."""
    return get_settings().secure_dir / "mobile" / re.sub(r"[^A-Za-z0-9]", "", project_id)


def store_upload(project_id: str, filename: str, data: bytes) -> Path:
    """Validate an uploaded APK and keep it under a random name. Nothing is stored when validation fails."""
    check_upload_name(filename)
    limit = settings.max_apk_bytes()
    if len(data) > limit:
        raise MobileError(f"The APK is {len(data) // (1024 * 1024)} MB, which is over the {limit // (1024 * 1024)} MB limit (MOBILE_MAX_APK_MB).")
    folder = uploads_dir(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    final = folder / f"{secrets.token_hex(16)}.apk"
    partial = final.with_suffix(".part.apk")
    try:
        partial.write_bytes(data)
        validate_apk(partial)
        os.replace(partial, final)
    finally:
        partial.unlink(missing_ok=True)
    return final


def remove_stored_apk(project_id: str, path: str) -> None:
    """Delete a previously uploaded APK (only files inside this project's upload folder are ever removed)."""
    if not path:
        return
    target, folder = Path(path).resolve(), uploads_dir(project_id).resolve()
    if folder in target.parents:
        target.unlink(missing_ok=True)


def check_local_path(text: str) -> Path:
    """A path the tester typed: it must be an existing, valid .apk file. The file is used where it is (not copied)."""
    raw = (text or "").strip().strip('"')
    if not raw or "\x00" in raw:
        raise MobileError("Enter the path of the APK file.")
    return validate_apk(Path(os.path.expandvars(os.path.expanduser(raw))).resolve())


# ----------------------------------------------------------------------------------------
# package and launch activity
# ----------------------------------------------------------------------------------------
def _from_pyaxmlparser(path: Path) -> ApkInfo | None:
    try:
        from pyaxmlparser import APK  # noqa: PLC0415 - optional dependency
    except ImportError:
        return None
    try:
        apk = APK(str(path))
        package = str(apk.package or "")
        activity = normalize_activity(str(apk.get_main_activity() or ""), package)
        return ApkInfo(package=package, activity=activity, version=str(getattr(apk, "version_name", "") or ""))
    except Exception as exc:  # noqa: BLE001 - a parser failure falls through to aapt
        LOGGER.info("pyaxmlparser could not read the APK: %s", exc.__class__.__name__)
        return None


def _from_aapt(path: Path, tools: Toolbox) -> ApkInfo | None:
    aapt = tools.aapt()
    if not aapt:
        return None
    result = tools.run([aapt, "dump", "badging", str(path)], 60)
    if not result.ok:
        return None
    package = re.search(r"package: name='([^']+)'", result.stdout)
    activity = re.search(r"launchable-activity: name='([^']+)'", result.stdout)
    version = re.search(r"versionName='([^']*)'", result.stdout)
    if not package:
        return None
    return ApkInfo(package=package.group(1), activity=normalize_activity(activity.group(1) if activity else "", package.group(1)), version=version.group(1) if version else "")


def read_apk_info(path: Path, tools: Toolbox | None = None) -> ApkInfo:
    """Package name and launchable activity from the binary manifest: pyaxmlparser first, then aapt2/aapt. Never raises."""
    tools = tools or default_tools()
    for reader in (lambda: _from_pyaxmlparser(path), lambda: _from_aapt(path, tools)):
        info = reader()
        if info and info.package:
            return info
    return ApkInfo(note="The package name could not be read from the APK automatically. Enter it below.")


# ----------------------------------------------------------------------------------------
# applications that are already installed on the device
# ----------------------------------------------------------------------------------------
COMPONENT = re.compile(r"^([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)$")


def is_installed(tools: Toolbox, serial: str, package: str) -> bool:
    adb = tools.adb()
    if not adb or not is_valid_package(package):
        return False
    result = tools.run([adb, "-s", serial, "shell", "pm", "path", package], 15)
    return result.ok and "package:" in result.stdout


def resolve_installed_activity(tools: Toolbox, serial: str, package: str) -> str:
    """The launcher activity of an installed package (``cmd package resolve-activity``, then ``dumpsys package``). Empty when unknown."""
    adb = tools.adb()
    if not adb or not is_valid_package(package):  # the package is part of an on-device shell command: it must be a plain package name
        return ""
    result = tools.run([adb, "-s", serial, "shell", "cmd", "package", "resolve-activity", "--brief", package], 20)
    for line in reversed([ln.strip() for ln in result.stdout.splitlines() if ln.strip()]) if result.ok else []:
        match = COMPONENT.match(line)
        if match:
            return normalize_activity(match.group(2), match.group(1))
    dump = tools.run([adb, "-s", serial, "shell", "dumpsys", "package", package], 30)
    if dump.ok:
        seen_main = False
        for line in dump.stdout.splitlines():
            if "android.intent.action.MAIN" in line:
                seen_main = True
                continue
            match = re.search(rf"\b{re.escape(package)}/([A-Za-z0-9_.$]+)", line) if seen_main else None
            if match:
                return normalize_activity(match.group(1), package)
    return ""
