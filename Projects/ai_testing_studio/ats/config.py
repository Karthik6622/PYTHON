"""Centralised configuration. Every setting comes from environment variables (or .streamlit/secrets.toml).

Nothing in the application hard-codes a model name, endpoint, key or token: change them here or in ``.env``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

APP_NAME = "AI Autonomous Testing Studio"
APP_ICON = "🧪"


def _secret(name: str) -> str | None:
    """Value from the process environment, then from Streamlit secrets (when running inside Streamlit)."""
    value = os.environ.get(name)
    if value not in (None, ""):
        return value
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # noqa: BLE001 - secrets are optional and may not exist outside a Streamlit run
        pass
    return None


def _str(name: str, default: str) -> str:
    return _secret(name) or default


def _int(name: str, default: int) -> int:
    try:
        return int(_secret(name) or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_secret(name) or default)
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = _secret(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ModelSettings:
    provider: str
    name: str
    base_url: str
    api_key: str = field(repr=False)
    temperature: float
    top_p: float
    max_tokens: int
    seed: int | None
    enable_thinking: bool
    timeout_seconds: int
    max_retries: int
    context_budget_tokens: int
    use_vision: bool

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.name)


@dataclass(frozen=True)
class ExecutionSettings:
    mode: str
    timeout_seconds: int
    docker_cpus: str
    docker_memory: str
    docker_shm_size: str
    docker_network: str
    playwright_version: str
    images: dict[str, str]


@dataclass(frozen=True)
class HealingSettings:
    enabled: bool
    max_attempts: int
    min_confidence: float
    approval_policy: str
    recheck_flaky: bool


@dataclass(frozen=True)
class Settings:
    model: ModelSettings
    execution: ExecutionSettings
    healing: HealingSettings
    database_url: str
    data_dir: Path
    allow_private_network: bool
    discovery_timeout_seconds: int
    discovery_default_max_pages: int
    discovery_default_depth: int
    github_api_url: str
    github_token: str = field(default="", repr=False)

    @property
    def db_path(self) -> Path:
        """Filesystem path of the SQLite database (the only backend implemented today)."""
        url = self.database_url
        if not url.startswith("sqlite:///"):
            raise ValueError("Only sqlite:/// DATABASE_URL values are supported in this release.")
        path = Path(url[len("sqlite:///") :])
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def secure_dir(self) -> Path:
        """Holds Playwright storage-state files. Never included in reports, exports or ZIPs."""
        return self.data_dir / "secure"


def load_settings() -> Settings:
    seed_raw = _secret("MODEL_SEED")
    data_dir = Path(_str("DATA_DIR", "data"))
    data_dir = data_dir if data_dir.is_absolute() else ROOT_DIR / data_dir
    pw = _str("PLAYWRIGHT_VERSION", "1.49.0")
    model = ModelSettings(
        provider=_str("MODEL_PROVIDER", "nvidia"),
        name=_str("MODEL_NAME", "nvidia/nemotron-3.5-super-vl-120b-a12b"),
        base_url=_str("MODEL_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        api_key=_secret("MODEL_API_KEY") or _secret("NVIDIA_API_KEY") or "",
        temperature=_float("MODEL_TEMPERATURE", 0.6),
        top_p=_float("MODEL_TOP_P", 0.95),
        max_tokens=_int("MODEL_MAX_TOKENS", 16384),
        seed=int(seed_raw) if seed_raw and seed_raw.lstrip("-").isdigit() else None,
        enable_thinking=_bool("MODEL_ENABLE_THINKING", True),
        timeout_seconds=_int("MODEL_TIMEOUT_SECONDS", 300),
        max_retries=max(_int("MODEL_MAX_RETRIES", 3), 1),
        context_budget_tokens=_int("MODEL_CONTEXT_BUDGET_TOKENS", 60000),
        use_vision=_bool("MODEL_USE_VISION", True),
    )
    execution = ExecutionSettings(
        mode=_str("EXECUTION_MODE", "docker").lower(),
        timeout_seconds=_int("EXECUTION_TIMEOUT_SECONDS", 1800),
        docker_cpus=_str("DOCKER_CPUS", "2"),
        docker_memory=_str("DOCKER_MEMORY", "3g"),
        docker_shm_size=_str("DOCKER_SHM_SIZE", "1g"),
        docker_network=_str("DOCKER_NETWORK", "bridge"),
        playwright_version=pw,
        images={
            "playwright_python": _str("RUNNER_IMAGE_PLAYWRIGHT_PYTHON", f"mcr.microsoft.com/playwright/python:v{pw}-jammy"),
            "playwright_node": _str("RUNNER_IMAGE_PLAYWRIGHT_NODE", f"mcr.microsoft.com/playwright:v{pw}-jammy"),
            "selenium_python": _str("RUNNER_IMAGE_SELENIUM_PYTHON", "ats-runner-selenium-python"),
            "selenium_java": _str("RUNNER_IMAGE_SELENIUM_JAVA", "ats-runner-selenium-java"),
        },
    )
    healing = HealingSettings(
        enabled=_bool("HEALING_ENABLED", True),
        max_attempts=max(_int("HEALING_MAX_ATTEMPTS", 2), 0),
        min_confidence=_float("HEALING_MIN_CONFIDENCE", 0.6),
        approval_policy=_str("HEALING_APPROVAL_POLICY", "manual").lower(),
        recheck_flaky=_bool("RECHECK_FLAKY", True),
    )
    return Settings(
        model=model,
        execution=execution,
        healing=healing,
        database_url=_str("DATABASE_URL", "sqlite:///data/studio.db"),
        data_dir=data_dir,
        allow_private_network=_bool("ALLOW_PRIVATE_NETWORK", False),
        discovery_timeout_seconds=_int("DISCOVERY_TIMEOUT_SECONDS", 240),
        discovery_default_max_pages=_int("DISCOVERY_DEFAULT_MAX_PAGES", 8),
        discovery_default_depth=_int("DISCOVERY_DEFAULT_DEPTH", 2),
        github_api_url=_str("GITHUB_API_URL", "https://api.github.com").rstrip("/"),
        github_token=_secret("GITHUB_TOKEN") or "",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
