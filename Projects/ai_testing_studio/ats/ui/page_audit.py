"""Status page: model routing, system check (browser, execution mode), AI call log and the project audit trail."""

from __future__ import annotations

import sys

import pandas as pd
import streamlit as st

from ats.ai.client import ModelClient
from ats.config import get_settings
from ats.discovery.diagnostics import browser_binaries, explain_launch_failure, missing_libraries
from ats.discovery.service import playwright_available
from ats.execution.runner import docker_status, resolve_mode
from ats.services import Services
from ats.ui import storage_status, theme
from ats.ui.session import current_project, safe


def short(model: str) -> str:
    return model.split("/")[-1]


def model_panel() -> None:
    model = get_settings().model
    st.markdown("### AI models")
    a, b, c, d = st.columns(4)
    a.metric("Reasoning", short(model.name))
    b.metric("Screenshots", short(model.vision_name or model.name))
    c.metric("Fast tasks", short(model.fast_name or model.name))
    d.metric("API key", "configured" if model.configured else "missing")
    st.caption(f"Endpoint {model.base_url} | fallbacks: {', '.join(short(m) for m in model.fallbacks) or 'none'} | thinking {'on' if model.enable_thinking else 'off'}")
    if not model.configured:
        st.warning("Set NVIDIA_API_KEY (or MODEL_API_KEY) in the environment or `.streamlit/secrets.toml`. AI steps are unavailable until then; non-AI features keep working.")
        return
    if st.button("Test model connection"):
        with st.spinner("Asking the models..."):
            for role in ("main", "vision", "fast"):
                client = ModelClient()
                try:
                    client.complete([{"role": "user", "content": "Reply with the single word: ready"}], thinking=False, max_tokens=32, temperature=0, role=role)
                    st.success(f"{role}: {short(client.model_name)} answered.")
                except Exception as exc:  # noqa: BLE001 - shown to the user, never raised
                    st.error(f"{role}: {exc}")


def system_panel() -> None:
    settings = get_settings()
    st.markdown("### System check")
    mode = resolve_mode(settings.execution.mode)
    docker_ok, docker_message = docker_status()
    a, b, c = st.columns(3)
    a.metric("Execution mode", mode)
    b.metric("Docker", "ready" if docker_ok else "not available")
    c.metric("Python", f"{sys.version_info.major}.{sys.version_info.minor}")
    if mode == "local":
        st.caption("Tests run as a local process (no container). " + ("" if docker_ok else docker_message))
    if not playwright_available():
        st.error("Playwright is not installed. Run: pip install playwright && python -m playwright install chromium")
        return
    binaries = browser_binaries()
    libraries = missing_libraries()
    if libraries:
        st.error(explain_launch_failure())
    elif binaries or sys.platform == "win32" or sys.platform == "darwin":
        st.success("Chromium is ready for discovery and test runs." if binaries or sys.platform != "linux" else "Chromium is ready.")
    else:
        st.info("Chromium is not downloaded yet; the first discovery installs it automatically (one-time, about 150 MB).")


def render(svc: Services) -> None:
    theme.page_header("Status", "Model routing, system health, AI call timings and the audit trail.", "SYSTEM")
    model_panel()
    storage_status.panel()
    system_panel()

    project = current_project(svc)
    if project is None:
        st.info("Open a project to see its audit trail and AI calls.")
        return
    audit_tab, ai_tab = st.tabs(["Audit trail", "AI calls"])
    with audit_tab:
        rows = svc.repo.list_audit(project.id)
        if rows:
            st.dataframe(pd.DataFrame([{"Time": r["ts"][:19], "Actor": r["actor"], "Action": r["action"], "Detail": str(r["detail"])[:200]} for r in rows]), hide_index=True, width="stretch")
        else:
            st.caption("No activity recorded yet.")
    with ai_tab:
        calls = svc.repo.list_ai_calls(project.id)
        if calls:
            st.dataframe(pd.DataFrame([{"Time": r["ts"][:19], "Agent": r["agent"], "Model": short(r.get("model", "") or ""), "OK": bool(r["ok"]), "Seconds": round(r["seconds"], 1), "Prompt tokens": r["prompt_tokens"], "Completion tokens": r["completion_tokens"], "Attempts": r["attempts"], "Error": r["error"]} for r in calls]), hide_index=True, width="stretch")
        else:
            st.caption("No model calls yet. Prompts and responses are never stored here, only timings and token counts.")
