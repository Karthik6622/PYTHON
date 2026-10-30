"""Models the user can pick in the UI. All of them are served by NVIDIA's OpenAI-compatible endpoint.

Each entry carries the model-specific request options from NVIDIA's reference snippets (thinking switch, reasoning budget).
Extra model ids can be added with NVIDIA_MODELS="vendor/model-a,vendor/model-b" (they use the default options).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .config import DEFAULT_NVIDIA_MODEL, settings


@dataclass(frozen=True)
class ModelInfo:
    id: str
    label: str
    note: str
    top_p: float | None = None
    max_tokens: int = 16384
    extra_body: dict[str, Any] = field(default_factory=dict)


CATALOG: tuple[ModelInfo, ...] = (
    ModelInfo(
        id=DEFAULT_NVIDIA_MODEL, label="Nemotron 3 Ultra 550B", note="Largest model; best for hard multi-file tasks.",
    ),
    ModelInfo(
        id="nvidia/nemotron-3.5-super-vl-120b-a12b", label="Nemotron 3.5 Super VL 120B", note="Vision-language model with thinking.",
        top_p=0.95, extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    ),
    ModelInfo(
        id="nvidia/nemotron-3.5-lightning-30b-a3b", label="Nemotron 3.5 Lightning 30B", note="Fast and light; good for quick edits.",
        top_p=0.95, extra_body={"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 16384},
    ),
)


def available_models() -> list[ModelInfo]:
    """Built-in catalog, the configured default model and any NVIDIA_MODELS extras (no duplicates, catalog order first)."""
    models = list(CATALOG)
    known = {m.id for m in models}
    extras = [settings.nvidia_model, *[item.strip() for item in os.environ.get("NVIDIA_MODELS", "").split(",")]]
    for model_id in extras:
        if model_id and model_id not in known:
            known.add(model_id)
            models.append(ModelInfo(id=model_id, label=model_id.split("/")[-1], note="Custom model."))
    return models


def get_model(model_id: str | None) -> ModelInfo:
    """The catalog entry for an id; unknown ids get default options so any NVIDIA model id still works."""
    wanted = model_id or settings.nvidia_model
    for model in available_models():
        if model.id == wanted:
            return model
    return ModelInfo(id=wanted, label=wanted.split("/")[-1], note="Custom model.")


def default_model_id() -> str:
    return get_model(settings.nvidia_model).id


# Which model to carry on with when the chosen one keeps timing out: the proven mid-size model first, the largest last.
_FALLBACK_ORDER = ("nvidia/nemotron-3.5-super-vl-120b-a12b", "nvidia/nemotron-3.5-lightning-30b-a3b", DEFAULT_NVIDIA_MODEL)


def fallback_model(current: str | None, tried: set[str] | None = None) -> ModelInfo | None:
    """The next model to try after `current` (and anything in `tried`) failed, or None when none is left."""
    skip = {current or settings.nvidia_model, *(tried or set())}
    for model_id in _FALLBACK_ORDER:
        if model_id not in skip:
            return get_model(model_id)
    return None
