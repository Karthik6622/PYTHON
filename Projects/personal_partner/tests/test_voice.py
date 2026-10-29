import io
import wave

import pytest

from src import voice


def _wav(frames: int = 160) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"\x00\x00" * frames)
    return buffer.getvalue()


def test_speakable_text_removes_markdown_and_emoji():
    text = "**Correction:** No correction needed ✓\n---\nHey love 😊 [link](http://x.y) `code`"
    cleaned = voice.speakable_text(text)
    assert "*" not in cleaned and "---" not in cleaned and "😊" not in cleaned and "http" not in cleaned
    assert "Hey love" in cleaned and "link" in cleaned


def test_split_for_speech_respects_limit():
    text = "This is a sentence. " * 30 + "word " * 100
    chunks = voice.split_for_speech(text)
    assert chunks and all(len(chunk) <= voice.TTS_CHUNK_CHARS for chunk in chunks)
    assert sum(len(c) for c in chunks) <= voice.TTS_MAX_CHARS


def test_merge_wav_joins_frames():
    merged = voice.merge_wav([_wav(100), _wav(50)])
    with wave.open(io.BytesIO(merged), "rb") as reader:
        assert reader.getnframes() == 150


def test_transcribe_prefers_nvidia(monkeypatch):
    monkeypatch.setattr(voice, "_nvidia_transcribe", lambda wav: "hello there")
    monkeypatch.setattr(voice, "_whisper_transcribe", lambda wav: pytest.fail("Whisper should not be used"))
    assert voice.transcribe_audio(_wav()) == "hello there"


def test_transcribe_falls_back_to_whisper(monkeypatch):
    def broken(wav):
        raise voice.VoiceError("nvidia down")

    monkeypatch.setattr(voice, "_nvidia_transcribe", broken)
    monkeypatch.setattr(voice, "groq_configured", lambda: True)
    monkeypatch.setattr(voice, "_whisper_transcribe", lambda wav: "from whisper")
    assert voice.transcribe_audio(_wav()) == "from whisper"


def test_transcribe_reports_nvidia_error_without_groq_key(monkeypatch):
    def broken(wav):
        raise voice.VoiceError("nvidia down")

    monkeypatch.setattr(voice, "_nvidia_transcribe", broken)
    monkeypatch.setattr(voice, "groq_configured", lambda: False)
    with pytest.raises(voice.VoiceError, match="nvidia down"):
        voice.transcribe_audio(_wav())


def test_transcribe_rejects_empty_audio():
    with pytest.raises(voice.VoiceError):
        voice.transcribe_audio(b"")


def test_clean_transcript_handles_thinking_and_silence():
    assert voice._clean_transcript("<think>hmm</think>Hi there") == "Hi there"
    assert voice._clean_transcript("[no speech]") == ""


def test_voice_for_partner(monkeypatch):
    monkeypatch.setattr(voice, "_configured", lambda name, default="": "")
    assert voice.voice_for({"mode": "Romantic", "partner": "Boyfriend"}) == "troy"
    assert voice.voice_for({"mode": "Normal"}) == "hannah"


def test_synthesize_requires_groq_key(monkeypatch):
    monkeypatch.setattr(voice, "_configured", lambda name, default="": "")
    with pytest.raises(voice.VoiceError, match="GROQ_API_KEY"):
        voice.synthesize_speech("Hello there.")
