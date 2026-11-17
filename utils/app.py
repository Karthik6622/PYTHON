"""Test session helper: element lookup, step recording and failure evidence."""

from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import Page

from pages import Pages
from utils.locators import load_locators, resolve

ROOT = Path(__file__).resolve().parent.parent
ENV_PATTERN = re.compile(r"\{\{env:([A-Za-z_][A-Za-z0-9_]*)\}\}")


class App:
    def __init__(self, page: Page, base_url: str, test_case_id: str) -> None:
        self.page = page
        self.base_url = base_url.rstrip("/") + "/"
        self.test_case_id = test_case_id
        self.locators = load_locators()
        self.steps: list[dict] = []
        self.console: list[str] = []
        self.failure: dict = {}
        self.pages = Pages(self)
        page.on("console", lambda m: self.console.append(f"{m.type}: {m.text[:300]}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: self.console.append(f"pageerror: {str(e)[:300]}"))

    def val(self, text: str) -> str:
        """Substitute {{env:NAME}} placeholders from the environment (values never appear in code or reports)."""

        def lookup(match: re.Match) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise AssertionError(f"Environment variable {name} is not set")
            return os.environ[name]

        return ENV_PATTERN.sub(lookup, text)

    def locator(self, key: str):
        spec = self.locators.get(key)
        if spec is None:
            raise AssertionError(f"Unknown element key: {key}")
        return resolve(self.page, spec["preferred"])

    def goto(self, target: str) -> None:
        url = target if re.match(r"^https?://", target) else urljoin(self.base_url, target.lstrip("/"))
        self.page.goto(url, wait_until="domcontentloaded")

    @contextmanager
    def step(self, description: str, action: str = "", element: str = ""):
        record = {"index": len(self.steps) + 1, "description": description, "action": action, "element": element, "status": "running"}
        self.steps.append(record)
        try:
            yield
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)[:1500]
            self.failure = {"step": record["index"], "action": action, "element": element, "error": record["error"]}
            raise
        else:
            record["status"] = "passed"

    def finish(self, failed: bool) -> None:
        folder = ROOT / "reports" / "evidence" / self.test_case_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "steps.json").write_text(json.dumps(self.steps, indent=2), encoding="utf-8")
        if not failed:
            return
        info = {"test_case_id": self.test_case_id, "console": self.console[-20:], **self.failure}
        try:
            info["url"] = self.page.url
            info["title"] = self.page.title()
            (folder / "dom.html").write_text(self.page.content()[:500_000], encoding="utf-8")
            self.page.screenshot(path=str(folder / "screenshot.png"))
        except Exception as exc:  # the page may already be closed; evidence is best effort
            info["evidence_error"] = str(exc)[:200]
        (folder / "failure.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
