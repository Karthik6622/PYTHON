"""JUnit XML parsing and evidence collection (shared by every framework)."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ats.models import Status
from ats.security import mask

TC_ID = re.compile(r"(?i)tc_[a-z0-9]{2,6}_\d{3}")
REPORT_GLOBS = ("reports/junit.xml", "reports/junit/*.xml", "reports/junit/**/*.xml", "target/surefire-reports/*.xml", "reports/results.xml")
MAX_MESSAGE = 4000
SEVERITY = {Status.FAIL.value: 3, Status.INCONCLUSIVE.value: 2, Status.SKIPPED.value: 1, Status.PASS.value: 0}


def find_reports(workdir: Path) -> list[Path]:
    seen: dict[Path, None] = {}
    for pattern in REPORT_GLOBS:
        for path in sorted(workdir.glob(pattern)):
            if path.is_file():
                seen[path.resolve()] = None
    return list(seen)


def _safe_parse(path: Path) -> ET.Element | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if "<!DOCTYPE" in text[:2000] or "<!ENTITY" in text:
        return None  # never expand entities from generated output
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        return None


def _case_id(*texts: str) -> str:
    for text in texts:
        match = TC_ID.search(text or "")
        if match:
            return match.group(0).upper()
    return ""


def parse_junit(workdir: Path) -> dict[str, dict[str, Any]]:
    """Return ``{test_case_id: result}``. When a test case appears more than once the worst outcome is kept."""
    results: dict[str, dict[str, Any]] = {}
    for report in find_reports(workdir):
        root = _safe_parse(report)
        if root is None:
            continue
        for case in root.iter("testcase"):
            name, classname = case.get("name", ""), case.get("classname", "")
            tc_id = _case_id(name, classname)
            if not tc_id:
                continue
            failure = case.find("failure")
            error = case.find("error")
            skipped = case.find("skipped")
            node = failure if failure is not None else error
            if node is not None:
                status, message = Status.FAIL.value, (node.get("message") or "").strip()
                stack = (node.text or "").strip()
                if stack and stack not in message:
                    message = f"{message}\n{stack}".strip()
            elif skipped is not None:
                status, message, stack = Status.SKIPPED.value, (skipped.get("message") or "").strip(), ""
            else:
                status, message, stack = Status.PASS.value, "", ""
            try:
                duration = float(case.get("time") or 0)
            except ValueError:
                duration = 0.0
            entry = {
                "test_case_id": tc_id, "test_name": name, "status": status, "duration": duration,
                "message": mask(message)[:MAX_MESSAGE], "details": {"classname": classname, "report": report.name},
            }  # fmt: skip
            previous = results.get(tc_id)
            if previous is None or SEVERITY[status] > SEVERITY[previous["status"]]:
                results[tc_id] = entry
    return results


# ----------------------------------------------------------------------------------------
# evidence
# ----------------------------------------------------------------------------------------
def evidence_dir(workdir: Path, test_case_id: str) -> Path:
    return workdir / "reports" / "evidence" / test_case_id


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_evidence(workdir: Path, test_case_id: str) -> dict[str, Any]:
    """Evidence written by the generated tests. Paths are relative to the workdir; absent items are simply missing."""
    folder = evidence_dir(workdir, test_case_id)
    if not folder.is_dir():
        return {}
    evidence: dict[str, Any] = {}
    steps = _json(folder / "steps.json")
    if isinstance(steps, list):
        evidence["steps"] = steps
    failure = _json(folder / "failure.json")
    if isinstance(failure, dict):
        evidence["failure"] = {k: (mask(v) if isinstance(v, str) else v) for k, v in failure.items()}
    for key, name in (("screenshot", "screenshot.png"), ("dom", "dom.html")):
        if (folder / name).is_file():
            evidence[key] = (folder / name).relative_to(workdir).as_posix()
    return evidence


def read_dom(workdir: Path, evidence: dict[str, Any], limit: int = 500_000) -> str:
    rel = evidence.get("dom")
    if not rel:
        return ""
    path = (workdir / rel).resolve()
    if workdir.resolve() not in path.parents:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def collect(workdir: Path, expected_ids: list[str]) -> list[dict[str, Any]]:
    """Merge JUnit results with evidence. Test cases that never reported are SKIPPED with an explanation, not silently PASS."""
    parsed = parse_junit(workdir)
    rows: list[dict[str, Any]] = []
    for tc_id in expected_ids:
        row = parsed.pop(tc_id, None) or {
            "test_case_id": tc_id, "test_name": "", "status": Status.SKIPPED.value, "duration": 0.0,
            "message": "No result was reported for this test case.", "details": {},
        }  # fmt: skip
        row["evidence"] = read_evidence(workdir, tc_id)
        rows.append(row)
    for tc_id, row in parsed.items():  # reported but not expected (for example after a rename)
        row["evidence"] = read_evidence(workdir, tc_id)
        rows.append(row)
    return rows
