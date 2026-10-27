from src.validation import (
    normalize_email,
    normalize_username,
    safe_conversation_title,
    validate_email,
    validate_message,
    validate_password,
    validate_username,
)


def test_username_normalization_and_rules():
    assert normalize_username("  Ada.Lovelace_1 ") == "ada.lovelace_1"
    assert validate_username("ok_user") is None
    assert validate_username("ab")
    assert validate_username("has space")


def test_email_normalization_and_validation():
    assert normalize_email("  ADA@example.com ") == "ada@example.com"
    assert validate_email("ada@example.com") is None
    assert validate_email("not-an-email")


def test_password_rules_and_message_limits():
    assert validate_password("Valid-Pass9!") is None
    assert validate_password("lowercase-only")
    assert validate_message("  ")
    assert validate_message("Hello") is None
    assert validate_message("x" * 8_001)


def test_safe_title_is_short_and_single_line():
    title = safe_conversation_title("A title\n with   spacing " + "x" * 80)
    assert "\n" not in title
    assert len(title) <= 50
