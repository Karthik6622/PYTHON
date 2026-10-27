from src import assistant, live_info, web_search


def convo(text):
    return {"messages": [{"role": "user", "content": text}]}


def system_text(messages):
    assert messages[0]["role"] == "system" and sum(1 for m in messages if m["role"] == "system") == 1
    return messages[0]["content"]


def test_system_message_contains_current_date_and_time():
    text = system_text(assistant.build_messages(convo("what is today's date?"), {}, timezone_name="Asia/Kolkata"))
    assert "Current date and time for the user" in text
    assert "Asia/Kolkata" in text
    assert "Never say you lack access to the date" in text


def test_unknown_timezone_falls_back_to_utc():
    note = live_info.current_time_note("Not/AZone")
    assert "UTC" in note and "timezone is unknown" in note


def test_romantic_topic_adds_romantic_style():
    plain = system_text(assistant.build_messages(convo("hi"), {"topics": ["Work"]}))
    romantic = system_text(assistant.build_messages(convo("hi"), {"topics": ["Romantic"]}))
    assert "Romantic mode is ON" not in plain
    assert "Romantic mode is ON" in romantic
    assert "never sexually explicit" in romantic


def use_key(monkeypatch, key="tvly-test-key"):
    monkeypatch.setattr(web_search, "tavily_api_key", lambda: key)


def test_current_question_gets_tavily_results(monkeypatch):
    use_key(monkeypatch)
    monkeypatch.setattr(
        web_search,
        "_search_cached",
        lambda query, bucket: ({"title": "CM page", "url": "https://example.org/cm", "content": "Example Person is the CM.", "published": ""},),
    )
    text = system_text(assistant.build_messages(convo("who is tamilnadu cm?"), {}))
    assert "Current web results" in text
    assert "Example Person is the CM" in text


def test_non_current_question_skips_search(monkeypatch):
    def should_not_run(query, bucket):
        raise AssertionError("non-current questions must not trigger a web search")

    monkeypatch.setattr(web_search, "_search_cached", should_not_run)
    text = system_text(assistant.build_messages(convo("what is the capital of France?"), {}))
    assert "Current web results" not in text


def test_small_talk_skips_search(monkeypatch):
    def should_not_run(query, bucket):
        raise AssertionError("small talk must not trigger a search")

    monkeypatch.setattr(web_search, "_search_cached", should_not_run)
    text = system_text(assistant.build_messages(convo("hi, how are you"), {}))
    assert "Current web results" not in text


def test_search_failure_is_reported_honestly(monkeypatch):
    use_key(monkeypatch)

    def boom(query, bucket):
        raise RuntimeError("offline")

    monkeypatch.setattr(web_search, "_search_cached", boom)
    text = system_text(assistant.build_messages(convo("which tamil movies released this year?"), {}))
    assert "failed just now" in text and "Do not guess" in text


def test_missing_key_is_reported_honestly(monkeypatch):
    use_key(monkeypatch, key="")
    text = system_text(assistant.build_messages(convo("what's the weather today?"), {}))
    assert "TAVILY_API_KEY is missing" in text


def test_follow_up_inherits_current_routing(monkeypatch):
    use_key(monkeypatch)
    seen = []

    def fake_search(query, bucket):
        seen.append(query)
        return ({"title": "t", "url": "https://example.org", "content": "c", "published": ""},)

    monkeypatch.setattr(web_search, "_search_cached", fake_search)
    conversation = {
        "messages": [
            {"role": "user", "content": "who is tamilnadu cm?"},
            {"role": "assistant", "content": "Example Person."},
            {"role": "user", "content": "and before him?"},
        ]
    }
    text = system_text(assistant.build_messages(conversation, {}))
    assert "Current web results" in text
    assert seen and "who is tamilnadu cm?" in seen[0]
