"""Helpers shared by scenario and test-case services: ids, de-duplication and applying reviewer change sets."""

from __future__ import annotations

import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ats.models import ChangeSet

M = TypeVar("M", bound=BaseModel)


def module_code(module: str) -> str:
    letters = re.sub(r"[^A-Za-z0-9]+", "", module or "").upper()
    return (letters[:4] or "GEN")


def next_id(prefix: str, module: str, taken: set[str]) -> str:
    code = module_code(module)
    n = 1
    while f"{prefix}_{code}_{n:03d}" in taken:
        n += 1
    value = f"{prefix}_{code}_{n:03d}"
    taken.add(value)
    return value


def valid_id(value: str, prefix: str, taken: set[str]) -> bool:
    return bool(re.fullmatch(rf"{prefix}_[A-Z0-9]{{2,6}}_\d{{3}}", value or "")) and value not in taken


def norm_title(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def apply_changeset(
    existing: list[M],
    change: ChangeSet,
    model: type[M],
    id_field: str,
    prefix: str,
    scope: list[str] | None = None,
) -> tuple[list[M], dict[str, Any]]:
    """Apply an AI change set. Only items inside ``scope`` (when given) may be updated or deleted.

    Updated items go back to ``draft`` so a human re-approves them. Returns the new list and a summary.
    """
    scope_set = set(scope or [])
    items = {getattr(i, id_field): i for i in existing}
    order = [getattr(i, id_field) for i in existing]
    taken = set(items)
    summary: dict[str, Any] = {"added": [], "updated": [], "deleted": [], "skipped": [], "explanation": change.explanation}

    def allowed(item_id: str) -> bool:
        return item_id in items and (not scope_set or item_id in scope_set)

    for item_id in change.delete:
        if allowed(item_id):
            items.pop(item_id)
            order.remove(item_id)
            summary["deleted"].append(item_id)
        else:
            summary["skipped"].append(f"delete {item_id}: outside the selected scope or unknown")

    for patch in change.update:
        item_id = str(patch.get(id_field, ""))
        if not allowed(item_id):
            summary["skipped"].append(f"update {item_id or '?'}: outside the selected scope or unknown")
            continue
        merged = {**items[item_id].model_dump(), **{k: v for k, v in patch.items() if k != id_field}, id_field: item_id}
        merged["status"] = "draft"
        merged["source"] = "ai-modified"
        try:
            items[item_id] = model.model_validate(merged)
            summary["updated"].append(item_id)
        except ValidationError:
            summary["skipped"].append(f"update {item_id}: invalid fields")

    for raw in change.add:
        try:
            candidate = model.model_validate({**raw, "status": "draft", "source": "ai"})
        except ValidationError:
            summary["skipped"].append("add: invalid item")
            continue
        current = getattr(candidate, id_field)
        if not valid_id(current, prefix, taken):
            current = next_id(prefix, getattr(candidate, "module", "GEN"), taken)
        else:
            taken.add(current)
        candidate = candidate.model_copy(update={id_field: current})
        items[current] = candidate
        order.append(current)
        summary["added"].append(current)
    return [items[i] for i in order], summary
