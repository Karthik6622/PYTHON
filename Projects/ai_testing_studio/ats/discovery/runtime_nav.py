"""Browser navigation helpers shared by discovery and by the generated Playwright (Python) test projects.

This file has NO imports from the studio: it is copied verbatim into every generated project as ``utils/nav.py`` (together
with ``actions.js``), so the tests open the application, wake it, step into an embedded frame, sign in and replay the clicks
that lead to a view with exactly the code that discovered it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urlparse

ACTIONS_JS = (Path(__file__).with_name("actions.js")).read_text(encoding="utf-8")

LOGIN_OPENER = re.compile(r"^(get started|log ?in|sign ?in)\b", re.I)
LOGIN_SUBMIT = re.compile(r"^(log ?in|sign ?in|submit|continue|enter)$", re.I)
PASSWORD_FIELD = "input[type=password]:visible"
USER_FIELD = "input[type=email]:visible, input[type=text]:visible, input:not([type]):visible"
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


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


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
        button.first.click()
        waited = 0
        while waited < max_ms and page.get_by_role("button", name=WAKE_BUTTON).count():
            page.wait_for_timeout(1000)
            waited += 1000
        warnings.append("The application was asleep and was woken up.")
    except Exception:  # noqa: BLE001
        return


def embedded_app_url(page: Any, wait_s: int = 25) -> str | None:
    """URL of the real application when the page is only a shell around one full-size same-site iframe (e.g. Streamlit Cloud)."""
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
            if not (src.startswith("http") and host_of(src) == host_of(page.url) and urldefrag(src)[0] != urldefrag(page.url)[0]):
                continue
            candidate = src
            if frame["area"] > 0.5 * view:
                return src
        if candidate is None and tick >= 5:
            return None
        page.wait_for_timeout(1000)
    return candidate


def open_page(page: Any, url: str, warnings: list[str] | None = None) -> Any:
    """Navigate, wake sleeping apps, step into an embedded app frame and wait for the page to finish rendering."""
    warnings = warnings if warnings is not None else []
    response = page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=6000)
    except Exception:  # noqa: BLE001
        pass
    wake_sleeping_app(page, warnings)
    inner = embedded_app_url(page)
    if inner:
        note = f"The site embeds its application in a frame; the application URL ({inner}) was used directly."
        if note not in warnings:
            warnings.append(note)
        response = page.goto(inner, wait_until="domcontentloaded")
    settle(page)
    return response


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


def sign_in(page: Any, username: str, password: str, auth: dict[str, Any], start_url: str, warnings: list[str] | None = None) -> str | None:
    """Sign in with the configured account. Returns ``None`` on success, otherwise a short problem description."""
    try:
        open_page(page, auth.get("login_url") or start_url, warnings)
        if auth.get("username_selector") and auth.get("password_selector"):
            page.locator(auth["username_selector"]).first.fill(username)
            page.locator(auth["password_selector"]).first.fill(password)
            submit = auth.get("submit_selector")
        else:
            reveal_login_form(page)
            page.locator(USER_FIELD).first.fill(username)
            page.locator(PASSWORD_FIELD).first.fill(password)
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
            return "Login could not be confirmed (success URL fragment not found); results may be limited to public pages."
        if page.locator(PASSWORD_FIELD).count():
            return "A password field is still visible after login; the sign-in may have failed (check the credentials)."
    except Exception as exc:  # noqa: BLE001
        return f"Login workflow failed: {str(exc).splitlines()[0][:160]}"
    return None


def find_control(page: Any, step: dict[str, Any]) -> Any | None:
    """The control a recorded navigation step refers to (role, visible label, occurrence), or ``None``."""
    handle = page.evaluate_handle(ACTIONS_JS, {"find": {"role": step["role"], "label": step["label"], "nth": step.get("nth", 0)}})
    return handle.as_element()


def click_control(page: Any, step: dict[str, Any]) -> bool:
    """Perform one recorded navigation step. Returns ``False`` when the control is not on the page."""
    if step.get("role") == "url":
        open_page(page, step["href"])
        return True
    element = find_control(page, step)
    if element is None:
        return False
    try:
        element.click(timeout=5000)
    except Exception:  # noqa: BLE001 - covered by an overlay, or a visually hidden (styled) radio
        try:
            element.click(timeout=3000, force=True)
        except Exception:  # noqa: BLE001
            element.evaluate("(e) => e.click()")
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception:  # noqa: BLE001
        pass
    settle(page, max_ms=12000, quiet_ms=1200)
    return True
