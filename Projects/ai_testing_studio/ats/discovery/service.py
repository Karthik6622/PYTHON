"""Discovery orchestration: pre-flight check, isolated Playwright worker, locator repository, AI understanding."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ats.ai.agents import LocatorIntelligenceAgent, WebDiscoveryAgent
from ats.config import ROOT_DIR, get_settings
from ats.discovery.preflight import preflight
from ats.errors import DiscoveryError
from ats.locators.builder import build_locators
from ats.logging_setup import get_logger
from ats.models import DiscoveryResult, LocatorSpec, PageSnapshot
from ats.repository import Project, Repository
from ats.security import mask

LOGGER = get_logger("discovery")
Progress = Callable[[str], None]

INSTALL_HINT = "Install the browser tooling with: pip install playwright  and  python -m playwright install chromium"


def playwright_available() -> bool:
    return importlib.util.find_spec("playwright") is not None


def storage_state_path(file_name: str) -> Path | None:
    """Resolve a storage-state file inside the secure folder (file name only; no path traversal)."""
    if not file_name:
        return None
    path = get_settings().secure_dir / Path(file_name).name
    return path if path.is_file() else None


def run_worker(job: dict[str, Any], timeout: int, on_progress: Progress | None = None, cancel: threading.Event | None = None) -> dict[str, Any]:
    """Run ``ats.discovery.worker`` as a subprocess and return its JSON result. Raises ``DiscoveryError`` on failure."""
    if not playwright_available():
        raise DiscoveryError(f"Playwright is not installed. {INSTALL_HINT}")
    with tempfile.TemporaryDirectory(prefix="ats_job_") as tmp:
        job_file, out_file = Path(tmp) / "job.json", Path(tmp) / "out.json"
        job = {**job, "output": str(out_file)}
        job_file.write_text(json.dumps(job), encoding="utf-8")
        process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [sys.executable, "-m", "ats.discovery.worker", str(job_file)],
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        deadline = time.time() + timeout
        timer = threading.Timer(timeout, process.kill)
        timer.start()
        tail: list[str] = []
        try:
            assert process.stdout is not None
            for line in process.stdout:
                line = line.rstrip()
                if line.startswith("PROGRESS "):
                    try:
                        message = json.loads(line[9:]).get("message", "")
                    except ValueError:
                        message = ""
                    if message and on_progress:
                        on_progress(message)
                elif line:
                    tail.append(line)
                    tail = tail[-15:]
                if cancel is not None and cancel.is_set():
                    process.kill()
                    raise DiscoveryError("Discovery was cancelled.")
            process.wait()
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
        if time.time() > deadline and not out_file.exists():
            raise DiscoveryError("Discovery timed out. Reduce the page limit or depth and try again.")
        if not out_file.exists():
            LOGGER.error("Worker produced no output: %s", mask(" | ".join(tail)))
            raise DiscoveryError("The browser worker stopped unexpectedly. " + INSTALL_HINT)
        data = json.loads(out_file.read_text(encoding="utf-8"))
    if "error" in data:
        text = str(data["error"])
        if "Executable doesn't exist" in text or "playwright install" in text:
            raise DiscoveryError("The browser is not installed. " + INSTALL_HINT)
        raise DiscoveryError(f"Browser analysis failed: {mask(text)[:300]}")
    return data


def build_digest(result: DiscoveryResult, max_items: int = 40) -> list[dict[str, Any]]:
    """Compact per-page summary sent to the model (no raw DOM, no values)."""
    digest = []
    for page in result.pages:
        items = []
        for el in page.elements:
            if not el.get("visible"):
                continue
            label = el.get("name") or el.get("label") or el.get("placeholder") or el.get("text")
            if not label and not el.get("testid"):
                continue
            items.append(
                {k: v for k, v in {
                    "role": el.get("role") or el.get("tag"), "name": str(label or "")[:60], "type": el.get("type"),
                    "required": el.get("required") or None, "testid": el.get("testid") or None,
                    "options": el.get("options")[:8] or None,
                    "href": (el.get("href") or "")[:80] or None,
                }.items() if v}  # fmt: skip
            )
            if len(items) >= max_items:
                break
        digest.append(
            {
                "page_key": page.page_key, "url": page.final_url or page.url, "title": page.title, "headings": page.headings[:8],
                "elements": items, "forms": [{"fields": len(f.get("fields", [])), "submit": f.get("submit", ""), "method": f.get("method")} for f in page.forms],
                "tables": page.tables[:3], "components": page.components, "requires_auth": page.requires_auth,
                "api_calls": sorted({f"{n['method']} {n['url']}" for n in page.network})[:6],
                "console_errors": page.console_errors[:3],
            }
        )  # fmt: skip
    return digest


class DiscoveryService:
    def __init__(self, repo: Repository, discovery_agent: WebDiscoveryAgent | None = None, locator_agent: LocatorIntelligenceAgent | None = None) -> None:
        self.repo = repo
        self.discovery_agent = discovery_agent or WebDiscoveryAgent(repository=repo)
        self.locator_agent = locator_agent or LocatorIntelligenceAgent(repository=repo)

    # ------------------------------------------------------------------ main entry
    def run(self, project: Project, on_progress: Progress | None = None, cancel: threading.Event | None = None) -> DiscoveryResult:
        say = on_progress or (lambda _m: None)
        settings = get_settings()
        discovery_id = self.repo.start_discovery(project.id)
        try:
            say("Checking that the website is reachable")
            check = preflight(project.url, project.limits.ignore_https_errors)
            if not check.ok:
                raise DiscoveryError(check.message)
            out_dir = settings.projects_dir / project.id / "discovery"
            out_dir.mkdir(parents=True, exist_ok=True)
            job = {
                "mode": "discover", "start_url": check.final_url or project.url, "limits": project.limits.model_dump(),
                "output_dir": str(out_dir), "auth": project.auth.model_dump(), "include_screenshots": project.limits.include_screenshots,
                "ignore_https_errors": project.limits.ignore_https_errors, "allow_private": settings.allow_private_network,
                "browser": "chromium", "time_budget_seconds": max(settings.discovery_timeout_seconds - 30, 60),
                "storage_state": str(storage_state_path(project.auth.storage_state_file) or ""),
            }
            if project.url != job["start_url"]:
                job["limits"]["allowed_domains"] = [*job["limits"]["allowed_domains"], project.url]
            raw = run_worker(job, settings.discovery_timeout_seconds, say, cancel)
            result = DiscoveryResult(
                start_url=project.url,
                pages=[PageSnapshot.model_validate(p) for p in raw["pages"]],
                skipped=raw.get("skipped", []),
                warnings=[*check.warnings, *raw.get("warnings", [])],
            )
            if not result.pages:
                raise DiscoveryError("; ".join(result.warnings) or "No pages could be analysed.")
            say(f"Building the locator repository from {sum(len(p.elements) for p in result.pages)} elements")
            specs = build_locators(result)
            self._ai_understanding(project, result, say)
            specs = self._enrich(project, specs, say, result)
            self.repo.replace_locators(project.id, specs)
            self.repo.finish_discovery(discovery_id, "completed", result)
            self.repo.audit(project.id, "agent:web_discovery", "discovery.completed", "discovery", {"pages": len(result.pages), "locators": len(specs)})
            say("Discovery complete")
            return result
        except DiscoveryError as exc:
            self.repo.finish_discovery(discovery_id, "failed", None, exc.user_message)
            self.repo.audit(project.id, "system", "discovery.failed", "discovery", {"error": exc.user_message})
            raise
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Discovery crashed")
            self.repo.finish_discovery(discovery_id, "failed", None, "Unexpected error during discovery.")
            raise DiscoveryError(f"Unexpected error during discovery: {mask(str(exc))[:200]}") from exc

    # ------------------------------------------------------------------ AI helpers (best effort: discovery data stays valid without them)
    def _ai_understanding(self, project: Project, result: DiscoveryResult, say: Progress) -> None:
        if not get_settings().model.configured:
            result.warnings.append("The AI model is not configured, so the application summary was skipped.")
            return
        say("Asking the Web Discovery Agent to understand the application")
        try:
            screenshots = [Path(p.screenshot).read_bytes() for p in result.pages[:2] if p.screenshot and Path(p.screenshot).is_file()]
            analysis = self.discovery_agent.analyze(
                project.url, project.description, build_digest(result), screenshots, project_id=project.id
            )
            result.summary = analysis.summary
            result.analysis = analysis.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Discovery analysis skipped: %s", mask(str(exc)))
            result.warnings.append("The AI application summary could not be produced; discovery data is still complete.")

    def _enrich(self, project: Project, specs: list[LocatorSpec], say: Progress, result: DiscoveryResult) -> list[LocatorSpec]:
        if not specs or not get_settings().model.configured:
            return specs
        say("Locator Intelligence Agent is annotating elements")
        try:
            candidates = [
                {"element_key": s.element_key, "role": s.role, "name": s.name, "tag": s.tag, "page": s.page_key,
                 "preferred": s.preferred.display(), "landmark": s.component}
                for s in specs if s.stability < 0.9 or not s.name
            ][:80]  # fmt: skip
            if not candidates:
                return specs
            enriched = {e.element_key: e for e in self.locator_agent.enrich(candidates, project_id=project.id).elements}
            for spec in specs:
                item = enriched.get(spec.element_key)
                if item:
                    spec.intent = item.intent
                    if item.fragile:
                        spec.stability = min(spec.stability, 0.5)
                    if item.note:
                        spec.evidence["note"] = item.note
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Locator enrichment skipped: %s", mask(str(exc)))
            result.warnings.append("Locator annotation by AI was skipped.")
        return specs

    # ------------------------------------------------------------------ authentication helpers
    def capture_session(self, project: Project, login_url: str, name: str = "", timeout: int = 600) -> str:
        """Open a visible browser on this machine so the person can sign in; stores the Playwright storage state."""
        settings = get_settings()
        file_name = (name or f"{project.id}_state") + ".json"
        out = settings.secure_dir / Path(file_name).name
        data = run_worker({"mode": "capture_session", "login_url": login_url, "storage_state_out": str(out), "timeout_seconds": timeout}, timeout + 30)
        if not data.get("saved"):
            raise DiscoveryError("No session was captured. Sign in and keep the browser open until it closes itself or you close it.")
        self.repo.audit(project.id, "user", "auth.session_captured", "auth", {"file": out.name})
        return out.name

    @staticmethod
    def validate_selectors_live(url: str, selectors: list[dict[str, Any]], storage_state: str = "") -> list[dict[str, Any]]:
        data = run_worker({"mode": "validate_url", "url": url, "selectors": selectors, "storage_state": storage_state}, 120)
        return data["results"]
