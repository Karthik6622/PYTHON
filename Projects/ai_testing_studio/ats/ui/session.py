"""Streamlit session helpers: account-scoped owner id, shared services, selected project, safe calls."""

from __future__ import annotations

import re
import sys
import threading
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

import streamlit as st

from ats.errors import NotFoundError, StudioError
from ats.logging_setup import get_logger
from ats.repository import Project
from ats.security import mask
from ats.services import Services, build_services

LOGGER = get_logger("ui")
COOKIE_NAME = "ats_owner"
OWNER_PATTERN = re.compile(r"^[a-f0-9]{32}$")
T = TypeVar("T")


@st.cache_resource(show_spinner=False)
def _holder() -> dict[str, Any]:
    """Process-wide slot for the services. Kept apart from ``get_services`` so it outlives code reloads (keep this function unchanged)."""
    return {"lock": threading.Lock()}


def _code_snapshot() -> dict[str, int]:
    return {name: id(module) for name, module in list(sys.modules.items()) if name == "ats" or name.startswith("ats.")}


def get_services() -> Services:
    """The shared services, rebuilt when the studio's code was reloaded.

    Streamlit (and Streamlit Cloud after a git push) reloads changed modules inside the running server. Services built from the
    old modules would then hand old-class objects to new code ("Input should be a valid dictionary or instance of Selector",
    "object has no attribute ..."). So the services are rebuilt as soon as any module they were built from is no longer the
    loaded one; running jobs and in-memory tokens are carried over."""
    holder = _holder()
    with holder["lock"]:
        services, snapshot = holder.get("services"), holder.get("snapshot") or {}
        stale = services is None or any(sys.modules.get(name) is None or id(sys.modules[name]) != ident for name, ident in snapshot.items())
        if stale:
            if services is not None:
                LOGGER.info("The studio's code changed: rebuilding the services")
            services = build_services(keep=services)
            holder["services"], holder["snapshot"] = services, _code_snapshot()
        return services


def _set_cookie(value: str) -> None:
    """Persist the owner id in the browser (one year). The id is random and only separates one browser's data from another's."""
    html = (
        "<script>try{var d=window.parent.document;"
        f"d.cookie='{COOKIE_NAME}={value}; max-age=31536000; path=/; SameSite=Lax';"
        "}catch(e){}</script>"
    )
    try:
        st.iframe(html, height=1)
    except Exception:  # noqa: BLE001 - older Streamlit
        import streamlit.components.v1 as components

        components.html(html, height=0)


def browser_owner_ids() -> list[str]:
    """Anonymous ids this browser used before accounts existed (cookie and current session). Their projects move to the account."""
    found: list[str] = []
    try:
        found.append(st.context.cookies.get(COOKIE_NAME))
    except Exception:  # noqa: BLE001 - cookies are unavailable outside a real browser session
        pass
    found.append(st.session_state.get("owner_id"))
    return [v for i, v in enumerate(found) if isinstance(v, str) and OWNER_PATTERN.match(v) and v not in found[:i]]


def owner_id() -> str:
    """The id that owns the visitor's projects: the signed-in account's id.

    Without a signed-in account (isolated tests, ``AppTest`` pages) it falls back to a random per-browser id, so pages
    stay usable; the app shell never reaches the pages in that state because ``require_login`` stops first.
    """
    user = st.session_state.get("auth_user")
    if isinstance(user, dict) and user.get("id"):
        return str(user["id"])
    existing = st.session_state.get("owner_id")
    if isinstance(existing, str) and OWNER_PATTERN.match(existing):
        return existing
    try:
        cookie = st.context.cookies.get(COOKIE_NAME)
    except Exception:  # noqa: BLE001
        cookie = None
    if isinstance(cookie, str) and OWNER_PATTERN.match(cookie):
        st.session_state["owner_id"] = cookie
        return cookie
    new = uuid.uuid4().hex
    st.session_state["owner_id"] = new
    st.session_state["owner_cookie_pending"] = True
    return new


def flush_cookie() -> None:
    if st.session_state.pop("owner_cookie_pending", False):
        _set_cookie(st.session_state["owner_id"])


def current_project(svc: Services) -> Project | None:
    project_id = st.session_state.get("project_id")
    if not project_id:
        return None
    try:
        return svc.repo.get_project(project_id, owner_id())
    except NotFoundError:
        st.session_state.pop("project_id", None)
        return None


def require_project(svc: Services) -> Project:
    project = current_project(svc)
    if project is None:
        st.info("Create or open a project on the **Projects** page first.")
        st.stop()
    return project


def select_project(project_id: str) -> None:
    st.session_state["project_id"] = project_id


def register_pages(pages: list[Any]) -> None:
    """Remember the ``st.Page`` objects of this run so any page can navigate by URL path (``st.switch_page`` needs the object)."""
    st.session_state["_pages"] = {page.url_path: page for page in pages}


def go_to(url_path: str) -> None:
    """Jump to another page of the app. Does nothing outside a multipage run (e.g. in isolated tests).

    A page that is not in this run's navigation (hidden for the open project, or only visible once the project's settings
    change) is remembered and opened on the next run if it exists by then; otherwise it is dropped."""
    pages = st.session_state.get("_pages")
    if pages is None:
        return
    page = pages.get(url_path)
    if page is not None:
        st.switch_page(page)
    else:
        st.session_state["_pending_goto"] = url_path


def resume_pending_navigation() -> None:
    """Call right after ``st.navigation``: open the page ``go_to`` could not reach in the previous run."""
    pending = st.session_state.pop("_pending_goto", None)
    page = st.session_state.get("_pages", {}).get(pending) if pending else None
    if page is not None:
        st.switch_page(page)


def notify(message: str, kind: str = "success") -> None:
    """Queue a message to show after the next rerun (useful before ``st.rerun``)."""
    st.session_state.setdefault("_notices", []).append((kind, message))


def show_notices() -> None:
    for kind, message in st.session_state.pop("_notices", []):
        {"success": st.success, "error": st.error, "warning": st.warning, "info": st.info}.get(kind, st.info)(message)


def safe(action: Callable[[], T], default: Any = None) -> T | Any:
    """Run an action; studio errors are shown as plain messages and everything else is logged without details."""
    try:
        return action()
    except StudioError as exc:
        st.error(exc.user_message)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Unexpected UI error")
        st.error(f"Something went wrong: {mask(str(exc))[:200]}")
    return default
