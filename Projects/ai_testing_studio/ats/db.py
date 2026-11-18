"""SQLite access and schema migrations.

This module is the only place that knows about the database driver. The SQL used by the repository is plain
ANSI SQL plus ``INTEGER PRIMARY KEY AUTOINCREMENT``, so a PostgreSQL backend only needs a new ``Database`` class
(``SERIAL`` instead of AUTOINCREMENT and ``%s`` placeholders) behind the same three methods.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ats.logging_setup import get_logger

LOGGER = get_logger("db")

# (version, SQL). Append new migrations; never edit an applied one.
MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    environment TEXT NOT NULL DEFAULT 'QA',
    base_url TEXT NOT NULL DEFAULT '',
    coverage TEXT NOT NULL DEFAULT 'BASIC',
    custom_categories TEXT NOT NULL DEFAULT '[]',
    limits TEXT NOT NULL DEFAULT '{}',
    auth TEXT NOT NULL DEFAULT '{}',
    test_data_notes TEXT NOT NULL DEFAULT '',
    framework TEXT NOT NULL DEFAULT 'playwright_python',
    browser TEXT NOT NULL DEFAULT 'chromium',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_projects_owner ON projects(owner_id);

CREATE TABLE discoveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    result TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_discoveries_project ON discoveries(project_id);

CREATE TABLE locators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    element_key TEXT NOT NULL,
    page_key TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, element_key)
);

CREATE TABLE scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scenario_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft',
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, scenario_id)
);

CREATE TABLE test_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    test_case_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft',
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, test_case_id)
);

CREATE TABLE bundles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    framework TEXT NOT NULL,
    browser TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    plan TEXT NOT NULL DEFAULT '{}',
    traceability TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE github_links (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    repo_url TEXT NOT NULL,
    default_branch TEXT NOT NULL DEFAULT '',
    branch TEXT NOT NULL DEFAULT '',
    commit_sha TEXT NOT NULL DEFAULT '',
    branch_url TEXT NOT NULL DEFAULT '',
    commit_url TEXT NOT NULL DEFAULT '',
    pr_url TEXT NOT NULL DEFAULT '',
    bundle_id INTEGER,
    updated_at TEXT NOT NULL
);

CREATE TABLE executions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    run_number INTEGER NOT NULL,
    bundle_id INTEGER,
    parent_id TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'full',
    status TEXT NOT NULL,
    phase TEXT NOT NULL DEFAULT '',
    branch TEXT NOT NULL DEFAULT '',
    commit_sha TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'bundle',
    framework TEXT NOT NULL,
    browser TEXT NOT NULL,
    environment TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT 'docker',
    totals TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL DEFAULT '',
    duration REAL NOT NULL DEFAULT 0
);
CREATE INDEX idx_exec_project ON executions(project_id);

CREATE TABLE results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    test_case_id TEXT NOT NULL,
    test_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    duration REAL NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT '{}',
    evidence TEXT NOT NULL DEFAULT '{}',
    analysis TEXT NOT NULL DEFAULT '{}',
    UNIQUE(execution_id, test_case_id)
);

CREATE TABLE healings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    execution_id TEXT NOT NULL,
    test_case_ids TEXT NOT NULL DEFAULT '[]',
    element_key TEXT NOT NULL,
    old_locator TEXT NOT NULL DEFAULT '{}',
    new_locator TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0,
    evidence TEXT NOT NULL DEFAULT '{}',
    validation TEXT NOT NULL DEFAULT '{}',
    original_code TEXT NOT NULL DEFAULT '',
    proposed_code TEXT NOT NULL DEFAULT '',
    rerun_execution_id TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'proposed',
    pr_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE defects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    execution_id TEXT NOT NULL,
    test_case_id TEXT NOT NULL,
    defect_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(execution_id, test_case_id)
);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL DEFAULT '',
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_audit_project ON audit_log(project_id);

CREATE TABLE ai_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL DEFAULT '',
    ts TEXT NOT NULL,
    agent TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 1,
    ok INTEGER NOT NULL DEFAULT 1,
    seconds REAL NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT ''
);
""",
    ),
    (
        2,
        """
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT '',
    owner_id TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    log TEXT NOT NULL DEFAULT '[]',
    activity TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    next_page TEXT NOT NULL DEFAULT '',
    notice TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_jobs_project ON jobs(project_id);
ALTER TABLE executions ADD COLUMN progress REAL NOT NULL DEFAULT 0;
""",
    ),
    (
        3,
        """
ALTER TABLE projects ADD COLUMN test_scope TEXT NOT NULL DEFAULT 'ui';
ALTER TABLE projects ADD COLUMN api_base_url TEXT NOT NULL DEFAULT '';
ALTER TABLE scenarios ADD COLUMN layer TEXT NOT NULL DEFAULT 'ui';
ALTER TABLE test_cases ADD COLUMN layer TEXT NOT NULL DEFAULT 'ui';
ALTER TABLE bundles ADD COLUMN layer TEXT NOT NULL DEFAULT 'ui';
CREATE TABLE api_endpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, key)
);
CREATE TABLE connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    part TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    env_name TEXT NOT NULL,
    secret INTEGER NOT NULL DEFAULT 1,
    value_enc TEXT NOT NULL DEFAULT '',
    meta TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, name, part)
);
CREATE INDEX idx_connections_project ON connections(project_id);
""",
    ),
    (
        4,
        """
CREATE TABLE mobile_config (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    platform TEXT NOT NULL DEFAULT 'android',
    app_source TEXT NOT NULL DEFAULT 'upload',
    apk_path TEXT NOT NULL DEFAULT '',
    apk_name TEXT NOT NULL DEFAULT '',
    package TEXT NOT NULL DEFAULT '',
    activity TEXT NOT NULL DEFAULT '',
    run_on TEXT NOT NULL DEFAULT 'emulator',
    device_serial TEXT NOT NULL DEFAULT '',
    device_label TEXT NOT NULL DEFAULT '',
    analysis TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);
""",
    ),
    (
        5,
        """
CREATE TABLE github_workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    branch TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    channels TEXT NOT NULL DEFAULT '[]',
    commit_sha TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    UNIQUE(repo, branch, project_id)
);
CREATE INDEX idx_workspaces_repo_branch ON github_workspaces(repo, branch);
""",
    ),
]


class Database:
    """Thread-safe: every call opens its own short-lived connection (WAL mode)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate_lock = threading.Lock()
        self.migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Run one write statement and return ``lastrowid``."""
        with self.connect() as conn:
            return conn.execute(sql, params).lastrowid or 0

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def transaction(self, statements: list[tuple[str, Sequence[Any]]]) -> None:
        with self.connect() as conn:
            for sql, params in statements:
                conn.execute(sql, params)

    def migrate(self) -> None:
        with self._migrate_lock, self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
            applied = {row[0] for row in conn.execute("SELECT version FROM schema_version")}
            for version, sql in MIGRATIONS:
                if version in applied:
                    continue
                for statement in [s.strip() for s in sql.split(";\n") if s.strip()]:
                    conn.execute(statement)
                conn.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
                LOGGER.info("Applied database migration %s", version)
