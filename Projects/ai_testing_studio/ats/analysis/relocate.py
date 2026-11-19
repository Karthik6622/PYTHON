"""Live locator repair: look for every failing element again on the real page and pick a selector that is verified there.

The DOM captured at the moment of a failure is often the wrong place to look: a single-page app may still have been rendering, or
the test may have been on another view. Here each view the failing tests need is opened exactly like the generated tests open it
(sign in, replay the recorded clicks), its elements are extracted, and the failing element is matched by what a person sees (role,
accessible name, label, placeholder, text). A replacement is accepted only when one element clearly matches and its new selector
matches exactly one element on the live page.
"""

from __future__ import annotations

import difflib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

from ats.config import get_settings
from ats.discovery.service import run_worker
from ats.errors import StudioError
from ats.locators.builder import build_selectors, shared_testids
from ats.logging_setup import get_logger
from ats.models import DiscoveryResult, PageSnapshot, Selector
from ats.progress import ProgressFn, report
from ats.security import mask

LOGGER = get_logger("analysis.relocate")
LOCATOR_FILE, VIEWS_FILE, AUTH_FILE = "config/locators.json", "config/views.json", "config/auth.json"
MIN_SCORE, MIN_MARGIN = 5, 2
PARALLEL_BROWSERS = 3
SECONDS_PER_VIEW = 90


@dataclass
class Relocation:
    key: str
    status: str  # relocated | still_matches | not_found | ambiguous | view_unreachable | unknown_view
    view: str = ""
    selector: Selector | None = None
    alternatives: list[Selector] = field(default_factory=list)
    detail: str = ""
    found_on_view: str = ""  # the element exists, but on another view than the one the test starts on


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def text_score(wanted: set[str], have: set[str]) -> int:
    best = 0
    for a in wanted:
        for b in have:
            if a == b:
                return 6
            if min(len(a), len(b)) >= 3 and (a in b or b in a):
                best = max(best, 4)
            elif difflib.SequenceMatcher(None, a, b).ratio() >= 0.8:
                best = max(best, 3)
    return best


def score(fp: dict[str, str], el: dict[str, Any]) -> int:
    """How well a live element fits the recorded fingerprint. Text evidence is required; role and tag only refine it."""
    wanted = {_norm(fp.get(k)) for k in ("name", "text", "label", "placeholder")} - {""}
    have = {_norm(el.get(k)) for k in ("name", "text", "label", "placeholder", "title", "alt")} - {""}
    words = text_score(wanted, have)
    if not words:
        return 0
    total = words
    if fp.get("role"):
        total += 3 if el.get("role") == fp["role"] else -3 if el.get("role") else 0
    if fp.get("tag") and el.get("tag") == fp["tag"]:
        total += 1
    if fp.get("type") and el.get("type") == fp["type"]:
        total += 1
    return total


def best_match(fp: dict[str, str], elements: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    ranked = sorted(((score(fp, el), i) for i, el in enumerate(elements)), reverse=True)
    if not ranked or ranked[0][0] < MIN_SCORE:
        return None, "no element on the page looks like it"
    if len(ranked) > 1 and ranked[1][0] > ranked[0][0] - MIN_MARGIN:
        return None, f"{sum(1 for s, _ in ranked if s >= ranked[0][0] - 1)} elements look alike"
    return elements[ranked[0][1]], ""


def verified_selectors(el: dict[str, Any], shared: set[str]) -> list[Selector]:
    """Selectors for a live element that matched exactly one element on that page, best first."""
    selectors, _ = build_selectors(el, shared)
    counts = {(c.get("kind"), c.get("value"), c.get("name") or ""): c.get("count") for c in el.get("checks", [])}
    return [s for s in selectors if counts.get(s.identity()) == 1]


def fingerprint_of(entry: dict[str, Any]) -> dict[str, str]:
    fp = dict(entry.get("fingerprint") or {})
    for key in ("role", "name"):
        if entry.get(key) and not fp.get(key):
            fp[key] = entry[key]
    if not fp.get("name") and not fp.get("text"):  # old projects: the accessible name of a role selector still says what it is
        preferred = entry.get("preferred") or {}
        if preferred.get("kind") == "role" and preferred.get("name"):
            fp["name"] = preferred["name"]
        elif preferred.get("kind") in {"text", "label", "placeholder"}:
            fp[preferred["kind"] if preferred["kind"] != "text" else "text"] = preferred.get("value", "")
    return fp


class Relocator:
    """Opens the needed views in parallel browser workers and matches the failing elements against what is really there."""

    def __init__(self, timeout_per_view: int = SECONDS_PER_VIEW) -> None:
        self.timeout_per_view = timeout_per_view

    def run(self, files: dict[str, str], base_url: str, keys: list[str], secrets: dict[str, str], ignore_https_errors: bool = False,
            progress: ProgressFn | None = None) -> dict[str, Relocation]:  # fmt: skip
        try:
            locators = json.loads(files.get(LOCATOR_FILE, "{}"))
            views_doc = json.loads(files.get(VIEWS_FILE, "{}"))
            auth = json.loads(files.get(AUTH_FILE, "{}"))
        except ValueError:
            return {k: Relocation(k, "unknown_view", detail="The project's locator or view files are not valid JSON.") for k in keys}
        views = views_doc.get("views") or {}
        out: dict[str, Relocation] = {}
        wanted: dict[str, dict[str, Any]] = {}
        for key in keys:
            entry = locators.get(key)
            view = (entry or {}).get("page", "")
            if entry is None or view not in views:
                out[key] = Relocation(key, "unknown_view", view, detail="The element's view is not in the recorded views.")
                continue
            spec = wanted.setdefault(view, {**views[view], "targets": {}})
            spec["targets"][key] = [entry["preferred"], *entry.get("alternatives", [])]
        if not wanted:
            return out
        # every view is opened, so an element that moved to another view can still be found
        for view_key, view in views.items():
            wanted.setdefault(view_key, {**view, "targets": {}})
        start_url = urljoin(base_url.rstrip("/") + "/", (urlparse(views_doc.get("start_url") or "").path or "/").lstrip("/"))
        live = self._open_views(start_url, auth, wanted, secrets, ignore_https_errors, progress)
        shared = shared_testids(DiscoveryResult(start_url=start_url, pages=[PageSnapshot(url=k, page_key=k, elements=v.get("elements", [])) for k, v in live.items()]))
        for view_key, spec in wanted.items():
            for key in spec["targets"]:
                out[key] = self._decide(key, view_key, locators[key], live, shared)
        return out

    def _open_views(self, start_url: str, auth: dict[str, Any], wanted: dict[str, dict[str, Any]], secrets: dict[str, str], insecure: bool,
                    progress: ProgressFn | None) -> dict[str, dict[str, Any]]:  # fmt: skip
        items = list(wanted.items())
        chunks = [dict(items[i :: PARALLEL_BROWSERS]) for i in range(min(PARALLEL_BROWSERS, len(items)))]
        settings = get_settings()

        def one(chunk: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
            job = {
                "mode": "relocate", "start_url": start_url, "auth": auth, "views": chunk, "ignore_https_errors": insecure,
                "allow_private": settings.allow_private_network, "headless": True,
            }  # fmt: skip
            try:
                return run_worker(job, self.timeout_per_view * len(chunk) + 60, None, None, secrets).get("views", {})
            except StudioError as exc:
                LOGGER.warning("Live locator check failed: %s", exc.user_message)
                return {k: {"reached": False, "error": exc.user_message, "elements": []} for k in chunk}

        report(progress, f"Looking for the failing elements on {len(items)} live view(s)")
        live: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=len(chunks) or 1) as pool:
            for part in pool.map(one, chunks):
                live.update(part)
        return live

    @staticmethod
    def _decide(key: str, view: str, entry: dict[str, Any], live: dict[str, dict[str, Any]], shared: set[str]) -> Relocation:
        page = live.get(view) or {}
        if not page.get("reached"):
            return Relocation(key, "view_unreachable", view, detail=mask(page.get("error") or "The view could not be opened."))
        counts = (page.get("selector_counts") or {}).get(key) or []
        if counts and counts[0] == 1:
            return Relocation(key, "still_matches", view, detail="The current selector finds the element on the live view: the failure is timing or test logic.")
        fp = fingerprint_of(entry)
        element, why = best_match(fp, page.get("elements", []))
        if element is None:
            for other, data in live.items():  # moved to another view?
                if other != view and data.get("reached"):
                    moved, _ = best_match(fp, data.get("elements", []))
                    if moved is not None:
                        return Relocation(key, "not_found", view, detail=f"Not on the '{view}' view; it is on the '{other}' view.", found_on_view=other)
            return Relocation(key, "ambiguous" if "alike" in why else "not_found", view, detail=why)
        verified = verified_selectors(element, shared)
        if not verified:
            return Relocation(key, "ambiguous", view, detail="The element was found, but no selector identifies it uniquely.")
        old = Selector.model_validate(entry["preferred"])
        verified = [s for s in verified if s.identity() != old.identity()] or verified
        if verified[0].identity() == old.identity():
            return Relocation(key, "still_matches", view, detail="The recorded selector is still the best one.")
        return Relocation(key, "relocated", view, verified[0], verified[1:4], detail=f"Found on the live '{view}' view as {verified[0].display()}.")


__all__ = ["Relocation", "Relocator", "best_match", "score"]
