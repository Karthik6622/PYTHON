"""Offline DOM analysis for failed tests: does the locator still match, and which current elements resemble it?"""

from __future__ import annotations

import json
import re
import tempfile
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ats.discovery.service import run_worker
from ats.errors import DiscoveryError
from ats.locators.builder import build_locators
from ats.logging_setup import get_logger
from ats.models import DiscoveryResult, LocatorSpec, PageSnapshot, Selector

LOGGER = get_logger("analysis.dom")
MAX_CANDIDATES = 6


def _run(job: dict[str, Any], html: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ats_dom_") as tmp:
        path = Path(tmp) / "page.html"
        path.write_text(html, encoding="utf-8")
        return run_worker({**job, "html_file": str(path)}, 90)


def selector_dict(selector: Selector) -> dict[str, Any]:
    return selector.model_dump()


def analyze_failure_dom(html: str, url: str, selectors: list[Selector]) -> tuple[list[dict[str, Any]], list[LocatorSpec]]:
    """Return per-selector match counts for ``selectors`` and the list of elements currently on the page."""
    if not html.strip():
        return [], []
    try:
        data = _run({"mode": "analyze_html", "selectors": [selector_dict(s) for s in selectors]}, html)
    except DiscoveryError as exc:
        LOGGER.warning("DOM analysis unavailable: %s", exc.user_message)
        return [], []
    page = PageSnapshot(page_key="current", url=url or "about:blank", **{k: v for k, v in data["page"].items() if k in PageSnapshot.model_fields})
    specs = build_locators(DiscoveryResult(start_url=url or "about:blank", pages=[page]))
    return data.get("results", []), specs


def validate_in_html(html: str, selectors: list[Selector]) -> list[dict[str, Any]]:
    if not html.strip() or not selectors:
        return []
    try:
        return _run({"mode": "validate_html", "selectors": [selector_dict(s) for s in selectors]}, html).get("results", [])
    except DiscoveryError as exc:
        LOGGER.warning("Selector validation unavailable: %s", exc.user_message)
        return []


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) > 1}


def similarity(old: LocatorSpec, new: LocatorSpec) -> float:
    """0..1 score of how likely ``new`` is the same UI element as ``old`` (never a proof; the AI and validation decide)."""
    score = 0.0
    if old.role and old.role == new.role:
        score += 0.3
    elif old.tag and old.tag == new.tag:
        score += 0.15
    old_text = " ".join([old.name, old.intent, str(old.evidence.get("label", "")), str(old.evidence.get("placeholder", ""))])
    new_text = " ".join([new.name, str(new.evidence.get("label", "")), str(new.evidence.get("placeholder", "")), str(new.evidence.get("text", ""))])
    a, b = _tokens(old_text), _tokens(new_text)
    if a and b:
        score += 0.4 * (len(a & b) / len(a | b))
    if old.name and new.name:
        score += 0.2 * SequenceMatcher(None, old.name.lower(), new.name.lower()).ratio()
    for field in ("type", "name_attr", "id", "testid"):
        if old.evidence.get(field) and old.evidence.get(field) == new.evidence.get(field):
            score += 0.1
    if old.component and old.component == new.component:
        score += 0.05
    return round(min(score, 1.0), 2)


def rank_candidates(old: LocatorSpec, current: list[LocatorSpec], limit: int = MAX_CANDIDATES) -> list[dict[str, Any]]:
    ranked = sorted(((similarity(old, spec), spec) for spec in current), key=lambda pair: pair[0], reverse=True)
    out = []
    for score, spec in ranked[:limit]:
        if score < 0.25:
            continue
        out.append(
            {
                "score": score, "role": spec.role or spec.tag, "name": spec.name, "component": spec.component,
                "selectors": [s.model_dump() for s in spec.all_selectors()[:4]],
                "attributes": {k: v for k, v in spec.evidence.items() if k in {"tag", "type", "id", "testid", "text", "placeholder", "label", "classes", "name_attr", "href"}},
            }
        )
    return out


def excerpt(html: str, limit: int = 6000) -> str:
    """Compact, comment-free body excerpt for the model (scripts, styles and inline data removed)."""
    body = re.sub(r"(?is)<(script|style|svg|noscript)\b.*?</\1>", "", html)
    body = re.sub(r"(?s)<!--.*?-->", "", body)
    body = re.sub(r"\s+", " ", body)
    start = body.lower().find("<body")
    return body[start if start >= 0 else 0 :][:limit]


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
