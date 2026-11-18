"""The platform abstraction. Android is the only implementation today; iOS becomes a second class registered in ``PLATFORMS``
(XCUITest capabilities, simulators/real devices instead of adb, ``.app``/``.ipa`` instead of ``.apk``) without touching the rest of the studio."""

from __future__ import annotations

from typing import Any

from ats.mobile import capabilities
from ats.mobile.devices import Device, list_avds, list_devices
from ats.mobile.environment import EnvReport, check_environment
from ats.mobile.models import MobileConfig, MobileError
from ats.mobile.tools import Toolbox


class MobilePlatform:
    key = ""
    label = ""
    app_extensions: tuple[str, ...] = ()
    config_file = ""  # where the generated project keeps the non-secret capabilities

    def capabilities(self, config: MobileConfig, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    def bundle_capabilities(self, config: MobileConfig) -> dict[str, Any]:
        raise NotImplementedError

    def check_environment(self, config: MobileConfig, tools: Toolbox | None = None, **kwargs: Any) -> EnvReport:
        raise NotImplementedError

    def devices(self, tools: Toolbox | None = None) -> list[Device]:
        raise NotImplementedError

    def virtual_devices(self, tools: Toolbox | None = None) -> list[str]:
        return []


class AndroidPlatform(MobilePlatform):
    key = "android"
    label = "Android"
    app_extensions = (".apk",)
    config_file = "mobile_config/android.json"

    def capabilities(self, config: MobileConfig, **kwargs: Any) -> dict[str, Any]:
        return capabilities.android_capabilities(config, **kwargs)

    def bundle_capabilities(self, config: MobileConfig) -> dict[str, Any]:
        return capabilities.bundle_capabilities(config)

    def check_environment(self, config: MobileConfig, tools: Toolbox | None = None, **kwargs: Any) -> EnvReport:
        return check_environment(config, tools=tools, **kwargs)

    def devices(self, tools: Toolbox | None = None) -> list[Device]:
        return list_devices(tools)

    def virtual_devices(self, tools: Toolbox | None = None) -> list[str]:
        return list_avds(tools)


PLATFORMS: dict[str, MobilePlatform] = {"android": AndroidPlatform()}


def platform_for(key: str) -> MobilePlatform:
    try:
        return PLATFORMS[key or "android"]
    except KeyError:
        raise MobileError("This mobile platform is not supported yet. Android is available today.") from None
