"""Traceability: scenario -> test case -> generated file / test, and (later) execution results."""

from __future__ import annotations

from typing import Any

TEST_PATH_MARKERS = ("tests/", "src/test/java/", "test/")


def _test_files(files: dict[str, str]) -> dict[str, str]:
    return {p: c for p, c in files.items() if any(m in p for m in TEST_PATH_MARKERS) and p.endswith((".py", ".ts", ".js", ".java"))}


def build_traceability(script_cases: list[Any], files: dict[str, str], skipped: list[dict[str, str]], all_cases: list[Any]) -> list[dict[str, Any]]:
    tests = _test_files(files)
    reasons = {s["test_case_id"]: s["reason"] for s in skipped}
    scripted = {item.test_case.test_case_id: item for item in script_cases}
    rows: list[dict[str, Any]] = []
    for case in all_cases:
        item = scripted.get(case.test_case_id)
        path = ""
        if item:
            marker = f'"{case.test_case_id}"'
            marker_alt = f"'{case.test_case_id}'"
            path = next((p for p, c in tests.items() if marker in c or marker_alt in c), "")
        rows.append(
            {
                "scenario_id": case.scenario_id,
                "test_case_id": case.test_case_id,
                "module": case.module,
                "title": case.title,
                "file": path,
                "steps": len(item.script.steps) if item else 0,
                "automated": bool(item),
                "notes": (item.script.notes if item else reasons.get(case.test_case_id, "")),
            }
        )
    return rows


def with_results(rows: list[dict[str, Any]], results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach the latest execution status to each traceability row."""
    by_id = {r["test_case_id"]: r for r in results}
    return [{**row, "status": (by_id.get(row["test_case_id"]) or {}).get("status", "NOT RUN")} for row in rows]
