"""App analysis: start Appium, open the app on the device, capture the screen (page source + screenshot) and safely explore a few more screens.

The explorer taps tabs, menu items and 'Next'-style buttons only. Anything that looks destructive (delete, remove, log out, pay, buy, send,
submit, reset, uninstall, ...) is never tapped. Everything that can go wrong comes back as a ``MobileError`` with a message a tester understands.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from ats.logging_setup import get_logger
from ats.mobile import hierarchy
from ats.mobile.models import APPIUM_BY, MobileAnalysis, MobileConfig, MobileElement, MobileError, MobileScreen
from ats.models import slugify, utc_now
from ats.progress import report
from ats.security import mask

LOGGER = get_logger("mobile.analysis")
TAPS_PER_SCREEN = 4
MAX_DEPTH = 2

Progress = Callable[..., None] | None


class Driver(Protocol):
    """The part of an Appium driver the analysis uses (a fake with the same methods stands in for tests)."""

    page_source: str
    current_activity: str
    current_package: str

    def get_screenshot_as_png(self) -> bytes: ...
    def find_element(self, by: str, value: str) -> Any: ...
    def back(self) -> None: ...
    def activate_app(self, app_id: str) -> Any: ...
    def terminate_app(self, app_id: str) -> Any: ...
    def quit(self) -> None: ...


DriverFactory = Callable[[str, dict[str, Any]], Driver]


def create_driver(url: str, capabilities: dict[str, Any]) -> Driver:
    """A real UiAutomator2 session. The Appium client is imported here so everything else works (and is testable) without it."""
    try:
        from appium import webdriver  # noqa: PLC0415
        from appium.options.android import UiAutomator2Options  # noqa: PLC0415
    except ImportError as exc:
        raise MobileError("The Appium Python client is not installed. Run: python -m pip install Appium-Python-Client") from exc
    options = UiAutomator2Options().load_capabilities(capabilities)
    return webdriver.Remote(url, options=options)


# ----------------------------------------------------------------------------------------
# error messages
# ----------------------------------------------------------------------------------------
ERROR_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)could not find a connected android device|no devices/emulators found|device '.*' not found|no connected devices|device offline|device unauthorized"),
     "No Android device detected. Start an Android emulator or connect an Android device with USB debugging enabled."),
    (re.compile(r"(?i)neither ANDROID_HOME nor ANDROID_SDK_ROOT|could not find 'adb"), "The Android SDK was not found. Set ANDROID_HOME to the Android SDK folder and make sure adb is installed."),
    (re.compile(r"(?i)INSTALL_FAILED_([A-Z_]+)"), "The app could not be installed on the device (reason: {0}). Uninstall an older copy or use a build that matches the device."),
    (re.compile(r"(?i)could not find a driver|uiautomator2 driver|automationName.*not (?:found|installed)"), "UiAutomator2 driver is not installed. Run: appium driver install uiautomator2"),
    (re.compile(r"(?i)unable to find an app|app.*does not exist or is not accessible|apk.*not found"), "Selected APK could not be found."),
    (re.compile(r"(?i)activity .*does not exist|cannot start the .* application|unable to launch|appActivity|app crashed|process .* is not running"),
     "The app could not be launched. Check the package name and launch activity, and that the app starts on the device."),
    (re.compile(r"(?i)ECONNREFUSED|failed to establish a new connection|max retries exceeded|connection refused"), "The Appium server could not be reached."),
    (re.compile(r"(?i)uiautomator2 server.*(?:failed|did not start|crashed)|instrumentation process"), "The UiAutomator2 server could not start on the device. Unlock the device, disable battery optimisation and try again."),
]


def friendly_error(exc: BaseException) -> str:
    """A tester-readable sentence for an Appium/adb exception. The raw message (masked, shortened) is appended when no rule matches."""
    if isinstance(exc, MobileError):
        return exc.user_message
    text = str(getattr(exc, "msg", "") or exc)
    for pattern, message in ERROR_RULES:
        match = pattern.search(text)
        if match:
            return message.format(*match.groups()) if "{0}" in message else message
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), exc.__class__.__name__)
    return f"The Appium session could not be created or lost its connection: {mask(first)[:220]}"


# ----------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------
def screen_key_for(activity: str, title: str, taken: set[str]) -> str:
    base = slugify(re.sub(r"^.*[./]", "", activity or ""), "") or slugify(title, "screen")
    if base == "screen" and title:
        base = slugify(title, "screen")
    candidate = base
    if candidate in taken and title:
        candidate = f"{base}_{slugify(title, '')[:24].strip('_')}".strip("_")
    number = 2
    while candidate in taken:
        candidate, number = f"{base}_{number}", number + 1
    return candidate


def locate(driver: Driver, element: MobileElement) -> Any | None:
    """The live element for a recorded one: the first ranked selector that finds it."""
    for selector in element.selectors:
        try:
            return driver.find_element(APPIUM_BY[selector.strategy], selector.value)
        except Exception:  # noqa: BLE001 - this selector does not match, try the next one
            continue
    return None


class Explorer:
    def __init__(self, driver: Driver, config: MobileConfig, out_dir: Path, max_screens: int, progress: Progress = None, check: Callable[[], None] | None = None,
                 sleep: Callable[[float], None] = time.sleep, settle: float = 1.2) -> None:  # fmt: skip
        self.driver, self.config, self.out_dir, self.max_screens = driver, config, out_dir, max_screens
        self.progress, self.check, self.sleep, self.settle = progress, check, sleep, settle
        self.screens: list[MobileScreen] = []
        self.paths: dict[str, list[MobileElement]] = {}  # screen key -> taps from the launch screen that reach it
        self.skipped: list[str] = []
        self.warnings: list[str] = []
        self._seen: set[str] = set()

    # ------------------------------------------------------------------ capture
    def capture(self, reached_by: list[str], path: list[MobileElement]) -> MobileScreen | None:
        source = str(self.driver.page_source or "")
        nodes = hierarchy.parse_page_source(source)
        fingerprint = hierarchy.fingerprint_of(nodes)
        if fingerprint in self._seen:
            return None
        activity = str(getattr(self.driver, "current_activity", "") or "")
        title = hierarchy.title_of(nodes, "")
        key = screen_key_for(activity, title, {s.screen_key for s in self.screens})
        elements = hierarchy.build_elements(nodes, key)
        screenshot = ""
        try:
            png = self.driver.get_screenshot_as_png()
            screenshot = f"{len(self.screens) + 1:02d}_{key}.png"
            (self.out_dir / screenshot).write_bytes(png)
        except Exception:  # noqa: BLE001 - a screen without a picture is still useful
            LOGGER.info("Screenshot of %s could not be saved", key)
            screenshot = ""
        self._seen.add(fingerprint)
        screen = MobileScreen(
            screen_key=key, title=title or key.replace("_", " ").title(), activity=activity, package=str(getattr(self.driver, "current_package", "") or ""),
            reached_by=reached_by, screenshot=screenshot, elements=elements, fingerprint=fingerprint,
        )  # fmt: skip
        self.screens.append(screen)
        self.paths[key] = path
        for label in hierarchy.blocked_controls(elements):
            if label not in self.skipped:
                self.skipped.append(label)
        return screen

    def _fingerprint(self) -> str:
        try:
            return hierarchy.fingerprint_of(hierarchy.parse_page_source(str(self.driver.page_source or "")))
        except MobileError:
            return ""

    # ------------------------------------------------------------------ navigation
    def _tap(self, element: MobileElement) -> bool:
        live = locate(self.driver, element)
        if live is None:
            return False
        try:
            live.click()
        except Exception:  # noqa: BLE001
            return False
        self.sleep(self.settle)
        return True

    def _return_to(self, screen: MobileScreen) -> bool:
        """Go back to ``screen``: the back button first, otherwise restart the app and repeat the taps that lead to it."""
        try:
            self.driver.back()
            self.sleep(self.settle / 2)
        except Exception:  # noqa: BLE001
            pass
        if self._fingerprint() == screen.fingerprint:
            return True
        package = screen.package or self.config.package
        try:
            self.driver.terminate_app(package)
            self.driver.activate_app(package)
            self.sleep(self.settle * 2)
        except Exception:  # noqa: BLE001
            return False
        for step in self.paths.get(screen.screen_key, []):
            if not self._tap(step):
                return False
        return self._fingerprint() == screen.fingerprint

    # ------------------------------------------------------------------ exploration
    def explore(self, screen: MobileScreen, depth: int = 0) -> None:
        tapped: set[str] = set()
        for candidate in hierarchy.tap_candidates(screen.elements, TAPS_PER_SCREEN + 2):
            if len(self.screens) >= self.max_screens or len(tapped) >= TAPS_PER_SCREEN:
                return
            if self.check:
                self.check()
            if candidate.name in tapped:
                continue
            tapped.add(candidate.name)
            report(self.progress, f"Opening '{candidate.name}' to find more screens ({len(self.screens)} of up to {self.max_screens})", 0.4 + 0.5 * len(self.screens) / self.max_screens)
            if not self._tap(candidate):
                continue
            try:
                opened = self.capture([*screen.reached_by, candidate.name], [*self.paths.get(screen.screen_key, []), candidate])
            except MobileError as exc:
                self.warnings.append(exc.user_message)
                opened = None
            if opened is not None and depth + 1 < MAX_DEPTH and len(self.screens) < self.max_screens:
                self.explore(opened, depth + 1)
            if not self._return_to(screen):
                self.warnings.append(f"The app did not return to '{screen.title}' after exploring it; exploration stopped there.")
                return


def explore_app(driver: Driver, config: MobileConfig, out_dir: Path, max_screens: int, progress: Progress = None, check: Callable[[], None] | None = None,
                device: str = "", sleep: Callable[[float], None] = time.sleep, settle: float = 1.2) -> MobileAnalysis:  # fmt: skip
    """Capture the launch screen and safely explore from it. ``driver`` is an open session on the app."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        old.unlink(missing_ok=True)
    explorer = Explorer(driver, config, out_dir, max_screens, progress, check, sleep, settle)
    report(progress, "Reading the first screen of the app", 0.38)
    home = explorer.capture([], [])
    if home is None or not home.elements:
        raise MobileError("The app opened, but no screen elements could be read. Make sure the app is on a normal screen (not a splash or system dialog) and try again.")
    explorer.explore(home)
    package = config.package or home.package
    activity = config.activity or home.activity
    return MobileAnalysis(
        platform=config.platform, package=package, activity=activity, device=device, screens=explorer.screens, skipped=explorer.skipped, warnings=explorer.warnings, analysed_at=utc_now()
    )
