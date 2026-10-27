from datetime import datetime, timedelta, timezone

import pytest

from src import auth, storage
from src.auth import AccountLockedError, AccountValidationError, authenticate_user, create_account


def configure(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(storage, "CONVERSATIONS_DIR", tmp_path / "conversations")
    storage.initialize_storage()


def make_account():
    return create_account("Ada", "ada.one", "ada@example.com", "Strong-Pass9!", "Strong-Pass9!", True)


def capture_mail(monkeypatch):
    sent = []
    monkeypatch.setattr(auth, "send_password_reset_email", lambda to, name, token, minutes: sent.append((to, token)) or True)
    return sent


def test_password_reset_flow_is_single_use(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    sent = capture_mail(monkeypatch)
    account = make_account()

    auth.request_password_reset(" ADA@example.com ")
    assert len(sent) == 1
    token = sent[0][1]
    stored = storage.find_user_by_username("ada.one")
    assert token not in str(stored["password_reset"])  # only a hash is stored
    assert auth.password_reset_token_is_valid(token)

    with pytest.raises(AccountValidationError):
        auth.reset_password(token, "weak", "weak")
    with pytest.raises(AccountValidationError, match="do not match"):
        auth.reset_password(token, "Another-Pass7!", "Different-Pass7!")

    auth.reset_password(token, "Another-Pass7!", "Another-Pass7!")
    assert authenticate_user("ada.one", "Another-Pass7!")["user_id"] == account["user_id"]
    assert authenticate_user("ada.one", "Strong-Pass9!") is None
    assert not auth.password_reset_token_is_valid(token)
    with pytest.raises(AccountValidationError, match="invalid or has expired"):
        auth.reset_password(token, "Third-Pass5!x", "Third-Pass5!x")


def test_password_reset_unknown_email_sends_nothing_and_is_throttled(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    sent = capture_mail(monkeypatch)
    make_account()
    auth.request_password_reset("nobody@example.com")
    assert sent == []
    auth.request_password_reset("ada@example.com")
    auth.request_password_reset("ada@example.com")
    assert len(sent) == 1


def test_expired_reset_token_is_rejected(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    sent = capture_mail(monkeypatch)
    make_account()
    auth.request_password_reset("ada@example.com")
    token = sent[0][1]
    users = storage._read_users_locked()
    users[0]["password_reset"]["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    storage._atomic_write(storage.USERS_FILE, {"users": users})
    assert not auth.password_reset_token_is_valid(token)


def test_account_locks_after_repeated_failures_and_reset_unlocks(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    sent = capture_mail(monkeypatch)
    make_account()
    for _ in range(storage.MAX_FAILED_LOGINS):
        assert authenticate_user("ada.one", "wrong") is None
    with pytest.raises(AccountLockedError):
        authenticate_user("ada.one", "Strong-Pass9!")

    auth.request_password_reset("ada@example.com")
    auth.reset_password(sent[0][1], "Another-Pass7!", "Another-Pass7!")
    assert authenticate_user("ada.one", "Another-Pass7!") is not None


def test_sensitive_fields_are_not_returned_publicly(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    capture_mail(monkeypatch)
    account = make_account()
    auth.request_password_reset("ada@example.com")
    public = storage.get_user_by_id(account["user_id"])
    assert not {"password_hash", "password_reset", "failed_logins", "locked_until"} & set(public)
