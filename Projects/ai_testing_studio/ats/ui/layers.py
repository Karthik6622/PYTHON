"""Channel (layer) helpers shared by every page: which layers a project has, the switch between them, and the navigation table.

A project's testing type is a set of channels (Web, API, Mobile). Every stored scenario, test case and bundle carries a layer id
("ui" is Web). Pages that list or generate those things show one layer at a time; ``layer_switch`` picks it and is hidden when the
project has only one layer, so a Web-only project looks exactly as before.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

import streamlit as st

from ats.errors import GenerationError
from ats.generation.adapters.common import frameworks_for
from ats.logging_setup import get_logger
from ats.models import LAYER_LABELS, LAYERS
from ats.repository import Project
from ats.services import Services
from ats.ui.session import go_to
from ats.workflow import WorkflowState, next_layer, next_page

LOGGER = get_logger("ui.layers")
MEMORY_KEY = "_layers"  # session state: {project id: layer chosen last}
BUILT_IN_LAYERS = ("ui", "api")


def available_layers(project: Project) -> list[str]:
    return project.layers


def layer_label(layer: str) -> str:
    return LAYER_LABELS.get(layer, layer.title())


def current_layer(project: Project) -> str:
    """The layer chosen last for this project (the first layer of the project until a choice is made)."""
    layers = available_layers(project)
    chosen = st.session_state.get(MEMORY_KEY, {}).get(project.id)
    return chosen if chosen in layers else layers[0]


def remember_layer(project: Project, layer: str) -> None:
    if layer in LAYERS:
        st.session_state.setdefault(MEMORY_KEY, {})[project.id] = layer


def layer_switch(project: Project, key: str) -> str:
    """Pick the layer a page works on. Shared by all pages (the choice follows the person from Scenarios to Test cases to Automation)."""
    layers = available_layers(project)
    current = current_layer(project)
    if len(layers) == 1:
        return current
    widget = f"layer_switch_{key}_{project.id}"
    if st.session_state.get(widget) != current:
        st.session_state[widget] = current  # keep this page's switch in step with the remembered choice

    def changed() -> None:
        remember_layer(project, st.session_state[widget])

    choice = st.radio("Channel", layers, key=widget, format_func=layer_label, horizontal=True, on_change=changed)
    remember_layer(project, choice)
    return choice


def layer_supported(layer: str) -> bool:
    """Web and API are built in; any other layer needs a registered automation framework (Mobile adds its own)."""
    return layer in BUILT_IN_LAYERS or bool(frameworks_for(layer))


def unavailable_text(layer: str) -> str:
    return f"{layer_label(layer)} support is not available in this build yet."


def guarded(layer: str, work: Callable[[Any], dict[str, Any] | None]) -> Callable[[Any], dict[str, Any] | None]:
    """Wrap a job's work function: a layer whose generator is missing reports a plain message instead of a crash."""

    def run(ctx: Any) -> dict[str, Any] | None:
        try:
            return work(ctx)
        except NotImplementedError as exc:
            raise GenerationError(unavailable_text(layer)) from exc

    return run


def stop_if_unsupported(layer: str) -> bool:
    """Show the friendly message and return True when the layer cannot be generated here."""
    if layer_supported(layer):
        return False
    st.info(unavailable_text(layer))
    return True


def open_next_step(project: Project, state: WorkflowState) -> None:
    """Go to the page of the next workflow step, with the channel that step is about already selected."""
    layer = next_layer(state)
    if layer:
        remember_layer(project, layer)
    go_to(next_page(state))


# ----------------------------------------------------------------------------------------
# navigation
# ----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class LayerPage:
    """One row of the navigation table. ``layers`` limits the page to projects that have one of these layers (empty = always shown);
    ``needs_project`` hides it until a project is open. ``load`` returns the page callable, or None to skip the page silently."""

    url_path: str
    title: str
    icon: str
    load: Callable[[Services], Callable[[], None] | None]
    layers: tuple[str, ...] = ()
    needs_project: bool = False
    default: bool = False

    def visible(self, project: Project | None) -> bool:
        if self.needs_project and project is None:
            return False
        if not self.layers:
            return True
        return bool(set(self.layers) & set(project.layers if project else ["ui"]))


def page_of(render: Callable[..., None]) -> Callable[[Services], Callable[[], None]]:
    return lambda svc: partial(render, svc)


def lazy_page(module: str, call: str = "render") -> Callable[[Services], Callable[[], None] | None]:
    """Page from a module that may not exist yet (another team's page): it is imported on first use and skipped when missing."""

    def load(svc: Services) -> Callable[[], None] | None:
        try:
            render = getattr(importlib.import_module(module), call)
        except (ImportError, AttributeError):
            LOGGER.info("Page %s is not available; it is left out of the navigation", module)
            return None
        return partial(render, svc)

    return load


def build_pages(svc: Services, project: Project | None, table: list[LayerPage]) -> list[Any]:
    """``st.Page`` objects for the rows of ``table`` that apply to the project."""
    pages = []
    for row in table:
        if not row.visible(project):
            continue
        render = row.load(svc)
        if render is None:
            continue
        pages.append(st.Page(render, title=row.title, icon=row.icon, url_path=row.url_path, default=row.default))
    return pages
