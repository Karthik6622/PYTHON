"""Audiobook and parallel chapter tests (no network)."""

from __future__ import annotations

import io
import json
import time
import wave

import pytest

from config import TTS_SAMPLE_RATE, TTSSettings
from services.audio_book import (
    MAX_CHARS,
    AudiobookBuilder,
    AudioError,
    AudioJob,
    FalTTS,
    audio_dir,
    build_sections,
    existing_audio,
    language_code_for,
    split_for_speech,
    strip_markdown,
    voices_for,
)
from services.book_pipeline import BookPipeline
from services.image_generator import PlaceholderImageGenerator

from conftest import FakeLLM


class FakeTTS:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def synthesize(self, text: str, language_code: str) -> bytes:
        self.calls.append(text)
        return b"\x00\x00" * (TTS_SAMPLE_RATE // 10)  # 0.1 s of silence


def _book(storage, book_input, workers: int = 1):
    project = storage.create_project(book_input)
    pipeline = BookPipeline(
        project, storage, llm=FakeLLM(fail_first_review=False), image_generator=PlaceholderImageGenerator(), chapter_workers=workers
    )
    pipeline.create_plan()
    pipeline.generate_complete_book()
    return project


def test_text_cleaning_and_splitting():
    assert "#" not in strip_markdown("# Title\n\nSome **bold** text.")
    text = " ".join(f"Sentence number {i} is here." for i in range(300)) + " " + "word " * 400
    parts = split_for_speech(text)
    assert parts and all(len(part) <= MAX_CHARS for part in parts)
    assert language_code_for("English") == "en"
    assert language_code_for("Klingon") is None
    assert voices_for("en")[0] == "af_heart" and voices_for("fr") == ["ff_siwis"] and voices_for("xx") == []


def _wav(rate: int = 24000, seconds: float = 0.1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"\x01\x00" * int(rate * seconds))
    return buffer.getvalue()


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self) -> None:
        pass

    def iter_content(self, size: int):
        yield self._data


class _FakeSession:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.urls: list[str] = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return _FakeResponse(self.data)


class _FakeFal:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result if result is not None else {"audio": {"url": "https://example.com/a.wav"}}
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def subscribe(self, application, arguments=None, **kwargs):
        self.calls.append((application, arguments))
        if self.error:
            raise self.error
        return self.result


def test_fal_tts_returns_pcm_and_uses_real_sample_rate():
    client, session = _FakeFal(), _FakeSession(_wav(rate=16000, seconds=0.5))
    engine = FalTTS(TTSSettings(api_key="k"), voice="am_adam", client=client, session=session)
    pcm = engine.synthesize("Hello there.", "en")
    assert len(pcm) == 16000 // 2 * 2 and engine.sample_rate == 16000
    assert client.calls == [("fal-ai/kokoro/american-english", {"prompt": "Hello there.", "voice": "am_adam"})]
    assert session.urls == ["https://example.com/a.wav"]


def test_fal_tts_falls_back_to_a_valid_voice_for_the_language():
    client = _FakeFal()
    engine = FalTTS(TTSSettings(api_key="k"), voice="af_heart", client=client, session=_FakeSession(_wav()))
    engine.synthesize("Bonjour.", "fr")
    assert client.calls[0] == ("fal-ai/kokoro/french", {"prompt": "Bonjour.", "voice": "ff_siwis"})


def test_fal_tts_errors_do_not_leak_and_are_clear():
    class Boom(Exception):
        status_code = 401

    engine = FalTTS(TTSSettings(api_key="secret-key"), client=_FakeFal(error=Boom("bad key secret-key")), session=_FakeSession(b""))
    with pytest.raises(AudioError) as info:
        engine.synthesize("Hi.", "en")
    assert "FAL_KEY" in str(info.value) and "secret-key" not in str(info.value)
    with pytest.raises(AudioError):
        FalTTS(TTSSettings(api_key=""))
    with pytest.raises(AudioError):
        FalTTS(TTSSettings(api_key="k"), client=_FakeFal(), session=_FakeSession(_wav())).synthesize("Hi.", "xx")
    with pytest.raises(AudioError):
        FalTTS(TTSSettings(api_key="k"), client=_FakeFal(), session=_FakeSession(b"junk")).synthesize("Hi.", "en")
    refused = FalTTS(TTSSettings(api_key="k"), client=_FakeFal({"audio": {"url": "http://example.com/a.wav"}}), session=_FakeSession(_wav()))
    with pytest.raises(AudioError):
        refused.synthesize("Hi.", "en")


def test_parallel_chapters_complete(storage, book_input):
    project = _book(storage, book_input, workers=3)
    assert project.status.stage == "completed"
    assert all(project.chapter_done(n) for n in (1, 2, 3))
    assert set(storage.load_project(project.project_id).chapters) == {1, 2, 3}


def test_audiobook_builds_and_resumes(storage, book_input, tmp_path):
    project = _book(storage, book_input)
    sections = build_sections(project)
    assert sections[0].key.endswith("_title")
    assert sum(1 for s in sections if "chapter" in s.key) == 3

    folder = audio_dir(tmp_path)
    engine = FakeTTS()
    summary = AudiobookBuilder(project, folder, engine, "en-US", sections, voice="v", workers=2).build(lambda f, m: None, lambda: False)
    assert len(summary.files) == len(sections) and summary.seconds > 0
    assert len(existing_audio(folder)) == len(sections)
    assert all(item.path.read_bytes()[:4] == b"RIFF" for item in summary.files)
    first_calls = len(engine.calls)

    AudiobookBuilder(project, folder, engine, "en-US", sections, voice="v").build(lambda f, m: None, lambda: False)
    assert len(engine.calls) == first_calls  # nothing narrated twice

    AudiobookBuilder(project, folder, engine, "en-US", sections, voice="other").build(lambda f, m: None, lambda: False)
    assert len(engine.calls) == first_calls * 2  # a new voice narrates everything again


def test_audio_job_completes_and_stops(storage, book_input, tmp_path):
    project = _book(storage, book_input)
    sections = build_sections(project)
    builder = AudiobookBuilder(project, audio_dir(tmp_path), FakeTTS(), "en-US", sections)
    job = AudioJob(builder)
    job.start()
    deadline = time.time() + 60
    while job.running and time.time() < deadline:
        time.sleep(0.05)
    assert job.summary is not None and job.error is None and not job.stopped
    assert json.loads((audio_dir(tmp_path) / "manifest.json").read_text(encoding="utf-8"))

    stopped = AudioJob(AudiobookBuilder(project, audio_dir(tmp_path / "x"), FakeTTS(), "en-US", sections))
    stopped.request_stop()
    stopped.start()
    while stopped.running and time.time() < deadline:
        time.sleep(0.05)
    assert stopped.stopped and stopped.summary is None
