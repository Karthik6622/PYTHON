"""Typed persistence operations. Every project access is scoped to the browser (owner) that created it."""

from __future__ import annotations

import json
import shutil
import uuid
from typing import Any

from pydantic import Field

from ats.config import get_settings
from ats.db import Database
from ats.errors import NotFoundError
from ats.models import (
    AuthConfig,
    DiscoveryLimits,
    DiscoveryResult,
    LocatorSpec,
    Scenario,
    TestCase,
    _Model,
    utc_now,
)


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def loads(text: str | None, default: Any = None) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except ValueError:
        return default


class Project(_Model):
    id: str
    owner_id: str
    name: str
    url: str
    description: str = ""
    environment: str = "QA"
    base_url: str = ""
    coverage: str = "BASIC"
    custom_categories: list[str] = Field(default_factory=list)
    limits: DiscoveryLimits = Field(default_factory=DiscoveryLimits)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    test_data_notes: str = ""
    framework: str = "playwright_python"
    browser: str = "chromium"
    created_at: str = ""
    updated_at: str = ""

    @property
    def app_base_url(self) -> str:
        return self.base_url or self.url


def _project(row: dict[str, Any]) -> Project:
    return Project(
        **{
            **row,
            "custom_categories": loads(row["custom_categories"], []),
            "limits": loads(row["limits"], {}),
            "auth": loads(row["auth"], {}),
        }
    )


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------ projects
    def create_project(self, owner_id: str, **fields: Any) -> Project:
        project_id = uuid.uuid4().hex[:12]
        now = utc_now()
        limits = fields.pop("limits", None) or DiscoveryLimits()
        auth = fields.pop("auth", None) or AuthConfig()
        self.db.execute(
            """INSERT INTO projects(id, owner_id, name, url, description, environment, base_url, coverage,
               custom_categories, limits, auth, test_data_notes, framework, browser, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                project_id,
                owner_id,
                fields["name"],
                fields["url"],
                fields.get("description", ""),
                fields.get("environment", "QA"),
                fields.get("base_url", ""),
                fields.get("coverage", "BASIC"),
                dumps(fields.get("custom_categories", [])),
                dumps(limits.model_dump()),
                dumps(auth.model_dump()),
                fields.get("test_data_notes", ""),
                fields.get("framework", "playwright_python"),
                fields.get("browser", "chromium"),
                now,
                now,
            ),
        )
        self.audit(project_id, "user", "project.created", "project", {"name": fields["name"], "url": fields["url"]})
        return self.get_project(project_id, owner_id)

    def get_project(self, project_id: str, owner_id: str) -> Project:
        row = self.db.one("SELECT * FROM projects WHERE id = ? AND owner_id = ?", (project_id, owner_id))
        if not row:
            raise NotFoundError()
        return _project(row)

    def list_projects(self, owner_id: str) -> list[Project]:
        rows = self.db.query("SELECT * FROM projects WHERE owner_id = ? ORDER BY updated_at DESC", (owner_id,))
        return [_project(row) for row in rows]

    def update_project(self, project_id: str, **fields: Any) -> None:
        allowed = {
            "name", "url", "description", "environment", "base_url", "coverage", "custom_categories",
            "limits", "auth", "test_data_notes", "framework", "browser",
        }  # fmt: skip
        sets, values = [], []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key in {"custom_categories"}:
                value = dumps(value)
            elif key in {"limits", "auth"}:
                value = dumps(value.model_dump() if hasattr(value, "model_dump") else value)
            sets.append(f"{key} = ?")
            values.append(value)
        if sets:
            sets.append("updated_at = ?")
            values.extend([utc_now(), project_id])
            self.db.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", values)

    def touch(self, project_id: str) -> None:
        self.db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (utc_now(), project_id))

    def delete_project(self, project_id: str, owner_id: str) -> None:
        self.get_project(project_id, owner_id)
        self.audit(project_id, "user", "project.deleted", "project", {})
        self.db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        settings = get_settings()
        for base in (settings.projects_dir, settings.runs_dir):
            shutil.rmtree(base / project_id, ignore_errors=True)

    # ------------------------------------------------------------------ discovery
    def start_discovery(self, project_id: str) -> int:
        return self.db.execute(
            "INSERT INTO discoveries(project_id, status, started_at) VALUES (?, 'running', ?)", (project_id, utc_now())
        )

    def finish_discovery(self, discovery_id: int, status: str, result: DiscoveryResult | None, error: str = "") -> None:
        self.db.execute(
            "UPDATE discoveries SET status = ?, result = ?, error = ?, finished_at = ? WHERE id = ?",
            (status, dumps(result.model_dump(mode="json")) if result else "{}", error, utc_now(), discovery_id),
        )

    def latest_discovery(self, project_id: str) -> tuple[dict[str, Any], DiscoveryResult | None] | None:
        row = self.db.one(
            "SELECT * FROM discoveries WHERE project_id = ? ORDER BY id DESC LIMIT 1", (project_id,)
        )
        if not row:
            return None
        data = loads(row["result"], {})
        result = DiscoveryResult.model_validate(data) if data else None
        return row, result

    def latest_successful_discovery(self, project_id: str) -> DiscoveryResult | None:
        row = self.db.one(
            "SELECT result FROM discoveries WHERE project_id = ? AND status = 'completed' ORDER BY id DESC LIMIT 1",
            (project_id,),
        )
        return DiscoveryResult.model_validate(loads(row["result"], {})) if row else None

    def save_discovery_result(self, project_id: str, result: DiscoveryResult) -> None:
        self.db.execute(
            """UPDATE discoveries SET result = ? WHERE id = (SELECT id FROM discoveries
               WHERE project_id = ? AND status = 'completed' ORDER BY id DESC LIMIT 1)""",
            (dumps(result.model_dump(mode="json")), project_id),
        )

    # ------------------------------------------------------------------ locators
    def replace_locators(self, project_id: str, specs: list[LocatorSpec]) -> None:
        now = utc_now()
        statements: list[tuple[str, Any]] = [("DELETE FROM locators WHERE project_id = ?", (project_id,))]
        for spec in specs:
            statements.append(
                (
                    "INSERT INTO locators(project_id, element_key, page_key, data, updated_at) VALUES (?,?,?,?,?)",
                    (project_id, spec.element_key, spec.page_key, dumps(spec.model_dump(mode="json")), now),
                )
            )
        self.db.transaction(statements)

    def list_locators(self, project_id: str) -> list[LocatorSpec]:
        rows = self.db.query("SELECT data FROM locators WHERE project_id = ? ORDER BY page_key, element_key", (project_id,))
        return [LocatorSpec.model_validate(loads(row["data"], {})) for row in rows]

    def update_locator(self, project_id: str, spec: LocatorSpec) -> None:
        self.db.execute(
            "UPDATE locators SET data = ?, updated_at = ? WHERE project_id = ? AND element_key = ?",
            (dumps(spec.model_dump(mode="json")), utc_now(), project_id, spec.element_key),
        )

    # ------------------------------------------------------------------ scenarios
    def list_scenarios(self, project_id: str, status: str | None = None) -> list[Scenario]:
        sql, params = "SELECT status, data FROM scenarios WHERE project_id = ?", [project_id]
        if status:
            sql, params = sql + " AND status = ?", [*params, status]
        rows = self.db.query(sql + " ORDER BY position, id", params)
        return [Scenario.model_validate({**loads(r["data"], {}), "status": r["status"]}) for r in rows]

    def save_scenarios(self, project_id: str, items: list[Scenario], replace: bool = False) -> None:
        statements: list[tuple[str, Any]] = []
        if replace:
            statements.append(("DELETE FROM scenarios WHERE project_id = ?", (project_id,)))
        base = 0 if replace else len(self.list_scenarios(project_id))
        now = utc_now()
        for offset, item in enumerate(items):
            statements.append(
                (
                    """INSERT INTO scenarios(project_id, scenario_id, position, status, data, updated_at) VALUES (?,?,?,?,?,?)
                       ON CONFLICT(project_id, scenario_id) DO UPDATE SET status = excluded.status,
                       data = excluded.data, updated_at = excluded.updated_at""",
                    (project_id, item.scenario_id, base + offset, item.status, dumps(item.model_dump()), now),
                )
            )
        self.db.transaction(statements)

    def delete_scenarios(self, project_id: str, ids: list[str]) -> None:
        self.db.transaction([("DELETE FROM scenarios WHERE project_id = ? AND scenario_id = ?", (project_id, i)) for i in ids])

    def set_scenario_status(self, project_id: str, ids: list[str], status: str) -> None:
        self.db.transaction(
            [
                (
                    "UPDATE scenarios SET status = ?, updated_at = ? WHERE project_id = ? AND scenario_id = ?",
                    (status, utc_now(), project_id, i),
                )
                for i in ids
            ]
        )

    # ------------------------------------------------------------------ test cases
    def list_test_cases(self, project_id: str, status: str | None = None) -> list[TestCase]:
        sql, params = "SELECT status, data FROM test_cases WHERE project_id = ?", [project_id]
        if status:
            sql, params = sql + " AND status = ?", [*params, status]
        rows = self.db.query(sql + " ORDER BY position, id", params)
        return [TestCase.model_validate({**loads(r["data"], {}), "status": r["status"]}) for r in rows]

    def save_test_cases(self, project_id: str, items: list[TestCase], replace: bool = False) -> None:
        statements: list[tuple[str, Any]] = []
        if replace:
            statements.append(("DELETE FROM test_cases WHERE project_id = ?", (project_id,)))
        base = 0 if replace else len(self.list_test_cases(project_id))
        now = utc_now()
        for offset, item in enumerate(items):
            statements.append(
                (
                    """INSERT INTO test_cases(project_id, test_case_id, scenario_id, position, status, data, updated_at)
                       VALUES (?,?,?,?,?,?,?) ON CONFLICT(project_id, test_case_id) DO UPDATE SET
                       scenario_id = excluded.scenario_id, status = excluded.status, data = excluded.data,
                       updated_at = excluded.updated_at""",
                    (project_id, item.test_case_id, item.scenario_id, base + offset, item.status, dumps(item.model_dump()), now),
                )
            )
        self.db.transaction(statements)

    def delete_test_cases(self, project_id: str, ids: list[str]) -> None:
        self.db.transaction([("DELETE FROM test_cases WHERE project_id = ? AND test_case_id = ?", (project_id, i)) for i in ids])

    def set_test_case_status(self, project_id: str, ids: list[str], status: str) -> None:
        self.db.transaction(
            [
                (
                    "UPDATE test_cases SET status = ?, updated_at = ? WHERE project_id = ? AND test_case_id = ?",
                    (status, utc_now(), project_id, i),
                )
                for i in ids
            ]
        )

    # ------------------------------------------------------------------ bundles (files live on disk)
    def create_bundle(self, project_id: str, framework: str, browser: str, plan: dict[str, Any], traceability: list[dict[str, Any]]) -> int:
        now = utc_now()
        return self.db.execute(
            "INSERT INTO bundles(project_id, framework, browser, status, plan, traceability, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (project_id, framework, browser, "draft", dumps(plan), dumps(traceability), now, now),
        )

    def get_bundle(self, bundle_id: int) -> dict[str, Any] | None:
        row = self.db.one("SELECT * FROM bundles WHERE id = ?", (bundle_id,))
        return self._bundle(row) if row else None

    def latest_bundle(self, project_id: str) -> dict[str, Any] | None:
        row = self.db.one("SELECT * FROM bundles WHERE project_id = ? ORDER BY id DESC LIMIT 1", (project_id,))
        return self._bundle(row) if row else None

    @staticmethod
    def _bundle(row: dict[str, Any]) -> dict[str, Any]:
        return {**row, "plan": loads(row["plan"], {}), "traceability": loads(row["traceability"], [])}

    def update_bundle(self, bundle_id: int, **fields: Any) -> None:
        sets, values = [], []
        for key, value in fields.items():
            if key in {"status", "plan", "traceability", "framework", "browser"}:
                sets.append(f"{key} = ?")
                values.append(dumps(value) if key in {"plan", "traceability"} else value)
        if sets:
            sets.append("updated_at = ?")
            values.extend([utc_now(), bundle_id])
            self.db.execute(f"UPDATE bundles SET {', '.join(sets)} WHERE id = ?", values)

    # ------------------------------------------------------------------ github
    def get_github(self, project_id: str) -> dict[str, Any] | None:
        return self.db.one("SELECT * FROM github_links WHERE project_id = ?", (project_id,))

    def save_github(self, project_id: str, **fields: Any) -> None:
        current = self.get_github(project_id) or {"project_id": project_id, "repo_url": ""}
        current.update({k: v for k, v in fields.items() if v is not None})
        columns = ["repo_url", "default_branch", "branch", "commit_sha", "branch_url", "commit_url", "pr_url", "bundle_id"]
        self.db.execute(
            f"""INSERT INTO github_links(project_id, {', '.join(columns)}, updated_at) VALUES (?, {', '.join('?' for _ in columns)}, ?)
                ON CONFLICT(project_id) DO UPDATE SET {', '.join(f'{c} = excluded.{c}' for c in columns)}, updated_at = excluded.updated_at""",
            (
                project_id,
                *[current.get(c, "" if c != "bundle_id" else None) for c in columns],
                utc_now(),
            ),
        )

    # ------------------------------------------------------------------ executions
    def create_execution(self, project_id: str, **fields: Any) -> str:
        execution_id = "EX-" + uuid.uuid4().hex[:10]
        row = self.db.one("SELECT COALESCE(MAX(run_number), 0) AS n FROM executions WHERE project_id = ?", (project_id,))
        run_number = int(row["n"]) + 1 if row else 1
        self.db.execute(
            """INSERT INTO executions(id, project_id, run_number, bundle_id, parent_id, kind, status, phase, branch,
               commit_sha, source, framework, browser, environment, mode, started_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                execution_id,
                project_id,
                run_number,
                fields.get("bundle_id"),
                fields.get("parent_id", ""),
                fields.get("kind", "full"),
                fields.get("status", "queued"),
                fields.get("phase", "Queued"),
                fields.get("branch", ""),
                fields.get("commit_sha", ""),
                fields.get("source", "bundle"),
                fields["framework"],
                fields["browser"],
                fields.get("environment", ""),
                fields.get("mode", "docker"),
                utc_now(),
            ),
        )
        return execution_id

    def update_execution(self, execution_id: str, **fields: Any) -> None:
        allowed = {"status", "phase", "branch", "commit_sha", "source", "totals", "error", "finished_at", "duration", "mode"}
        sets, values = [], []
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key} = ?")
                values.append(dumps(value) if key == "totals" else value)
        if sets:
            values.append(execution_id)
            self.db.execute(f"UPDATE executions SET {', '.join(sets)} WHERE id = ?", values)

    @staticmethod
    def _execution(row: dict[str, Any]) -> dict[str, Any]:
        return {**row, "totals": loads(row["totals"], {})}

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        row = self.db.one("SELECT * FROM executions WHERE id = ?", (execution_id,))
        return self._execution(row) if row else None

    def list_executions(self, project_id: str, kinds: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM executions WHERE project_id = ? ORDER BY run_number DESC", (project_id,))
        items = [self._execution(r) for r in rows]
        return [i for i in items if kinds is None or i["kind"] in kinds]

    def replace_results(self, execution_id: str, rows: list[dict[str, Any]]) -> None:
        statements: list[tuple[str, Any]] = [("DELETE FROM results WHERE execution_id = ?", (execution_id,))]
        for row in rows:
            statements.append(
                (
                    """INSERT INTO results(execution_id, test_case_id, test_name, status, duration, message, details, evidence)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        execution_id,
                        row["test_case_id"],
                        row.get("test_name", ""),
                        row["status"],
                        float(row.get("duration", 0.0)),
                        row.get("message", ""),
                        dumps(row.get("details", {})),
                        dumps(row.get("evidence", {})),
                    ),
                )
            )
        self.db.transaction(statements)

    def list_results(self, execution_id: str) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM results WHERE execution_id = ? ORDER BY test_case_id", (execution_id,))
        return [
            {**r, "details": loads(r["details"], {}), "evidence": loads(r["evidence"], {}), "analysis": loads(r["analysis"], {})}
            for r in rows
        ]

    def update_result(self, execution_id: str, test_case_id: str, **fields: Any) -> None:
        sets, values = [], []
        for key, value in fields.items():
            if key in {"status", "duration", "message", "details", "evidence", "analysis", "test_name"}:
                sets.append(f"{key} = ?")
                values.append(dumps(value) if key in {"details", "evidence", "analysis"} else value)
        if sets:
            values.extend([execution_id, test_case_id])
            self.db.execute(f"UPDATE results SET {', '.join(sets)} WHERE execution_id = ? AND test_case_id = ?", values)

    # ------------------------------------------------------------------ healings
    def create_healing(self, project_id: str, execution_id: str, **fields: Any) -> int:
        now = utc_now()
        return self.db.execute(
            """INSERT INTO healings(project_id, execution_id, test_case_ids, element_key, old_locator, new_locator, reason,
               confidence, evidence, validation, original_code, proposed_code, rerun_execution_id, outcome, status,
               created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                project_id,
                execution_id,
                dumps(fields.get("test_case_ids", [])),
                fields["element_key"],
                dumps(fields.get("old_locator", {})),
                dumps(fields.get("new_locator", {})),
                fields.get("reason", ""),
                float(fields.get("confidence", 0.0)),
                dumps(fields.get("evidence", {})),
                dumps(fields.get("validation", {})),
                fields.get("original_code", ""),
                fields.get("proposed_code", ""),
                fields.get("rerun_execution_id", ""),
                fields.get("outcome", ""),
                fields.get("status", "proposed"),
                now,
                now,
            ),
        )

    @staticmethod
    def _healing(row: dict[str, Any]) -> dict[str, Any]:
        return {
            **row,
            "test_case_ids": loads(row["test_case_ids"], []),
            "old_locator": loads(row["old_locator"], {}),
            "new_locator": loads(row["new_locator"], {}),
            "evidence": loads(row["evidence"], {}),
            "validation": loads(row["validation"], {}),
        }

    def list_healings(self, project_id: str, execution_id: str | None = None) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM healings WHERE project_id = ?", [project_id]
        if execution_id:
            sql, params = sql + " AND execution_id = ?", [*params, execution_id]
        return [self._healing(r) for r in self.db.query(sql + " ORDER BY id DESC", params)]

    def get_healing(self, healing_id: int) -> dict[str, Any] | None:
        row = self.db.one("SELECT * FROM healings WHERE id = ?", (healing_id,))
        return self._healing(row) if row else None

    def update_healing(self, healing_id: int, **fields: Any) -> None:
        sets, values = [], []
        for key, value in fields.items():
            if key in {"status", "outcome", "pr_url", "rerun_execution_id", "validation", "evidence"}:
                sets.append(f"{key} = ?")
                values.append(dumps(value) if key in {"validation", "evidence"} else value)
        if sets:
            sets.append("updated_at = ?")
            values.extend([utc_now(), healing_id])
            self.db.execute(f"UPDATE healings SET {', '.join(sets)} WHERE id = ?", values)

    # ------------------------------------------------------------------ defects
    def save_defect(self, project_id: str, execution_id: str, test_case_id: str, data: dict[str, Any]) -> None:
        self.db.execute(
            """INSERT INTO defects(project_id, execution_id, test_case_id, defect_id, data, created_at) VALUES (?,?,?,?,?,?)
               ON CONFLICT(execution_id, test_case_id) DO UPDATE SET data = excluded.data, defect_id = excluded.defect_id""",
            (project_id, execution_id, test_case_id, data.get("defect_id", ""), dumps(data), utc_now()),
        )

    def list_defects(self, project_id: str, execution_id: str | None = None) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM defects WHERE project_id = ?", [project_id]
        if execution_id:
            sql, params = sql + " AND execution_id = ?", [*params, execution_id]
        return [{**r, "data": loads(r["data"], {})} for r in self.db.query(sql + " ORDER BY id DESC", params)]

    # ------------------------------------------------------------------ audit and AI calls
    def audit(self, project_id: str, actor: str, action: str, entity: str = "", detail: dict[str, Any] | None = None) -> None:
        from ats.security import mask_obj

        self.db.execute(
            "INSERT INTO audit_log(project_id, ts, actor, action, entity, detail) VALUES (?,?,?,?,?,?)",
            (project_id or "", utc_now(), actor, action, entity, dumps(mask_obj(detail or {}))),
        )

    def list_audit(self, project_id: str, limit: int = 300) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM audit_log WHERE project_id = ? ORDER BY id DESC LIMIT ?", (project_id, limit))
        return [{**r, "detail": loads(r["detail"], {})} for r in rows]

    def log_ai_call(self, **fields: Any) -> None:
        self.db.execute(
            """INSERT INTO ai_calls(project_id, ts, agent, model, prompt_tokens, completion_tokens, attempts, ok, seconds, error)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                fields.get("project_id", ""),
                utc_now(),
                fields["agent"],
                fields["model"],
                int(fields.get("prompt_tokens", 0)),
                int(fields.get("completion_tokens", 0)),
                int(fields.get("attempts", 1)),
                1 if fields.get("ok", True) else 0,
                float(fields.get("seconds", 0.0)),
                str(fields.get("error", ""))[:500],
            ),
        )

    def list_ai_calls(self, project_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM ai_calls WHERE project_id = ? ORDER BY id DESC LIMIT ?", (project_id, limit))
