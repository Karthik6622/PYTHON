"""Appium capabilities. Testers choose a platform, an app and a device; every Appium setting is derived here and never shown in the UI."""

from __future__ import annotations

from typing import Any

from ats.mobile.models import MobileConfig

# Settings that exist only inside this module and the generated project. The Mobile page must never expose or ask for them.
INTERNAL_CAPABILITIES = (
    "automationName", "udid", "deviceName", "systemPort", "newCommandTimeout", "uiautomator2ServerInstallTimeout", "uiautomator2ServerLaunchTimeout",
    "adbExecTimeout", "androidInstallTimeout", "fullReset", "noReset", "autoGrantPermissions", "ignoreHiddenApiPolicyError", "disableWindowAnimation",
    "appWaitDuration", "app", "appPackage", "appActivity", "appWaitActivity", "appWaitForLaunch",
)  # fmt: skip
ANDROID_DEFAULTS: dict[str, Any] = {
    "platformName": "Android",
    "appium:automationName": "UiAutomator2",
    "appium:newCommandTimeout": 300,
    "appium:uiautomator2ServerInstallTimeout": 120000,
    "appium:uiautomator2ServerLaunchTimeout": 120000,
    "appium:adbExecTimeout": 60000,
    "appium:androidInstallTimeout": 180000,
    "appium:autoGrantPermissions": True,
    "appium:ignoreHiddenApiPolicyError": True,
    "appium:disableWindowAnimation": True,
    "appium:fullReset": False,
}


def android_capabilities(config: MobileConfig, *, serial: str = "", app_path: str = "", system_port: int | None = None, wait_activity: bool = True) -> dict[str, Any]:
    """The capabilities of an Android UiAutomator2 session for what the tester selected."""
    caps = dict(ANDROID_DEFAULTS)
    caps["appium:deviceName"] = serial or "Android"
    if serial:
        caps["appium:udid"] = serial
    if system_port:
        caps["appium:systemPort"] = system_port
    # An installed app keeps its data; an APK is installed fresh for a predictable starting point.
    caps["appium:noReset"] = config.app_source == "installed"
    if config.uses_apk and app_path:
        caps["appium:app"] = app_path
    if config.package:
        caps["appium:appPackage"] = config.package
    if config.activity:
        caps["appium:appActivity"] = config.activity
        if wait_activity:
            caps["appium:appWaitActivity"] = "*"
    return caps


def bundle_capabilities(config: MobileConfig) -> dict[str, Any]:
    """Non-secret capabilities written to ``mobile_config/android.json``: no APK path, no device id, no credentials."""
    caps = {k: v for k, v in ANDROID_DEFAULTS.items()}
    caps["appium:noReset"] = config.app_source == "installed"
    if config.package:
        caps["appium:appPackage"] = config.package
    if config.activity:
        caps["appium:appActivity"] = config.activity
        caps["appium:appWaitActivity"] = "*"
    return caps


def ui_summary(config: MobileConfig) -> dict[str, str]:
    """What the UI may show about the configuration: only the tester's own choices."""
    from ats.mobile.models import APP_SOURCES, RUN_ON

    summary = {"Platform": config.platform.title(), "Application source": APP_SOURCES[config.app_source], "Run on": RUN_ON[config.run_on]}
    if config.apk_name:
        summary["APK"] = config.apk_name
    if config.package:
        summary["Package"] = config.package
    if config.activity:
        summary["Launch activity"] = config.activity
    if config.device_label:
        summary["Device"] = config.device_label
    return summary
