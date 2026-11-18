"""Per-project connections: named credentials and settings, encrypted at rest (Fernet), exposed to runs as environment variables.

A *connection* is a named group (for example ``payments-oauth``) of one or more variables (``CLIENT_ID``, ``CLIENT_SECRET``...). Each
variable is one row in the ``connections`` table: its value is always encrypted, the ``secret`` flag decides whether the UI may show it
again. Values never reach logs, audit entries or generated files - generated projects only contain the variable NAMES.
"""

from __future__ import annotations

import base64
import hashlib
import imaplib
import os
import re
import smtplib
import ssl
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from cryptography.fernet import Fernet, InvalidToken

from ats.config import get_settings, lookup_secret
from ats.errors import StudioError
from ats.logging_setup import get_logger
from ats.repository import Project, Repository
from ats.security import UnsafeURLError, is_private_address, mask, register_secret, validate_target_url

LOGGER = get_logger("connections")
KEY_FILE = "connections.key"
MASKED = "\u2022" * 8
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,79}$")
CONNECTION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,59}$")
# Names a run must never be able to override: they steer the interpreter, the loader or the runner itself.
RESERVED_ENV = {
    "PATH", "PATHEXT", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUTF8", "LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES", "NODE_OPTIONS",
    "SYSTEMROOT", "COMSPEC", "WINDIR", "HOME", "USERPROFILE", "TEMP", "TMP", "BASE_URL", "BROWSER", "HEADLESS", "CI", "IGNORE_HTTPS_ERRORS",
}  # fmt: skip


class ConnectionProblem(StudioError):
    default_message = "The connection could not be saved."


@dataclass(frozen=True)
class PartSpec:
    part: str
    label: str
    env: str
    secret: bool = True
    required: bool = True


@dataclass(frozen=True)
class MetaSpec:
    key: str
    label: str
    default: str
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class KindSpec:
    key: str
    label: str
    description: str
    parts: tuple[PartSpec, ...]
    meta: tuple[MetaSpec, ...] = ()


KINDS: dict[str, KindSpec] = {
    "api_key": KindSpec(
        "api_key", "API key", "A key sent in a header or as a query parameter.",
        (PartSpec("value", "API key", "API_KEY"),),
        (MetaSpec("placement", "Send it in", "header", ("header", "query")), MetaSpec("param", "Header / parameter name", "X-API-Key")),
    ),
    "bearer": KindSpec("bearer", "Bearer token", "Sent as 'Authorization: Bearer <token>'.", (PartSpec("value", "Token", "BEARER_TOKEN"),)),
    "basic": KindSpec(
        "basic", "Basic auth", "Username and password sent as HTTP Basic authentication.",
        (PartSpec("username", "Username", "BASIC_USERNAME", secret=False), PartSpec("password", "Password", "BASIC_PASSWORD")),
    ),
    "oauth2": KindSpec(
        "oauth2", "OAuth2 client credentials", "The generated tests fetch a token from the token URL and cache it for the run.",
        (
            PartSpec("token_url", "Token URL", "OAUTH_TOKEN_URL", secret=False),
            PartSpec("client_id", "Client ID", "CLIENT_ID"),
            PartSpec("client_secret", "Client secret", "CLIENT_SECRET"),
            PartSpec("scope", "Scope (optional)", "OAUTH_SCOPE", secret=False, required=False),
        ),
        (MetaSpec("auth_style", "Send client credentials", "body", ("body", "basic")),),
    ),
    "custom": KindSpec("custom", "Custom value", "Any variable your tests read (for example a tenant id or a test data value).", (PartSpec("value", "Value", "CUSTOM_VALUE"),)),
    "smtp": KindSpec(
        "smtp", "Mail server (SMTP)", "Used by tests that send mail.",
        (
            PartSpec("host", "SMTP host", "SMTP_HOST", secret=False), PartSpec("port", "SMTP port", "SMTP_PORT", secret=False),
            PartSpec("username", "Username", "SMTP_USERNAME", secret=False, required=False), PartSpec("password", "Password", "SMTP_PASSWORD", required=False),
            PartSpec("from_addr", "From address", "SMTP_FROM", secret=False, required=False),
        ),
    ),
    "imap": KindSpec(
        "imap", "Mailbox (IMAP)", "Used by tests that read verification mails.",
        (
            PartSpec("host", "IMAP host", "IMAP_HOST", secret=False), PartSpec("port", "IMAP port", "IMAP_PORT", secret=False),
            PartSpec("username", "Username", "IMAP_USERNAME", secret=False), PartSpec("password", "Password", "IMAP_PASSWORD"),
        ),
    ),
    "ui_account": KindSpec(
        "ui_account", "UI test account", "The account UI tests and discovery sign in with.",
        (PartSpec("username", "Username", "TEST_APP_USERNAME", secret=False), PartSpec("password", "Password", "TEST_APP_PASSWORD")),
    ),
}

TEMPLATES: list[dict[str, Any]] = [
    {"label": "API key in a header (API_KEY)", "kind": "api_key", "name": "api-key"},
    {"label": "Bearer token (BEARER_TOKEN)", "kind": "bearer", "name": "bearer-token"},
    {"label": "OAuth2 client credentials (CLIENT_ID / CLIENT_SECRET)", "kind": "oauth2", "name": "oauth-client"},
    {"label": "Basic auth (BASIC_USERNAME / BASIC_PASSWORD)", "kind": "basic", "name": "basic-auth"},
    {"label": "Mail server for sending (SMTP_HOST ...)", "kind": "smtp", "name": "smtp"},
    {"label": "Mailbox for verification mails (IMAP_HOST ...)", "kind": "imap", "name": "imap"},
    {"label": "UI test account (TEST_APP_USERNAME / TEST_APP_PASSWORD)", "kind": "ui_account", "name": "ui-account"},
    {"label": "Custom variable", "kind": "custom", "name": "custom-value"},
]


# ----------------------------------------------------------------------------------------
# encryption
# ----------------------------------------------------------------------------------------
def _fernet_key(raw: str) -> bytes:
    """``ATS_SECRET_KEY`` may be a real Fernet key; any other passphrase is stretched into one."""
    try:
        if len(base64.urlsafe_b64decode(raw.encode())) == 32:
            return raw.encode()
    except ValueError:
        pass
    return base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())


def _restrict(path: Path) -> None:
    """Make the key file readable by the current user only, as far as the operating system allows."""
    try:
        os.chmod(path, 0o600)
        if os.name == "nt":
            user = os.environ.get("USERNAME", "")
            if user:
                subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"], capture_output=True, timeout=15, check=False)  # noqa: S603,S607
    except (OSError, subprocess.TimeoutExpired):
        LOGGER.warning("Could not tighten the permissions of the connection key file")


class SecretBox:
    """Fernet encryption. The key is ``ATS_SECRET_KEY`` when set, otherwise generated once into the secure folder."""

    _lock = threading.Lock()

    def __init__(self, key: bytes | None = None) -> None:
        self._fernet = Fernet(key) if key else None

    @property
    def fernet(self) -> Fernet:
        if self._fernet is None:
            self._fernet = Fernet(self._load_key())
        return self._fernet

    @classmethod
    def _load_key(cls) -> bytes:
        configured = lookup_secret("ATS_SECRET_KEY").strip()
        if configured:
            return _fernet_key(configured)
        path = get_settings().secure_dir / KEY_FILE
        with cls._lock:
            if path.is_file():
                return path.read_bytes().strip()
            path.parent.mkdir(parents=True, exist_ok=True)
            key = Fernet.generate_key()
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                return path.read_bytes().strip()
            with os.fdopen(fd, "wb") as handle:
                handle.write(key)
            _restrict(path)
            return key

    def encrypt(self, text: str) -> str:
        return self.fernet.encrypt(text.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            return self.fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise ConnectionProblem("A saved value could not be decrypted. The secret key changed; enter the value again.") from exc


# ----------------------------------------------------------------------------------------
# value objects
# ----------------------------------------------------------------------------------------
@dataclass
class ConnectionPart:
    part: str
    label: str
    env_name: str
    secret: bool
    configured: bool
    value: str = ""  # only ever filled for non-secret parts

    @property
    def shown(self) -> str:
        return (MASKED if self.configured else "") if self.secret else self.value


@dataclass
class Connection:
    name: str
    kind: str
    parts: list[ConnectionPart] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)
    updated_at: str = ""

    @property
    def label(self) -> str:
        return KINDS[self.kind].label if self.kind in KINDS else self.kind

    @property
    def env_names(self) -> list[str]:
        return [p.env_name for p in self.parts if p.configured]


def clean_env_name(name: str) -> str:
    text = (name or "").strip()
    if not ENV_NAME.match(text):
        raise ConnectionProblem(f"'{text}' is not a valid variable name. Use letters, digits and underscores, starting with a letter.")
    if text.upper() in RESERVED_ENV:
        raise ConnectionProblem(f"{text} is reserved by the system and cannot be used as a variable name.")
    return text


def apply_auth(descriptor: dict[str, Any], env: dict[str, str], token: str = "") -> tuple[dict[str, str], dict[str, str], tuple[str, str] | None]:
    """Headers, query parameters and basic-auth pair that a connection descriptor adds to a request (pure; used by the connection test)."""
    kind = descriptor.get("type")
    if kind == "api_key":
        value = env.get(descriptor.get("env", ""), "")
        if descriptor.get("in") == "query":
            return {}, {descriptor.get("name", "api_key"): value}, None
        return {descriptor.get("name", "X-API-Key"): value}, {}, None
    if kind == "bearer":
        return {"Authorization": f"Bearer {env.get(descriptor.get('env', ''), '')}"}, {}, None
    if kind == "basic":
        return {}, {}, (env.get(descriptor.get("username_env", ""), ""), env.get(descriptor.get("password_env", ""), ""))
    if kind == "oauth2" and token:
        return {"Authorization": f"Bearer {token}"}, {}, None
    return {}, {}, None


# ----------------------------------------------------------------------------------------
# service
# ----------------------------------------------------------------------------------------
class ConnectionService:
    def __init__(self, repo: Repository, box: SecretBox | None = None) -> None:
        self.repo = repo
        self.box = box or SecretBox()

    # ------------------------------------------------------------------ reading
    def _rows(self, project_id: str, owner_id: str | None = None) -> list[dict[str, Any]]:
        if owner_id is not None:
            self.repo.get_project(project_id, owner_id)  # raises NotFoundError for somebody else's project
        return self.repo.list_connection_rows(project_id, owner_id)

    def list_connections(self, project_id: str, owner_id: str) -> list[Connection]:
        """Saved connections of a project owned by ``owner_id``. Secret values are never included."""
        grouped: dict[str, Connection] = {}
        for row in self._rows(project_id, owner_id):
            spec = KINDS.get(row["kind"])
            label = next((p.label for p in spec.parts if p.part == row["part"]), row["part"] or "Value") if spec else row["part"]
            connection = grouped.setdefault(row["name"], Connection(row["name"], row["kind"], meta=dict(row["meta"]), updated_at=row["updated_at"]))
            shown = ""
            if not row["secret"] and row["value_enc"]:
                try:
                    shown = self.box.decrypt(row["value_enc"])
                except ConnectionProblem:
                    shown = ""
            connection.parts.append(ConnectionPart(row["part"], label, row["env_name"], row["secret"], bool(row["value_enc"]), shown))
            connection.updated_at = max(connection.updated_at, row["updated_at"])
        return list(grouped.values())

    def get(self, project_id: str, owner_id: str, name: str) -> Connection | None:
        return next((c for c in self.list_connections(project_id, owner_id) if c.name == name), None)

    def names(self, project_id: str) -> list[str]:
        """Connection names (never values) - what the AI and the generated tests refer to."""
        return sorted({row["name"] for row in self.repo.list_connection_rows(project_id) if row["value_enc"]})

    def variable_names(self, project_id: str) -> list[str]:
        return sorted({row["env_name"] for row in self.repo.list_connection_rows(project_id) if row["value_enc"]})

    def environment(self, project_id: str, owner_id: str | None = None) -> dict[str, str]:
        """Decrypted ``{ENV_NAME: value}`` for a run. Every value is registered for masking before it leaves this method."""
        env: dict[str, str] = {}
        for row in self._rows(project_id, owner_id):
            if not row["value_enc"]:
                continue
            try:
                value = self.box.decrypt(row["value_enc"])
            except ConnectionProblem:
                LOGGER.warning("Skipping connection variable %s: it could not be decrypted", row["env_name"])
                continue
            if value:
                register_secret(value)
                env[row["env_name"]] = value
        return env

    def descriptors(self, project_id: str) -> dict[str, dict[str, Any]]:
        """``{connection name: how to authenticate}`` using variable NAMES only. Written into generated projects (config/api.json)."""
        result: dict[str, dict[str, Any]] = {}
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in self.repo.list_connection_rows(project_id):
            if row["value_enc"]:
                grouped.setdefault(row["name"], []).append(row)
        for name, rows in grouped.items():
            env = {r["part"]: r["env_name"] for r in rows}
            meta = rows[0]["meta"]
            kind = rows[0]["kind"]
            if kind == "api_key":
                result[name] = {"type": "api_key", "env": env.get("value", ""), "in": meta.get("placement", "header"), "name": meta.get("param") or "X-API-Key"}
            elif kind == "bearer":
                result[name] = {"type": "bearer", "env": env.get("value", "")}
            elif kind == "basic":
                result[name] = {"type": "basic", "username_env": env.get("username", ""), "password_env": env.get("password", "")}
            elif kind == "oauth2":
                result[name] = {
                    "type": "oauth2", "token_url_env": env.get("token_url", ""), "client_id_env": env.get("client_id", ""), "client_secret_env": env.get("client_secret", ""),
                    "scope_env": env.get("scope", ""), "auth_style": meta.get("auth_style", "body"),
                }  # fmt: skip
            else:
                result[name] = {"type": kind, "env": env.get("value", ""), "vars": env}
        return result

    # ------------------------------------------------------------------ writing
    def save(
        self, project_id: str, owner_id: str, name: str, kind: str, values: dict[str, str] | None = None, envs: dict[str, str] | None = None,
        secrets: dict[str, bool] | None = None, meta: dict[str, str] | None = None,
    ) -> Connection:  # fmt: skip
        """Create or update a connection. A blank value keeps the stored one (secrets are never shown again, so editing must not need them)."""
        self.repo.get_project(project_id, owner_id)
        spec = KINDS.get(kind)
        if spec is None:
            raise ConnectionProblem("Choose a connection type.")
        name = (name or "").strip()
        if not CONNECTION_NAME.match(name):
            raise ConnectionProblem("Give the connection a short name (letters, digits, spaces, '-', '_' or '.').")
        values, envs, secrets = values or {}, envs or {}, secrets or {}
        rows = self.repo.list_connection_rows(project_id, owner_id)
        existing = {r["part"]: r for r in rows if r["name"] == name}
        if existing and next(iter(existing.values()))["kind"] != kind:
            raise ConnectionProblem(f"'{name}' already exists as another type. Delete it first or choose a different name.")
        old_meta = next(iter(existing.values()))["meta"] if existing else {}
        taken = {r["env_name"].upper() for r in rows if r["name"] != name}
        meta_clean = {m.key: (meta or {}).get(m.key) or old_meta.get(m.key) or m.default for m in spec.meta}
        for item in spec.meta:
            if item.options and meta_clean[item.key] not in item.options:
                raise ConnectionProblem(f"'{meta_clean[item.key]}' is not an allowed choice for {item.label}.")
        pending: list[tuple[PartSpec, str, bool, str | None]] = []
        chosen: set[str] = set()
        for part in spec.parts:
            env = clean_env_name(envs.get(part.part) or (existing[part.part]["env_name"] if part.part in existing else part.env))
            if env.upper() in taken or env.upper() in chosen:
                raise ConnectionProblem(f"The variable name {env} is already used by another connection.")
            chosen.add(env.upper())
            secret = bool(secrets.get(part.part, existing[part.part]["secret"] if part.part in existing else part.secret)) if kind == "custom" else part.secret
            raw = values.get(part.part) or ""
            value = raw.strip("\r\n") if secret else raw.strip()
            if not value and part.part not in existing:
                if part.required:
                    raise ConnectionProblem(f"Enter a value for {part.label}.")
                continue
            if part.part == "token_url" and value and not re.match(r"^https?://", value):
                raise ConnectionProblem("The token URL must start with http:// or https://.")
            pending.append((part, env, secret, self.box.encrypt(value) if value else None))
            if value and secret:
                register_secret(value)
        for part, env, secret, encrypted in pending:
            self.repo.save_connection_row(project_id, owner_id, name, part.part, kind, env, secret, encrypted, meta_clean)
        self.repo.audit(project_id, "user", "connection.saved", "connection", {"name": name, "kind": kind, "variables": [env for _, env, _, _ in pending]})
        return self.get(project_id, owner_id, name) or Connection(name, kind)

    def delete(self, project_id: str, owner_id: str, name: str) -> None:
        self.repo.get_project(project_id, owner_id)
        self.repo.delete_connection(project_id, name)
        self.repo.audit(project_id, "user", "connection.deleted", "connection", {"name": name})

    # ------------------------------------------------------------------ connection tests (messages never contain a value)
    @staticmethod
    def _check_host(host: str) -> None:
        if not host:
            raise ConnectionProblem("No host is configured.")
        if not get_settings().allow_private_network and is_private_address(host):
            raise ConnectionProblem("That address is on a private or local network. Set ALLOW_PRIVATE_NETWORK=true to allow it.")

    def fetch_token(self, descriptor: dict[str, Any], env: dict[str, str], verify: bool = True) -> str:
        url = env.get(descriptor.get("token_url_env", ""), "")
        try:
            validate_target_url(url, get_settings().allow_private_network)
        except UnsafeURLError as exc:
            raise ConnectionProblem(str(exc)) from exc
        data = {"grant_type": "client_credentials"}
        scope = env.get(descriptor.get("scope_env", ""), "")
        if scope:
            data["scope"] = scope
        client_id, client_secret = env.get(descriptor.get("client_id_env", ""), ""), env.get(descriptor.get("client_secret_env", ""), "")
        auth = None
        if descriptor.get("auth_style") == "basic":
            auth = (client_id, client_secret)
        else:
            data.update({"client_id": client_id, "client_secret": client_secret})
        with httpx.Client(timeout=15, follow_redirects=False, verify=verify) as client:
            response = client.post(url, data=data, auth=auth, headers={"Accept": "application/json"})
        if response.status_code >= 400:
            raise ConnectionProblem(f"The token endpoint answered HTTP {response.status_code}. Check the client id, secret and scope.")
        try:
            token = str(response.json().get("access_token") or "")
        except ValueError:
            token = ""
        if not token:
            raise ConnectionProblem("The token endpoint did not return an access_token.")
        register_secret(token)
        return token

    def test_api(self, project: Project, owner_id: str, name: str, path: str = "") -> str:
        """GET the API base URL (plus ``path``) with the named connection's authentication. Returns a safe, human readable result."""
        self.repo.get_project(project.id, owner_id)
        descriptor = self.descriptors(project.id).get(name)
        if descriptor is None:
            raise ConnectionProblem("Save the connection first.")
        env = self.environment(project.id, owner_id)
        try:
            url = validate_target_url(urljoin(project.api_url.rstrip("/") + "/", path.lstrip("/")), get_settings().allow_private_network)
        except UnsafeURLError as exc:
            raise ConnectionProblem(str(exc)) from exc
        verify = not project.limits.ignore_https_errors
        try:
            token = self.fetch_token(descriptor, env, verify) if descriptor.get("type") == "oauth2" else ""
            headers, params, basic = apply_auth(descriptor, env, token)
            with httpx.Client(timeout=15, follow_redirects=False, verify=verify) as client:
                response = client.get(url, headers=headers, params=params, auth=basic)
        except httpx.HTTPError as exc:
            return mask(f"Could not reach {url}: {type(exc).__name__}.")
        verdict = "accepted" if response.status_code < 400 else "rejected the credentials" if response.status_code in (401, 403) else "answered with an error"
        return mask(f"{url} {verdict} (HTTP {response.status_code}) using '{name}'.")

    def test_mail(self, project_id: str, owner_id: str, name: str) -> str:
        """Log in to the saved SMTP or IMAP server. Nothing is sent or read."""
        connection = self.get(project_id, owner_id, name)
        if connection is None or connection.kind not in {"smtp", "imap"}:
            raise ConnectionProblem("Choose a saved mail connection.")
        rows = {r["part"]: r for r in self.repo.list_connection_rows(project_id, owner_id) if r["name"] == name}

        def value(part: str) -> str:
            row = rows.get(part)
            return self.box.decrypt(row["value_enc"]) if row and row["value_enc"] else ""

        host, port, username, password = value("host"), value("port"), value("username"), value("password")
        self._check_host(host)
        register_secret(password)
        try:
            number = int(port or (587 if connection.kind == "smtp" else 993))
            if connection.kind == "smtp":
                factory = smtplib.SMTP_SSL if number == 465 else smtplib.SMTP
                with factory(host, number, timeout=15) as server:
                    if number != 465:
                        server.ehlo()
                        if server.has_extn("starttls"):
                            server.starttls(context=ssl.create_default_context())
                            server.ehlo()
                    if username:
                        server.login(username, password)
                    return f"Connected to {host}:{number}" + (" and signed in." if username else ".")
            mailbox = imaplib.IMAP4_SSL(host, number, timeout=15) if number == 993 else imaplib.IMAP4(host, number, timeout=15)
            try:
                mailbox.login(username, password)
            finally:
                try:
                    mailbox.logout()
                except (imaplib.IMAP4.error, OSError):
                    pass
            return f"Connected to {host}:{number} and signed in."
        except (smtplib.SMTPException, imaplib.IMAP4.error, OSError, ValueError) as exc:
            return mask(f"Could not sign in to {host}: {type(exc).__name__}.")


__all__ = ["KINDS", "TEMPLATES", "Connection", "ConnectionPart", "ConnectionProblem", "ConnectionService", "SecretBox", "apply_auth", "clean_env_name"]
