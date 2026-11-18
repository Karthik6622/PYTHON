"""Sign-in check after discovery: deterministic signals from the recorded pages, merged with the model's requirement check.

The signals are facts the browser saw (a password field, a view or API call that answered HTTP 401/403, an API call with a key-like
query parameter). They are always computed and need no model. The model adds requirements the pages suggest and writes the summary.
A signal always wins over a model-only item of the same kind. Values (passwords, keys, tokens) are never read or stored here.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlsplit

from ats.ai.agents.discovery_agents import AuthRequirementCheck
from ats.connections.service import KINDS
from ats.models import DiscoveryResult, utc_now

KEY_PARAMS = {"api_key", "apikey", "api-key", "key", "token", "access_token"}  # query parameter names that carry a credential
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
MAX_LISTED = 3  # evidence and pages listed per kind; the rest is counted


def _label(page: Any) -> str:
    return page.view_name or page.title or page.final_url or page.url


def _signals(result: DiscoveryResult) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for page in result.pages:
        label = _label(page)
        if any(str(el.get("type") or "").lower() == "password" for el in page.elements):
            found.append({"kind": "ui_account", "where": label, "evidence": f"password field on {label}", "confidence": "high"})
        if page.requires_auth:  # the worker sets this when the view answered HTTP 401 or 403
            found.append({"kind": "ui_account", "where": label, "evidence": f"{label} answered HTTP {page.status} (sign-in required)", "confidence": "high"})
        for call in page.network:
            url = str(call.get("url") or "")
            method = str(call.get("method") or "GET")
            path = urlsplit(url).path or url
            if call.get("status") in (401, 403):
                found.append({"kind": "ui_account", "where": path, "evidence": f"{method} {path} answered HTTP {call['status']} during discovery", "confidence": "medium"})
            names = sorted({name.lower() for name, _ in parse_qsl(urlsplit(url).query, keep_blank_values=True)} & KEY_PARAMS)
            if names:  # only the parameter NAME is kept; the value never leaves the page data
                found.append({"kind": "api_key", "where": path, "evidence": f"{method} {path} sends a '{names[0]}' query parameter", "confidence": "medium"})
    return found


def _listed(values: list[str]) -> str:
    shown = ", ".join(values[:MAX_LISTED])
    return shown + (f" and {len(values) - MAX_LISTED} more" if len(values) > MAX_LISTED else "")


def auth_signals(result: DiscoveryResult) -> list[dict[str, Any]]:
    """Sign-in evidence found in the recorded pages: one item per kind, listing the pages and the strongest confidence."""
    groups: dict[str, dict[str, Any]] = {}
    for item in _signals(result):
        group = groups.setdefault(item["kind"], {"where": [], "evidence": [], "confidence": "low"})
        if item["where"] not in group["where"]:
            group["where"].append(item["where"])
        if item["evidence"] not in group["evidence"]:
            group["evidence"].append(item["evidence"])
        if CONFIDENCE_RANK[item["confidence"]] > CONFIDENCE_RANK[group["confidence"]]:
            group["confidence"] = item["confidence"]
    return [
        {"kind": kind, "where": _listed(group["where"]), "evidence": _listed(group["evidence"]), "confidence": group["confidence"], "source": "signal"}
        for kind, group in groups.items()
    ]


def _signal_summary(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No sign-in details were found in the discovered pages."
    labels = ", ".join(KINDS[item["kind"]].label if item["kind"] in KINDS else item["kind"] for item in items)
    return f"The discovered pages show signs of sign-in ({labels}). Check the evidence below."


def build_authentication(signals: list[dict[str, Any]], check: AuthRequirementCheck | None = None, now: str = "") -> dict[str, Any]:
    """The value stored as ``analysis["authentication"]``: observed signals first, then model-only items; one requirement per kind."""
    items: dict[str, dict[str, Any]] = {}
    for item in signals:
        items.setdefault(item["kind"], {**item, "source": "signal"})
    for item in check.requirements if check else []:
        if item.kind not in items:
            items[item.kind] = {"kind": item.kind, "where": item.where, "evidence": item.evidence, "confidence": item.confidence, "source": "model"}
    requirements = list(items.values())
    requires = bool(requirements) or bool(check and check.requires_authentication)
    # The model's summary is used only when it agrees with the evidence it was given; otherwise the summary follows the requirements.
    model_summary = check.summary if check and check.summary and check.requires_authentication == requires else ""
    return {
        "requires_authentication": requires,
        "summary": model_summary or _signal_summary(requirements),
        "requirements": requirements,
        "checked_by": "model+signals" if check else "signals",
        "checked_at": now or utc_now(),
    }


__all__ = ["KEY_PARAMS", "auth_signals", "build_authentication"]
