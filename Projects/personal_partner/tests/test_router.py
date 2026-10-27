import pytest

from src import router


@pytest.mark.parametrize(
    ("reply", "latest", "expected"),
    [
        ('{"action": "ANSWER"}', "what is 2+2?", None),
        ('{"action": "SEARCH", "query": "chief damu"}', "who is chief damu?", "chief damu"),
        ('{"action": "search", "query": "tamil nadu cm"}', "who is tamilnadu cm?", "tamil nadu cm"),
        ('{"action": "SEARCH"}', "latest news on cricket", "latest news on cricket"),
        ("I think the answer is simple.", "hello", None),
        ("", "hello", None),
        ('Sure: {"action": "SEARCH", "query": "gold price today"} thanks', "gold price?", "gold price today"),
        ("SEARCH", "who won the match yesterday", "who won the match yesterday"),
    ],
)
def test_parse_decision(reply, latest, expected):
    assert router.parse_decision(reply, latest) == expected


def test_decide_search_passes_history_and_returns_model_query(monkeypatch):
    seen = {}

    def fake_complete(messages, max_tokens=200):
        seen["messages"] = messages
        return '{"action": "SEARCH", "query": "Tamil Nadu chief minister before the current one"}'

    monkeypatch.setattr(router, "complete_text", fake_complete)
    history = [
        {"role": "user", "content": "who is tamilnadu cm?"},
        {"role": "assistant", "content": "Example Person."},
        {"role": "user", "content": "and before him?"},
    ]
    query = router.decide_search(history, {"city": "Chennai"}, "Asia/Kolkata")
    assert query == "Tamil Nadu chief minister before the current one"
    assert "Chennai" in seen["messages"][0]["content"]
    assert "and before him?" in seen["messages"][1]["content"]


def test_decide_search_skips_model_call_for_empty_message(monkeypatch):
    def should_not_run(messages, max_tokens=200):
        raise AssertionError("no routing call expected without a user message")

    monkeypatch.setattr(router, "complete_text", should_not_run)
    assert router.decide_search([{"role": "user", "content": "   "}]) is None
