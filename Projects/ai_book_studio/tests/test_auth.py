"""Accounts, sessions and ownership of saved projects."""

from __future__ import annotations

import sqlite3

import pytest

from services import auth_service, user_store
from services.auth_service import AuthError

EMAIL = "reader@example.com"
PASSWORD = "Lantern2024"


def make_account(email: str = EMAIL, password: str = PASSWORD) -> dict[str, str]:
    return auth_service.create_account("Mara Reader", email, password, password)


def test_signup_then_login_round_trip() -> None:
    created = make_account()
    assert created["email"] == EMAIL
    assert auth_service.authenticate(EMAIL, PASSWORD)["id"] == created["id"]
    assert auth_service.authenticate("  Reader@Example.COM ", PASSWORD)["id"] == created["id"]


def test_password_is_hashed_not_stored() -> None:
    make_account()
    stored = user_store.find_by_email(EMAIL)
    assert stored is not None
    assert PASSWORD not in stored["password_hash"]
    assert stored["password_hash"].startswith("$2")


@pytest.mark.parametrize(
    ("name", "email", "password", "confirm"),
    [
        ("M", EMAIL, PASSWORD, PASSWORD),
        ("Mara", "not-an-email", PASSWORD, PASSWORD),
        ("Mara", EMAIL, "short1", "short1"),
        ("Mara", EMAIL, "onlyletters", "onlyletters"),
        ("Mara", EMAIL, "12345678", "12345678"),
        ("Mara", EMAIL, PASSWORD, PASSWORD + "x"),
    ],
)
def test_signup_validation(name: str, email: str, password: str, confirm: str) -> None:
    with pytest.raises(AuthError):
        auth_service.create_account(name, email, password, confirm)
    assert user_store.find_by_email(EMAIL) is None


def test_duplicate_email_is_rejected() -> None:
    make_account()
    with pytest.raises(AuthError, match="already exists"):
        make_account("READER@example.com")


def test_wrong_password_and_unknown_email_look_the_same() -> None:
    make_account()
    with pytest.raises(AuthError) as wrong:
        auth_service.authenticate(EMAIL, "Wrong-pass1")
    with pytest.raises(AuthError) as unknown:
        auth_service.authenticate("nobody@example.com", "Wrong-pass1")
    assert str(wrong.value) == str(unknown.value)


def test_account_locks_after_repeated_failures_and_recovers() -> None:
    make_account()
    for _ in range(auth_service.MAX_FAILED_LOGINS):
        with pytest.raises(AuthError):
            auth_service.authenticate(EMAIL, "Wrong-pass1")
    with pytest.raises(AuthError, match="Too many"):
        auth_service.authenticate(EMAIL, PASSWORD)
    stored = user_store.find_by_email(EMAIL)
    assert stored is not None
    with user_store._connect() as db:  # simulate the lock expiring
        db.execute("UPDATE users SET locked_until = 1 WHERE id = ?", (stored["id"],))
    assert auth_service.authenticate(EMAIL, PASSWORD)["email"] == EMAIL


def test_long_passwords_count_in_full() -> None:
    long_password = "a1" * 50
    make_account(password=long_password)
    with pytest.raises(AuthError):
        auth_service.authenticate(EMAIL, long_password[:-1] + "b")
    assert auth_service.authenticate(EMAIL, long_password)["email"] == EMAIL


def test_session_token_round_trip_and_logout() -> None:
    user = make_account()
    token = auth_service.start_session(user["id"])
    assert auth_service.user_for_session(token) == user
    with user_store._connect() as db:
        hashes = [row[0] for row in db.execute("SELECT token_hash FROM sessions")]
    assert token not in hashes  # only a digest is stored
    auth_service.end_session(token)
    assert auth_service.user_for_session(token) is None


@pytest.mark.parametrize("token", [None, "", "short", "x" * 200, 12345])
def test_bad_session_tokens_are_ignored(token: object) -> None:
    assert auth_service.user_for_session(token) is None  # type: ignore[arg-type]


def test_expired_session_is_rejected() -> None:
    user = make_account()
    token = auth_service.start_session(user["id"])
    with user_store._connect() as db:
        db.execute("UPDATE sessions SET expires_at = 1")
    assert auth_service.user_for_session(token) is None


def test_social_sign_in_creates_then_reuses_and_links_by_email() -> None:
    first = auth_service.social_sign_in("github", "42", "Dev@Example.com", "Dev One")
    again = auth_service.social_sign_in("github", "42", "changed@example.com", "Dev One")
    assert again["id"] == first["id"]
    password_user = make_account("pw@example.com")
    linked = auth_service.social_sign_in("google", "g-1", "pw@example.com", "Someone")
    assert linked["id"] == password_user["id"]


def test_social_only_account_cannot_use_password_login() -> None:
    auth_service.social_sign_in("google", "g-2", "oauth@example.com", "OAuth User")
    with pytest.raises(AuthError, match="Google or GitHub"):
        auth_service.authenticate("oauth@example.com", PASSWORD)


def test_social_sign_in_requires_a_verified_email() -> None:
    with pytest.raises(AuthError):
        auth_service.social_sign_in("github", "7", "", "No Email")


def test_create_user_enforces_unique_email() -> None:
    user_store.create_user("same@example.com", "A")
    with pytest.raises(sqlite3.IntegrityError):
        user_store.create_user("same@example.com", "B")


# ------------------------------------------------------------------ forgot password
def test_reset_without_email_setup_sets_new_password(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import mailer

    monkeypatch.setattr(mailer, "is_configured", lambda: False)
    user = make_account()
    step = auth_service.begin_password_reset(EMAIL)
    assert step["needs_code"] is False and step["id"] == user["id"]
    token = auth_service.start_session(user["id"])
    auth_service.finish_password_reset(user["id"], "", "Brand-new9", "Brand-new9", False)
    assert auth_service.authenticate(EMAIL, "Brand-new9")["id"] == user["id"]
    with pytest.raises(AuthError):
        auth_service.authenticate(EMAIL, PASSWORD)
    assert auth_service.user_for_session(token) is None  # old sessions end


def test_reset_validates_new_password(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import mailer

    monkeypatch.setattr(mailer, "is_configured", lambda: False)
    user = make_account()
    with pytest.raises(AuthError):
        auth_service.finish_password_reset(user["id"], "", "short", "short", False)
    with pytest.raises(AuthError, match="do not match"):
        auth_service.finish_password_reset(user["id"], "", "Brand-new9", "Brand-new8", False)
    assert auth_service.authenticate(EMAIL, PASSWORD)["id"] == user["id"]


def test_reset_rejects_unknown_and_social_only_accounts() -> None:
    unknown, social = "nobody" + "@" + "example.com", "social" + "@" + "example.com"
    with pytest.raises(AuthError, match="could not find"):
        auth_service.begin_password_reset(unknown)
    auth_service.social_sign_in("google", "g-9", social, "Social")
    with pytest.raises(AuthError, match="Google or GitHub"):
        auth_service.begin_password_reset(social)


def test_reset_with_emailed_code(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import mailer

    sent: list[str] = []
    monkeypatch.setattr(mailer, "is_configured", lambda: True)
    monkeypatch.setattr(mailer, "send_reset_code", lambda to, code, minutes: sent.append(code) or True)
    user = make_account()
    step = auth_service.begin_password_reset(EMAIL)
    assert step["needs_code"] is True and len(sent) == 1
    with pytest.raises(AuthError, match="just sent"):
        auth_service.begin_password_reset(EMAIL)
    with pytest.raises(AuthError, match="not right"):
        auth_service.finish_password_reset(user["id"], "000000" if sent[0] != "000000" else "111111", "Brand-new9", "Brand-new9", True)
    auth_service.finish_password_reset(user["id"], sent[0], "Brand-new9", "Brand-new9", True)
    assert auth_service.authenticate(EMAIL, "Brand-new9")["id"] == user["id"]
    with pytest.raises(AuthError):  # a code works once
        auth_service.finish_password_reset(user["id"], sent[0], "Other-pass7", "Other-pass7", True)


def test_reset_code_is_locked_after_too_many_guesses(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import mailer

    sent: list[str] = []
    monkeypatch.setattr(mailer, "is_configured", lambda: True)
    monkeypatch.setattr(mailer, "send_reset_code", lambda to, code, minutes: sent.append(code) or True)
    user = make_account()
    auth_service.begin_password_reset(EMAIL)
    wrong = "000000" if sent[0] != "000000" else "111111"
    for _ in range(auth_service.RESET_MAX_TRIES):
        with pytest.raises(AuthError):
            auth_service.finish_password_reset(user["id"], wrong, "Brand-new9", "Brand-new9", True)
    with pytest.raises(AuthError):
        auth_service.finish_password_reset(user["id"], sent[0], "Brand-new9", "Brand-new9", True)
