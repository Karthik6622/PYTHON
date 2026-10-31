"""Status and audit page: model configuration, AI call log and the project audit trail."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ats.config import get_settings
from ats.services import Services
from ats.ui.session import require_project


def render(svc: Services) -> None:
    settings = get_settings()
    st.header("Status and audit")
    model = settings.model
    with st.container(border=True):
        st.subheader("Model")
        a, b, c = st.columns(3)
        a.metric("Model", model.name.split("/")[-1])
        b.metric("API key", "configured" if model.configured else "missing")
        c.metric("Execution mode", settings.execution.mode)
        st.caption(f"Endpoint {model.base_url} | thinking {'on' if model.enable_thinking else 'off'} | max tokens {model.max_tokens}")
        if not model.configured:
            st.warning("Set NVIDIA_API_KEY (or MODEL_API_KEY) in the environment or `.streamlit/secrets.toml`. AI steps are unavailable until then; non-AI features keep working.")

    project = require_project(svc)
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
            st.dataframe(pd.DataFrame([{"Time": r["ts"][:19], "Agent": r["agent"], "OK": bool(r["ok"]), "Seconds": round(r["seconds"], 1), "Prompt tokens": r["prompt_tokens"], "Completion tokens": r["completion_tokens"], "Attempts": r["attempts"], "Error": r["error"]} for r in calls]), hide_index=True, width="stretch")
        else:
            st.caption("No model calls yet. Prompts and responses are never stored here, only timings and token counts.")
