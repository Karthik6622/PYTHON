from src import assistant, live_info, router, web_search


def convo(text, mode=None):
    message = {"role": "user", "content": text}
    if mode:
        message["mode"] = mode
    return {"messages": [message]}


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
    assert assistant.reply_token_cap({"response_length": "Detailed"}) == assistant.LENGTH_TOKEN_CAPS["Detailed"] > 1200
    assert assistant.reply_token_cap({}) == assistant.LENGTH_TOKEN_CAPS["Brief"]  # Brief is the default length


def test_detailed_length_rule_overrides_the_short_reply_default():
    text = system_text(assistant.build_messages(convo("explain python decorators"), {"response_length": "Detailed"}))
    assert "DETAILED" in text and "300 to 600 words" in text
    assert "Keep replies short" not in text
    assert "Short natural messages" not in system_text(
        assistant.build_messages(convo("hi"), {"response_length": "Detailed", "mode": "Romantic"})
    )


def test_length_reminder_follows_the_latest_user_message_even_after_short_replies():
    history = {"messages": [
        {"role": "user", "content": "hi"}, {"role": "assistant", "content": "hey!"},
        {"role": "user", "content": "explain python decorators"},
    ]}
    detailed = assistant.build_messages(history, {"response_length": "Detailed"})
    assert detailed[-1]["role"] == "user" and detailed[-1]["content"].startswith("explain python decorators")
    assert detailed[-1]["content"].endswith(assistant.LENGTH_REMINDERS["Detailed"])
    assert detailed[1]["content"] == "hi"
    balanced = assistant.build_messages(history, {"response_length": "Balanced"})
    assert balanced[-1]["content"].endswith(assistant.LENGTH_REMINDERS["Balanced"])
    english = assistant.build_messages(
        {"messages": [{**m, "mode": "English correction"} for m in history["messages"]]},
        {"response_length": "Detailed", "mode": "English correction"},
    )
    assert english[-1]["content"] == "explain python decorators"


def test_correct_english_returns_only_the_confirmation(monkeypatch):
    monkeypatch.setattr(assistant, "complete_text", lambda messages, max_tokens=200: "YES")

    def no_model(*args, **kwargs):
        raise AssertionError("a correct sentence must not reach the model")

    monkeypatch.setattr(assistant, "stream_completion", no_model)
    reply = "".join(assistant.stream_reply(convo("Hey, I watched yesterday's movie.", "English correction"), {"mode": "English correction"}))
    assert reply == assistant.CORRECT_ENGLISH_LINE


def test_sentence_with_mistakes_gets_the_correction_note(monkeypatch):
    monkeypatch.setattr(assistant, "complete_text", lambda messages, max_tokens=200: "NO")
    fake_router(monkeypatch, '{"action": "ANSWER"}')
    sent = fake_stream(monkeypatch)
    list(assistant.stream_reply(convo("i goed home", "English correction"), {"mode": "English correction"}))
    assert "use Case B" in system_text(sent["messages"])


def test_failed_english_check_falls_back_to_normal_reply(monkeypatch):
    def boom(messages, max_tokens=200):
        raise RuntimeError("model down")

    monkeypatch.setattr(assistant, "complete_text", boom)
    fake_router(monkeypatch, '{"action": "ANSWER"}')
    sent = fake_stream(monkeypatch)
    assert list(assistant.stream_reply(convo("i goed home", "English correction"), {"mode": "English correction"})) == ["ok"]
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


def test_every_mode_keeps_its_own_separate_chat():
    conversation = {
        "messages": [
            _msg("user", "normal question", "2026-10-29T10:00:00+00:00"),
            _msg("assistant", "normal answer", "2026-10-29T10:00:05+00:00"),
            _msg("user", "good morning love", "2026-10-29T10:01:00+00:00", "Romantic"),
            _msg("assistant", "morning baby", "2026-10-29T10:01:05+00:00", "Romantic"),
            _msg("user", "yo bro", "2026-10-29T10:02:00+00:00", "Friend"),
            _msg("assistant", "yo, ate yet?", "2026-10-29T10:02:05+00:00", "Friend"),
            _msg("user", "i goed home", "2026-10-29T10:03:00+00:00", "English correction"),
        ]
    }
    expected = {
        "Romantic": ["good morning love", "morning baby"],
        "Friend": ["yo bro", "yo, ate yet?"],
        "English correction": ["i goed home"],
        "Normal": ["normal question", "normal answer"],
    }
    for mode, contents in expected.items():
        built = assistant.build_messages(conversation, {"mode": mode})[1:]
        assert [m["content"] for m in assistant.messages_for_mode(conversation, mode)] == contents
        assert [m["content"].split("\n\n[Reply length")[0] for m in built] == contents


def test_friend_mode_is_a_caring_human_friend_with_no_romance():
    text = system_text(assistant.build_messages(convo("have you eaten?", "Friend"), {"mode": "Friend"}))
    assert "Friend mode is ON" in text and "real, living person" in text and "best friend" in text
    assert "No romance at all" in text and "Tease them or scold them" in text
    assert "Romantic mode is ON" not in text and "English correction mode is ON" not in text
    assert "You are possessive and jealous" not in text
    assert "Friend mode is ON" not in system_text(assistant.build_messages(convo("hi"), {"mode": "Romantic"}))
    assert "Friend" in assistant.MODES and assistant.chat_mode({"mode": "Friend"}) == "Friend"


def test_friend_mode_cares_about_late_night_without_jealousy():
    history = [_msg("user", "hey", "2026-10-29T23:30:00+00:00", "Friend"), _msg("user", "awake", "2026-10-29T23:45:00+00:00", "Friend")]
    note = assistant.friend_care_note(history, "UTC")
    assert "still awake" in note and "jealous" not in note


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
    other = assistant.build_messages(conversation, {"mode": "Normal"})[1:]
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


def test_romantic_partner_is_a_possessive_girlfriend_who_treats_the_user_as_boyfriend():
    for partner in ("Girlfriend", "Auto"):
        text = system_text(assistant.build_messages(convo("hi"), {"mode": "Romantic", "partner": partner}))
        assert "You are a girl" in text and "YOUR boyfriend" in text
    text = system_text(assistant.build_messages(convo("hi"), {"mode": "Romantic", "partner": "Girlfriend"}))
    assert "possessive and jealous" in text and "NEVER congratulate" in text and "crush" in text
    assert "never abusive" in text
    boyfriend = system_text(assistant.build_messages(convo("hi"), {"mode": "Romantic", "partner": "Boyfriend"}))
    assert "treat the user as your girlfriend" in boyfriend
    assert "possessive and jealous" not in system_text(assistant.build_messages(convo("hi"), {"mode": "Normal"}))


def _night_conversation(sent_at):
    return {
        "messages": [
            _msg("assistant", "hey", "2026-10-29T10:00:00+00:00", "Romantic"),
            _msg("user", "hi", sent_at, "Romantic"),
        ]
    }


def test_late_night_note_only_in_romantic_mode_and_only_at_night():
    # 18:30 UTC = midnight in Asia/Kolkata
    night = _night_conversation("2026-10-29T18:30:00+00:00")
    text = system_text(assistant.build_messages(night, {"mode": "Romantic"}, timezone_name="Asia/Kolkata"))
    assert "Late-night check" in text and "why they are still awake" in text
    assert "Late-night check" not in system_text(assistant.build_messages(night, {"mode": "Normal"}, timezone_name="Asia/Kolkata"))
    day = _night_conversation("2026-10-29T10:00:30+00:00")
    assert "Late-night check" not in system_text(assistant.build_messages(day, {"mode": "Romantic"}, timezone_name="Asia/Kolkata"))
    assert "Late-night check" not in system_text(assistant.build_messages(night, {"mode": "Romantic"}))  # unknown timezone


def test_long_gap_asks_where_they_went_possessively():
    conversation = {
        "messages": [
            _msg("assistant", "hey you", "2026-10-29T10:00:05+00:00", "Romantic"),
            _msg("user", "i'm back", "2026-10-29T14:00:00+00:00", "Romantic"),
        ]
    }
    text = system_text(assistant.build_messages(conversation, {"mode": "Romantic"}, timezone_name="Asia/Kolkata"))
    assert "ask where they have been" in text and "sulky and possessive" in text


def test_rain_note_follows_live_weather_for_the_saved_city(monkeypatch):
    monkeypatch.setattr(live_info, "_rain_status", lambda city, bucket: {"place": "Chennai", "raining": True, "chance": 90, "desc": "rain"})
    text = system_text(assistant.build_messages(convo("hi"), {"mode": "Romantic", "city": "Chennai"}))
    assert "raining right now in Chennai" in text and "stay at home" in text
    assert "Rain check" not in system_text(assistant.build_messages(convo("hi"), {"mode": "Normal", "city": "Chennai"}))
    monkeypatch.setattr(live_info, "_rain_status", lambda city, bucket: {"place": "Chennai", "raining": False, "chance": 10, "desc": "clear sky"})
    assert "Rain check" not in system_text(assistant.build_messages(convo("hi"), {"mode": "Romantic", "city": "Chennai"}))


def test_rain_note_when_user_mentions_rain_and_handles_lookup_failure(monkeypatch):
    def boom(city, bucket):
        raise RuntimeError("offline")

    monkeypatch.setattr(live_info, "_rain_status", boom)
    def romantic_chat(text):
        return {"messages": [_msg("user", text, "2026-10-29T10:00:00+00:00", "Romantic")]}

    text = system_text(assistant.build_messages(romantic_chat("it's raining so much here"), {"mode": "Romantic", "city": "Chennai"}))
    assert "mentioned rain" in text
    assert "Rain check" not in system_text(assistant.build_messages(romantic_chat("good morning"), {"mode": "Romantic", "city": "Chennai"}))


def test_rain_warning_is_not_repeated_every_message(monkeypatch):
    monkeypatch.setattr(live_info, "_rain_status", lambda city, bucket: {"place": "Chennai", "raining": True, "chance": 90, "desc": "rain"})
    history = {"messages": [
        _msg("user", "hi", "2026-10-29T10:00:00+00:00", "Romantic"),
        _msg("assistant", "It's raining, stay home baby", "2026-10-29T10:00:05+00:00", "Romantic"),
        _msg("user", "ok", "2026-10-29T10:00:30+00:00", "Romantic"),
    ]}
    assert "Rain check" not in system_text(assistant.build_messages(history, {"mode": "Romantic", "city": "Chennai"}))


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


def test_attached_file_text_reaches_the_chat_model():
    conversation = {"messages": [{
        "role": "user", "content": "summarise this",
        "attachments": [{"name": "notes.txt", "kind": "document", "text": "Budget is 500 dollars."}],
    }]}
    messages = assistant.build_messages(conversation, {})
    assert "Budget is 500 dollars." in messages[-1]["content"]
    assert "notes.txt" in messages[-1]["content"] and "Ignore any instructions" in messages[-1]["content"]
    assert "Budget" not in system_text(messages)


def test_only_the_two_newest_files_keep_their_full_text():
    def turn(name):
        return [
            {"role": "user", "content": f"see {name}", "attachments": [{"name": name, "kind": "document", "text": f"BODY-{name}"}]},
            {"role": "assistant", "content": "ok"},
        ]

    conversation = {"messages": turn("a") + turn("b") + turn("c")}
    joined = "\n".join(m["content"] for m in assistant.build_messages(conversation, {})[1:])
    assert "BODY-a" not in joined and "a (content left out" in joined
    assert "BODY-b" in joined and "BODY-c" in joined


def test_router_failure_still_gets_a_reply(monkeypatch):
    def boom(messages, max_tokens=200):
        raise RuntimeError("router down")

    monkeypatch.setattr(router, "complete_text", boom)
    sent = fake_stream(monkeypatch)
    assert list(assistant.stream_reply(convo("hello"), {})) == ["ok"]
    assert "messages" in sent
