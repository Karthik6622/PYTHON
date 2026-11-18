"""Framework adapter registry."""

from __future__ import annotations

from ats.generation.adapters.api_python import ApiPythonAdapter
from ats.generation.adapters.appium_python import AppiumPythonAdapter
from ats.generation.adapters.common import BROWSERS, FRAMEWORKS, FrameworkAdapter, RenderContext, ScriptCase, browsers_for, frameworks_for, is_api_framework, is_mobile_framework, layer_of
from ats.generation.adapters.playwright_js import PlaywrightJsAdapter
from ats.generation.adapters.playwright_python import PlaywrightPythonAdapter
from ats.generation.adapters.selenium_java import SeleniumJavaAdapter
from ats.generation.adapters.selenium_python import SeleniumPythonAdapter


def get_adapter(framework: str) -> FrameworkAdapter:
    if framework == "api_python":
        return ApiPythonAdapter()
    if framework == "appium_python":
        return AppiumPythonAdapter()
    if framework == "playwright_python":
        return PlaywrightPythonAdapter()
    if framework == "playwright_typescript":
        return PlaywrightJsAdapter(typescript=True)
    if framework == "playwright_javascript":
        return PlaywrightJsAdapter(typescript=False)
    if framework == "selenium_python":
        return SeleniumPythonAdapter()
    if framework == "selenium_java":
        return SeleniumJavaAdapter()
    raise ValueError(f"Unsupported framework: {framework}")


__all__ = ["BROWSERS", "FRAMEWORKS", "FrameworkAdapter", "RenderContext", "ScriptCase", "browsers_for", "frameworks_for", "get_adapter", "is_api_framework", "is_mobile_framework", "layer_of"]
