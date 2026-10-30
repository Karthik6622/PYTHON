"""Configuration. Everything comes from environment variables (optionally a local .env file); nothing is hardcoded.

Secrets entered through the Settings dialog are kept in memory only and are never written to disk.
"""

from __future__ import annotations

import contextvars
import json
import os
import sys
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


def is_hosted() -> bool:
    """True on a shared deployment (Streamlit Cloud, Docker, a Linux server without a screen); False on the user's own desktop.

    STUDIO_HOSTED=1/0 forces the answer."""
    forced = _env("STUDIO_HOSTED").lower()
    if forced in {"1", "true", "yes", "on"}:
        return True
    if forced in {"0", "false", "no", "off"}:
        return False
    return not (os.name == "nt" or sys.platform == "darwin" or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")))


# The secrets of the visitor whose request is being served. The UI binds it for its own thread and every worker thread it starts
# (agent, terminal), so one visitor's GitHub token or API key can never be used for another visitor's work.
_session_secrets: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar("rk_session_secrets", default=None)
_by_window: dict[str, dict[str, str]] = {}
_by_window_lock = threading.Lock()
_SECRET_KEYS = ("nvidia_api_key", "github_token")


class Settings:
    """Read-only view of the configuration plus in-memory secret overrides."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._overrides: dict[str, str] = {}

    # ---- secrets: this visitor's own value first, then the environment (the deployment's own key)
    def session_store(self, window: str) -> dict[str, str]:
        """Where the secrets of one browser window live. On a hosted deployment every window has its own (in memory only);
        on the user's own computer all windows share one, so a token is entered once."""
        if not is_hosted():
            return self._overrides
        with _by_window_lock:
            store = _by_window.pop(window, None)
            if store is None:
                store = {}
            _by_window[window] = store  # most recently used last
            while len(_by_window) > 500:
                _by_window.pop(next(iter(_by_window)))
            return store

    def bind_session(self, store: dict[str, str] | None) -> None:
        _session_secrets.set(store)

    def current_session(self) -> dict[str, str] | None:
        return _session_secrets.get()

    def _secret(self, key: str) -> str:
        scoped = _session_secrets.get()
        if scoped is not None and scoped.get(key):
            return scoped[key]
        return self._overrides.get(key, "") if not (scoped is not None and is_hosted()) else ""

    @property
    def nvidia_api_key(self) -> str:
        return self._secret("nvidia_api_key") or _env("NVIDIA_API_KEY")

    @property
    def github_token(self) -> str:
        """The visitor's own token. A GITHUB_TOKEN in the deployment's environment is used on the user's own computer, but on a shared
        deployment only when ALLOW_SHARED_GITHUB_TOKEN=1 (it would otherwise let every visitor act as its owner)."""
        own = self._secret("github_token")
        if own:
            return own
        if is_hosted() and not _env_bool("ALLOW_SHARED_GITHUB_TOKEN", False):
            return ""
        return _env("GITHUB_TOKEN")

    @property
    def github_client_id(self) -> str:
        """Client id of a GitHub OAuth App with Device Flow enabled: lets visitors sign in with GitHub instead of pasting a token."""
        return _env("GITHUB_CLIENT_ID")

    def set_secrets(self, nvidia_api_key: str | None = None, github_token: str | None = None, store: dict[str, str] | None = None) -> None:
        with self._lock:
            target = store if store is not None else (_session_secrets.get() if _session_secrets.get() is not None else self._overrides)
            if nvidia_api_key is not None:
                target["nvidia_api_key"] = nvidia_api_key.strip()
            if github_token is not None:
                target["github_token"] = github_token.strip()

    def clear_github(self) -> None:
        with self._lock:
            for target in (_session_secrets.get(), self._overrides):
                if target is not None:
                    target.pop("github_token", None)
                    target.pop("github_user", None)

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
        """How long to wait for the model to send anything (large models queue for a while before the first word)."""
        return float(max(30, _env_int("NVIDIA_TIMEOUT_SECONDS", 600)))

    @property
    def nvidia_max_retries(self) -> int:
        return max(0, min(6, _env_int("NVIDIA_MAX_RETRIES", 3)))

    @property
    def agent_turn_retries(self) -> int:
        """Extra attempts for one model turn when the connection drops in the middle of the reply."""
        return max(0, min(6, _env_int("AGENT_TURN_RETRIES", 2)))

    @property
    def model_fallback(self) -> bool:
        """When the chosen model keeps timing out, carry on with the next model instead of ending the task (a notice says so)."""
        return _env_bool("NVIDIA_MODEL_FALLBACK", True)

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
    def scratch_path(self) -> Path:
        """Folder used when no repository is connected (SCRATCH_PATH, else <workspaces>/scratch)."""
        configured = _env("SCRATCH_PATH")
        path = Path(configured).expanduser() if configured else PROJECT_ROOT / "workspaces" / "scratch"
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

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
