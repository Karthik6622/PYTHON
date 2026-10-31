"""Discovery of single-page shells: embedded app frames, late rendering, container noise, automatic browser install."""

from __future__ import annotations

import pytest

from ats.discovery import service as discovery_service
from ats.discovery.service import BrowserMissingError, DiscoveryService
from ats.errors import DiscoveryError


@pytest.fixture()
def no_ai(monkeypatch):
    monkeypatch.setattr(DiscoveryService, "_ai_understanding", lambda *_a, **_k: None)
    monkeypatch.setattr(DiscoveryService, "_enrich", lambda _self, _project, specs, _say, _result: specs)


def test_embedded_app_frame_is_unwrapped_and_cleaned(repo, site_url, browser_ready, no_ai):
    if not browser_ready:
        pytest.skip("Chromium is not installed")
    project = repo.create_project("owner", name="Shell", url=f"{site_url}/shell.html", base_url=site_url)
    result = DiscoveryService(repo).run(project)
    page = result.pages[0]
    assert page.final_url.endswith("/shell_app.html")
    assert any("embeds its application in a frame" in w for w in result.warnings)
    names = {(e.get("name") or "") for e in page.elements}
    assert {"Your name", "Say hello", "Late button"} <= names  # late render was waited for
    assert not any(e.get("testid") in {"appRoot", "mainBlock"} for e in page.elements)  # layout wrappers are not controls


SPA_USER = "tester" + "@example.com"


def _spa_project(repo, site_url):
    from ats.models import AuthConfig

    auth = AuthConfig(mode="env_credentials", username_env="ATS_TEST_SPA_USER", password_env="ATS_TEST_SPA_PASS")
    return repo.create_project("owner", name="Spa", url=f"{site_url}/spa_shell.html", base_url=site_url, auth=auth)


def test_sign_in_through_landing_button_in_embedded_app(repo, site_url, browser_ready, no_ai, monkeypatch):
    if not browser_ready:
        pytest.skip("Chromium is not installed")
    monkeypatch.setenv("ATS_TEST_SPA_USER", SPA_USER)
    monkeypatch.setenv("ATS_TEST_SPA_PASS", "correct-horse")
    result = DiscoveryService(repo).run(_spa_project(repo, site_url))
    page = result.pages[0]
    names = {(e.get("name") or "") for e in page.elements if e.get("visible")}
    assert {"New conversation", "Log out", "Search notes"} <= names  # the signed-in dashboard was analysed
    assert "Dashboard" in " ".join(page.headings)
    assert not any("sign-in may have failed" in w or "Login workflow failed" in w for w in result.warnings)


def test_wrong_password_is_reported(repo, site_url, browser_ready, no_ai, monkeypatch):
    if not browser_ready:
        pytest.skip("Chromium is not installed")
    monkeypatch.setenv("ATS_TEST_SPA_USER", SPA_USER)
    monkeypatch.setenv("ATS_TEST_SPA_PASS", "wrong")
    result = DiscoveryService(repo).run(_spa_project(repo, site_url))
    assert any("sign-in may have failed" in w for w in result.warnings)


def test_missing_browser_is_installed_once_then_retried(monkeypatch):
    calls = {"run": 0, "install": 0}

    def fake_once(*_a, **_k):
        calls["run"] += 1
        if calls["run"] == 1:
            raise BrowserMissingError("missing")
        return {"ok": True}

    monkeypatch.setattr(discovery_service, "_run_worker_once", fake_once)
    monkeypatch.setattr(discovery_service, "install_browser", lambda *_a, **_k: calls.__setitem__("install", calls["install"] + 1))
    assert discovery_service.run_worker({}, 5) == {"ok": True}
    assert calls == {"run": 2, "install": 1}


def test_missing_browser_after_install_gives_clear_message(monkeypatch):
    def always_missing(*_a, **_k):
        raise BrowserMissingError("missing")

    monkeypatch.setattr(discovery_service, "_run_worker_once", always_missing)
    monkeypatch.setattr(discovery_service, "install_browser", lambda *_a, **_k: None)
    with pytest.raises(DiscoveryError, match="not installed"):
        discovery_service.run_worker({}, 5)
