"""Mobile page: choose the platform, the app and the device, check the environment, analyse the app and look at the screens that were found.

Only the tester's own choices appear here. Appium settings (automation name, udid, ports, timeouts, reset behaviour) are built internally.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ats.mobile import apk as apk_tools
from ats.mobile.capabilities import ui_summary
from ats.mobile.devices import Device, devices_for
from ats.mobile.environment import FAIL, OK, EnvReport
from ats.mobile.models import APP_SOURCES, RUN_ON, MobileAnalysis, MobileScreen
from ats.mobile.platforms import PLATFORMS
from ats.services import Services
from ats.ui import jobs_ui, theme
from ats.ui.session import notify, require_project, safe, show_notices

KIND = "mobile_analysis"
BADGE = {OK: ":green-badge[OK]", FAIL: ":red-badge[Needs attention]"}


def _devices(svc: Services, refresh: bool = False) -> list[Device]:
    """Detected devices, remembered for this browser session so a rerun does not call adb again (Refresh does)."""
    if refresh or "mobile_devices" not in st.session_state:
        st.session_state["mobile_devices"] = svc.mobile.all_devices()
        st.session_state["mobile_avds"] = svc.mobile.virtual_devices()
    return st.session_state["mobile_devices"]


def show_report(report: EnvReport) -> None:
    for check in report.checks:
        with st.container(border=True):
            st.markdown(f"**{check.title}** {BADGE.get(check.status, ':orange-badge[Check]')}")
            st.write(check.message)
            if check.fix and check.status != OK:
                st.caption(f"How to fix: {check.fix}")
    if report.ok:
        st.success("The environment is ready for mobile testing.")
    else:
        st.error("Mobile testing is not possible yet. Fix the items marked 'Needs attention' and check again.")


def _platform_section(svc: Services, project, config):  # noqa: ANN001, ANN202
    keys = list(PLATFORMS)
    choice = st.selectbox("Mobile Platform *", keys, index=keys.index(config.platform) if config.platform in keys else 0, format_func=lambda k: PLATFORMS[k].label)
    st.caption("Android is supported today; iOS is planned.")
    if choice != config.platform:
        config = safe(lambda: svc.mobile.set_platform(project, choice), config)
    return config


def _app_section(svc: Services, project, config):  # noqa: ANN001, ANN202
    sources = list(APP_SOURCES)
    source = st.radio("Application Source *", sources, index=sources.index(config.app_source), format_func=APP_SOURCES.get, horizontal=True)
    saved = config.app_source == source and config.has_app
    upload = path = package = activity = None
    if source == "upload":
        upload = st.file_uploader("APK file *", type=["apk"], help="Kept in the studio's secure folder under a random name. It is never committed, zipped or shown in reports.")
        if saved and config.apk_name:
            st.caption(f"Current APK: {config.apk_name}")
    elif source == "path":
        path = st.text_input("APK path *", value=config.apk_path if config.app_source == "path" else "", placeholder=r"C:\builds\app-debug.apk")
        st.caption("The file stays where it is (it is not copied). The studio must run on the machine that has it.")
    else:
        package = st.text_input("Package name *", value=config.package if config.app_source == "installed" else "", placeholder="com.example.app")
        activity = st.text_input("Launch activity (only if it cannot be found automatically)", value=config.activity if config.app_source == "installed" else "", placeholder=".MainActivity")
    ready = bool(upload) if source == "upload" else bool((path or "").strip()) if source == "path" else bool((package or "").strip())
    if st.button("Save application", disabled=not ready):
        def save():  # noqa: ANN202
            if source == "upload":
                return svc.mobile.use_upload(project, upload.name, upload.getvalue())
            if source == "path":
                return svc.mobile.use_local_path(project, path)
            return svc.mobile.use_installed(project, package, activity), None

        outcome = safe(save)
        if outcome:
            new_config, info = outcome
            notify(f"Application saved: {new_config.package or new_config.apk_name}.")
            if info is not None and info.note:
                notify(info.note, "warning")
            st.rerun()
    if config.uses_apk and config.apk_path and not config.package:
        st.warning("The package name could not be read from the APK automatically. Enter it (and the launch activity if you know it).")
        package = st.text_input("Package name of this APK *", key="mobile_pkg_fix", placeholder="com.example.app")
        activity = st.text_input("Launch activity (optional)", key="mobile_act_fix", placeholder=".MainActivity")
        if st.button("Save package", disabled=not (package or "").strip()) and safe(lambda: svc.mobile.set_package(project, package, activity)):
            st.rerun()
    if config.has_app and apk_tools.is_valid_package(config.package):
        st.caption(f"Package: {config.package}" + (f" | Launch activity: {config.activity}" if config.activity else " | Launch activity: found automatically when the app starts"))
    return svc.mobile.config(project.id)


def _device_section(svc: Services, project, config):  # noqa: ANN001, ANN202
    kinds = list(RUN_ON)
    run_on = st.radio("Run On *", kinds, index=kinds.index(config.run_on), format_func=RUN_ON.get, horizontal=True)
    if run_on != config.run_on:
        config = safe(lambda: svc.mobile.select_run_on(project, run_on), config)
    left, right = st.columns([5, 1], vertical_alignment="bottom")
    refresh = right.button("Refresh", help="Look for emulators and devices again", width="stretch")
    devices = devices_for(run_on, _devices(svc, refresh))
    if devices:
        serials = [d.serial for d in devices]
        titles = {d.serial: d.picker_label() for d in devices}
        index = serials.index(config.device_serial) if config.device_serial in serials else None
        chosen = left.selectbox("Device *", serials, index=index, format_func=titles.get, placeholder="Choose a device")
        if chosen and chosen != config.device_serial:
            device = next(d for d in devices if d.serial == chosen)
            config = safe(lambda: svc.mobile.select_run_on(project, run_on, device), config)
        picked = next((d for d in devices if d.serial == config.device_serial), None)
        if picked is not None and not picked.ready:
            st.warning(f"{picked.title} is {picked.state}. " + ("Accept the USB debugging prompt on the device." if picked.state == "unauthorized" else "Reconnect it or restart the emulator."))
    else:
        left.selectbox("Device *", [], placeholder="No device detected", disabled=True)
        st.info("No Android device detected. Start an Android emulator or connect an Android device with USB debugging enabled.")
        avds = st.session_state.get("mobile_avds") or []
        if run_on == "emulator" and avds:
            st.caption("Installed emulators (not running): " + ", ".join(avds))
    if config.device_serial and config.device_serial not in [d.serial for d in devices]:
        st.caption("The device chosen earlier is not available right now.")
    return svc.mobile.config(project.id)


def _screens_section(svc: Services, project, analysis: MobileAnalysis) -> None:  # noqa: ANN001
    st.subheader("Analysed screens")
    total = sum(len(s.elements) for s in analysis.screens)
    st.caption(f"{len(analysis.screens)} screen(s) and {total} element(s) found in {analysis.package} on {analysis.device or 'the selected device'} ({analysis.analysed_at[:19].replace('T', ' ')}).")
    if analysis.skipped:
        st.caption("Not tapped because they look destructive: " + ", ".join(sorted(set(analysis.skipped))[:12]))
    for warning in analysis.warnings:
        st.warning(warning)
    folder = svc.mobile.screens_dir(project.id)
    for screen in analysis.screens:
        _screen_card(folder, screen)


def _screen_card(folder, screen: MobileScreen) -> None:  # noqa: ANN001
    with st.expander(f"{screen.title}  |  {screen.screen_key}  |  {len(screen.elements)} elements", expanded=not screen.reached_by):
        left, right = st.columns([1, 3])
        shot = folder / screen.screenshot if screen.screenshot else None
        if shot is not None and shot.is_file():
            left.image(str(shot), width="stretch")
        else:
            left.caption("No screenshot was captured.")
        right.caption(("Opened by: " + " > ".join(screen.reached_by)) if screen.reached_by else "Shown when the app starts.")
        rows = [
            {
                "Element": e.key.split(".", 1)[-1], "Role": e.role, "Name": e.name, "Best locator": e.preferred.display() if e.preferred else "",
                "Other locators": max(len(e.selectors) - 1, 0), "Clickable": e.clickable, "Enabled": e.enabled,
            }
            for e in screen.elements
        ]  # fmt: skip
        right.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=min(60 + 36 * len(rows), 360))


def render(svc: Services) -> None:
    project = require_project(svc)
    theme.page_header("Mobile", "Tell the studio which Android app to test and where. It opens the app on the device and learns its screens and elements.", "MOBILE // APP")
    show_notices()
    if "mobile" not in project.channels:
        st.info("This project's testing type does not include Mobile yet. You can still prepare the app here; add Mobile to the testing type on the Projects page to generate mobile tests.")
    if jobs_ui.running_panel(svc, project, (KIND,), "Analyzing the app"):
        return
    jobs_ui.last_problem(svc, project, (KIND,))

    config = svc.mobile.config(project.id)
    with st.container(border=True):
        config = _platform_section(svc, project, config)
    with st.container(border=True):
        config = _app_section(svc, project, config)
    with st.container(border=True):
        config = _device_section(svc, project, config)

    st.subheader("Environment")
    st.caption("Checks adb, the Android SDK, Appium, the UiAutomator2 driver, the Appium Python client, the device and the app.")
    if st.button("Check environment"):
        with st.spinner("Checking the environment..."):
            st.session_state["mobile_report"] = svc.mobile.environment(project.id)
    report = st.session_state.get("mobile_report")
    if report is not None:
        show_report(report)

    st.subheader("Analyze the app")
    st.caption("Opens the app, captures the screen (page source and screenshot) and safely taps a few tabs, menus and 'Next' buttons to find more screens. Delete, log out, pay, send, submit and reset controls are never tapped.")
    ready = config.has_app and bool(config.device_serial)
    if not ready:
        st.info("Save the application and choose a device first.")
    analysis = svc.mobile.analysis(project.id)
    if st.button("Analyze App" if analysis is None else "Analyze App again", type="primary", disabled=not ready):
        def work(ctx):  # noqa: ANN001, ANN202
            result = svc.mobile.analyze(project, progress=ctx.reporter, check=ctx.check)
            return {"screens": len(result.screens), "elements": sum(len(s.elements) for s in result.screens)}

        jobs_ui.start_job(svc, project, KIND, "Analyzing the mobile app", work, notice="App analysed: {screens} screen(s) and {elements} element(s) found.")
    if analysis is not None:
        with st.expander("Your selections", expanded=False):
            st.table(pd.DataFrame(list(ui_summary(config).items()), columns=["Setting", "Value"]))
        _screens_section(svc, project, analysis)
