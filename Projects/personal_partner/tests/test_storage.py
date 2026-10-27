import json
import uuid

from src import storage


def configure_storage(tmp_path, monkeypatch):
    users_file = tmp_path / "users.json"
    conversations_dir = tmp_path / "conversations"
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "USERS_FILE", users_file)
    monkeypatch.setattr(storage, "CONVERSATIONS_DIR", conversations_dir)
    storage.initialize_storage()
    return users_file, conversations_dir


def add_user(user_id):
    return storage.create_user(
        {
            "user_id": user_id,
            "username": f"user_{user_id[:6]}",
            "display_name": "Test User",
            "email": f"{user_id[:6]}@example.com",
            "password_hash": "$2b$12$not-a-real-hash-for-storage-only",
        }
    )


def test_conversations_are_isolated_and_duplicate_messages_are_ignored(tmp_path, monkeypatch):
    _, conversation_dir = configure_storage(tmp_path, monkeypatch)
    first_user, second_user = uuid.uuid4().hex, uuid.uuid4().hex
    add_user(first_user)
    add_user(second_user)
    first_chat = storage.create_conversation(first_user)
    message = {"message_id": "same-id", "role": "user", "content": "hello"}
    assert storage.append_message(first_user, first_chat["conversation_id"], message)
    assert not storage.append_message(first_user, first_chat["conversation_id"], message)
    assert len(storage.load_conversations(first_user)[0]["messages"]) == 1
    assert storage.load_conversations(second_user) == []
    assert (conversation_dir / f"{first_user}.json").exists()
    assert (conversation_dir / f"{second_user}.json").exists()


def test_user_read_does_not_expose_password_hash(tmp_path, monkeypatch):
    configure_storage(tmp_path, monkeypatch)
    user_id = uuid.uuid4().hex
    add_user(user_id)
    assert "password_hash" not in storage.get_user_by_id(user_id)
    assert storage.find_user_by_username(f"USER_{user_id[:6]}")["user_id"] == user_id


def test_malformed_json_is_backed_up_before_reset(tmp_path, monkeypatch):
    users_file, _ = configure_storage(tmp_path, monkeypatch)
    users_file.write_text("{broken json", encoding="utf-8")
    storage.initialize_storage()
    backups = list(tmp_path.glob("users.json.corrupt-*.bak"))
    assert backups
    assert backups[0].read_text(encoding="utf-8") == "{broken json"
    assert json.loads(users_file.read_text(encoding="utf-8")) == {"users": []}


def test_delete_all_user_data_removes_only_target(tmp_path, monkeypatch):
    _, conversations_dir = configure_storage(tmp_path, monkeypatch)
    user_a, user_b = uuid.uuid4().hex, uuid.uuid4().hex
    add_user(user_a)
    add_user(user_b)
    storage.create_conversation(user_a)
    storage.create_conversation(user_b)
    assert storage.delete_all_user_data(user_a)
    assert storage.get_user_by_id(user_a) is None
    assert storage.get_user_by_id(user_b) is not None
    assert not (conversations_dir / f"{user_a}.json").exists()
    assert (conversations_dir / f"{user_b}.json").exists()


def test_social_identity_links_by_verified_email_and_is_idempotent(tmp_path, monkeypatch):
    configure_storage(tmp_path, monkeypatch)
    user = storage.create_or_link_social_user(
        "google", "google-subject-1", "[REDACTED_EMAIL_ADDRESS_1]", "Ada", "$2b$12$random-hash"
    )
    linked = storage.create_or_link_social_user(
        "github", "42", "[REDACTED_EMAIL_ADDRESS_1]", "Ada Lovelace", "$2b$12$another-hash"
    )
    assert linked["user_id"] == user["user_id"]
    repeated = storage.create_or_link_social_user(
        "github", "42", "[REDACTED_EMAIL_ADDRESS_1]", "Ada Lovelace", "$2b$12$another-hash"
    )
    assert repeated["user_id"] == user["user_id"]
    assert len(storage.find_user_by_username(user["username"])["auth_identities"]) == 2
