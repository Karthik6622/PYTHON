"""Helpers for API test design: choose the endpoints a model call needs, build its input, and validate what comes back.

The model may only test endpoints that exist, may only chain values that an earlier request saved, and may only authenticate with
connections that are saved. Anything else is dropped (never "fixed" by guessing).
"""

from __future__ import annotations

import json
import re
from typing import Any

from ats.api.models import ApiEndpoint, endpoint_digest
from ats.generation.common import module_code, norm_title, valid_id
from ats.models import API_TEST_TYPES, COVERAGE_GUIDE, ApiRequest, Scenario, TestCase
from ats.repository import Project
from ats.security import mask

CALL = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[^\s,;)\]\"'`]*)", re.I)
VAR = re.compile(r"\{\{\s*var\.([A-Za-z_][A-Za-z0-9_]*)[^}]*\}\}")
PLACEHOLDER = re.compile(r"\{\{[^{}]*\}\}|\{[^{}/]+\}")
MAX_ENDPOINTS_PER_CALL = 25
MAX_REQUESTS = 12


def next_api_id(prefix: str, module: str, taken: set[str]) -> str:
    """``SC_A<MODULE>_001`` / ``TC_A<MODULE>_001``: the leading A keeps API ids apart from UI ids (they share one table per project)."""
    code = ("A" + module_code(module))[:6]
    n = 1
    while f"{prefix}_{code}_{n:03d}" in taken:
        n += 1
    value = f"{prefix}_{code}_{n:03d}"
    taken.add(value)
    return value


# ----------------------------------------------------------------------------------------
# endpoints
# ----------------------------------------------------------------------------------------
def _shape(path: str) -> str:
    """Path with every placeholder (``{id}``, ``{{var.x}}``) replaced by ``{}`` so templates compare equal."""
    return PLACEHOLDER.sub("{}", path.split("?")[0]).rstrip("/") or "/"


def match_endpoint(method: str, path: str, endpoints: list[ApiEndpoint]) -> ApiEndpoint | None:
    """The known endpoint a request targets: same method and a path that equals the template or fits it with literal values."""
    method = method.upper()
    wanted = _shape(path)
    for endpoint in endpoints:
        if endpoint.method == method and _shape(endpoint.path) == wanted:
            return endpoint
    for endpoint in endpoints:
        if endpoint.method != method:
            continue
        pattern = "^" + "[^/]+".join(re.escape(part) for part in _shape(endpoint.path).split("{}")) + "$"
        if re.match(pattern, wanted.replace("{}", "x")):
            return endpoint
    return None


def endpoint_chunks(endpoints: list[ApiEndpoint], size: int = MAX_ENDPOINTS_PER_CALL) -> list[list[ApiEndpoint]]:
    """Group endpoints by tag into chunks of at most ``size`` so every model call sees whole resources (journeys stay together)."""
    groups: dict[str, list[ApiEndpoint]] = {}
    for endpoint in endpoints:
        groups.setdefault(endpoint.tag, []).append(endpoint)
    chunks: list[list[ApiEndpoint]] = []
    current: list[ApiEndpoint] = []
    for group in groups.values():
        for start in range(0, len(group), size):
            part = group[start : start + size]
            if current and len(current) + len(part) > size:
                chunks.append(current)
                current = []
            current += part
    if current:
        chunks.append(current)
    return chunks


def endpoints_for(scenarios: list[Scenario], endpoints: list[ApiEndpoint], limit: int = 20) -> list[ApiEndpoint]:
    """The endpoints the given scenarios talk about (by 'METHOD /path' mentions, module and tag), capped for the prompt."""
    chosen: dict[str, ApiEndpoint] = {}
    for scenario in scenarios:
        text = " ".join([scenario.page, scenario.title, scenario.description, scenario.expected_outcome])
        for method, path in CALL.findall(text):
            endpoint = match_endpoint(method, path, endpoints)
            if endpoint:
                chosen[endpoint.key] = endpoint
        module = norm_title(scenario.module)
        for endpoint in endpoints:
            if module and module in {norm_title(t) for t in endpoint.tags}:
                chosen.setdefault(endpoint.key, endpoint)
    return list(chosen.values())[:limit] or endpoints[:limit]


# ----------------------------------------------------------------------------------------
# model input
# ----------------------------------------------------------------------------------------
def application(project: Project) -> dict[str, Any]:
    return {"name": project.name, "environment": project.environment, "description": project.description, "notes": project.test_data_notes}


def scenario_payload(project: Project, endpoints: list[ApiEndpoint], connections: list[str], requirements: str, allowed: list[str]) -> dict[str, Any]:
    return {
        "application": application(project), "base_url": project.api_url, "coverage": project.coverage, "coverage_guide": COVERAGE_GUIDE.get(project.coverage, ""),
        "allowed_test_types": allowed, "endpoints": endpoint_digest(endpoints, max_items=MAX_ENDPOINTS_PER_CALL + 5), "connections": connections,
        "user_requirements": requirements or project.test_data_notes,
    }  # fmt: skip


def testcase_payload(project: Project, scenarios: list[Scenario], endpoints: list[ApiEndpoint], connections: list[str], requirements: str, taken: set[str]) -> dict[str, Any]:
    return {
        "scenarios": [s.model_dump() for s in scenarios], "endpoints": endpoint_digest(endpoints, max_items=24, body_chars=900), "connections": connections,
        "base_url": project.api_url, "user_requirements": requirements or project.test_data_notes, "existing_test_case_ids": sorted(taken),
    }  # fmt: skip


def allowed_types(project: Project) -> list[str]:
    return project.custom_categories if project.coverage == "CUSTOM" and project.custom_categories else API_TEST_TYPES


# ----------------------------------------------------------------------------------------
# validation of model output
# ----------------------------------------------------------------------------------------
def clean_scenarios(items: list[Scenario], endpoints: list[ApiEndpoint], taken: set[str], allowed: list[str] | None, already: list[Scenario] | None = None) -> list[Scenario]:
    seen = {(norm_title(s.module), norm_title(s.title)) for s in already or []}
    cleaned: list[Scenario] = []
    for item in items:
        key = (norm_title(item.module), norm_title(item.title))
        if not item.title or key in seen:
            continue
        if allowed is not None and item.test_type not in allowed:
            continue
        mentioned = CALL.findall(item.page)
        if mentioned and not all(match_endpoint(m, p, endpoints) for m, p in mentioned):
            continue  # refers to an endpoint that is not in the definition
        seen.add(key)
        sid = item.scenario_id if valid_id(item.scenario_id, "SC", taken) else next_api_id("SC", item.module, taken)
        taken.add(sid)
        suitability = item.automation_suitability if item.automation_suitability != "Manual only" else "High"
        cleaned.append(item.model_copy(update={"scenario_id": sid, "status": "draft", "source": "ai", "layer": "api", "automation_suitability": suitability}))
    return cleaned


def _referenced_vars(request: ApiRequest) -> set[str]:
    text = json.dumps([request.path, request.path_params, request.query, request.headers, request.body], default=str)
    return set(VAR.findall(text))


def validate_requests(case: TestCase, endpoints: list[ApiEndpoint], connections: list[str]) -> tuple[TestCase | None, str]:
    """Return the test case with safe defaults filled in, or ``None`` and the reason it was rejected."""
    if case.api is None or not case.api.requests:
        return None, "no requests"
    if len(case.api.requests) > MAX_REQUESTS:
        return None, f"more than {MAX_REQUESTS} requests"
    saved: set[str] = set()
    notes: list[str] = []
    fixed: list[ApiRequest] = []
    for number, request in enumerate(case.api.requests, 1):
        endpoint = match_endpoint(request.method, request.path, endpoints)
        if endpoint is None:
            return None, f"request {number} targets {request.method} {request.path}, which is not in the API definition"
        missing = _referenced_vars(request) - saved
        if missing:
            return None, f"request {number} uses {{{{var.{sorted(missing)[0]}}}}} before an earlier request saved it"
        update: dict[str, Any] = {}
        if request.auth and request.auth not in connections:
            notes.append(f"Connection '{request.auth}' is not saved yet: create it on the Connections page before running.")
        if request.expect.status is None:
            documented = sorted(int(r.status) for r in endpoint.responses if r.status.isdigit() and r.status.startswith("2"))
            update["expect"] = request.expect.model_copy(update={"status": documented[:1] or [200, 201, 202, 204]})
            notes.append(f"Request {number} had no expected status; the documented success status was used.")
        if any(not str(path).strip() for path in request.save.values()):
            return None, f"request {number} saves a variable from an empty JSON path"
        saved |= set(request.save)
        fixed.append(request.model_copy(update=update) if update else request)
    description = " ".join([case.description, *notes]).strip()
    return case.model_copy(update={"api": case.api.model_copy(update={"requests": fixed}), "description": description}), ""


def clean_testcases(
    items: list[TestCase], scenario_ids: set[str], taken: set[str], already: list[TestCase], endpoints: list[ApiEndpoint], connections: list[str],
    rejected: list[str] | None = None,
) -> list[TestCase]:  # fmt: skip
    seen = {(t.scenario_id, norm_title(t.title)) for t in already}
    out: list[TestCase] = []
    for item in items:
        if item.scenario_id not in scenario_ids or not item.title:
            continue
        key = (item.scenario_id, norm_title(item.title))
        if key in seen:
            continue
        checked, reason = validate_requests(item, endpoints, connections)
        if checked is None:
            if rejected is not None:
                rejected.append(f"{item.title}: {reason}")
            continue
        seen.add(key)
        tid = item.test_case_id if valid_id(item.test_case_id, "TC", taken) else next_api_id("TC", item.module, taken)
        taken.add(tid)
        steps = checked.steps or [f"Send {r.method} {r.path}" for r in checked.api.requests]  # type: ignore[union-attr]
        data = {k: mask(v) for k, v in checked.test_data.items()}
        out.append(checked.model_copy(update={"test_case_id": tid, "status": "draft", "source": "ai", "layer": "api", "steps": steps, "test_data": data, "automation_candidate": True}))
    return out
