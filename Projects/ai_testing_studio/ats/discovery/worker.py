"""Playwright discovery worker. Runs in its own process so a crashing browser can never take the Streamlit app down.

Usage:  python -m ats.discovery.worker <job.json>

The job file selects a ``mode``:
  discover         crawl the application (bounded) and write a discovery result JSON
  extract_html     extract elements from an HTML file (used for offline analysis and tests)
  validate_html    check selectors against an HTML file
  analyze_html     extract elements from an HTML file and check selectors against it in one browser session
  validate_url     check selectors against a live URL
  capture_session  open a visible browser so a person can sign in, then save the Playwright storage state
  relocate         open given views like the generated tests do and record their live elements (locator repair after a run)

Progress lines are printed as ``PROGRESS {json}``; the final result is written to ``job["output"]``.
Only light-weight modules are imported here (no Streamlit).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

from ats.discovery.runtime_nav import (  # noqa: E402 - shared with the generated test projects
    ACTIONS_JS, LOGIN_OPENER, LOGIN_SUBMIT, PASSWORD_FIELD, click_control, host_of as _host, open_page, settle, sign_in,
)

EXTRACTOR_JS = (Path(__file__).with_name("extractor.js")).read_text(encoding="utf-8")
SKIP_EXTENSIONS = {
    ".pdf", ".zip", ".gz", ".tar", ".rar", ".7z", ".exe", ".dmg", ".msi", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".ico", ".mp3", ".mp4", ".avi", ".mov", ".webm", ".css", ".js", ".json", ".xml", ".doc", ".docx", ".xls", ".xlsx", ".ppt",
    ".pptx", ".csv", ".woff", ".woff2", ".ttf",
}
LOGIN_HINTS = ("login", "signin", "sign-in", "log-in", "auth", "sso")


def progress(message: str, **extra: Any) -> None:
    print("PROGRESS " + json.dumps({"message": message, **extra}), flush=True)


def slug(url: str, used: set[str]) -> str:
    parsed = urlparse(url)
    path = re.sub(r"\.(html?|php|aspx?|jsp)$", "", parsed.path.strip("/").lower())
    base = re.sub(r"[^a-z0-9]+", "_", path or "home").strip("_") or "home"
    if parsed.query:
        base += "_q"
    key, n = base[:48], 2
    while key in used:
        key = f"{base[:44]}_{n}"
        n += 1
    used.add(key)
    return key


def normalise_link(href: str, base: str) -> str | None:
    if not href or href.startswith(("mailto:", "tel:", "javascript:", "data:", "blob:", "sms:")):
        return None
    absolute, _ = urldefrag(urljoin(base, href))
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return None
    if Path(parsed.path).suffix.lower() in SKIP_EXTENSIONS:
        return None
    return absolute


# ------------------------------------------------------------------------------------------
# Selector resolution (mirrors the adapters that render generated automation code)
# ------------------------------------------------------------------------------------------
def resolve(page: Any, selector: dict[str, Any]) -> Any:
    kind, value, name = selector["kind"], selector["value"], selector.get("name")
    exact = bool(selector.get("exact"))
    if kind == "testid":
        return page.get_by_test_id(value)
    if kind == "role":
        return page.get_by_role(value, name=name, exact=exact) if name else page.get_by_role(value)
    if kind == "label":
        return page.get_by_label(value, exact=exact)
    if kind == "placeholder":
        return page.get_by_placeholder(value, exact=exact)
    if kind == "text":
        return page.get_by_text(value, exact=exact)
    if kind == "id":
        return page.locator('[id="' + value.replace('"', '\\"') + '"]')
    if kind == "name":
        return page.locator('[name="' + value.replace('"', '\\"') + '"]')
    if kind == "xpath":
        return page.locator("xpath=" + value)
    return page.locator(value)


def validate_selectors(page: Any, selectors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for selector in selectors:
        entry: dict[str, Any] = {"selector": selector, "count": 0, "visible": 0, "error": ""}
        try:
            locator = resolve(page, selector)
            entry["count"] = locator.count()
            if entry["count"]:
                entry["visible"] = sum(1 for i in range(min(entry["count"], 5)) if locator.nth(i).is_visible())
        except Exception as exc:  # noqa: BLE001
            entry["error"] = str(exc).splitlines()[0][:200]
        results.append(entry)
    return results


def launch(playwright: Any, browser_name: str = "chromium", headless: bool = True) -> Any:
    kind = getattr(playwright, browser_name)
    if browser_name == "chromium":
        return kind.launch(
            headless=headless,
            args=[
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-breakpad",
                "--disable-component-extensions-with-background-pages",
                "--disable-ipc-flooding-protection",
                "--disable-renderer-backgrounding",
                "--enable-features=NetworkService,NetworkServiceInProcess",
                "--force-color-profile=srgb",
                "--metrics-recording-only",
                "--use-mock-keychain",
            ]
        )
    return kind.launch(headless=headless)


# ------------------------------------------------------------------------------------------
# Authentication
# ------------------------------------------------------------------------------------------
def perform_login(page: Any, auth: dict[str, Any], start_url: str) -> tuple[str | None, bool]:
    """Sign in using credentials from environment variables.

    Returns ``(warning, signed_in)``: a warning when the sign-in cannot be confirmed, and whether the current page is the signed-in session.
    """
    username = os.environ.get(auth.get("username_env") or "", "")
    password = os.environ.get(auth.get("password_env") or "", "")
    if not username or not password:
        return "Credential environment variables are not set; discovery continued without signing in.", False
    problem = sign_in(page, username, password, auth, start_url)
    return problem, problem is None


# ------------------------------------------------------------------------------------------
# Modes
# ------------------------------------------------------------------------------------------
def new_context(browser: Any, job: dict[str, Any]) -> Any:
    options: dict[str, Any] = {
        "viewport": {"width": 1366, "height": 900},
        "ignore_https_errors": bool(job.get("ignore_https_errors")),
        "locale": "en-US",
    }
    state = job.get("storage_state")
    if state and Path(state).is_file():
        options["storage_state"] = state
    return browser.new_context(**options)


def extract_page(page: Any) -> dict[str, Any]:
    data = page.evaluate(EXTRACTOR_JS)
    try:
        data["aria_snapshot"] = page.locator("body").aria_snapshot()[:6000]
    except Exception:  # noqa: BLE001
        data["aria_snapshot"] = ""
    return data


VERIFY_LIMIT = 260


def verify_elements(page: Any, elements: list[dict[str, Any]]) -> None:
    """Count, on the live page, how many elements each candidate selector matches (stored in ``element["checks"]``).

    A selector that matches exactly one element is safe to use in generated tests; the locator builder ranks by this.
    """
    from ats.locators.builder import build_selectors

    done = 0
    for element in elements:
        if done >= VERIFY_LIMIT:
            break
        if not element.get("visible"):
            continue
        try:
            selectors, _ = build_selectors(element)
        except Exception:  # noqa: BLE001
            continue
        done += 1
        checks: list[dict[str, Any]] = []
        unique = 0
        for selector in selectors[:6]:
            spec = selector.model_dump(exclude_none=True)
            try:
                count = resolve(page, spec).count()
            except Exception:  # noqa: BLE001
                count = -1
            checks.append({**spec, "count": count})
            unique += count == 1
            if unique >= 2:  # the preferred selector and one verified alternative are enough
                break
        element["checks"] = checks


VIEW_SIGNATURE_JS = r"""() => {
  document.querySelectorAll('details:not([open])').forEach((d) => { d.open = true; });
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  const heads = Array.from(document.querySelectorAll('h1,h2,h3,[role=heading]')).filter(vis).slice(0, 6)
    .map((h) => norm(h.textContent).replace(/\d+/g, '#').slice(0, 60));
  const fields = Array.from(document.querySelectorAll('input:not([type=hidden]):not([type=radio]):not([type=checkbox]),select,textarea'))
    .filter(vis).map((e) => (e.type || e.tagName) + ':' + norm(e.getAttribute('aria-label') || e.name || e.placeholder || '')).sort();
  const tabs = Array.from(document.querySelectorAll('[role=tab][aria-selected=true]')).map((t) => norm(t.textContent));
  const dialogs = document.querySelectorAll('[role=dialog],dialog[open]').length;
  return location.pathname + location.search + location.hash + '|' + heads.join('/') + '|' + fields.join(',') + '|' + tabs.join(',') + '|' + dialogs;
}"""
# Labels of controls that change data, leave the application or end the session: never clicked while exploring.
UNSAFE_ACTION = re.compile(
    r"\b(log ?out|sign ?out|log ?off|delete|remove|erase|clear|reset|discard|destroy|deactivate|unsubscribe|cancel|pay|buy|purchase|"
    r"checkout|order|send|submit|save|apply|confirm|upload|attach|download|export|import|print|share|deploy|stop|retry|regenerate|"
    r"refresh|reload|record|mic|microphone|speak|play|copy|fork|manage app|report|continue with|sign ?in with|log ?in with|google|"
    r"github|microsoft|apple|facebook|linkedin|twitter)\b",
    re.I,
)
CREATES_DATA = re.compile(r"^(new|add|\+)(\b|$)", re.I)
ROLE_ORDER = {"radio": 0, "tab": 0, "menuitem": 0, "menuitemradio": 0, "treeitem": 0, "link": 1, "button": 2, "url": 3}
MAX_ACTIONS_PER_VIEW = 24


def describe(action: dict[str, Any]) -> str:
    role, label = action["role"], action["label"]
    if role == "url":
        return f"Open {action['href']}"
    if role == "radio":
        return f"Select '{label}' in the navigation"
    if role == "tab":
        return f"Open the '{label}' tab"
    if role == "link":
        return f"Click the '{label}' link"
    if role.startswith("menuitem"):
        return f"Choose '{label}' in the menu"
    return f"Click the '{label}' button"


def label_slug(text: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:44] or "view"
    key, n = base, 2
    while key in used:
        key = f"{base}_{n}"
        n += 1
    used.add(key)
    return key


def view_signature(page: Any) -> str:
    """Identity of the view on screen, independent of how it was reached (single-page apps keep one URL for many views)."""
    try:
        return page.evaluate(VIEW_SIGNATURE_JS)
    except Exception:  # noqa: BLE001 - page is navigating
        page.wait_for_timeout(800)
        return page.evaluate(VIEW_SIGNATURE_JS)


class Crawl:
    """Explores an application the way a tester does: open it, then click through its navigation, tabs and view-changing
    buttons inside the live session. Every distinct view is recorded with the steps that reach it, so views that share
    one URL (Streamlit and other single-page apps keep sign-in state in memory) are discovered without reloading."""

    def __init__(self, job: dict[str, Any], result: dict[str, Any]) -> None:
        self.job, self.result = job, result
        self.start_url = job["start_url"]
        limits = job["limits"]
        self.max_pages = int(limits.get("max_pages", 8))
        self.max_depth = int(limits.get("max_depth", 2))
        self.allowed = {_host(self.start_url)} | {_host("//" + d) if "://" not in d else _host(d) for d in limits.get("allowed_domains", []) if d}
        self.excluded = [p.strip().lower() for p in limits.get("excluded_paths", []) if p.strip()]
        self.allow_private = bool(job.get("allow_private"))
        self.shots = Path(job["output_dir"]) / "screenshots"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.signatures: set[str] = set()
        self.captured_urls: set[str] = set()
        self.seen_urls: set[str] = set()
        self.used_keys: set[str] = set()
        self.console: list[str] = []
        self.network: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ helpers
    def skip(self, url: str, reason: str) -> None:
        if len(self.result["skipped"]) < 100 and not any(s["url"] == url for s in self.result["skipped"]):
            self.result["skipped"].append({"url": url, "reason": reason})

    def permitted(self, url: str) -> str | None:
        host = _host(url)
        if host not in self.allowed:
            return "domain not allowed"
        path = urlparse(url).path.lower()
        if any(fragment in path or fragment in url.lower() for fragment in self.excluded):
            return "excluded path"
        if not self.allow_private and host != _host(self.start_url):
            from ats.security import is_private_address

            if is_private_address(host):
                return "private network address"
        return None

    def full(self) -> bool:
        return len(self.result["pages"]) >= self.max_pages

    def watch(self, page: Any) -> None:
        page.on("console", lambda m: self.console.append(f"{m.type}: {m.text[:200]}") if m.type in ("error", "warning") and "Unrecognized feature" not in m.text else None)
        page.on("pageerror", lambda e: self.console.append("pageerror: " + str(e)[:200]))
        page.on(
            "response",
            lambda r: self.network.append({"method": r.request.method, "url": r.url.split("?")[0][:200], "status": r.status})
            if r.request.resource_type in ("fetch", "xhr")
            else None,
        )
        page.on("popup", lambda p: p.close())
        page.on("dialog", lambda d: d.dismiss())

    def actions(self, page: Any, data: dict[str, Any] | None) -> list[dict[str, Any]]:
        """View-changing controls on the current view, safest and most navigational first."""
        try:
            found = page.evaluate(ACTIONS_JS, None)
        except Exception:  # noqa: BLE001
            return []
        password_visible = bool(page.locator(PASSWORD_FIELD).count())
        chosen: list[dict[str, Any]] = []
        for action in found:
            label = action["label"]
            if UNSAFE_ACTION.search(label) or CREATES_DATA.search(label):
                continue
            if password_visible and LOGIN_SUBMIT.match(label):
                continue  # pressing sign-in with empty fields only counts failed attempts
            if action["href"]:
                link = normalise_link(action["href"], page.url)
                reason = self.permitted(link) if link else "not a page"
                if reason:
                    self.skip(action["href"], reason)
                    continue
                if urldefrag(link)[0] == urldefrag(page.url)[0] and not urlparse(link).fragment:
                    continue
                action["href"] = link
            chosen.append(action)
        clickable = {a["href"] for a in chosen if a["href"]}
        for href in (data or {}).get("links", []):  # links that exist but are not visible (collapsed menus)
            link = normalise_link(href, page.url)
            if not link or link in clickable or urldefrag(link)[0] == urldefrag(page.url)[0]:
                continue
            reason = self.permitted(link)
            if reason:
                self.skip(link, reason)
                continue
            clickable.add(link)
            chosen.append({"role": "url", "label": link, "nth": 0, "href": link, "region": "url"})
        chosen.sort(key=lambda a: (ROLE_ORDER.get(a["role"], 2), a["region"] == "main"))
        return chosen[: MAX_ACTIONS_PER_VIEW + 40]

    def perform(self, page: Any, action: dict[str, Any]) -> bool:
        """Carry out one exploration step. Returns False when the control is no longer there."""
        if action["role"] == "url":
            try:
                open_page(page, action["href"], self.result["warnings"])
                return True
            except Exception:  # noqa: BLE001
                return False
        try:
            handle = page.evaluate_handle(ACTIONS_JS, {"find": {"role": action["role"], "label": action["label"], "nth": action["nth"]}})
            element = handle.as_element()
            if element is None:
                return False
            try:
                element.click(timeout=5000)
            except Exception:  # noqa: BLE001 - covered by an overlay or visually hidden (styled radios)
                try:
                    element.click(timeout=3000, force=True)
                except Exception:  # noqa: BLE001
                    element.evaluate("(e) => e.click()")
        except Exception:  # noqa: BLE001
            return False
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:  # noqa: BLE001
            pass
        settle(page, max_ms=12000, quiet_ms=1200)
        return True

    def capture(self, page: Any, path: list[dict[str, Any]], signed_in: bool, status: int | None = None) -> dict[str, Any] | None:
        data = extract_page(page)
        try:
            verify_elements(page, data["elements"])
        except Exception:  # noqa: BLE001 - verification only improves the ranking; discovery must not fail because of it
            pass
        final_url = page.url
        base = urldefrag(final_url)[0]
        headings = [h.split(": ", 1)[-1] for h in data["headings"] if h.split(": ", 1)[-1]]
        label = path[-1]["label"] if path and path[-1]["role"] != "url" else ""
        heading = headings[0] if headings and len(headings[0]) <= 40 else ""
        view_name = heading or label or data["title"]
        if base not in self.captured_urls:
            key = slug(final_url, self.used_keys)
        elif not path:
            key = label_slug("landing" if not signed_in else "home", self.used_keys)  # start view of the second (signed-out) pass
            view_name = f"{view_name} (signed out)" if not signed_in else view_name
        else:
            key = label_slug(label or view_name, self.used_keys)
        self.captured_urls.add(base)
        self.seen_urls.add(base)
        snapshot: dict[str, Any] = {
            "page_key": key, "url": path[-1]["href"] if path and path[-1]["href"] else final_url, "final_url": final_url,
            "title": data["title"], "status": status, "depth": len(path), "view_name": view_name[:80], "signed_in": signed_in,
            "reached_by": (["Sign in with the test account"] if signed_in and self.job.get("auth", {}).get("mode") in ("env_credentials", "login_workflow") else [])
            + [describe(a) for a in path],
            "nav_steps": [{"role": a["role"], "label": a["label"], "nth": a["nth"], "href": a["href"]} for a in path],
            "headings": data["headings"], "elements": data["elements"], "forms": data["forms"], "tables": data["tables"],
            "navigation": data["navigation"], "components": data["components"], "aria_snapshot": data["aria_snapshot"],
            "console_errors": self.console[:10], "network": self.network[:25], "links": [], "screenshot": "",
            "requires_auth": bool(status in (401, 403))
            or (data["has_password_field"] and len(data["elements"]) < 15 and any(h in final_url.lower() for h in LOGIN_HINTS)
                and not any(h in self.start_url.lower() for h in LOGIN_HINTS)),
        }  # fmt: skip
        if self.job.get("include_screenshots", True):
            try:
                shot = self.shots / f"{key}.png"
                page.screenshot(path=str(shot), full_page=False)
                snapshot["screenshot"] = str(shot)
            except Exception:  # noqa: BLE001
                pass
        links = [normalise_link(h, final_url) for h in data["links"]]
        snapshot["links"] = [link for link in dict.fromkeys(links) if link and not self.permitted(link)][:100]
        self.result["pages"].append(snapshot)
        return data

    # ------------------------------------------------------------------ exploration
    def explore(self, page: Any, signed_in: bool, reset: Any, deadline: float, page_limit: int, status: int | None = None) -> None:
        """Breadth-first exploration of the views reachable from the current one by clicking."""
        root_sig = view_signature(page)
        if root_sig in self.signatures:
            return
        self.signatures.add(root_sig)
        root_password = bool(page.locator(PASSWORD_FIELD).count())
        data = self.capture(page, [], signed_in, status)
        frontier: deque[tuple[list[dict[str, Any]], str, str]] = deque()
        queued: set[Any] = set()

        def enqueue(path: list[dict[str, Any]], parent_sig: str, view_data: dict[str, Any] | None) -> None:
            if len(path) >= self.max_depth:
                return
            added = 0
            for action in self.actions(page, view_data):
                if action["href"]:
                    key: Any = ("href", urldefrag(action["href"])[0])
                    if key[1] in self.seen_urls:
                        continue
                elif action["region"] != "main":
                    key = (action["role"], action["label"].lower())  # sidebar / menu items are the same from every view
                else:
                    key = (parent_sig, action["role"], action["label"].lower(), action["nth"])
                if key in queued:
                    continue
                if action["role"] == "url" and signed_in and not self.job.get("_reload_keeps_session"):
                    continue  # opening a URL would drop a sign-in held in memory; such links are visited in the public pass
                queued.add(key)
                frontier.append(([*path, action], parent_sig, page.url))
                added += 1
                if added >= MAX_ACTIONS_PER_VIEW:
                    break

        enqueue([], root_sig, data)
        while frontier and len(self.result["pages"]) < page_limit and not self.full():
            if time.time() > deadline:
                self.result["warnings"].append("Discovery stopped at the time budget; increase DISCOVERY_TIMEOUT_SECONDS or reduce the depth for a complete map.")
                break
            path, parent_sig, parent_url = frontier.popleft()
            action = path[-1]
            progress(f"Exploring: {' > '.join(a['label'][:30] for a in path)}", pages=len(self.result["pages"]), depth=len(path))
            if action["href"]:
                self.seen_urls.add(urldefrag(action["href"])[0])
            if not self.reach(page, path, parent_sig, parent_url, reset):
                continue
            if _host(page.url) not in self.allowed:
                self.skip(page.url, "left the application")
                continue
            if signed_in and not root_password and page.locator(PASSWORD_FIELD).count():
                continue  # the session ended (a sign-out control); the next step starts again from a fresh sign-in
            self.console.clear()
            self.network.clear()
            settle(page, max_ms=4000, quiet_ms=800)
            sig = view_signature(page)
            if sig in self.signatures:
                continue
            self.signatures.add(sig)
            data = self.capture(page, path, signed_in)
            enqueue(path, sig, data)

    def reach(self, page: Any, path: list[dict[str, Any]], parent_sig: str, parent_url: str, reset: Any) -> bool:
        """Bring the browser to ``path``: click from the current view when possible, otherwise start over and replay."""
        last = path[-1]
        if last["role"] != "url":
            current = view_signature(page)
            if current != parent_sig and last["region"] == "main" and page.url != parent_url:
                try:
                    page.go_back(wait_until="domcontentloaded", timeout=10000)
                    settle(page, max_ms=8000, quiet_ms=1000)
                    current = view_signature(page)
                except Exception:  # noqa: BLE001
                    pass
            if (current == parent_sig or last["region"] != "main") and self.perform(page, last):
                return True
        else:
            return self.perform(page, last)  # a URL opens the same view from anywhere
        try:
            if not reset():
                return False
        except Exception:  # noqa: BLE001
            return False
        return all(self.perform(page, step) for step in path)


def discover(job: dict[str, Any]) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    start_url = job["start_url"]
    result: dict[str, Any] = {"start_url": start_url, "pages": [], "skipped": [], "warnings": []}
    crawl = Crawl(job, result)
    started = time.time()
    budget = int(job.get("time_budget_seconds", 200))
    auth = job.get("auth") or {}
    uses_login = auth.get("mode") in ("env_credentials", "login_workflow")

    with sync_playwright() as pw:
        browser = launch(pw, job.get("browser", "chromium"), headless=job.get("headless", True))

        def fresh(with_state: bool = True) -> tuple[Any, Any]:
            context = new_context(browser, job if with_state else {**job, "storage_state": ""})
            context.set_default_timeout(20000)
            page = context.new_page()
            crawl.watch(page)
            return context, page

        if uses_login:
            # 1) Signed-in pass: sign in once and click through the application inside that session.
            context, page = fresh()
            progress("Signing in with configured credentials")
            warning, signed_in = perform_login(page, auth, start_url)
            if warning:
                result["warnings"].append(warning)
            if signed_in:
                root_url = page.url
                reserve = min(4, crawl.max_pages // 3) if crawl.max_pages > 3 else 0

                def sign_in_again() -> bool:
                    if job.get("_reload_keeps_session") is not False:
                        open_page(page, root_url, result["warnings"])
                        keeps = not page.locator(PASSWORD_FIELD).count() and not page.get_by_role("button", name=LOGIN_OPENER).count()
                        job["_reload_keeps_session"] = keeps
                        if keeps:
                            return True
                    progress("Signing in again to continue exploring")
                    return perform_login(page, auth, start_url)[1]

                crawl.explore(page, True, sign_in_again, started + budget * 0.75, crawl.max_pages - reserve)
            context.close()
            # 2) Public pass in a fresh session: welcome, sign-in, sign-up and password-reset views.
            if not crawl.full() and time.time() < started + budget:
                progress("Exploring the public (signed-out) views")
                context, page = fresh(with_state=False)
                try:
                    response = open_page(page, start_url, result["warnings"])
                    crawl.explore(page, False, lambda: bool(open_page(page, start_url, result["warnings"]) or True), started + budget, crawl.max_pages,
                                  response.status if response else None)  # fmt: skip
                except Exception as exc:  # noqa: BLE001
                    crawl.skip(start_url, "navigation failed: " + str(exc).splitlines()[0][:120])
                context.close()
        else:
            context, page = fresh()
            signed = bool(job.get("storage_state") and Path(job["storage_state"]).is_file())
            job["_reload_keeps_session"] = True
            try:
                response = open_page(page, start_url, result["warnings"])
                crawl.explore(page, signed, lambda: bool(open_page(page, start_url, result["warnings"]) or True), started + budget, crawl.max_pages,
                              response.status if response else None)  # fmt: skip
            except Exception as exc:  # noqa: BLE001
                crawl.skip(start_url, "navigation failed: " + str(exc).splitlines()[0][:120])
            context.close()
        browser.close()
    if not result["pages"]:
        result["warnings"].append("No pages could be analysed. Check the URL, network access and authentication.")
    return result


def with_html_page(job: dict[str, Any], action: Any) -> Any:
    from playwright.sync_api import sync_playwright

    html = Path(job["html_file"]).read_text(encoding="utf-8")
    with sync_playwright() as pw:
        browser = launch(pw, headless=job.get("headless", True))
        context = browser.new_context()
        context.route("**/*", lambda route: route.abort() if not route.request.url.startswith(("data:", "about:")) else route.continue_())
        page = context.new_page()
        page.set_content(html, wait_until="domcontentloaded")
        try:
            return action(page)
        finally:
            browser.close()


def validate_url(job: dict[str, Any]) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = launch(pw, job.get("browser", "chromium"), headless=job.get("headless", True))
        context = new_context(browser, job)
        page = context.new_page()
        page.goto(job["url"], wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:  # noqa: BLE001
            pass
        results = validate_selectors(page, job["selectors"])
        browser.close()
    return {"results": results}


def relocate(job: dict[str, Any]) -> dict[str, Any]:
    """Open every requested view the way the generated tests do (sign in, replay the recorded clicks) and record its live elements,
    with how many elements each candidate selector matches, plus the match counts of the selectors the tests currently use.

    Used to repair locators after a run: the element is looked for on the real page, not in a snapshot taken at the moment of failure."""
    from playwright.sync_api import sync_playwright

    start_url, auth = job["start_url"], job.get("auth") or {}
    out: dict[str, Any] = {"views": {}}
    with sync_playwright() as pw:
        browser = launch(pw, job.get("browser", "chromium"), headless=job.get("headless", True))
        for view_key, view in job["views"].items():
            progress(f"Opening the '{view.get('name') or view_key}' view")
            entry: dict[str, Any] = {"reached": False, "error": "", "elements": [], "selector_counts": {}}
            context = new_context(browser, job)
            context.set_default_timeout(15000)
            page = context.new_page()
            try:
                if view.get("signed_in"):
                    warning, signed_in = perform_login(page, auth, start_url)
                    if not signed_in:
                        raise RuntimeError(warning or "the sign-in did not succeed")
                else:
                    open_page(page, start_url)
                for step in view.get("steps", []):
                    if not click_control(page, step):
                        raise RuntimeError(f"the control '{step.get('label')}' that opens this view was not found")
                settle(page, max_ms=8000, quiet_ms=1000)
                data = extract_page(page)
                elements = [e for e in data.get("elements", []) if e.get("visible")]
                verify_elements(page, elements)
                entry["elements"] = elements
                for key, selectors in (view.get("targets") or {}).items():
                    counts = []
                    for selector in selectors:
                        try:
                            counts.append(resolve(page, selector).count())
                        except Exception:  # noqa: BLE001
                            counts.append(-1)
                    entry["selector_counts"][key] = counts
                entry["reached"] = True
            except Exception as exc:  # noqa: BLE001 - reported per view; the other views are still checked
                entry["error"] = str(exc).splitlines()[0][:300] if str(exc) else type(exc).__name__
            finally:
                context.close()
            out["views"][view_key] = entry
        browser.close()
    return out


def capture_session(job: dict[str, Any]) -> dict[str, Any]:
    """Visible browser: the person signs in manually, then closes the window. Passwords never reach this application."""
    from playwright.sync_api import sync_playwright

    target = Path(job["storage_state_out"])
    target.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + int(job.get("timeout_seconds", 600))
    saved = False
    with sync_playwright() as pw:
        browser = launch(pw, job.get("browser", "chromium"), headless=False)
        context = browser.new_context(viewport=None)
        page = context.new_page()
        page.goto(job["login_url"], wait_until="domcontentloaded")
        progress("Browser opened. Sign in, then close the browser window.")
        while time.time() < deadline and browser.is_connected():
            try:
                if context.pages:
                    context.storage_state(path=str(target))
                    saved = True
            except Exception:  # noqa: BLE001
                break
            time.sleep(1.5)
        try:
            browser.close()
        except Exception:  # noqa: BLE001
            pass
    return {"saved": saved, "path": str(target)}


def main(argv: list[str]) -> int:
    job = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    mode = job["mode"]
    try:
        if mode == "discover":
            payload = discover(job)
        elif mode == "extract_html":
            payload = with_html_page(job, extract_page)
        elif mode == "validate_html":
            payload = {"results": with_html_page(job, lambda page: validate_selectors(page, job["selectors"]))}
        elif mode == "analyze_html":
            payload = with_html_page(job, lambda page: {"page": extract_page(page), "results": validate_selectors(page, job.get("selectors", []))})
        elif mode == "validate_url":
            payload = validate_url(job)
        elif mode == "capture_session":
            payload = capture_session(job)
        elif mode == "relocate":
            payload = relocate(job)
        else:
            raise ValueError(f"Unknown mode {mode!r}")
        Path(job["output"]).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return 0
    except Exception as exc:  # noqa: BLE001
        Path(job["output"]).write_text(json.dumps({"error": f"{type(exc).__name__}: {exc}"[:800]}), encoding="utf-8")
        print("ERROR " + str(exc)[:500], flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
