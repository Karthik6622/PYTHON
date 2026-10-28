"""Audiobook: turns the written book into spoken audio with text-to-speech.

The default engine is OpenAI ``tts-1`` on Pollinations; Kokoro on fal.ai (English, Spanish, French) is the alternative.
The book is cut into sentence-aligned pieces that are narrated in parallel (several requests at a time) and
joined into one WAV file per section (title, front matter, every chapter, conclusion).

This module never imports Streamlit. The interface polls ``AudioJob`` for live status.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import threading
import time
import wave
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import requests

from config import POLLINATIONS_TTS_URL, TTS_SAMPLE_RATE, TTSSettings
from models.book_models import BookProject
from utils.retry_utils import AIBookError, call_with_retries, redact
from utils.text_utils import chapter_label, label

LOGGER = logging.getLogger("ai_book_studio.audio")

# Book languages that can be narrated, with their short codes, fal endpoints and Kokoro voices.
LANGUAGE_CODES = {"English": "en", "Spanish": "es", "French": "fr"}
ENDPOINTS = {
    "en": "fal-ai/kokoro/american-english",
    "es": "fal-ai/kokoro/spanish",
    "fr": "fal-ai/kokoro/french",
}
VOICES = {
    "en": [
        "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah",
        "af_sky", "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael", "am_onyx", "am_puck", "am_santa",
    ],
    "es": ["ef_dora", "em_alex", "em_santa"],
    "fr": ["ff_siwis"],
}
POLLINATIONS_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]  # OpenAI tts-1 voices
MAX_CHARS = 800  # characters per speech request (about a minute of speech)
PAUSE_SECONDS = 0.25
_WRITTEN_BY = {"English": "Written by", "Spanish": "Escrito por", "French": "Écrit par"}


class AudioError(AIBookError):
    default_message = "Audio generation failed."


class TransientAudioError(AudioError):
    """Temporary problem that is worth retrying."""

    default_message = "The speech service is busy or temporarily unavailable."


class AudioStopped(AIBookError):
    default_message = "Audio generation was stopped. Finished sections are saved; press Continue to carry on."


def language_code_for(language: str, provider: str = "fal") -> str | None:
    """Short language code for a book language, or ``None`` when audio is not available for it.

    Pollinations ``tts-1`` detects the language itself, so every book language can be narrated with it.
    """
    code = LANGUAGE_CODES.get(language)
    if code is None and provider == "pollinations":
        return re.sub(r"[^a-z]", "", language.lower())[:12] or "xx"
    return code


# --------------------------------------------------------------------------------------
# Text preparation
# --------------------------------------------------------------------------------------
def strip_markdown(text: str) -> str:
    """Remove Markdown marks that should not be read aloud."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*([-*_]\s*){3,}$", "", text, flags=re.M)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*\d+[.)]\s+", "", text, flags=re.M)
    text = re.sub(r"(\*\*|__|\*|_|`)", "", text)
    return text.strip()


_SENTENCE_END = re.compile(r"(?<=[.!?…。！？])\s+")
_END_MARKS = ".!?…。！？:;,"


def _break_long(sentence: str, limit: int) -> list[str]:
    if len(sentence) <= limit:
        return [sentence]
    pieces, current = [], ""
    for word in sentence.split():
        if current and len(current) + 1 + len(word) > limit:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        pieces.append(current)
    return pieces


def split_for_speech(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Cut text into pieces of at most ``limit`` characters, at paragraph and sentence boundaries."""
    chunks: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        lines = []
        for line in paragraph.splitlines():
            line = " ".join(line.split())
            if line:
                lines.append(line if line[-1] in _END_MARKS else line + ".")
        flat = " ".join(lines)
        if not flat:
            continue
        current = ""
        for sentence in _SENTENCE_END.split(flat):
            for piece in _break_long(sentence, limit):
                if current and len(current) + 1 + len(piece) > limit:
                    chunks.append(current)
                    current = piece
                else:
                    current = f"{current} {piece}".strip()
        if current:
            chunks.append(current)
    return chunks


@dataclass(frozen=True)
class AudioSection:
    """One narrated part of the book. ``key`` is the file name without extension."""

    key: str
    title: str
    text: str


def build_sections(project: BookProject, include_front: bool = True, include_back: bool = True) -> list[AudioSection]:
    """The parts of the book that are read aloud, in reading order."""
    plan = project.plan
    if plan is None:
        return []
    language = plan.language
    sections: list[AudioSection] = []

    def add(slug: str, title: str, text: str) -> None:
        text = text.strip()
        if text:
            sections.append(AudioSection(f"{len(sections):02d}_{slug}", title, text))

    by = _WRITTEN_BY.get(language, _WRITTEN_BY["English"])
    intro = ". ".join(part.strip().rstrip(".") for part in (plan.title, plan.subtitle, f"{by} {plan.author}" if plan.author else "") if part and part.strip())
    add("title", "Title", intro + "." if intro else "")
    if include_front:
        for key in ("dedication", "preface", "introduction"):
            body = strip_markdown(project.front_matter.get(key, ""))
            if body:
                add(key, label(key, language), f"{label(key, language)}.\n\n{body}")
    for chapter in plan.chapters:
        number = chapter.chapter_number
        body = strip_markdown(project.chapters.get(number, ""))
        if body:
            heading = f"{chapter_label(number, language)}. {chapter.title}."
            add(f"chapter_{number:02d}", f"{chapter_label(number, language)}: {chapter.title}", f"{heading}\n\n{body}")
    if include_back:
        body = strip_markdown(project.front_matter.get("conclusion", ""))
        if body:
            add("conclusion", label("conclusion", language), f"{label('conclusion', language)}.\n\n{body}")
    return sections


# --------------------------------------------------------------------------------------
# Speech engines
# --------------------------------------------------------------------------------------
class TTSEngine(Protocol):
    """Turns a short text into raw 16-bit mono PCM audio. ``sample_rate`` (optional) is the rate of that audio."""

    def synthesize(self, text: str, language_code: str) -> bytes: ...


class FalTTS:
    """Kokoro text-to-speech on fal.ai (``fal-ai/kokoro/*``) through the ``fal-client`` package.

    Each request returns a WAV file URL; the WAV is downloaded and its PCM data handed to the builder.
    The API key is passed to the client and never logged.
    """

    _MAX_DOWNLOAD_BYTES = 60 * 1024 * 1024

    def __init__(self, settings: TTSSettings, voice: str = "", client=None, session: requests.Session | None = None) -> None:
        if not settings.api_key:
            raise AudioError("The fal API key is missing. Add FAL_KEY to .streamlit/secrets.toml or your environment.")
        self.settings = settings
        self.voice = voice or settings.voice
        self.sample_rate = TTS_SAMPLE_RATE
        self._client = client
        self._session = session or requests.Session()
        self._lock = threading.Lock()
        self._rate_set = False

    def _get_client(self):
        with self._lock:
            if self._client is None:
                try:
                    import fal_client
                except ImportError as exc:
                    raise AudioError("The fal client is not installed. Run: pip install fal-client") from exc
                self._client = fal_client.SyncClient(key=self.settings.api_key, default_timeout=180.0)
            return self._client

    def synthesize(self, text: str, language_code: str) -> bytes:
        endpoint = ENDPOINTS.get(language_code)
        if endpoint is None:
            raise AudioError("This language is not available for audio.")
        voices = VOICES[language_code]
        voice = self.voice if self.voice in voices else voices[0]
        return call_with_retries(lambda: self._once(endpoint, text, voice), retryable=(TransientAudioError,))

    def _once(self, endpoint: str, text: str, voice: str) -> bytes:
        client = self._get_client()
        try:
            result = client.subscribe(endpoint, arguments={"prompt": text, "voice": voice})
        except Exception as exc:  # noqa: BLE001 - translated below
            raise self._translate(exc) from exc
        url = ((result or {}).get("audio") or {}).get("url") if isinstance(result, dict) else None
        if not isinstance(url, str) or not url:
            raise TransientAudioError("The speech service returned no audio.")
        return self._pcm(self._download(url))

    def _download(self, url: str) -> bytes:
        if not url.startswith("https://"):
            raise AudioError("The speech service returned a non-HTTPS audio URL, which was refused.")
        try:
            with self._session.get(url, timeout=60, stream=True) as response:
                response.raise_for_status()
                chunks, total = [], 0
                for chunk in response.iter_content(65536):
                    total += len(chunk)
                    if total > self._MAX_DOWNLOAD_BYTES:
                        raise AudioError("The generated audio is too large.")
                    chunks.append(chunk)
        except requests.RequestException as exc:
            raise TransientAudioError("The generated audio could not be downloaded.") from exc
        return b"".join(chunks)

    def _pcm(self, wav_bytes: bytes) -> bytes:
        try:
            with wave.open(io.BytesIO(wav_bytes)) as wav:
                channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
                frames = wav.readframes(wav.getnframes())
        except (wave.Error, EOFError) as exc:
            raise AudioError("The speech service returned audio that is not a PCM WAV file.") from exc
        if channels != 1 or width != 2:
            raise AudioError("The speech service returned audio in an unexpected format (expected mono 16-bit WAV).")
        with self._lock:
            if not self._rate_set:
                self.sample_rate, self._rate_set = rate, True
            elif rate != self.sample_rate:
                raise AudioError("The speech service changed the audio sample rate in the middle of a book.")
        return frames

    def _translate(self, exc: Exception) -> AIBookError:
        status = getattr(exc, "status_code", None)
        detail = redact(exc)
        for part in {self.settings.api_key, *self.settings.api_key.split(":")}:
            if len(part) >= 6:
                detail = detail.replace(part, "***")
        detail = detail[:200]
        LOGGER.warning("Speech request failed (%s %s): %s", type(exc).__name__, status, detail)
        if status == 401:
            return AudioError(f"fal authentication failed. Check FAL_KEY. (fal says: {detail})")
        if status == 403:
            return AudioError(
                "fal denied access. Check that FAL_KEY is valid, allows the fal-ai/kokoro models and that your fal account has credit. "
                f"(fal says: {detail})"
            )
        if status in (429, 500, 502, 503, 504):
            return TransientAudioError()
        if status in (400, 422):
            return AudioError(f"The speech service rejected the text ({detail}).")
        if isinstance(exc, (TimeoutError, ConnectionError)) or any(word in type(exc).__name__ for word in ("Timeout", "Transport", "Connect", "Network")):
            return TransientAudioError()
        return AudioError(f"The speech service failed ({type(exc).__name__}).")


class PollinationsTTS:
    """OpenAI ``tts-1`` text-to-speech on Pollinations (``POST /v1/audio/speech``, OpenAI compatible).

    The reply is a WAV file (24 kHz, mono, 16-bit) whose PCM data is handed to the builder.
    The API key is sent as a Bearer token and never logged or shown.
    """

    _MAX_BYTES = 60 * 1024 * 1024
    _pcm = FalTTS._pcm  # same WAV check and sample-rate consistency as the fal engine

    def __init__(self, settings: TTSSettings, voice: str = "", session: requests.Session | None = None) -> None:
        if not settings.pollinations_key:
            raise AudioError("The Pollinations API key is missing. Add POLLINATIONS_API_KEY to .streamlit/secrets.toml or your environment.")
        self.settings = settings
        self.voice = voice or settings.voice
        self.sample_rate = TTS_SAMPLE_RATE
        self._session = session or requests.Session()
        self._lock = threading.Lock()
        self._rate_set = False

    def synthesize(self, text: str, language_code: str) -> bytes:
        voice = self.voice if self.voice in POLLINATIONS_VOICES else POLLINATIONS_VOICES[0]
        return call_with_retries(lambda: self._once(text, voice), retryable=(TransientAudioError,))

    def _once(self, text: str, voice: str) -> bytes:
        payload = {"model": self.settings.pollinations_model, "input": text, "voice": voice, "response_format": "wav"}
        headers = {"Authorization": f"Bearer {self.settings.pollinations_key}", "Content-Type": "application/json"}
        try:
            response = self._session.post(POLLINATIONS_TTS_URL, json=payload, headers=headers, timeout=(10, 180))
        except requests.RequestException as exc:
            LOGGER.warning("Pollinations request failed: %s", type(exc).__name__)
            raise TransientAudioError() from exc
        if response.status_code != 200:
            raise self._translate(response)
        data = response.content
        if len(data) > self._MAX_BYTES:
            raise AudioError("The generated audio is too large.")
        if not data:
            raise TransientAudioError("The speech service returned no audio.")
        return self._pcm(data)

    def _detail(self, response) -> str:
        try:
            body = response.json()
            error = body.get("error", body) if isinstance(body, dict) else body
            text = error.get("message", "") if isinstance(error, dict) else str(error)
        except ValueError:
            text = response.text or ""
        text = redact(text)
        key = self.settings.pollinations_key
        if len(key) >= 6:
            text = text.replace(key, "***")
        return " ".join(text.split())[:200]

    def _translate(self, response) -> AIBookError:
        status = response.status_code
        detail = self._detail(response)
        LOGGER.warning("Pollinations speech request failed (%s): %s", status, detail)
        suffix = f" (Pollinations says: {detail})" if detail else ""
        if status == 401:
            return AudioError(f"Pollinations rejected the API key. Check POLLINATIONS_API_KEY.{suffix}")
        if status == 402:
            return AudioError(f"Pollinations has no Pollen left for this key or account. Top up at enter.pollinations.ai.{suffix}")
        if status == 403:
            return AudioError(
                "Pollinations denied access. The key must be allowed to use the audio model "
                f"({self.settings.pollinations_model}); check its permissions at enter.pollinations.ai.{suffix}"
            )
        if status in (429, 500, 502, 503, 504):
            return TransientAudioError()
        if status in (400, 422):
            return AudioError(f"The speech service rejected the text.{suffix}")
        return AudioError(f"The speech service failed (HTTP {status}).{suffix}")


def make_engine(settings: TTSSettings, voice: str = "") -> TTSEngine:
    """The speech engine chosen by the settings (Pollinations first, fal as the alternative)."""
    if settings.active_provider == "pollinations":
        return PollinationsTTS(settings, voice=voice)
    return FalTTS(settings, voice=voice)


# --------------------------------------------------------------------------------------
# Narration
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class AudioFile:
    key: str
    title: str
    path: Path
    seconds: float


@dataclass(frozen=True)
class AudioSummary:
    files: list[AudioFile]

    @property
    def seconds(self) -> float:
        return sum(item.seconds for item in self.files)


def audio_dir(project_dir: Path) -> Path:
    return project_dir / "audio"


def _manifest_path(folder: Path) -> Path:
    return folder / "manifest.json"


def _read_manifest(folder: Path) -> dict:
    try:
        data = json.loads(_manifest_path(folder).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def existing_audio(folder: Path) -> list[AudioFile]:
    """Narrated sections that are saved on disk, in reading order."""
    manifest = _read_manifest(folder)
    found = []
    for key, entry in sorted(manifest.items(), key=lambda item: item[0]):
        path = folder / f"{key}.wav"
        if isinstance(entry, dict) and path.exists() and path.stat().st_size > 0:
            found.append(AudioFile(key, str(entry.get("title", key)), path, float(entry.get("seconds", 0.0))))
    return found


def voices_for(language_code: str, provider: str = "fal") -> list[str]:
    """Voices offered for a language code (empty when the language is not supported)."""
    if provider == "pollinations":
        return list(POLLINATIONS_VOICES) if language_code else []
    return list(VOICES.get(language_code, []))


class AudiobookBuilder:
    """Narrates a finished book section by section. Finished sections are saved and skipped on the next run."""

    def __init__(
        self,
        project: BookProject,
        folder: Path,
        engine: TTSEngine,
        language_code: str,
        sections: list[AudioSection],
        voice: str = "",
        workers: int = 3,
    ) -> None:
        self.project = project
        self.folder = folder
        self.engine = engine
        self.language_code = language_code
        self.sections = sections
        self.voice = voice
        self.workers = max(1, workers)

    def build(self, progress: Callable[[float, str], None], should_stop: Callable[[], bool]) -> AudioSummary:
        self.folder.mkdir(parents=True, exist_ok=True)
        plan = [(section, split_for_speech(section.text)) for section in self.sections]
        total = max(sum(len(chunks) for _, chunks in plan), 1)
        manifest = _read_manifest(self.folder)
        done = 0
        files: list[AudioFile] = []
        for section, chunks in plan:
            if should_stop():
                raise AudioStopped()
            digest = hashlib.sha256(
                json.dumps([self.voice, self.language_code, chunks], ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            path = self.folder / f"{section.key}.wav"
            entry = manifest.get(section.key)
            if isinstance(entry, dict) and entry.get("sha") == digest and path.exists() and path.stat().st_size > 0:
                done += len(chunks)
                progress(min(done / total, 0.99), f"{section.title}: already narrated")
                files.append(AudioFile(section.key, section.title, path, float(entry.get("seconds", 0.0))))
                continue
            progress(min(done / total, 0.99), f"Narrating {section.title}")

            def on_chunk(count: int, base: int = done, title: str = section.title) -> None:
                progress(min((base + count) / total, 0.99), f"Narrating {title} ({count} of {len(chunks)} parts)")

            pcm = self._narrate(chunks, should_stop, on_chunk)
            seconds = self._write_wav(path, pcm, int(getattr(self.engine, "sample_rate", TTS_SAMPLE_RATE)))
            done += len(chunks)
            manifest[section.key] = {"title": section.title, "sha": digest, "seconds": seconds}
            _manifest_path(self.folder).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            files.append(AudioFile(section.key, section.title, path, seconds))
        progress(1.0, "Your audiobook is ready.")
        return AudioSummary(files)

    def _narrate(self, chunks: list[str], should_stop: Callable[[], bool], on_chunk: Callable[[int], None]) -> list[bytes]:
        """Speak all pieces of one section, several at a time, keeping them in reading order."""
        results: list[bytes] = []
        with ThreadPoolExecutor(max_workers=min(self.workers, max(len(chunks), 1)), thread_name_prefix="tts") as pool:
            futures = [pool.submit(self.engine.synthesize, chunk, self.language_code) for chunk in chunks]
            try:
                for index, future in enumerate(futures, start=1):
                    results.append(future.result())
                    on_chunk(index)
                    if should_stop():
                        raise AudioStopped()
            except BaseException:
                for pending in futures:
                    pending.cancel()
                raise
        return results

    @staticmethod
    def _write_wav(path: Path, parts: list[bytes], rate: int) -> float:
        silence = b"\x00\x00" * int(rate * PAUSE_SECONDS)
        temp = path.with_name(path.stem + ".tmp.wav")
        frames = 0
        with wave.open(str(temp), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            for index, part in enumerate(parts):
                if index:
                    out.writeframes(silence)
                    frames += len(silence) // 2
                out.writeframes(part)
                frames += len(part) // 2
        temp.replace(path)
        return frames / rate


class AudioJob:
    """One background audiobook run for one project (the audio counterpart of ``GenerationJob``)."""

    def __init__(self, builder: AudiobookBuilder) -> None:
        self.builder = builder
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.fraction = 0.0
        self.message = "Starting..."
        self.log: deque[str] = deque(maxlen=40)
        self.started_at = 0.0
        self.finished_at = 0.0
        self.error: str | None = None
        self.stopped = False
        self.summary: AudioSummary | None = None
        self.handled = False

    @property
    def project(self) -> BookProject:
        return self.builder.project

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def stopping(self) -> bool:
        return self.running and self._stop.is_set()

    @property
    def elapsed_seconds(self) -> int:
        end = self.finished_at or time.time()
        return int(max(end - self.started_at, 0)) if self.started_at else 0

    def start(self) -> None:
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._run, name="audiobook", daemon=True)
        self._thread.start()

    def request_stop(self) -> None:
        self._stop.set()
        self._on_progress(self.fraction, "Stopping after the current part...")

    def log_lines(self) -> list[str]:
        with self._lock:
            return list(self.log)

    def _on_progress(self, fraction: float, message: str) -> None:
        with self._lock:
            self.fraction = fraction
            if message != self.message and " parts)" not in message:  # part-by-part updates would flood the log
                self.log.append(f"{time.strftime('%H:%M:%S')}  {message}")
            self.message = message

    def _run(self) -> None:
        try:
            self.summary = self.builder.build(self._on_progress, self._stop.is_set)
        except AudioStopped:
            self.stopped = True
            self._on_progress(self.fraction, "Stopped. Finished sections are saved.")
        except AIBookError as exc:
            self.error = exc.user_message
            LOGGER.warning("Audiobook stopped: %s: %s", type(exc).__name__, redact(exc))
        except Exception as exc:  # noqa: BLE001
            self.error = f"Audio generation stopped unexpectedly ({type(exc).__name__}). Finished sections are saved."
            LOGGER.error("Audiobook crashed: %s: %s", type(exc).__name__, redact(exc), exc_info=True)
        finally:
            self.finished_at = time.time()
