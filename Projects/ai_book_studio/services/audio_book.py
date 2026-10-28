"""Audiobook: turns the written book into spoken audio with NVIDIA Magpie TTS Zeroshot.

The model is served over gRPC (Riva) and uses the same NVIDIA API key as the text model. It speaks at most about
20 seconds per request, so the book is cut into short, sentence-aligned pieces that are narrated in parallel and
joined into one WAV file per section (title, front matter, every chapter, conclusion).

This module never imports Streamlit. The interface polls ``AudioJob`` for live status.
"""

from __future__ import annotations

import hashlib
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

from config import TTS_SAMPLE_RATE, TTSSettings
from models.book_models import BookProject
from utils.retry_utils import AIBookError, NvidiaKeyMissingError, call_with_retries, redact
from utils.text_utils import chapter_label, label

LOGGER = logging.getLogger("ai_book_studio.audio")

# Languages the Magpie TTS Zeroshot model can speak, mapped to its language codes.
LANGUAGE_CODES = {"English": "en-US", "Spanish": "es-US", "French": "fr-FR"}
MAX_CHARS = 220  # about 15 seconds of speech, safely under the model's 20 second limit per request
PAUSE_SECONDS = 0.25
VOICE_PROMPT_NAME = "voice_prompt.wav"
_WRITTEN_BY = {"English": "Written by", "Spanish": "Escrito por", "French": "Écrit par"}


class AudioError(AIBookError):
    default_message = "Audio generation failed."


class TransientAudioError(AudioError):
    """Temporary problem that is worth retrying."""

    default_message = "The speech service is busy or temporarily unavailable."


class AudioStopped(AIBookError):
    default_message = "Audio generation was stopped. Finished sections are saved; press Continue to carry on."


def language_code_for(language: str) -> str | None:
    """Magpie language code for a book language, or ``None`` when the model cannot speak it."""
    return LANGUAGE_CODES.get(language)


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
    """Turns a short text into raw 16-bit mono PCM audio at ``TTS_SAMPLE_RATE``."""

    def synthesize(self, text: str, language_code: str) -> bytes: ...


class MagpieTTS:
    """NVIDIA Magpie TTS Zeroshot through the hosted gRPC endpoint (``nvidia-riva-client``)."""

    def __init__(self, settings: TTSSettings, voice_prompt: Path | None = None) -> None:
        if not settings.api_key:
            raise NvidiaKeyMissingError()
        if not settings.function_id:
            raise AudioError(
                "The Magpie TTS function id is missing. Copy it from build.nvidia.com (magpie-tts-zeroshot, Python example, "
                "'function-id') into NVIDIA_TTS_FUNCTION_ID in .streamlit/secrets.toml."
            )
        self.settings = settings
        self.voice_prompt = voice_prompt if voice_prompt and voice_prompt.exists() else None
        self._service = None
        self._lock = threading.Lock()

    def _get_service(self):
        with self._lock:
            if self._service is None:
                try:
                    import riva.client
                except ImportError as exc:
                    raise AudioError("The speech client is not installed. Run: pip install nvidia-riva-client") from exc
                auth = riva.client.Auth(
                    use_ssl=True,
                    uri=self.settings.server,
                    metadata_args=[["function-id", self.settings.function_id], ["authorization", f"Bearer {self.settings.api_key}"]],
                )
                self._service = riva.client.SpeechSynthesisService(auth)
            return self._service

    def synthesize(self, text: str, language_code: str) -> bytes:
        return call_with_retries(lambda: self._once(text, language_code), retryable=(TransientAudioError,))

    def _once(self, text: str, language_code: str) -> bytes:
        import grpc
        import riva.client

        service = self._get_service()
        kwargs: dict = {
            "voice_name": self.settings.voice,
            "language_code": language_code,
            "encoding": riva.client.AudioEncoding.LINEAR_PCM,
            "sample_rate_hz": TTS_SAMPLE_RATE,
        }
        if self.voice_prompt is not None:
            kwargs["zero_shot_audio_prompt_file"] = str(self.voice_prompt)
        try:
            response = service.synthesize(text, **kwargs)
        except grpc.RpcError as exc:
            raise self._translate(exc) from exc
        if not response.audio:
            raise TransientAudioError("The speech service returned no audio.")
        return bytes(response.audio)

    @staticmethod
    def _translate(exc) -> AIBookError:
        code = exc.code().name if hasattr(exc, "code") and exc.code() else "UNKNOWN"
        LOGGER.warning("Speech request failed (%s): %s", code, redact(exc.details() if hasattr(exc, "details") else exc))
        if code in {"UNAUTHENTICATED", "PERMISSION_DENIED"}:
            return AudioError("Speech authentication failed. Check NVIDIA_API_KEY and that it has access to Magpie TTS Zeroshot.")
        if code in {"UNAVAILABLE", "DEADLINE_EXCEEDED", "RESOURCE_EXHAUSTED", "INTERNAL", "ABORTED"}:
            return TransientAudioError()
        if code == "NOT_FOUND":
            return AudioError("The speech function was not found. Check NVIDIA_TTS_FUNCTION_ID.")
        return AudioError(f"The speech service rejected the request ({code}).")


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


def voice_tag(voice: str, prompt: Path | None) -> str:
    """Changes when the voice or the voice sample changes, so old audio is not reused."""
    if prompt is not None and prompt.exists():
        return f"{voice}|{hashlib.sha256(prompt.read_bytes()).hexdigest()[:16]}"
    return voice


def validate_voice_prompt(data: bytes) -> str | None:
    """Return a problem description for an unusable voice sample, or ``None`` when it looks fine."""
    import io

    if len(data) > 8 * 1024 * 1024:
        return "The voice sample is larger than 8 MB."
    try:
        with wave.open(io.BytesIO(data)) as sample:
            seconds = sample.getnframes() / max(sample.getframerate(), 1)
    except (wave.Error, EOFError):
        return "The voice sample must be a PCM WAV file."
    if seconds < 2:
        return "The voice sample is too short. Use 3 to 10 seconds of clear speech."
    if seconds > 30:
        return "The voice sample is too long. Use 3 to 10 seconds of clear speech."
    return None


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
            seconds = self._write_wav(path, pcm)
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
    def _write_wav(path: Path, parts: list[bytes]) -> float:
        silence = b"\x00\x00" * int(TTS_SAMPLE_RATE * PAUSE_SECONDS)
        temp = path.with_name(path.stem + ".tmp.wav")
        frames = 0
        with wave.open(str(temp), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(TTS_SAMPLE_RATE)
            for index, part in enumerate(parts):
                if index:
                    out.writeframes(silence)
                    frames += len(silence) // 2
                out.writeframes(part)
                frames += len(part) // 2
        temp.replace(path)
        return frames / TTS_SAMPLE_RATE


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
