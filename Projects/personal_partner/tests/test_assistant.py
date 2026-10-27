from src import assistant, live_info


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


def test_weather_without_city_asks_instead_of_guessing():
    text = system_text(assistant.build_messages(convo("what's the weather today?"), {}))
    assert "no city is known" in text


def test_weather_city_detection_and_saved_city(monkeypatch):
    assert live_info.extract_city("weather in New York today?") == "New York"
    assert live_info.extract_city("weather today") is None
    monkeypatch.setattr(live_info, "_fetch_weather", lambda city, bucket: f"Live weather for {city}")
    note = live_info.weather_note(["how is the weather today?"], default_city="Chennai")
    assert note and "Live weather for Chennai" in note
    assert live_info.weather_note(["tell me a joke"], default_city="Chennai") is None


def test_weather_lookup_failure_is_reported_honestly(monkeypatch):
    def boom(city, bucket):
        raise RuntimeError("offline")

    monkeypatch.setattr(live_info, "_fetch_weather", boom)
    note = live_info.weather_note(["weather in Paris"])
    assert note and "Do not invent weather" in note
