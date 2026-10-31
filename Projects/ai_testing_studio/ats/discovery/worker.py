"""Playwright discovery worker. Runs in its own process so a crashing browser can never take the Streamlit app down.

Usage:  python -m ats.discovery.worker <job.json>

The job file selects a ``mode``:
  discover         crawl the application (bounded) and write a discovery result JSON
  extract_html     extract elements from an HTML file (used for offline analysis and tests)
  validate_html    check selectors against an HTML file
  analyze_html     extract elements from an HTML file and check selectors against it in one browser session
  validate_url     check selectors against a live URL
  capture_session  open a visible browser so a person can sign in, then save the Playwright storage state

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

EXTRACTOR_JS = (Path(__file__).with_name("extractor.js")).read_text(encoding="utf-8")
SKIP_EXTENSIONS = {
    ".pdf", ".zip", ".gz", ".tar", ".rar", ".7z", ".exe", ".dmg", ".msi", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".ico", ".mp3", ".mp4", ".avi", ".mov", ".webm", ".css", ".js", ".json", ".xml", ".doc", ".docx", ".xls", ".xlsx", ".ppt",
    ".pptx", ".csv", ".woff", ".woff2", ".ttf",
}
LOGIN_HINTS = ("login", "signin", "sign-in", "log-in", "auth", "sso")


def progress(message: str, **extra: Any) -> None:
    print("PROGRESS " + json.dumps({"message": message, **extra}), flush=True)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


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
    return kind.launch(headless=headless, args=["--disable-dev-shm-usage"] if browser_name == "chromium" else [])


# ------------------------------------------------------------------------------------------
# Authentication
# ------------------------------------------------------------------------------------------
LOGIN_OPENER = re.compile(r"^(get started|log ?in|sign ?in)\b", re.I)
LOGIN_SUBMIT = re.compile(r"^(log ?in|sign ?in|submit|continue|enter)$", re.I)
PASSWORD_FIELD = "input[type=password]:visible"


def reveal_login_form(page: Any) -> None:
    """Single-page apps often show a landing page first; open the sign-in form when no password field is visible yet."""
    if page.locator(PASSWORD_FIELD).count():
        return
    for role in ("button", "link"):
        opener = page.get_by_role(role, name=LOGIN_OPENER)
        if opener.count():
            opener.first.click()
            settle(page, max_ms=6000, quiet_ms=1000)
            if page.locator(PASSWORD_FIELD).count():
                return


def perform_login(page: Any, auth: dict[str, Any], start_url: str) -> tuple[str | None, bool]:
    """Sign in using credentials from environment variables.

    Returns ``(warning, signed_in)``: a warning when the sign-in cannot be confirmed, and whether the current page is the signed-in session.
    """
    username = os.environ.get(auth.get("username_env") or "", "")
    password = os.environ.get(auth.get("password_env") or "", "")
    if not username or not password:
        return "Credential environment variables are not set; discovery continued without signing in.", False
    try:
        open_page(page, auth.get("login_url") or start_url, [])
        if auth.get("username_selector") and auth.get("password_selector"):
            page.locator(auth["username_selector"]).first.fill(username)
            page.locator(auth["password_selector"]).first.fill(password)
            submit = auth.get("submit_selector")
        else:
            reveal_login_form(page)
            password_field = page.locator(PASSWORD_FIELD).first
            user_field = page.locator(
                "input[type=email]:visible, input[type=text]:visible, input:not([type]):visible"
            ).first
            user_field.fill(username)
            password_field.fill(password)
            submit = "button[type=submit], input[type=submit]"
        if submit and page.locator(submit).count():
            page.locator(submit).first.click()
        elif not auth.get("submit_selector") and page.get_by_role("button", name=LOGIN_SUBMIT).count():
            page.get_by_role("button", name=LOGIN_SUBMIT).first.click()
        else:
            page.keyboard.press("Enter")
        settle(page, max_ms=15000, quiet_ms=1500)
        needle = auth.get("success_url_contains") or ""
        if needle and needle not in page.url:
            return "Login could not be confirmed (success URL fragment not found); results may be limited to public pages.", False
        if page.locator(PASSWORD_FIELD).count():
            return "A password field is still visible after login; the sign-in may have failed (check the credentials).", False
    except Exception as exc:  # noqa: BLE001
        return f"Login workflow failed: {str(exc).splitlines()[0][:160]}", False
    return None, True


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


SIGNATURE_JS = (
    "() => (document.body ? document.body.innerText.length : 0) + ':' + "
    "document.querySelectorAll('input,button,a,select,textarea,[role],[data-testid]').length + ':' + "
    # Streamlit keeps the placeholder title until the script has run; treat that as 'still loading'.
    "(document.querySelector('[data-testid=stApp]') && document.title === 'Streamlit' ? 'loading' : 'ready')"
)
IFRAMES_JS = (
    "() => Array.from(document.querySelectorAll('iframe')).map((f) => { const r = f.getBoundingClientRect(); "
    "return { src: f.src || '', area: r.width * r.height }; }).concat([{ src: '', area: -(innerWidth * innerHeight) }])"
)
WAKE_BUTTON = re.compile(r"get this app back up", re.I)


def settle(page: Any, max_ms: int = 15000, quiet_ms: int = 2000) -> None:
    """Single-page apps keep rendering after the load event: wait until the page content stops changing."""
    waited, stable, last = 0, 0, ""
    while waited < max_ms:
        page.wait_for_timeout(500)
        waited += 500
        try:
            signature = page.evaluate(SIGNATURE_JS)
        except Exception:  # noqa: BLE001 - page is navigating
            stable = 0
            continue
        stable = stable + 500 if signature == last else 0
        last = signature
        if stable >= quiet_ms and signature.endswith(":ready"):
            return


def wake_sleeping_app(page: Any, warnings: list[str], max_ms: int = 90000) -> None:
    """Streamlit Community Cloud puts idle apps to sleep behind a button; wake the app and wait for it."""
    try:
        button = page.get_by_role("button", name=WAKE_BUTTON)
        if not button.count():
            return
        progress("The app is asleep; waking it up")
        button.first.click()
        waited = 0
        while waited < max_ms and page.get_by_role("button", name=WAKE_BUTTON).count():
            page.wait_for_timeout(1000)
            waited += 1000
        warnings.append("The application was asleep and was woken up for discovery.")
    except Exception:  # noqa: BLE001
        return


def embedded_app_url(page: Any, wait_s: int = 25) -> str | None:
    """URL of the real application when the page is only a shell around one full-size same-site iframe (e.g. Streamlit Cloud).

    Such shells keep the frame at zero size while the app boots, so wait for it to become visible.
    """
    candidate = None
    for tick in range(wait_s):
        try:
            frames = page.evaluate(IFRAMES_JS)
            plain_page = page.evaluate("document.querySelectorAll('iframe').length === 0 && document.body && document.body.innerText.length > 200")
        except Exception:  # noqa: BLE001
            return candidate
        if plain_page:
            return None
        view = -frames[-1]["area"] or 1
        for frame in frames[:-1]:
            src = frame["src"]
            if not (src.startswith("http") and _host(src) == _host(page.url) and urldefrag(src)[0] != urldefrag(page.url)[0]):
                continue
            candidate = src
            if frame["area"] > 0.5 * view:
                return src
        if candidate is None and tick >= 5:
            return None
        page.wait_for_timeout(1000)
    return candidate


def open_page(page: Any, url: str, warnings: list[str]) -> Any:
    """Navigate, wake sleeping apps, step into an embedded app frame and wait for the page to finish rendering."""
    response = page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=6000)
    except Exception:  # noqa: BLE001
        pass
    wake_sleeping_app(page, warnings)
    inner = embedded_app_url(page)
    if inner:
        note = f"The site embeds its application in a frame; the application URL ({inner}) was analysed directly."
        if note not in warnings:
            warnings.append(note)
        response = page.goto(inner, wait_until="domcontentloaded")
    settle(page)
    return response


def extract_page(page: Any) -> dict[str, Any]:
    data = page.evaluate(EXTRACTOR_JS)
    try:
        data["aria_snapshot"] = page.locator("body").aria_snapshot()[:6000]
    except Exception:  # noqa: BLE001
        data["aria_snapshot"] = ""
    return data


def discover(job: dict[str, Any]) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    start_url = job["start_url"]
    limits = job["limits"]
    out_dir = Path(job["output_dir"])
    shots = out_dir / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    allowed = {_host(start_url)} | {_host("//" + d) if "://" not in d else _host(d) for d in limits.get("allowed_domains", []) if d}
    excluded = [p.strip().lower() for p in limits.get("excluded_paths", []) if p.strip()]
    allow_private = bool(job.get("allow_private"))
    result: dict[str, Any] = {"start_url": start_url, "pages": [], "skipped": [], "warnings": []}

    def skip(url: str, reason: str) -> None:
        if len(result["skipped"]) < 100:
            result["skipped"].append({"url": url, "reason": reason})

    def permitted(url: str) -> str | None:
        host = _host(url)
        if host not in allowed:
            return "domain not allowed"
        path = urlparse(url).path.lower()
        if any(fragment in path or fragment in url.lower() for fragment in excluded):
            return "excluded path"
        if not allow_private and host != _host(start_url):
            from ats.security import is_private_address

            if is_private_address(host):
                return "private network address"
        return None

    with sync_playwright() as pw:
        browser = launch(pw, job.get("browser", "chromium"))
        context = new_context(browser, job)
        context.set_default_timeout(20000)
        page = context.new_page()
        console: list[str] = []
        network: list[dict[str, Any]] = []
        page.on("console", lambda m: console.append(f"{m.type}: {m.text[:200]}") if m.type in ("error", "warning") and "Unrecognized feature" not in m.text else None)
        page.on("pageerror", lambda e: console.append("pageerror: " + str(e)[:200]))
        page.on(
            "response",
            lambda r: network.append({"method": r.request.method, "url": r.url.split("?")[0][:200], "status": r.status})
            if r.request.resource_type in ("fetch", "xhr")
            else None,
        )
        auth = job.get("auth") or {}
        signed_in_page = False
        if auth.get("mode") in ("env_credentials", "login_workflow"):
            progress("Signing in with configured credentials")
            warning, signed_in_page = perform_login(page, auth, start_url)
            if warning:
                result["warnings"].append(warning)

        queue: deque[tuple[str, int]] = deque([(start_url, 0)])
        seen = {urldefrag(start_url)[0]}
        used_keys: set[str] = set()
        started = time.time()
        while queue and len(result["pages"]) < int(limits.get("max_pages", 8)):
            if time.time() - started > int(job.get("time_budget_seconds", 200)):
                result["warnings"].append("Discovery stopped at the time budget; increase the limit for deeper crawling.")
                break
            url, depth = queue.popleft()
            progress(f"Analysing {url}", pages=len(result["pages"]), depth=depth)
            console.clear()
            network.clear()
            try:
                if signed_in_page:
                    # Analyse the signed-in session as it is: reloading would drop sessions held in memory (single-page apps).
                    signed_in_page, response = False, None
                else:
                    response = open_page(page, url, result["warnings"])
                status = response.status if response else None
                data = extract_page(page)
            except Exception as exc:  # noqa: BLE001
                skip(url, "navigation failed: " + str(exc).splitlines()[0][:120])
                continue
            final_url = page.url
            seen.add(urldefrag(final_url)[0])
            key = slug(final_url, used_keys)
            snapshot: dict[str, Any] = {
                "page_key": key, "url": url, "final_url": final_url, "title": data["title"], "status": status, "depth": depth,
                "headings": data["headings"], "elements": data["elements"], "forms": data["forms"], "tables": data["tables"],
                "navigation": data["navigation"], "components": data["components"], "aria_snapshot": data["aria_snapshot"],
                "console_errors": console[:10], "network": network[:25], "links": [], "screenshot": "",
                "requires_auth": bool(status in (401, 403))
                or (data["has_password_field"] and len(data["elements"]) < 15 and any(h in final_url.lower() for h in LOGIN_HINTS)
                    and not any(h in start_url.lower() for h in LOGIN_HINTS)),
            }
            if job.get("include_screenshots", True):
                try:
                    shot = shots / f"{key}.png"
                    page.screenshot(path=str(shot), full_page=False)
                    snapshot["screenshot"] = str(shot)
                except Exception:  # noqa: BLE001
                    pass
            nav_links = [link["href"] for nav in data["navigation"] for link in nav["links"]]
            ordered = [urljoin(final_url, h) for h in nav_links] + data["links"]
            for href in ordered:
                link = normalise_link(href, final_url)
                if not link or link in seen:
                    continue
                reason = permitted(link)
                seen.add(link)
                if reason:
                    skip(link, reason)
                    continue
                snapshot["links"].append(link)
                if depth < int(limits.get("max_depth", 2)):
                    queue.append((link, depth + 1))
            snapshot["links"] = snapshot["links"][:100]
            result["pages"].append(snapshot)
        context.close()
        browser.close()
    if not result["pages"]:
        result["warnings"].append("No pages could be analysed. Check the URL, network access and authentication.")
    return result


def with_html_page(job: dict[str, Any], action: Any) -> Any:
    from playwright.sync_api import sync_playwright

    html = Path(job["html_file"]).read_text(encoding="utf-8")
    with sync_playwright() as pw:
        browser = launch(pw)
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
        browser = launch(pw, job.get("browser", "chromium"))
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
