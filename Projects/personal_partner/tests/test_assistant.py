from src import assistant, live_info, router, web_search


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


def fake_router(monkeypatch, reply):
    """Stand in for Nemotron's routing decision and record what it was shown."""
    seen = {}

    def decide(messages, max_tokens=200):
        seen["messages"] = messages
        return reply

    monkeypatch.setattr(router, "complete_text", decide)
    return seen


def fake_stream(monkeypatch):
    sent = {}

    def capture(messages):
        sent["messages"] = messages
        return iter(["ok"])

    monkeypatch.setattr(assistant, "stream_completion", capture)
    return sent


def test_model_chooses_search_and_final_reply_uses_results(monkeypatch):
    use_key(monkeypatch)
    fake_router(monkeypatch, '{"action": "SEARCH", "query": "chief damu"}')
    queries = []

    def fake_search(query, bucket):
        queries.append(query)
        return ({"title": "Damu page", "url": "https://example.org/damu", "content": "Damu is the chief of X.", "published": ""},)

    monkeypatch.setattr(web_search, "_search_cached", fake_search)
    sent = fake_stream(monkeypatch)
    assert list(assistant.stream_reply(convo("who is chief damu?"), {})) == ["ok"]
    assert queries == ["chief damu"]
    text = system_text(sent["messages"])
    assert "Current web results" in text and "Damu is the chief of X." in text


def test_model_answers_directly_without_search(monkeypatch):
    fake_router(monkeypatch, '{"action": "ANSWER"}')

    def should_not_run(query, bucket):
        raise AssertionError("direct answers must not trigger a web search")

    monkeypatch.setattr(web_search, "_search_cached", should_not_run)
    sent = fake_stream(monkeypatch)
    list(assistant.stream_reply(convo("what is the capital of France?"), {}))
    assert "Current web results" not in system_text(sent["messages"])


def test_search_failure_is_reported_honestly(monkeypatch):
    use_key(monkeypatch)
    fake_router(monkeypatch, '{"action": "SEARCH", "query": "tamil movies released this year"}')

    def boom(query, bucket):
        raise RuntimeError("offline")

    monkeypatch.setattr(web_search, "_search_cached", boom)
    sent = fake_stream(monkeypatch)
    list(assistant.stream_reply(convo("which tamil movies released this year?"), {}))
    text = system_text(sent["messages"])
    assert "failed just now" in text and "Do not guess" in text


def test_missing_key_is_reported_honestly(monkeypatch):
    use_key(monkeypatch, key="")
    fake_router(monkeypatch, '{"action": "SEARCH", "query": "weather in chennai today"}')
    sent = fake_stream(monkeypatch)
    list(assistant.stream_reply(convo("what's the weather today?"), {"city": "Chennai"}))
    assert "TAVILY_API_KEY is missing" in system_text(sent["messages"])


def test_router_sees_history_and_saved_city_and_writes_follow_up_query(monkeypatch):
    use_key(monkeypatch)
    seen = fake_router(monkeypatch, '{"action": "SEARCH", "query": "Tamil Nadu chief minister before the current one"}')
    queries = []

    def fake_search(query, bucket):
        queries.append(query)
        return ({"title": "t", "url": "https://example.org", "content": "c", "published": ""},)

    monkeypatch.setattr(web_search, "_search_cached", fake_search)
    fake_stream(monkeypatch)
    conversation = {
        "messages": [
            {"role": "user", "content": "who is tamilnadu cm?"},
            {"role": "assistant", "content": "Example Person."},
            {"role": "user", "content": "and before him?"},
        ]
    }
    list(assistant.stream_reply(conversation, {"city": "Chennai"}))
    router_input = seen["messages"]
    assert "and before him?" in router_input[1]["content"]
    assert "Chennai" in router_input[0]["content"]
    assert queries == ["Tamil Nadu chief minister before the current one"]
