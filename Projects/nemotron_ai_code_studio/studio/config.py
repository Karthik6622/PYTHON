"""Configuration. Everything comes from environment variables (optionally a local .env file); nothing is hardcoded.

Secrets entered through the Settings dialog are kept in memory only and are never written to disk.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_NVIDIA_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"


def _load_env_file(path: Path) -> None:
    """Minimal .env loader. Real environment variables win over the file."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if value and value[0] in "\"'" and value[-1:] == value[0] and len(value) >= 2:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key and key not in os.environ:
            os.environ[key] = value


for _candidate in (PROJECT_ROOT / ".env",):
    _load_env_file(_candidate)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


class Settings:
    """Read-only view of the configuration plus in-memory secret overrides."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._overrides: dict[str, str] = {}

    # ---- secrets (environment first, then in-memory overrides from the Settings dialog)
    @property
    def nvidia_api_key(self) -> str:
        return self._overrides.get("nvidia_api_key") or _env("NVIDIA_API_KEY")

    @property
    def github_token(self) -> str:
        return self._overrides.get("github_token") or _env("GITHUB_TOKEN")

    def set_secrets(self, nvidia_api_key: str | None = None, github_token: str | None = None) -> None:
        with self._lock:
            if nvidia_api_key is not None:
                self._overrides["nvidia_api_key"] = nvidia_api_key.strip()
            if github_token is not None:
                self._overrides["github_token"] = github_token.strip()

    def secret_values(self) -> list[str]:
        """Secret strings that must never appear in output or logs."""
        return [value for value in (self.nvidia_api_key, self.github_token) if value and len(value) >= 8]

    # ---- plain settings
    @property
    def nvidia_base_url(self) -> str:
        return _env("NVIDIA_BASE_URL", DEFAULT_NVIDIA_BASE_URL).rstrip("/")

    @property
    def nvidia_model(self) -> str:
        return _env("NVIDIA_MODEL", DEFAULT_NVIDIA_MODEL)

    @property
    def nvidia_extra_body(self) -> dict[str, Any]:
        """Optional model-specific request fields as JSON (for example chat_template_kwargs)."""
        raw = _env("NVIDIA_EXTRA_BODY_JSON")
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except ValueError:
            return {}
        return value if isinstance(value, dict) else {}

    @property
    def nvidia_timeout_seconds(self) -> float:
        return float(_env_int("NVIDIA_TIMEOUT_SECONDS", 180))

    @property
    def nvidia_max_retries(self) -> int:
        return max(0, min(6, _env_int("NVIDIA_MAX_RETRIES", 3)))

    @property
    def context_window_tokens(self) -> int:
        return max(8_000, _env_int("NVIDIA_CONTEXT_TOKENS", 100_000))

    @property
    def context_budget_tokens(self) -> int:
        """Tokens the context engine may spend on repository files for one request."""
        return max(2_000, _env_int("CONTEXT_BUDGET_TOKENS", 24_000))

    @property
    def workspace_path(self) -> Path:
        """Folder that holds cloned repositories: the one the user picked, else WORKSPACE_PATH, else ./workspaces."""
        configured = self._overrides.get("workspace_path") or _env("WORKSPACE_PATH")
        path = Path(configured).expanduser() if configured else PROJECT_ROOT / "workspaces"
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

    @property
    def workspace_configured(self) -> bool:
        """True when a clone folder was picked by the user or set with WORKSPACE_PATH."""
        return bool(self._overrides.get("workspace_path") or _env("WORKSPACE_PATH"))

    def set_workspace_path(self, path: str | Path | None) -> None:
        with self._lock:
            if path:
                self._overrides["workspace_path"] = str(path)
            else:
                self._overrides.pop("workspace_path", None)

    @property
    def backend_host(self) -> str:
        return _env("BACKEND_HOST", "127.0.0.1")

    @property
    def backend_port(self) -> int:
        return _env_int("BACKEND_PORT", 8000)

    @property
    def allowed_origins(self) -> list[str]:
        configured = _env("ALLOWED_ORIGINS")
        if configured:
            return [item.strip() for item in configured.split(",") if item.strip()]
        return ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173"]

    @property
    def allowed_hosts(self) -> set[str]:
        return {"localhost", "127.0.0.1", "[::1]", "testserver"}

    @property
    def terminal_shell(self) -> str:
        """Optional shell executable (for example bash). Empty means the platform default."""
        return _env("TERMINAL_SHELL")

    @property
    def command_timeout_seconds(self) -> int:
        return max(5, _env_int("COMMAND_TIMEOUT_SECONDS", 120))

    @property
    def terminal_timeout_seconds(self) -> int:
        """Time limit for commands typed in the terminal (installs, test suites and scripts can take a while)."""
        return max(10, _env_int("TERMINAL_TIMEOUT_SECONDS", 1800))

    @property
    def agent_max_steps(self) -> int:
        return max(2, min(60, _env_int("AGENT_MAX_STEPS", 30)))

    @property
    def auto_validate(self) -> bool:
        return _env_bool("AUTO_VALIDATE", True)

    @property
    def max_file_bytes(self) -> int:
        return max(10_000, _env_int("MAX_FILE_BYTES", 1_000_000))


settings = Settings()
