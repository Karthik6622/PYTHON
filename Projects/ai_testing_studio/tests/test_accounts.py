"""Accounts, sessions, social sign-in and per-account project isolation."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ats.accounts import mailer, service, store
from ats.accounts.service import AuthError
from ats.errors import NotFoundError

EMAIL = "mara" + "@" + "example.com"
PASSWORD = "Lantern2024"
APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def users_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "db_path", lambda: tmp_path / "users.db")
    monkeypatch.setattr(mailer, "is_configured", lambda: False)
    return tmp_path / "users.db"


def make_account(email: str = EMAIL, password: str = PASSWORD) -> dict[str, str]:
    return service.create_account("Mara Tester", email, password, password)


def test_create_account_then_log_in(users_db) -> None:
    created = make_account()
    assert created["email"] == EMAIL and created["id"].startswith("u")
    assert users_db.exists()
    assert service.authenticate(f"  {EMAIL.upper()} ", PASSWORD)["id"] == created["id"]
    stored = store.find_by_email(EMAIL)
    assert stored is not None and stored["password_hash"].startswith("$2") and PASSWORD not in stored["password_hash"]


def test_duplicate_email_is_rejected() -> None:
    make_account()
    with pytest.raises(AuthError, match="already exists"):
        make_account(EMAIL.upper())


@pytest.mark.parametrize(
    ("email", "password", "confirm"),
    [("not-an-email", PASSWORD, PASSWORD), ("sam" + "@" + "gmial.com", PASSWORD, PASSWORD), (EMAIL, "short1", "short1"), (EMAIL, PASSWORD, PASSWORD + "x")],
)
def test_sign_up_validation(email: str, password: str, confirm: str) -> None:
    with pytest.raises(AuthError):
        service.create_account("Mara", email, password, confirm)
    assert store.find_by_email(EMAIL) is None


def test_wrong_password_and_unknown_email_look_the_same() -> None:
    make_account()
    with pytest.raises(AuthError) as wrong:
        service.authenticate(EMAIL, "Wrong-pass1")
    with pytest.raises(AuthError) as unknown:
        service.authenticate("nobody" + "@" + "example.com", "Wrong-pass1")
    assert str(wrong.value) == str(unknown.value)


def test_lockout_after_repeated_failures_then_recovery() -> None:
    user = make_account()
    for _ in range(service.MAX_FAILED_LOGINS):
        with pytest.raises(AuthError):
            service.authenticate(EMAIL, "Wrong-pass1")
    with pytest.raises(AuthError, match="Too many"):
        service.authenticate(EMAIL, PASSWORD)  # even the right password is refused while locked
    with store._connect() as db:
        db.execute("UPDATE users SET locked_until = 1 WHERE id = ?", (user["id"],))
    assert service.authenticate(EMAIL, PASSWORD)["id"] == user["id"]


def test_password_reset_without_smtp() -> None:
    user = make_account()
    step = service.begin_password_reset(EMAIL)
    assert step["needs_code"] is False and step["id"] == user["id"]
    token = service.start_session(user["id"])
    service.finish_password_reset(user["id"], "", "Brand-new9", "Brand-new9", False)
    assert service.authenticate(EMAIL, "Brand-new9")["id"] == user["id"]
    with pytest.raises(AuthError):
        service.authenticate(EMAIL, PASSWORD)
    assert service.user_for_session(token) is None  # a reset signs the account out everywhere
    with pytest.raises(AuthError, match="could not find"):
        service.begin_password_reset("nobody" + "@" + "example.com")


def test_session_token_lifecycle() -> None:
    user = make_account()
    token = service.start_session(user["id"])
    assert service.user_for_session(token) == user
    with store._connect() as db:
        assert token not in [row[0] for row in db.execute("SELECT token_hash FROM sessions")]  # only a digest is stored
    for bad in (None, "", "short", "x" * 200):
        assert service.user_for_session(bad) is None
    with store._connect() as db:
        db.execute("UPDATE sessions SET expires_at = 1")
    assert service.user_for_session(token) is None  # expired
    token = service.start_session(user["id"])
    service.end_session(token)
    assert service.user_for_session(token) is None


def test_social_sign_in_creates_links_and_reuses() -> None:
    first = service.social_sign_in("github", "42", "dev" + "@" + "example.com", "Dev One")
    assert service.social_sign_in("github", "42", "other" + "@" + "example.com", "Dev One")["id"] == first["id"]
    existing = make_account()
    assert service.social_sign_in("google", "g-1", EMAIL, "Someone")["id"] == existing["id"]  # same verified email: linked
    with pytest.raises(AuthError, match="Google or GitHub"):
        service.authenticate("dev" + "@" + "example.com", PASSWORD)
    with pytest.raises(AuthError):
        service.social_sign_in("github", "7", "", "No Email")


def test_users_only_see_their_own_projects(repo) -> None:
    alice, bob = make_account(), make_account("bob" + "@" + "example.com")
    mine = repo.create_project(alice["id"], name="Alice shop", url="https://example.com")
    theirs = repo.create_project(bob["id"], name="Bob shop", url="https://example.org")
    assert [p.id for p in repo.list_projects(alice["id"])] == [mine.id]
    assert [p.id for p in repo.list_projects(bob["id"])] == [theirs.id]
    with pytest.raises(NotFoundError):
        repo.get_project(mine.id, bob["id"])
    with pytest.raises(NotFoundError):
        repo.delete_project(theirs.id, alice["id"])
    assert repo.get_project(mine.id, alice["id"]).name == "Alice shop"


def test_browser_projects_move_to_the_account(repo) -> None:
    old = "c" * 32
    project = repo.create_project(old, name="Before accounts", url="https://example.com")
    user = make_account()
    assert repo.transfer_owner(old, user["id"]) == 1
    assert repo.list_projects(old) == []
    assert repo.get_project(project.id, user["id"]).name == "Before accounts"
    assert repo.transfer_owner(old, user["id"]) == 0 and repo.transfer_owner("", user["id"]) == 0


def test_owner_id_is_the_account_id_when_signed_in() -> None:
    script = "import streamlit as st\nfrom ats.ui.session import owner_id\nst.session_state['seen'] = owner_id()\n"
    app = AppTest.from_string(script).run()
    assert len(app.session_state["seen"]) == 32  # anonymous fallback
    app.session_state["auth_user"] = {"id": "u" + "1" * 32, "name": "Mara", "email": EMAIL}
    app.run()
    assert app.session_state["seen"] == "u" + "1" * 32


def test_welcome_page_then_sign_up_and_sign_out() -> None:
    app = AppTest.from_file(APP, default_timeout=60).run()
    assert not app.exception, [e.value for e in app.exception]
    assert [t.label for t in app.tabs] == ["Log in", "Create account"]
    assert not app.sidebar.button  # nobody signed in: no studio navigation
    app.text_input(key="auth_signup_name").input("Mara Tester")
    app.text_input(key="auth_signup_email").input(EMAIL)
    app.text_input(key="auth_signup_password").input(PASSWORD)
    app.text_input(key="auth_signup_confirm").input(PASSWORD)
    next(b for b in app.button if b.label == "Create my account").click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert app.session_state["auth_user"]["email"] == EMAIL
    sign_out = [b for b in app.sidebar.button if b.label == "Sign out"]
    assert sign_out, "signed-in user chip missing"
    sign_out[0].click().run()
    assert not app.exception, [e.value for e in app.exception]
    assert "auth_user" not in app.session_state
