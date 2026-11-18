"""Typed persistence operations. Every project access is scoped to the account (owner) that created it."""

from __future__ import annotations

import json
import shutil
import uuid
from typing import Any

from pydantic import Field

from ats.api.models import ApiEndpoint
from ats.config import get_settings
from ats.db import Database
from ats.errors import NotFoundError
from ats.github.client import repo_slug, workspace_key
from ats.mobile.models import MobileAnalysis, MobileConfig
from ats.models import (
    CHANNEL_LAYER,
    CHANNELS,
    AuthConfig,
    DiscoveryLimits,
    DiscoveryResult,
    LocatorSpec,
    Scenario,
    TestCase,
    _Model,
    parse_scope,
    scope_text,
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
    test_scope: str = "web"  # channels of the testing type, e.g. "web", "web,api", "mobile,api" (legacy: ui | api | both)
    api_base_url: str = ""
    created_at: str = ""
    updated_at: str = ""

    @property
    def app_base_url(self) -> str:
        return self.base_url or self.url

    @property
    def channels(self) -> list[str]:
        """The channels (web, api, mobile) this project tests, in display order."""
        return parse_scope(self.test_scope)

    @property
    def layers(self) -> list[str]:
        """Layer ids of the channels (``ui`` is Web), in display order."""
        return [CHANNEL_LAYER[c] for c in self.channels]

    @property
    def api_url(self) -> str:
        """Where API tests send requests: the API base URL, else the application's own address."""
        return self.api_base_url or self.app_base_url


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
        extra = {k: fields[k] for k in ("test_scope", "api_base_url") if fields.get(k)}
        if extra:
            self.update_project(project_id, **extra)
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

    def transfer_owner(self, old_owner_id: str, new_owner_id: str) -> int:
        """Hand every project of one owner id to another (browser-era projects move to the account). Returns the count."""
        if not old_owner_id or not new_owner_id or old_owner_id == new_owner_id:
            return 0
        with self.db.connect() as conn:
            conn.execute("UPDATE connections SET owner_id = ? WHERE owner_id = ?", (new_owner_id, old_owner_id))
            return conn.execute("UPDATE projects SET owner_id = ? WHERE owner_id = ?", (new_owner_id, old_owner_id)).rowcount

    def update_project(self, project_id: str, **fields: Any) -> None:
        allowed = {
            "name", "url", "description", "environment", "base_url", "coverage", "custom_categories",
            "limits", "auth", "test_data_notes", "framework", "browser", "test_scope", "api_base_url",
        }  # fmt: skip
        sets, values = [], []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "test_scope":
                value = scope_text(value)
            elif key in {"custom_categories"}:
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
        shutil.rmtree(settings.secure_dir / "mobile" / project_id, ignore_errors=True)  # uploaded APKs
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
    def list_scenarios(self, project_id: str, status: str | None = None, layer: str | None = None) -> list[Scenario]:
        sql, params = "SELECT status, layer, data FROM scenarios WHERE project_id = ?", [project_id]
        if status:
            sql, params = sql + " AND status = ?", [*params, status]
        if layer:
            sql, params = sql + " AND layer = ?", [*params, layer]
        rows = self.db.query(sql + " ORDER BY position, id", params)
        return [Scenario.model_validate({**loads(r["data"], {}), "status": r["status"], "layer": r["layer"]}) for r in rows]

    def save_scenarios(self, project_id: str, items: list[Scenario], replace: bool = False, layer: str | None = None) -> None:
        """Save scenarios. ``replace`` swaps out the scenarios of one layer (the given one, else the one the items belong to)."""
        layer = layer or (items[0].layer if items else "ui")
        statements: list[tuple[str, Any]] = []
        if replace:
            statements.append(("DELETE FROM scenarios WHERE project_id = ? AND layer = ?", (project_id, layer)))
        base = 0 if replace else len(self.list_scenarios(project_id))
        now = utc_now()
        for offset, item in enumerate(items):
            statements.append(
                (
                    """INSERT INTO scenarios(project_id, scenario_id, position, status, layer, data, updated_at) VALUES (?,?,?,?,?,?,?)
                       ON CONFLICT(project_id, scenario_id) DO UPDATE SET status = excluded.status,
                       data = excluded.data, updated_at = excluded.updated_at""",
                    (project_id, item.scenario_id, base + offset, item.status, item.layer, dumps(item.model_dump()), now),
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
    def list_test_cases(self, project_id: str, status: str | None = None, layer: str | None = None) -> list[TestCase]:
        sql, params = "SELECT status, layer, data FROM test_cases WHERE project_id = ?", [project_id]
        if status:
            sql, params = sql + " AND status = ?", [*params, status]
        if layer:
            sql, params = sql + " AND layer = ?", [*params, layer]
        rows = self.db.query(sql + " ORDER BY position, id", params)
        return [TestCase.model_validate({**loads(r["data"], {}), "status": r["status"], "layer": r["layer"]}) for r in rows]

    def save_test_cases(self, project_id: str, items: list[TestCase], replace: bool = False, layer: str | None = None) -> None:
        """Save test cases. ``replace`` swaps out the test cases of one layer (the given one, else the one the items belong to)."""
        layer = layer or (items[0].layer if items else "ui")
        statements: list[tuple[str, Any]] = []
        if replace:
            statements.append(("DELETE FROM test_cases WHERE project_id = ? AND layer = ?", (project_id, layer)))
        base = 0 if replace else len(self.list_test_cases(project_id))
        now = utc_now()
        for offset, item in enumerate(items):
            statements.append(
                (
                    """INSERT INTO test_cases(project_id, test_case_id, scenario_id, position, status, layer, data, updated_at)
                       VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(project_id, test_case_id) DO UPDATE SET
                       scenario_id = excluded.scenario_id, status = excluded.status, data = excluded.data,
                       updated_at = excluded.updated_at""",
                    (project_id, item.test_case_id, item.scenario_id, base + offset, item.status, item.layer, dumps(item.model_dump()), now),
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
    def create_bundle(self, project_id: str, framework: str, browser: str, plan: dict[str, Any], traceability: list[dict[str, Any]], layer: str = "ui") -> int:
        now = utc_now()
        return self.db.execute(
            "INSERT INTO bundles(project_id, framework, browser, status, layer, plan, traceability, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (project_id, framework, browser, "draft", layer, dumps(plan), dumps(traceability), now, now),
        )

    def get_bundle(self, bundle_id: int) -> dict[str, Any] | None:
        row = self.db.one("SELECT * FROM bundles WHERE id = ?", (bundle_id,))
        return self._bundle(row) if row else None

    def latest_bundle(self, project_id: str, layer: str | None = None) -> dict[str, Any] | None:
        sql, params = "SELECT * FROM bundles WHERE project_id = ?", [project_id]
        if layer:
            sql, params = sql + " AND layer = ?", [*params, layer]
        row = self.db.one(sql + " ORDER BY id DESC LIMIT 1", params)
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

    # ------------------------------------------------------------------ API endpoints
    def list_api_endpoints(self, project_id: str) -> list[ApiEndpoint]:
        rows = self.db.query("SELECT data FROM api_endpoints WHERE project_id = ? ORDER BY position, id", (project_id,))
        return [ApiEndpoint.model_validate(loads(r["data"], {})) for r in rows]

    def save_api_endpoints(self, project_id: str, items: list[ApiEndpoint], replace_source: str | None = None) -> None:
        """Insert or update endpoints by key. ``replace_source`` first removes every endpoint that came from that source."""
        existing = self.list_api_endpoints(project_id)
        statements: list[tuple[str, Any]] = []
        if replace_source:
            statements += [("DELETE FROM api_endpoints WHERE project_id = ? AND key = ?", (project_id, e.key)) for e in existing if e.source == replace_source]
            existing = [e for e in existing if e.source != replace_source]
        base = len(existing)
        now = utc_now()
        for offset, item in enumerate(items):
            statements.append(
                (
                    """INSERT INTO api_endpoints(project_id, key, position, data, updated_at) VALUES (?,?,?,?,?)
                       ON CONFLICT(project_id, key) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at""",
                    (project_id, item.key, base + offset, dumps(item.model_dump(by_alias=True)), now),
                )
            )
        self.db.transaction(statements)

    def delete_api_endpoints(self, project_id: str, keys: list[str] | None = None) -> None:
        """Delete the listed endpoints, or all of them when ``keys`` is None."""
        if keys is None:
            self.db.execute("DELETE FROM api_endpoints WHERE project_id = ?", (project_id,))
        else:
            self.db.transaction([("DELETE FROM api_endpoints WHERE project_id = ? AND key = ?", (project_id, k)) for k in keys])

    # ------------------------------------------------------------------ connections (values arrive already encrypted)
    def list_connection_rows(self, project_id: str, owner_id: str | None = None) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM connections WHERE project_id = ?", [project_id]
        if owner_id is not None:
            sql, params = sql + " AND owner_id = ?", [*params, owner_id]
        return [{**r, "secret": bool(r["secret"]), "meta": loads(r["meta"], {})} for r in self.db.query(sql + " ORDER BY name, id", params)]

    def save_connection_row(self, project_id: str, owner_id: str, name: str, part: str, kind: str, env_name: str, secret: bool, value_enc: str | None, meta: dict[str, Any]) -> None:
        """Insert or update one variable of a connection. ``value_enc=None`` keeps the stored value (non-secret edits)."""
        now = utc_now()
        current = self.db.one("SELECT id FROM connections WHERE project_id = ? AND name = ? AND part = ?", (project_id, name, part))
        if current:
            sets, values = ["kind = ?", "env_name = ?", "secret = ?", "meta = ?", "updated_at = ?"], [kind, env_name, int(secret), dumps(meta), now]
            if value_enc is not None:
                sets.append("value_enc = ?")
                values.append(value_enc)
            self.db.execute(f"UPDATE connections SET {', '.join(sets)} WHERE id = ?", [*values, current["id"]])
        else:
            self.db.execute(
                """INSERT INTO connections(project_id, owner_id, name, part, kind, env_name, secret, value_enc, meta, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (project_id, owner_id, name, part, kind, env_name, int(secret), value_enc or "", dumps(meta), now, now),
            )

    def delete_connection(self, project_id: str, name: str) -> None:
        self.db.execute("DELETE FROM connections WHERE project_id = ? AND name = ?", (project_id, name))

    # ------------------------------------------------------------------ mobile (configuration and analysed screens, one row per project)
    def get_mobile_config(self, project_id: str) -> MobileConfig:
        row = self.db.one("SELECT * FROM mobile_config WHERE project_id = ?", (project_id,))
        return MobileConfig.model_validate(row) if row else MobileConfig()

    def save_mobile_config(self, project_id: str, config: MobileConfig) -> None:
        values = config.model_dump()
        columns = list(values)
        self.db.execute(
            f"""INSERT INTO mobile_config(project_id, {', '.join(columns)}, updated_at) VALUES (?, {', '.join('?' for _ in columns)}, ?)
                ON CONFLICT(project_id) DO UPDATE SET {', '.join(f'{c} = excluded.{c}' for c in columns)}, updated_at = excluded.updated_at""",
            (project_id, *values.values(), utc_now()),
        )

    def get_mobile_analysis(self, project_id: str) -> MobileAnalysis | None:
        row = self.db.one("SELECT analysis FROM mobile_config WHERE project_id = ?", (project_id,))
        data = loads(row["analysis"], {}) if row else {}
        return MobileAnalysis.model_validate(data) if data.get("screens") else None

    def save_mobile_analysis(self, project_id: str, analysis: MobileAnalysis | None) -> None:
        """Store (or clear, with ``None``) the analysed screens and elements of the project."""
        if self.db.one("SELECT 1 AS present FROM mobile_config WHERE project_id = ?", (project_id,)) is None:
            self.save_mobile_config(project_id, MobileConfig())
        self.db.execute(
            "UPDATE mobile_config SET analysis = ?, updated_at = ? WHERE project_id = ?",
            (dumps(analysis.model_dump(mode="json")) if analysis else "{}", utc_now(), project_id),
        )

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

    # ------------------------------------------------------------------ github workspaces: (repository, branch) identity
    def record_workspace(self, project_id: str, repo_url: str, branch: str, channels: list[str], commit_sha: str = "") -> dict[str, Any]:
        """Remember that ``project_id`` publishes to the workspace (repository, exact branch). Channels accumulate per project."""
        repo = repo_slug(repo_url)
        row = self.db.one("SELECT channels FROM github_workspaces WHERE repo = ? AND branch = ? AND project_id = ?", (repo, branch, project_id))
        merged = [c for c in CHANNELS if c in ({*loads(row["channels"], []), *channels} if row else set(channels))]
        self.db.execute(
            """INSERT INTO github_workspaces(repo, branch, project_id, channels, commit_sha, updated_at) VALUES (?,?,?,?,?,?)
               ON CONFLICT(repo, branch, project_id) DO UPDATE SET channels = excluded.channels, commit_sha = excluded.commit_sha, updated_at = excluded.updated_at""",
            (repo, branch, project_id, dumps(merged), commit_sha, utc_now()),
        )
        return {"repo": repo, "branch": branch, "channels": merged}

    def workspace_projects(self, repo_url: str, branch: str) -> list[dict[str, Any]]:
        """Every project (of any account) that publishes to this repository and branch."""
        rows = self.db.query("SELECT project_id, channels, commit_sha, updated_at FROM github_workspaces WHERE repo = ? AND branch = ? ORDER BY updated_at", (repo_slug(repo_url), branch))
        return [{**r, "channels": loads(r["channels"], [])} for r in rows]

    def project_workspace(self, project_id: str) -> dict[str, Any] | None:
        """The workspace the project points at: its linked repository and branch, and how many projects share it."""
        link = self.get_github(project_id)
        if not link or not link.get("repo_url") or not link.get("branch"):
            return None
        sharing = self.workspace_projects(link["repo_url"], link["branch"])
        mine = next((w for w in sharing if w["project_id"] == project_id), None)
        return {
            "repo": repo_slug(link["repo_url"]), "branch": link["branch"], "channels": (mine or {}).get("channels", []),
            "projects": len(sharing) or 1, "key": workspace_key(link["repo_url"], link["branch"]),
        }  # fmt: skip

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
        allowed = {"status", "phase", "branch", "commit_sha", "source", "totals", "error", "finished_at", "duration", "mode", "progress"}
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

    def active_execution(self, project_id: str) -> dict[str, Any] | None:
        """The newest full run of the project that has not finished (one cheap row, for pages that poll)."""
        row = self.db.one(
            "SELECT * FROM executions WHERE project_id = ? AND kind = 'full' AND status IN ('queued', 'running', 'analyzing') ORDER BY run_number DESC LIMIT 1",
            (project_id,),
        )
        return self._execution(row) if row else None

    def result_statuses(self, execution_id: str) -> dict[str, str]:
        """Test case id -> status, without the evidence and analysis payloads."""
        return {r["test_case_id"]: r["status"] for r in self.db.query("SELECT test_case_id, status FROM results WHERE execution_id = ?", (execution_id,))}

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

    def has_audit(self, project_id: str, action: str) -> bool:
        return self.db.one("SELECT 1 AS found FROM audit_log WHERE project_id = ? AND action = ? LIMIT 1", (project_id, action)) is not None

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

    # ------------------------------------------------------------------ background jobs
    def create_job(self, project_id: str, owner_id: str, kind: str, title: str, next_page: str = "", notice: str = "") -> str:
        job_id = "JOB-" + uuid.uuid4().hex[:10]
        now = utc_now()
        self.db.execute(
            """INSERT INTO jobs(id, project_id, owner_id, kind, title, status, next_page, notice, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (job_id, project_id, owner_id, kind, title, "queued", next_page, notice, now, now),
        )
        return job_id

    def update_job(self, job_id: str, **fields: Any) -> None:
        allowed = {"status", "progress", "message", "log", "activity", "result", "error", "started_at", "finished_at"}
        sets, values = ["updated_at = ?"], [utc_now()]
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key} = ?")
                values.append(dumps(value) if key in {"log", "result"} else value)
        values.append(job_id)
        self.db.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", values)

    @staticmethod
    def _job(row: dict[str, Any]) -> dict[str, Any]:
        return {**row, "log": loads(row["log"], []), "result": loads(row["result"], {})}

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = self.db.one("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return self._job(row) if row else None

    def list_jobs(self, project_id: str, kinds: tuple[str, ...] | None = None, limit: int = 30) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM jobs WHERE project_id = ? ORDER BY created_at DESC LIMIT ?", (project_id, limit))
        return [j for j in (self._job(r) for r in rows) if kinds is None or j["kind"] in kinds]

    def active_jobs(self, project_id: str | None = None) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM jobs WHERE status IN ('queued', 'running')", []
        if project_id:
            sql, params = sql + " AND project_id = ?", [project_id]
        return [self._job(r) for r in self.db.query(sql + " ORDER BY created_at", params)]

    def interrupt_stale_jobs(self) -> int:
        """Jobs left 'running' by a server process that no longer exists can never finish: mark them interrupted."""
        stale = self.active_jobs()
        for job in stale:
            self.update_job(job["id"], status="interrupted", message="The server restarted while this was running. Start it again.", finished_at=utc_now())
        return len(stale)
