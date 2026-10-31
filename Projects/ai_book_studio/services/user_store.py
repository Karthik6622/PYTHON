"""SQLite storage for accounts, linked social identities and login sessions.

Passwords are never stored here in clear text (the service layer hands in bcrypt hashes) and session tokens are stored only
as SHA-256 digests, so a copy of the database cannot be used to sign in.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS identities (
    provider TEXT NOT NULL,
    subject TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (provider, subject)
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS resets (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0
);
"""


def db_path() -> Path:
    return Path(config.USERS_DB)


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(_SCHEMA)
    return connection


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


# ------------------------------------------------------------------ users
def find_by_email(email: str) -> dict[str, Any] | None:
    with closing(_connect()) as db:
        return _row(db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone())


def find_by_id(user_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as db:
        return _row(db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def create_user(email: str, name: str, password_hash: str = "") -> dict[str, Any]:
    """Insert a user. Raises ``sqlite3.IntegrityError`` when the email already exists."""
    user_id = "u" + uuid.uuid4().hex
    with closing(_connect()) as db, db:
        db.execute(
            "INSERT INTO users (id, email, name, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, email, name, password_hash, time.time()),
        )
    return find_by_id(user_id) or {}


def find_by_identity(provider: str, subject: str) -> dict[str, Any] | None:
    with closing(_connect()) as db:
        return _row(
            db.execute(
                "SELECT users.* FROM identities JOIN users ON users.id = identities.user_id "
                "WHERE identities.provider = ? AND identities.subject = ?",
                (provider, subject),
            ).fetchone()
        )


def link_identity(user_id: str, provider: str, subject: str) -> None:
    with closing(_connect()) as db, db:
        db.execute("INSERT OR IGNORE INTO identities (provider, subject, user_id) VALUES (?, ?, ?)", (provider, subject, user_id))


def record_failure(user_id: str, limit: int, lock_seconds: int) -> None:
    with closing(_connect()) as db, db:
        db.execute("UPDATE users SET failed_logins = failed_logins + 1 WHERE id = ?", (user_id,))
        db.execute(
            "UPDATE users SET failed_logins = 0, locked_until = ? WHERE id = ? AND failed_logins >= ?",
            (time.time() + lock_seconds, user_id, limit),
        )


def clear_failures(user_id: str) -> None:
    with closing(_connect()) as db, db:
        db.execute("UPDATE users SET failed_logins = 0, locked_until = 0 WHERE id = ?", (user_id,))


# ------------------------------------------------------------------ sessions
def add_session(token_hash: str, user_id: str, lifetime_seconds: int) -> None:
    now = time.time()
    with closing(_connect()) as db, db:
        db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        db.execute(
            "INSERT OR REPLACE INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token_hash, user_id, now, now + lifetime_seconds),
        )


def user_for_session(token_hash: str) -> dict[str, Any] | None:
    with closing(_connect()) as db:
        return _row(
            db.execute(
                "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id "
                "WHERE sessions.token_hash = ? AND sessions.expires_at > ?",
                (token_hash, time.time()),
            ).fetchone()
        )


def delete_session(token_hash: str) -> None:
    with closing(_connect()) as db, db:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


# ------------------------------------------------------------------ password reset
def set_password(user_id: str, password_hash: str) -> None:
    """Replace the password, lift any lock and sign the account out everywhere."""
    with closing(_connect()) as db, db:
        db.execute("UPDATE users SET password_hash = ?, failed_logins = 0, locked_until = 0 WHERE id = ?", (password_hash, user_id))
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM resets WHERE user_id = ?", (user_id,))


def save_reset(user_id: str, code_hash: str, lifetime_seconds: int) -> None:
    now = time.time()
    with closing(_connect()) as db, db:
        db.execute(
            "INSERT OR REPLACE INTO resets (user_id, code_hash, created_at, expires_at, attempts) VALUES (?, ?, ?, ?, 0)",
            (user_id, code_hash, now, now + lifetime_seconds),
        )


def get_reset(user_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as db:
        return _row(db.execute("SELECT * FROM resets WHERE user_id = ?", (user_id,)).fetchone())


def bump_reset_attempts(user_id: str) -> None:
    with closing(_connect()) as db, db:
        db.execute("UPDATE resets SET attempts = attempts + 1 WHERE user_id = ?", (user_id,))


def delete_reset(user_id: str) -> None:
    with closing(_connect()) as db, db:
        db.execute("DELETE FROM resets WHERE user_id = ?", (user_id,))
