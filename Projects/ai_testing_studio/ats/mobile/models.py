"""Domain models of the mobile channel: project configuration, devices, analysed screens/elements, and the mobile automation plan."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from ats.errors import StudioError
from ats.models import _Model

APP_SOURCES = {"upload": "Upload APK", "path": "Local APK Path", "installed": "Already Installed Application"}
RUN_ON = {"emulator": "Android Emulator", "device": "Connected Android Device"}
SELECTOR_STRATEGIES = ("accessibility_id", "id", "uiautomator", "xpath")  # best first
# Appium's locator strategy names (the values of ``AppiumBy``), kept here so nothing but the generated project needs the Appium client.
APPIUM_BY = {"accessibility_id": "accessibility id", "id": "id", "uiautomator": "-android uiautomator", "xpath": "xpath"}
APPIUM_BY_CONSTANT = {"accessibility_id": "ACCESSIBILITY_ID", "id": "ID", "uiautomator": "ANDROID_UIAUTOMATOR", "xpath": "XPATH"}


class MobileError(StudioError):
    default_message = "The mobile request failed."


class MobileConfig(_Model):
    """What a tester chooses on the Mobile page. Internal Appium settings are never part of it (see ats.mobile.capabilities)."""

    platform: str = "android"
    app_source: Literal["upload", "path", "installed"] = "upload"
    apk_path: str = ""  # the stored upload, or the path the tester typed
    apk_name: str = ""  # original file name of an upload (display only)
    package: str = ""
    activity: str = ""
    run_on: Literal["emulator", "device"] = "emulator"
    device_serial: str = ""
    device_label: str = ""

    @field_validator("app_source", mode="before")
    @classmethod
    def _source(cls, value: Any) -> str:
        return value if value in APP_SOURCES else "upload"

    @field_validator("run_on", mode="before")
    @classmethod
    def _run_on(cls, value: Any) -> str:
        return value if value in RUN_ON else "emulator"

    @property
    def uses_apk(self) -> bool:
        return self.app_source in {"upload", "path"}

    @property
    def has_app(self) -> bool:
        return bool(self.apk_path) if self.uses_apk else bool(self.package)


class MobileSelector(_Model):
    strategy: Literal["accessibility_id", "id", "uiautomator", "xpath"]
    value: str
    unique: bool = True  # matched exactly one element on the screen where it was captured

    def display(self) -> str:
        labels = {"accessibility_id": "accessibility id", "id": "resource id", "uiautomator": "UiSelector", "xpath": "xpath"}
        return f"{labels[self.strategy]}: {self.value}"

    def identity(self) -> tuple[str, str]:
        return (self.strategy, self.value)


class MobileElement(_Model):
    key: str  # <screen_key>.<name>, unique per project
    screen: str = ""
    name: str = ""  # readable label (accessibility label, text, hint or resource id)
    role: str = "element"
    resource_id: str = ""
    accessibility_id: str = ""
    text: str = ""
    class_name: str = ""
    package: str = ""
    clickable: bool = False
    enabled: bool = True
    focusable: bool = False
    scrollable: bool = False
    checkable: bool = False
    password: bool = False
    bounds: list[int] = Field(default_factory=list)  # [left, top, right, bottom]
    selectors: list[MobileSelector] = Field(default_factory=list)  # ranked, best first

    @property
    def preferred(self) -> MobileSelector | None:
        return self.selectors[0] if self.selectors else None


class MobileScreen(_Model):
    screen_key: str
    title: str = ""
    activity: str = ""
    package: str = ""
    reached_by: list[str] = Field(default_factory=list)  # taps that opened it from the launch screen
    screenshot: str = ""  # file name inside the project's mobile folder
    elements: list[MobileElement] = Field(default_factory=list)
    fingerprint: str = ""


class MobileAnalysis(_Model):
    platform: str = "android"
    package: str = ""
    activity: str = ""
    device: str = ""
    screens: list[MobileScreen] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)  # controls that were deliberately not tapped (destructive labels)
    warnings: list[str] = Field(default_factory=list)
    analysed_at: str = ""

    def elements(self) -> dict[str, MobileElement]:
        return {e.key: e for s in self.screens for e in s.elements}

    def screen_of(self, key: str) -> MobileScreen | None:
        return next((s for s in self.screens if s.screen_key == key), None)


# ----------------------------------------------------------------------------------------
# automation plan (what the script-planning agent returns, before it is rendered as Appium code)
# ----------------------------------------------------------------------------------------
MOBILE_ACTIONS = [
    "launch_app", "tap", "long_press", "type", "clear", "swipe", "back", "hide_keyboard", "rotate", "accept_alert", "dismiss_alert", "wait",
    "expect_visible", "expect_hidden", "expect_text", "expect_enabled", "expect_disabled",
]  # fmt: skip
ELEMENT_ACTIONS = {"tap", "long_press", "type", "clear", "expect_visible", "expect_hidden", "expect_text", "expect_enabled", "expect_disabled"}
VALUE_ACTIONS = {"type", "swipe", "rotate", "wait", "expect_text"}
SWIPE_DIRECTIONS = ("up", "down", "left", "right")
ORIENTATIONS = ("portrait", "landscape")


class MobileStep(_Model):
    action: str
    element: str | None = None
    value: str | None = None
    description: str = ""

    @field_validator("action", mode="before")
    @classmethod
    def _action(cls, value: Any) -> str:
        text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {"click": "tap", "press": "tap", "fill": "type", "enter_text": "type", "send_keys": "type", "scroll": "swipe", "relaunch": "launch_app",
                   "restart_app": "launch_app", "assert_visible": "expect_visible", "assert_text": "expect_text", "expect_not_visible": "expect_hidden"}  # fmt: skip
        text = aliases.get(text, text)
        if text not in MOBILE_ACTIONS:
            raise ValueError(f"unsupported action '{value}'")
        return text

    @field_validator("value", mode="before")
    @classmethod
    def _value(cls, value: Any) -> str | None:
        return None if value is None else str(value)


class MobileScript(_Model):
    test_case_id: str
    title: str = ""
    notes: str = ""
    steps: list[MobileStep] = Field(default_factory=list)


class MobilePlan(_Model):
    scripts: list[MobileScript] = Field(default_factory=list)
