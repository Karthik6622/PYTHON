import pytest

from src import auth, storage
from src.auth import AccountLockedError, AccountValidationError, authenticate_user, create_account

EMAIL = "ada@example.com"
UNKNOWN = "nobody@example.com"


def configure(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(storage, "CONVERSATIONS_DIR", tmp_path / "conversations")
    storage.initialize_storage()


def make_account():
    return create_account("Ada", "ada.one", EMAIL, "Strong-Pass9!", "Strong-Pass9!", True)


def test_unknown_email_is_reported(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    make_account()
    assert auth.email_has_account(f" {EMAIL.upper()} ")
    assert not auth.email_has_account(UNKNOWN)
    with pytest.raises(AccountValidationError, match="No account exists"):
        auth.reset_password_for_email(UNKNOWN, "Another-Pass7!", "Another-Pass7!")


def test_password_reset_for_email_validates_and_updates(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    account = make_account()
    with pytest.raises(AccountValidationError):
        auth.reset_password_for_email(EMAIL, "weak", "weak")
    with pytest.raises(AccountValidationError, match="do not match"):
        auth.reset_password_for_email(EMAIL, "Another-Pass7!", "Different-Pass7!")

    auth.reset_password_for_email(EMAIL, "Another-Pass7!", "Another-Pass7!")
    assert authenticate_user("ada.one", "Another-Pass7!")["user_id"] == account["user_id"]
    assert authenticate_user("ada.one", "Strong-Pass9!") is None


def test_account_locks_after_repeated_failures_and_reset_unlocks(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    make_account()
    for _ in range(storage.MAX_FAILED_LOGINS):
        assert authenticate_user("ada.one", "wrong") is None
    with pytest.raises(AccountLockedError):
        authenticate_user("ada.one", "Strong-Pass9!")

    auth.reset_password_for_email(EMAIL, "Another-Pass7!", "Another-Pass7!")
    assert authenticate_user("ada.one", "Another-Pass7!") is not None


def test_sensitive_fields_are_not_returned_publicly(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    account = make_account()
    auth.reset_password_for_email(EMAIL, "Another-Pass7!", "Another-Pass7!")
    public = storage.get_user_by_id(account["user_id"])
    assert not {"password_hash", "password_reset", "failed_logins", "locked_until"} & set(public)
