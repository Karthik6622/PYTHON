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


def test_romantic_mode_is_a_human_partner_not_an_assistant():
    text = system_text(assistant.build_messages(convo("have you eaten dinner?"), {"mode": "Romantic", "partner": "Girlfriend"}))
    assert "Romantic mode is ON" in text and "real, living person" in text
    assert "You are a girl" in text and "girlfriend" in text
    assert "English correction mode is ON" not in text


def test_english_correction_mode_adds_correction_rules():
    text = system_text(assistant.build_messages(convo("i goed home"), {"mode": "English correction"}))
    assert "English correction mode is ON" in text and "Your sentence is correct" in text
    assert "Romantic mode is ON" not in text


def test_correct_sentence_gets_only_a_confirmation():
    rules = assistant.ENGLISH_PROMPT
    assert "Case A" in rules and "ONE short line only" in rules
    assert "Do not repeat the user's sentence" in rules and "Do not write \"What changed\"" in rules
    assert "No correction needed" not in rules


def test_tone_and_length_preferences_reach_the_system_message():
    text = system_text(assistant.build_messages(convo("hi"), {"tone": "Direct", "response_length": "Brief"}))
    assert assistant.TONE_GUIDES["Direct"] in text
    assert assistant.LENGTH_GUIDES["Brief"] in text
    assert assistant.TONE_GUIDES["Warm"] not in text and assistant.LENGTH_GUIDES["Detailed"] not in text


def test_brief_length_caps_reply_tokens_and_other_lengths_do_not():
    assert assistant.reply_token_cap({"response_length": "Brief"}) == assistant.LENGTH_TOKEN_CAPS["Brief"]
    assert assistant.reply_token_cap({"response_length": "Balanced"}) is None
    assert assistant.reply_token_cap({"response_length": "Detailed"}) is None
    assert assistant.reply_token_cap({}) is None


def test_correct_english_returns_only_the_confirmation(monkeypatch):
    monkeypatch.setattr(assistant, "complete_text", lambda messages, max_tokens=200: "YES")

    def no_model(*args, **kwargs):
        raise AssertionError("a correct sentence must not reach the model")

    monkeypatch.setattr(assistant, "stream_completion", no_model)
    reply = "".join(assistant.stream_reply(convo("Hey, I watched yesterday's movie."), {"mode": "English correction"}))
    assert reply == assistant.CORRECT_ENGLISH_LINE


def test_sentence_with_mistakes_gets_the_correction_note(monkeypatch):
    monkeypatch.setattr(assistant, "complete_text", lambda messages, max_tokens=200: "NO")
    fake_router(monkeypatch, '{"action": "ANSWER"}')
    sent = fake_stream(monkeypatch)
    list(assistant.stream_reply(convo("i goed home"), {"mode": "English correction"}))
    assert "use Case B" in system_text(sent["messages"])


def test_failed_english_check_falls_back_to_normal_reply(monkeypatch):
    def boom(messages, max_tokens=200):
        raise RuntimeError("model down")

    monkeypatch.setattr(assistant, "complete_text", boom)
    fake_router(monkeypatch, '{"action": "ANSWER"}')
    sent = fake_stream(monkeypatch)
    assert list(assistant.stream_reply(convo("i goed home"), {"mode": "English correction"})) == ["ok"]
    assert "use Case B" not in system_text(sent["messages"])


def test_normal_mode_and_legacy_romantic_topic():
    assert assistant.chat_mode({"mode": "Normal", "topics": ["Romantic"]}) == "Normal"
    assert assistant.chat_mode({"topics": ["Romantic"]}) == "Romantic"
    assert assistant.chat_mode({}) == "Normal"
    plain = system_text(assistant.build_messages(convo("hi"), {"mode": "Normal"}))
    assert "mode is ON" not in plain


def _msg(role, text, when, mode=None):
    item = {"role": role, "content": text, "created_at": when}
    if mode:
        item["mode"] = mode
    return item


def test_romantic_messages_are_isolated_from_other_modes():
    conversation = {
        "messages": [
            _msg("user", "normal question", "2026-10-29T10:00:00+00:00"),
            _msg("assistant", "normal answer", "2026-10-29T10:00:05+00:00"),
            _msg("user", "good morning love", "2026-10-29T10:01:00+00:00", "Romantic"),
            _msg("assistant", "morning baby", "2026-10-29T10:01:05+00:00", "Romantic"),
        ]
    }
    romantic = assistant.build_messages(conversation, {"mode": "Romantic"})[1:]
    other = assistant.build_messages(conversation, {"mode": "English correction"})[1:]
    assert [m["content"] for m in romantic] == ["good morning love", "morning baby"]
    assert [m["content"] for m in other] == ["normal question", "normal answer"]


def test_romantic_mode_notes_how_long_the_user_was_away():
    conversation = {
        "messages": [
            _msg("user", "hi", "2026-10-29T10:00:00+00:00", "Romantic"),
            _msg("assistant", "hey you", "2026-10-29T10:00:05+00:00", "Romantic"),
            _msg("user", "i'm back", "2026-10-29T11:30:00+00:00", "Romantic"),
        ]
    }
    text = system_text(assistant.build_messages(conversation, {"mode": "Romantic"}, timezone_name="Asia/Kolkata"))
    assert "away for 1 hour 29 minutes" in text and "ask where they have been" in text
    quick = {
        "messages": [
            _msg("assistant", "hey", "2026-10-29T10:00:00+00:00", "Romantic"),
            _msg("user", "hi", "2026-10-29T10:00:30+00:00", "Romantic"),
        ]
    }
    assert "Do not mention any gap" in system_text(assistant.build_messages(quick, {"mode": "Romantic"}))
    assert "Message timing" not in system_text(assistant.build_messages(conversation, {"mode": "Normal"}))


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

    def capture(messages, max_tokens=None):
        sent["messages"] = messages
        sent["max_tokens"] = max_tokens
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


def test_voice_turn_is_short_and_speech_friendly(monkeypatch):
    fake_router(monkeypatch, '{"action": "ANSWER"}')
    sent = fake_stream(monkeypatch)
    list(assistant.stream_reply(convo("how are you"), {}, voice=True))
    assert assistant.VOICE_NOTE in system_text(sent["messages"])
    assert sent["max_tokens"] == assistant.VOICE_TOKEN_CAP
    sent = fake_stream(monkeypatch)
    list(assistant.stream_reply(convo("how are you"), {}))
    assert assistant.VOICE_NOTE not in system_text(sent["messages"])
    assert sent["max_tokens"] is None


def test_router_failure_still_gets_a_reply(monkeypatch):
    def boom(messages, max_tokens=200):
        raise RuntimeError("router down")

    monkeypatch.setattr(router, "complete_text", boom)
    sent = fake_stream(monkeypatch)
    assert list(assistant.stream_reply(convo("hello"), {})) == ["ok"]
    assert "messages" in sent
