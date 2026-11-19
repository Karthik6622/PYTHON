"""Test session helper: waits, step recording and failure evidence."""

from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urljoin

from selenium.webdriver.support.ui import WebDriverWait

from pages import Pages
from utils.locators import by_for, load_locators

ROOT = Path(__file__).resolve().parent.parent
ENV_PATTERN = re.compile(r"\{\{env:([A-Za-z_][A-Za-z0-9_]*)\}\}")


class App:
    def __init__(self, driver, base_url: str, test_case_id: str) -> None:
        self.driver = driver
        self.base_url = base_url.rstrip("/") + "/"
        self.test_case_id = test_case_id
        self.timeout = float(os.environ.get("STEP_TIMEOUT", "10"))
        self.locators = load_locators()
        self.steps: list[dict] = []
        self.failure: dict = {}
        self.pages = Pages(self)

    def val(self, text: str) -> str:
        """Substitute {{env:NAME}} placeholders from the environment (values never appear in code or reports)."""

        def lookup(match: re.Match) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise AssertionError(f"Environment variable {name} is not set")
            return os.environ[name]

        return ENV_PATTERN.sub(lookup, text)

    def by(self, key: str) -> tuple[str, str]:
        spec = self.locators.get(key)
        if spec is None:
            raise AssertionError(f"Unknown element key: {key}")
        return by_for(spec)

    def goto(self, target: str) -> None:
        url = target if re.match(r"^https?://", target) else urljoin(self.base_url, target.lstrip("/"))
        self.driver.get(url)

    def expect_url_contains(self, text: str) -> None:
        WebDriverWait(self.driver, self.timeout).until(lambda d: text in d.current_url, f"URL does not contain {text!r}")

    def expect_title_contains(self, text: str) -> None:
        WebDriverWait(self.driver, self.timeout).until(lambda d: text in d.title, f"Title does not contain {text!r}")

    @contextmanager
    def step(self, description: str, action: str = "", element: str = ""):
        record = {"index": len(self.steps) + 1, "description": description, "action": action, "element": element, "status": "running"}
        self.steps.append(record)
        try:
            yield
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = (getattr(exc, "msg", None) or str(exc))[:1500]
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
        info = {"test_case_id": self.test_case_id, **self.failure}
        try:
            info["url"] = self.driver.current_url
            info["title"] = self.driver.title
            (folder / "dom.html").write_text(self.driver.page_source[:500_000], encoding="utf-8")
            self.driver.save_screenshot(str(folder / "screenshot.png"))
            try:
                info["console"] = [f"{e['level']}: {e['message'][:300]}" for e in self.driver.get_log("browser")][-20:]
            except Exception:
                info["console"] = []
        except Exception as exc:
            info["evidence_error"] = str(exc)[:200]
        (folder / "failure.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
