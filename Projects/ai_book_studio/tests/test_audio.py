"""Audiobook, parallel chapters and Cloudflare image tests (no network)."""

from __future__ import annotations

import base64
import io
import json
import time
import wave

from config import TTS_SAMPLE_RATE, ImageSettings
from services.audio_book import (
    AudiobookBuilder,
    AudioJob,
    audio_dir,
    build_sections,
    existing_audio,
    language_code_for,
    split_for_speech,
    strip_markdown,
    validate_voice_prompt,
)
from services.book_pipeline import BookPipeline
from services.image_generator import CloudflareImageGenerator, PlaceholderImageGenerator

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
    text = " ".join(f"Sentence number {i} is here." for i in range(60)) + " " + "word " * 120
    parts = split_for_speech(text)
    assert parts and all(len(part) <= 220 for part in parts)
    assert language_code_for("English") == "en-US"
    assert language_code_for("Klingon") is None


def test_voice_prompt_validation():
    def wav(seconds: float) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(TTS_SAMPLE_RATE)
            out.writeframes(b"\x00\x00" * int(TTS_SAMPLE_RATE * seconds))
        return buffer.getvalue()

    assert validate_voice_prompt(wav(5)) is None
    assert validate_voice_prompt(wav(0.5)) is not None
    assert validate_voice_prompt(b"not a wav") is not None


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


class _Response:
    status_code = 200
    ok = True
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self, payload):
        self.payload = payload
        self.calls: list[dict] = []

    def post(self, url, json=None, headers=None, timeout=None):  # noqa: A002
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _Response(self.payload)


def test_cloudflare_generator_decodes_image(tmp_path):
    image = base64.b64encode(b"fake-image-bytes").decode()
    session = _Session({"result": {"image": image}, "success": True})
    settings = ImageSettings(api_key="", cloudflare_account_id="acct", cloudflare_token="tok")
    path = CloudflareImageGenerator(settings, session).generate_image("a lantern", tmp_path / "x.jpg", "square")
    assert path.read_bytes() == b"fake-image-bytes"
    call = session.calls[0]
    assert call["url"].endswith("/accounts/acct/ai/run/@cf/black-forest-labs/flux-1-schnell")
    assert call["headers"]["Authorization"] == "Bearer tok"
    assert call["json"]["prompt"] == "a lantern" and "seed" not in call["json"]
    assert settings.use_cloudflare and settings.provider_label == "Cloudflare FLUX.1 schnell"
