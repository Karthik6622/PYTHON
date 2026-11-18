"""The mobile service: project configuration, environment checks, devices and app analysis (wired as ``svc.mobile``)."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from ats.config import get_settings
from ats.jobs import JobCancelled
from ats.logging_setup import get_logger
from ats.mobile import apk as apk_tools
from ats.mobile import settings
from ats.mobile.analysis import DriverFactory, Progress, create_driver, explore_app, friendly_error
from ats.mobile.appium_server import AppiumServer, free_port
from ats.mobile.devices import Device, devices_for
from ats.mobile.environment import EnvReport
from ats.mobile.models import MobileAnalysis, MobileConfig, MobileError
from ats.mobile.platforms import platform_for
from ats.mobile.tools import Toolbox, default_tools
from ats.progress import report
from ats.repository import Project, Repository

LOGGER = get_logger("mobile.service")


def mobile_dir(project_id: str) -> Path:
    return get_settings().projects_dir / project_id / "mobile"


class MobileService:
    def __init__(self, repo: Repository, tools: Toolbox | None = None) -> None:
        self.repo = repo
        self._tools = tools

    @property
    def tools(self) -> Toolbox:
        return self._tools or default_tools()

    # ------------------------------------------------------------------ configuration
    def config(self, project_id: str) -> MobileConfig:
        return self.repo.get_mobile_config(project_id)

    def analysis(self, project_id: str) -> MobileAnalysis | None:
        return self.repo.get_mobile_analysis(project_id)

    def screens_dir(self, project_id: str) -> Path:
        return mobile_dir(project_id) / "screens"

    def set_platform(self, project: Project, platform: str) -> MobileConfig:
        platform_for(platform)
        config = self.config(project.id).model_copy(update={"platform": platform})
        self.repo.save_mobile_config(project.id, config)
        return config

    def _app_changed(self, project: Project, before: MobileConfig, after: MobileConfig) -> None:
        """The analysed screens belong to one app: choosing another one discards them."""
        if (before.apk_path, before.package, before.app_source) != (after.apk_path, after.package, after.app_source):
            self.repo.save_mobile_analysis(project.id, None)

    def use_upload(self, project: Project, filename: str, data: bytes) -> tuple[MobileConfig, apk_tools.ApkInfo]:
        """Validate and keep an uploaded APK; its package and launch activity are read from the manifest when possible."""
        stored = apk_tools.store_upload(project.id, filename, data)
        info = apk_tools.read_apk_info(stored, self.tools)
        before = self.config(project.id)
        if before.app_source == "upload" and before.apk_path:
            apk_tools.remove_stored_apk(project.id, before.apk_path)
        after = before.model_copy(update={"app_source": "upload", "apk_path": str(stored), "apk_name": filename, "package": info.package, "activity": info.activity})
        self.repo.save_mobile_config(project.id, after)
        self._app_changed(project, before, after)
        self.repo.audit(project.id, "user", "mobile.apk_uploaded", "mobile", {"name": filename, "package": info.package, "size": len(data)})
        return after, info

    def use_local_path(self, project: Project, text: str) -> tuple[MobileConfig, apk_tools.ApkInfo]:
        path = apk_tools.check_local_path(text)
        info = apk_tools.read_apk_info(path, self.tools)
        before = self.config(project.id)
        if before.app_source == "upload" and before.apk_path:
            apk_tools.remove_stored_apk(project.id, before.apk_path)
        after = before.model_copy(update={"app_source": "path", "apk_path": str(path), "apk_name": path.name, "package": info.package, "activity": info.activity})
        self.repo.save_mobile_config(project.id, after)
        self._app_changed(project, before, after)
        self.repo.audit(project.id, "user", "mobile.apk_path_set", "mobile", {"name": path.name, "package": info.package})
        return after, info

    def use_installed(self, project: Project, package: str, activity: str = "") -> MobileConfig:
        package, activity = (package or "").strip(), (activity or "").strip()
        if not apk_tools.is_valid_package(package):
            raise MobileError("Enter a valid package name, for example com.example.app.")
        if activity and not apk_tools.is_valid_activity(activity):
            raise MobileError("The launch activity is not valid. Use a name like .MainActivity or com.example.app.MainActivity.")
        before = self.config(project.id)
        if before.app_source == "upload" and before.apk_path:
            apk_tools.remove_stored_apk(project.id, before.apk_path)
        after = before.model_copy(update={"app_source": "installed", "apk_path": "", "apk_name": "", "package": package, "activity": apk_tools.normalize_activity(activity, package)})
        self.repo.save_mobile_config(project.id, after)
        self._app_changed(project, before, after)
        return after

    def set_package(self, project: Project, package: str, activity: str = "") -> MobileConfig:
        """Package (and optional activity) of an APK whose manifest could not be read automatically."""
        package, activity = (package or "").strip(), (activity or "").strip()
        if not apk_tools.is_valid_package(package):
            raise MobileError("Enter a valid package name, for example com.example.app.")
        if activity and not apk_tools.is_valid_activity(activity):
            raise MobileError("The launch activity is not valid. Use a name like .MainActivity or com.example.app.MainActivity.")
        after = self.config(project.id).model_copy(update={"package": package, "activity": apk_tools.normalize_activity(activity, package)})
        self.repo.save_mobile_config(project.id, after)
        return after

    def select_run_on(self, project: Project, run_on: str, device: Device | None = None) -> MobileConfig:
        update = {"run_on": run_on, "device_serial": device.serial if device else "", "device_label": device.title if device else ""}
        before = self.config(project.id)
        if device is None and before.run_on == run_on:  # same kind, nothing picked: keep the earlier choice
            update = {"run_on": run_on}
        after = before.model_copy(update=update)
        self.repo.save_mobile_config(project.id, after)
        return after

    # ------------------------------------------------------------------ environment and devices
    def environment(self, project_id: str, **kwargs: bool) -> EnvReport:
        config = self.config(project_id)
        return platform_for(config.platform).check_environment(config, self.tools, **kwargs)

    def devices(self, run_on: str) -> list[Device]:
        """Devices of the selected kind that adb can see (Android is the only platform today)."""
        return devices_for(run_on, self.all_devices())

    def all_devices(self) -> list[Device]:
        return platform_for("android").devices(self.tools)

    def virtual_devices(self) -> list[str]:
        return platform_for("android").virtual_devices(self.tools)

    def resolve_serial(self, config: MobileConfig, devices: list[Device]) -> str:
        """The device to use: the chosen one, or the only ready one of the selected kind."""
        fitting = [d for d in devices_for(config.run_on, devices) if d.ready]
        if config.device_serial:
            if any(d.serial == config.device_serial for d in fitting):
                return config.device_serial
            raise MobileError("The selected device is no longer available. Press Refresh on the Mobile page and choose a device again.")
        if len(fitting) == 1:
            return fitting[0].serial
        raise MobileError("Choose the device to test on (Mobile page, Device).")

    # ------------------------------------------------------------------ analysis
    def analyze(
        self, project: Project, progress: Progress = None, check: Callable[[], None] | None = None, *, driver_factory: DriverFactory | None = None,
        server_factory: Callable[..., AppiumServer] | None = None, sleep: Callable[[float], None] = time.sleep, settle: float = 1.2,
    ) -> MobileAnalysis:  # fmt: skip
        """Open the app on the chosen device through Appium, capture its screens and store them. Every failure is a ``MobileError``."""
        config = self.config(project.id)
        platform = platform_for(config.platform)
        report(progress, "Checking the environment", 0.03)
        env = platform.check_environment(config, self.tools)
        if not env.ok:
            raise MobileError(" ".join(f"{c.message} {c.fix}".strip() for c in env.failures[:3]))
        serial = self.resolve_serial(config, env.devices)
        device = next((d for d in env.devices if d.serial == serial), None)
        config = self._complete_app(project, config, serial)
        folder = mobile_dir(project.id)
        folder.mkdir(parents=True, exist_ok=True)
        caps = platform.capabilities(config, serial=serial, app_path=config.apk_path if config.uses_apk else "", system_port=free_port())
        server = (server_factory or AppiumServer)(self.tools, folder / "appium.log")
        driver = None
        try:
            report(progress, "Starting Appium", 0.1)
            server.start()
            report(progress, "Opening the app on the device (the first start can take a minute)", 0.2, 0.36)
            driver = (driver_factory or create_driver)(server.url, caps)
            analysis = explore_app(
                driver, config, self.screens_dir(project.id), settings.max_screens(), progress, check, device.title if device else serial, sleep, settle
            )  # fmt: skip
        except (MobileError, JobCancelled):
            raise
        except Exception as exc:  # noqa: BLE001 - Appium/adb errors become one readable sentence
            LOGGER.warning("App analysis failed: %s", exc.__class__.__name__, exc_info=True)
            raise MobileError(friendly_error(exc)) from exc
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:  # noqa: BLE001
                    LOGGER.info("The Appium session was already closed")
            server.stop()
        report(progress, "Saving the analysed screens", 0.96)
        self.repo.save_mobile_analysis(project.id, analysis)
        if (analysis.package, analysis.activity) != (config.package, config.activity):
            self.repo.save_mobile_config(project.id, config.model_copy(update={"package": analysis.package or config.package, "activity": analysis.activity or config.activity}))
        self.repo.audit(project.id, "agent:mobile", "mobile.analyzed", "mobile", {"screens": len(analysis.screens), "elements": sum(len(s.elements) for s in analysis.screens), "skipped": len(analysis.skipped)})
        return analysis

    def _complete_app(self, project: Project, config: MobileConfig, serial: str) -> MobileConfig:
        """Fill in what is still unknown about the app (package from the APK, launch activity of an installed package)."""
        update: dict[str, str] = {}
        if config.uses_apk and not config.package and config.apk_path:
            info = apk_tools.read_apk_info(Path(config.apk_path), self.tools)
            update.update({"package": info.package, "activity": config.activity or info.activity})
        if config.app_source == "installed" and not config.activity:
            update["activity"] = apk_tools.resolve_installed_activity(self.tools, serial, config.package)
        update = {k: v for k, v in update.items() if v}
        if not update:
            return config
        config = config.model_copy(update=update)
        self.repo.save_mobile_config(project.id, config)
        return config
