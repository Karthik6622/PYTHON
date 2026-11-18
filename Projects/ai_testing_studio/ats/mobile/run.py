"""Preparing a test run on a device: what the generated tests read from the environment, and a plain-language reason when it cannot start."""

from __future__ import annotations

from dataclasses import dataclass, field

from ats.mobile.environment import check_environment
from ats.mobile.models import MobileConfig, MobileError
from ats.mobile.service import MobileService
from ats.mobile.tools import Toolbox, default_tools
from ats.repository import Repository


@dataclass
class RunPrep:
    env: dict[str, str] = field(default_factory=dict)  # APP_PATH, APP_PACKAGE, APP_ACTIVITY, ANDROID_SERIAL (never secrets)
    problem: str = ""


def run_environment(config: MobileConfig, serial: str, tools: Toolbox) -> dict[str, str]:
    env = {"ANDROID_SERIAL": serial}
    if config.uses_apk and config.apk_path:
        env["APP_PATH"] = config.apk_path
    if config.package:
        env["APP_PACKAGE"] = config.package
    if config.activity:
        env["APP_ACTIVITY"] = config.activity
    sdk = tools.sdk_root()
    if sdk and not (tools.env("ANDROID_HOME") or tools.env("ANDROID_SDK_ROOT")):
        env["ANDROID_HOME"] = sdk
    return env


def prepare_run(repo: Repository, project_id: str, tools: Toolbox | None = None) -> RunPrep:
    """Check that adb, Appium, the UiAutomator2 driver, a device and the app are in place; return the variables the tests need.

    ``problem`` explains in plain language what is missing (never an exception)."""
    tools = tools or default_tools()
    config = repo.get_mobile_config(project_id)
    report = check_environment(config, tools=tools)
    if not report.ok:
        return RunPrep(problem=" ".join(f"{c.message} {c.fix}".strip() for c in report.failures[:3]))
    try:
        serial = MobileService(repo, tools).resolve_serial(config, report.devices)
    except MobileError as exc:
        return RunPrep(problem=exc.user_message)
    return RunPrep(env=run_environment(config, serial, tools))
