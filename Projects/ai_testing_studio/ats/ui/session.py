"""Streamlit session helpers: browser-scoped owner id, shared services, selected project, safe calls."""

from __future__ import annotations

import re
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
def get_services() -> Services:
    return build_services()


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


def owner_id() -> str:
    """Identify this browser. Projects are visible only to the browser that created them."""
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
