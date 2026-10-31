"""Service container: one object that wires every component together (shared by the Streamlit app and the tests)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from ats.analysis.defects import DefectBuilder
from ats.analysis.healing import HealingEngine
from ats.analysis.pipeline import FailureAnalyzer
from ats.analysis.service import AnalysisService
from ats.automation.bundle_store import BundleStore
from ats.automation.script_service import ScriptService
from ats.config import get_settings
from ats.db import Database
from ats.discovery.service import DiscoveryService
from ats.execution.executor import ExecutionService
from ats.generation.scenarios import ScenarioService
from ats.generation.testcases import TestCaseService
from ats.github.service import GitHubService
from ats.repository import Repository
from ats.reporting import ReportService
from ats.security import register_secret


class TokenVault:
    """GitHub tokens live only in process memory, per project, and are never written to disk or to the database."""

    def __init__(self) -> None:
        self._tokens: dict[str, str] = {}
        self._lock = threading.Lock()

    def set(self, project_id: str, token: str) -> None:
        token = token.strip()
        if not token:
            return
        register_secret(token)
        with self._lock:
            self._tokens[project_id] = token

    def get(self, project_id: str) -> str:
        with self._lock:
            return self._tokens.get(project_id, "")

    def clear(self, project_id: str) -> None:
        with self._lock:
            self._tokens.pop(project_id, None)


@dataclass
class Services:
    repo: Repository
    store: BundleStore
    discovery: DiscoveryService
    scenarios: ScenarioService
    testcases: TestCaseService
    scripts: ScriptService
    executor: ExecutionService
    analysis: AnalysisService
    github: GitHubService
    reports: ReportService
    tokens: TokenVault = field(default_factory=TokenVault)

    @property
    def healer(self) -> HealingEngine:
        return self.analysis.healer


def build_services(repo: Repository | None = None) -> Services:
    repo = repo or Repository(Database(get_settings().db_path))
    store = BundleStore()
    tokens = TokenVault()
    executor = ExecutionService(repo)
    analyzer = FailureAnalyzer(repo)
    healer = HealingEngine(repo, executor, analyzer, store=store)
    github = GitHubService(repo, store)

    def project_token(ctx_project_id: str) -> str:
        return tokens.get(ctx_project_id)

    def on_verified(ctx, healing_ids):  # noqa: ANN001 - signature fixed by AnalysisService
        github.pr_callback(lambda: project_token(ctx.project.id))(ctx, healing_ids)

    analysis = AnalysisService(repo, executor, analyzer, healer, DefectBuilder(repo), on_verified=on_verified)
    executor.post_run = analysis.post_run
    return Services(
        repo=repo, store=store, discovery=DiscoveryService(repo), scenarios=ScenarioService(repo), testcases=TestCaseService(repo),
        scripts=ScriptService(repo, store), executor=executor, analysis=analysis, github=github, reports=ReportService(repo), tokens=tokens,
    )  # fmt: skip
