import pytest

from src import storage
from src.auth import AccountValidationError, authenticate_user, create_account


def test_create_and_authenticate_account(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(storage, "CONVERSATIONS_DIR", tmp_path / "conversations")
    storage.initialize_storage()

    account = create_account(
        "  Ada Lovelace ", "  Ada.L  ", " ADA@example.com ", "Strong-Pass9!", "Strong-Pass9!", True
    )
    assert account["username"] == "ada.l"
    assert "password_hash" not in account
    stored = storage.find_user_by_username("ada.l")
    assert stored["password_hash"] != "Strong-Pass9!"
    assert authenticate_user("ADA.L", "Strong-Pass9!")["user_id"] == account["user_id"]
    assert authenticate_user("ada.l", "incorrect") is None
    assert authenticate_user("unknown", "incorrect") is None


def test_account_creation_rejects_duplicate_email_case_insensitively(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(storage, "CONVERSATIONS_DIR", tmp_path / "conversations")
    storage.initialize_storage()
    create_account("Ada", "ada.one", "ada@example.com", "Strong-Pass9!", "Strong-Pass9!", True)
    with pytest.raises(ValueError, match="already uses"):
        create_account("Other", "ada.two", "ADA@example.com", "Strong-Pass9!", "Strong-Pass9!", True)


def test_account_creation_requires_terms():
    with pytest.raises(AccountValidationError, match="accept the privacy"):
        create_account("Ada", "ada.one", "ada@example.com", "Strong-Pass9!", "Strong-Pass9!", False)
