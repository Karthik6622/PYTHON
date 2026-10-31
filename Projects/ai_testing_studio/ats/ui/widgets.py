"""Reusable Streamlit widgets: status chips, workflow tracker, model-activity stream, generic record editor."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import streamlit as st

from ats.workflow import WorkflowState

STATUS_COLOR = {
    "PASS": "green", "FAIL": "red", "HEALED": "orange", "INCONCLUSIVE": "violet", "SKIPPED": "gray", "NOT RUN": "gray",
    "completed": "green", "running": "blue", "analyzing": "blue", "queued": "gray", "error": "red", "cancelled": "gray",
    "approved": "green", "draft": "gray", "committed": "green",
    "proposed": "orange", "verified": "green", "applied": "green", "failed": "red", "rejected": "gray", "pr_opened": "blue",
}  # fmt: skip
STAGE_ICON = {"done": "✅", "current": "🔵", "waiting": "⚪", "optional": "➖", "blocked": "⛔"}


def chip(status: str) -> str:
    return f":{STATUS_COLOR.get(status, 'gray')}-badge[{status}]"


def stage_tracker(state: WorkflowState, compact: bool = False) -> None:
    if compact:
        for stage in state.stages:
            detail = f" - {stage.detail}" if stage.detail and stage.status != "waiting" else ""
            st.markdown(f"{STAGE_ICON[stage.status]} **{stage.name}**{detail}")
        return
    columns = st.columns(len(state.stages))
    for column, stage in zip(columns, state.stages, strict=True):
        with column:
            st.markdown(f"{STAGE_ICON[stage.status]} **{stage.name}**")
            if stage.detail:
                st.caption(stage.detail)


class ModelStream:
    """Shows what the model is doing while a long call runs. Use ``callback`` as ``on_event``."""

    def __init__(self, label: str = "AI model activity") -> None:
        self.box = st.expander(label, expanded=False)
        with self.box:
            self.reasoning = st.empty()
            self.content = st.empty()
        self.buffers = {"reasoning": "", "content": ""}
        self.last = 0.0

    def callback(self, kind: str, text: str) -> None:
        self.buffers[kind] = (self.buffers.get(kind, "") + text)[-3000:]
        now = time.time()
        if now - self.last > 0.4:
            self.last = now
            self.render()

    def render(self) -> None:
        if self.buffers["reasoning"]:
            self.reasoning.caption("Reasoning: " + self.buffers["reasoning"][-700:])
        if self.buffers["content"]:
            self.content.code(self.buffers["content"][-900:], language="json")


def progress_logger(status: Any) -> Callable[[str], None]:
    def say(message: str) -> None:
        status.write(message)
        status.update(label=message)

    return say


# ---------------------------------------------------------------------------------------- field editors
def edit_fields(prefix: str, record: dict[str, Any], spec: list[tuple[str, str, Any]]) -> dict[str, Any]:
    """Render inputs for ``spec`` = [(field, kind, options)] and return the edited values.

    kinds: text, area, lines (one item per line), select, bool, pairs (key: value per line)."""
    values: dict[str, Any] = {}
    for name, kind, options in spec:
        label, key, current = name.replace("_", " ").capitalize(), f"{prefix}_{name}", record.get(name)
        if kind == "text":
            values[name] = st.text_input(label, value=str(current or ""), key=key)
        elif kind == "area":
            values[name] = st.text_area(label, value=str(current or ""), key=key, height=110)
        elif kind == "lines":
            text = st.text_area(label + " (one per line)", value="\n".join(current or []), key=key, height=130)
            values[name] = [line.strip() for line in text.splitlines() if line.strip()]
        elif kind == "select":
            choices = list(options)
            values[name] = st.selectbox(label, choices, index=choices.index(current) if current in choices else 0, key=key)
        elif kind == "bool":
            values[name] = st.checkbox(label, value=bool(current), key=key)
        elif kind == "pairs":
            text = st.text_area(label + " (key: value per line)", value="\n".join(f"{k}: {v}" for k, v in (current or {}).items()), key=key, height=100)
            pairs = {}
            for line in text.splitlines():
                head, sep, rest = line.partition(":")
                if sep and head.strip():
                    pairs[head.strip()] = rest.strip()
            values[name] = pairs
    return values


def selected_rows(event: Any, frame_ids: list[str]) -> list[str]:
    """Ids picked in an ``st.dataframe(on_select='rerun')`` table."""
    rows = list(getattr(getattr(event, "selection", None), "rows", []) or [])
    return [frame_ids[i] for i in rows if 0 <= i < len(frame_ids)]
