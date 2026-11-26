"""Test session helper: opens the application, signs in, reaches views, finds elements robustly and records evidence."""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Page

from pages import Pages
from utils import nav
from utils.locators import load_locators, resolve

ROOT = Path(__file__).resolve().parent.parent
ENV_PATTERN = re.compile(r"\{\{env:([A-Za-z_][A-Za-z0-9_]*)\}\}")
FIND_TIMEOUT = float(os.environ.get("FIND_TIMEOUT", "20"))  # seconds an element may take to appear on a page that is still rendering
IDLE_GIVE_UP = float(os.environ.get("IDLE_GIVE_UP", "5"))  # seconds after which a missing element on an idle page counts as not found


def _describe(selector: dict) -> str:
    return f"{selector.get('kind')}={selector.get('value')!r}" + (f" name={selector['name']!r}" if selector.get("name") else "")


def _load(name: str) -> dict:
    path = ROOT / "config" / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


class App:
    def __init__(self, page: Page, base_url: str, test_case_id: str) -> None:
        self.page = page
        self.base_url = base_url.rstrip("/") + "/"
        self.test_case_id = test_case_id
        self.locators = load_locators()
        self.views = _load("views.json")
        self.auth = _load("auth.json")
        self.steps: list[dict] = []
        self.console: list[str] = []
        self.failure: dict = {}
        self.warnings: list[str] = []
        self.fallbacks: dict[str, dict] = {}  # element key -> selector that worked when the preferred one did not
        self.view = ""
        self.pages = Pages(self)
        page.set_default_timeout(FIND_TIMEOUT * 1000)
        page.on("console", lambda m: self.console.append(f"{m.type}: {m.text[:300]}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: self.console.append(f"pageerror: {str(e)[:300]}"))

    # ------------------------------------------------------------------ values
    def val(self, text: str) -> str:
        """Substitute {{env:NAME}} placeholders from the environment (values never appear in code or reports)."""

        def lookup(match: re.Match) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise AssertionError(f"Environment variable {name} is not set")
            return os.environ[name]

        return ENV_PATTERN.sub(lookup, text)

    # ------------------------------------------------------------------ navigation
    def start_url(self) -> str:
        """Where the application starts: the configured base address plus the path discovery started on."""
        path = urlparse(self.views.get("start_url") or "").path or "/"
        return urljoin(self.base_url, path.lstrip("/"))

    def goto(self, target: str) -> None:
        url = target if re.match(r"^https?://", target) else urljoin(self.base_url, target.lstrip("/"))
        nav.open_page(self.page, url, self.warnings)

    def sign_in(self) -> None:
        user, password = self.auth.get("username_env", ""), self.auth.get("password_env", "")
        if self.auth.get("mode") not in ("env_credentials", "login_workflow") or user not in os.environ or password not in os.environ:
            raise AssertionError(
                "This test needs a signed-in session: set the credential variables "
                f"{user or 'TEST_APP_USERNAME'} and {password or 'TEST_APP_PASSWORD'}"
            )
        problem = nav.sign_in(self.page, os.environ[user], os.environ[password], self.auth, self.start_url(), self.warnings)
        if problem:
            raise AssertionError(problem)

    def open_view(self, key: str, retry: bool = True) -> None:
        """Put a fresh browser on a discovered view: open (and sign in when needed), then repeat the recorded clicks.

        The arrival is confirmed by the view's headings; a replay that landed elsewhere (a click on a page that was still rendering)
        is repeated once from a fresh page, so a flaky replay is not reported as a failure of the test or of the application."""
        view = (self.views.get("views") or {}).get(key)
        if view is None:
            self.goto("/")
            return
        if view.get("signed_in"):
            self.sign_in()
        else:
            nav.open_page(self.page, self.start_url(), self.warnings)
        for step in view.get("steps", []):
            if not nav.click_control(self.page, step):
                raise AssertionError(f"Could not reach the '{view.get('name', key)}' view: the control '{step.get('label')}' was not found")
        if not self._arrived(view):
            if retry:
                self.open_view(key, retry=False)
                return
            self.warnings.append(f"The '{view.get('name', key)}' view could not be confirmed by its headings {view.get('headings')}.")
        self.view = key

    def _arrived(self, view: dict, wait_ms: int = 6000) -> bool:
        headings = view.get("headings") or []
        if not headings:
            return True
        waited = 0
        while waited <= wait_ms:
            for heading in headings:
                try:
                    if self.page.get_by_role("heading", name=heading, exact=True).count() or self.page.get_by_text(heading, exact=True).count():
                        return True
                except Exception:  # noqa: BLE001 - the page is re-rendering
                    pass
            self.page.wait_for_timeout(500)
            waited += 500
        return False

    def settle(self, max_ms: int = 4000) -> None:
        """Let the application finish re-rendering after an interaction (single-page apps update asynchronously)."""
        nav.settle(self.page, max_ms=max_ms, quiet_ms=600)

    @staticmethod
    def _forceable(locator) -> bool:
        """A click may be forced only on something a person could see or use: a visible element, or the hidden input behind a styled
        checkbox / radio. A hidden control (inside a collapsed section) is never clicked through the DOM."""
        try:
            return locator.is_visible() or bool(locator.evaluate("(e) => e.tagName === 'INPUT' && ['checkbox', 'radio'].includes((e.type || '').toLowerCase())"))
        except Exception:  # noqa: BLE001
            return False

    def click(self, locator, double: bool = False) -> None:
        """Click like a person would. Styled controls (hidden radio buttons, custom checkboxes) are covered by a label that
        receives the click, so when the element exists but is not 'actionable' the click is forced, then sent through the DOM."""
        action = locator.dblclick if double else locator.click
        try:
            action(timeout=6000)
        except Exception:
            if locator.count() != 1 or not self._forceable(locator):
                raise
            try:
                action(timeout=3000, force=True)
            except Exception:
                locator.evaluate("(element) => element.click()")
        self.settle()

    def check(self, locator, checked: bool = True) -> None:
        action = locator.check if checked else locator.uncheck
        try:
            action(timeout=6000)
        except Exception:
            if locator.count() != 1 or not self._forceable(locator):
                raise
            try:
                action(timeout=3000, force=True)
            except Exception:
                locator.evaluate("(element) => element.click()")
        self.settle()

    def select(self, locator, label: str) -> None:
        """Choose an option. A native <select> uses select_option; a custom dropdown (a combobox widget) is opened and its option clicked."""
        try:
            locator.select_option(label=label, timeout=6000)
        except Exception as exc:
            if "not a <select>" not in str(exc):
                raise
            self.click(locator)
            option = self.page.get_by_role("option", name=label, exact=True)
            if not option.count():
                option = self.page.get_by_role("option", name=label)
            option.locator("visible=true").first.click()
        self.settle()

    def _reveal(self, spec: dict, found) -> None:
        """Open the collapsed sections (expanders, accordions) that hold the element; discovery saw them open, a fresh page has them closed."""
        labels = spec.get("reveal") or []
        try:
            if not labels or found.count() != 1 or found.is_visible():
                return
        except Exception:  # noqa: BLE001
            return
        for label in labels:
            summary = self.page.locator("summary").filter(has_text=label).locator("visible=true")
            if summary.count():
                summary.first.click()
                self.page.wait_for_timeout(300)
        self.settle(2000)

    # ------------------------------------------------------------------ elements
    def _by_fingerprint(self, spec: dict) -> tuple[dict, object] | None:
        """Find the element by what a person sees (role and name, label, placeholder, text) when no recorded selector matches.
        Only a candidate that matches exactly one element is used."""
        fp = spec.get("fingerprint") or {}
        role, name = fp.get("role") or spec.get("role"), fp.get("name") or spec.get("name")
        candidates = []
        if role and name:
            candidates.append({"kind": "role", "value": role, "name": name, "exact": True})
        if fp.get("label"):
            candidates.append({"kind": "label", "value": fp["label"], "exact": True})
        if fp.get("placeholder"):
            candidates.append({"kind": "placeholder", "value": fp["placeholder"], "exact": True})
        for text in (fp.get("text"), name):
            if text and not (role and name):
                candidates.append({"kind": "text", "value": text, "exact": True})
        for selector in candidates:
            try:
                found = resolve(self.page, selector)
                if found.count() == 1:
                    return selector, found
            except Exception:  # noqa: BLE001
                continue
        return None

    def locator(self, key: str, wait: bool = True):
        """Resolve an element key to ONE element on screen (see ``_locate``) and open the collapsed section that holds it, if any."""
        found = self._locate(key, wait)
        spec = self.locators.get(key) or {}
        if wait:
            self._reveal(spec, found)
        return found

    def _locate(self, key: str, wait: bool = True):
        """Resolve an element key. The preferred selector is used first; if it matches nothing, the recorded alternatives are tried,
        then the element's fingerprint (role and name, label, text). Whatever worked instead of the preferred selector is remembered
        (reports/evidence/<id>/fallbacks.json) so auto-fix can update the locator file. Waiting stops early once the page is idle.
        When a selector matches several elements, the ones a person can see decide: one visible match is the element; several
        visible matches with the same role and name (a sidebar and a page button) resolve to the first of them, and say so."""
        spec = self.locators.get(key)
        if spec is None:
            raise AssertionError(f"Unknown element key: {key}")
        candidates = [spec["preferred"], *spec.get("alternatives", [])]
        started = time.monotonic()
        ambiguous = None
        while True:
            for index, selector in enumerate(candidates):
                try:
                    found = resolve(self.page, selector)
                    count = found.count()
                    if count > 1:
                        shown = found.locator("visible=true")
                        if shown.count() == 1:
                            found, count = shown, 1
                except Exception:  # noqa: BLE001 - a selector that cannot be evaluated is simply not a match
                    continue
                if count == 1:
                    if index:
                        self.fallbacks[key] = {"selector": selector, "preferred": candidates[0], "index": index}
                    return found
                if count > 1 and ambiguous is None:
                    ambiguous = (index, selector, found)
            elapsed = time.monotonic() - started
            if elapsed > 1.5 or not wait:
                by_fingerprint = self._by_fingerprint(spec)
                if by_fingerprint is not None:
                    selector, found = by_fingerprint
                    self.fallbacks[key] = {"selector": selector, "preferred": candidates[0], "index": len(candidates), "fingerprint": True}
                    return found
            if not wait or (ambiguous is not None and elapsed > 2) or elapsed > FIND_TIMEOUT:
                break
            if elapsed > IDLE_GIVE_UP and nav.is_idle(self.page):
                break  # the page has finished rendering and the element is not on it: waiting longer only wastes time
            self.page.wait_for_timeout(300)
        if ambiguous is not None:
            index, selector, found = ambiguous
            shown = found.locator("visible=true")
            if shown.count() > 1 and (selector.get("kind") == "role" and selector.get("name")):
                self.fallbacks[key] = {"selector": selector, "preferred": candidates[0], "index": index, "ambiguous": True}
                return shown.first  # the same control twice (for example in the sidebar and in the page): the first one on screen
            raise AssertionError(f"Ambiguous locator for '{key}': {_describe(selector)} matched multiple elements; no unique alternative.")
        if not wait:
            return resolve(self.page, spec["preferred"])
        tried = ", ".join(_describe(s) for s in candidates[:4])
        raise AssertionError(f"Element not found: '{key}' is not on the {self.view or 'current'} view after {time.monotonic() - started:.0f}s. Tried: {tried}")

    # ------------------------------------------------------------------ steps and evidence
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
        if self.fallbacks:
            (folder / "fallbacks.json").write_text(json.dumps(self.fallbacks, indent=2), encoding="utf-8")
        if not failed:
            return
        info = {"test_case_id": self.test_case_id, "console": self.console[-20:], "view": self.view, "warnings": self.warnings[-5:], **self.failure}
        try:
            info["url"] = self.page.url
            info["title"] = self.page.title()
            (folder / "dom.html").write_text(self.page.content()[:500_000], encoding="utf-8")
            self.page.screenshot(path=str(folder / "screenshot.png"))
        except Exception as exc:  # the page may already be closed; evidence is best effort
            info["evidence_error"] = str(exc)[:200]
        (folder / "failure.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
