"""Voice chat: speech to text (NVIDIA Nemotron omni, Groq Whisper fallback) and text to speech (Groq).

Flow: microphone audio -> transcript -> the normal Nemotron chat pipeline -> reply text -> spoken audio.
"""

from __future__ import annotations

import base64
import io
import re
import unicodedata
import wave
from typing import Any

import httpx

from .model_client import ModelConfigurationError, _configured, get_model_settings

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_STT_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
DEFAULT_WHISPER_MODEL = "whisper-large-v3"
DEFAULT_TTS_MODEL = "canopylabs/orpheus-v1-english"
TTS_CHUNK_CHARS = 190  # Groq text-to-speech accepts at most 200 characters per request.
TTS_MAX_CHARS = 760
MAX_AUDIO_BYTES = 12 * 1024 * 1024

_TRANSCRIBE_PROMPT = (
    "Transcribe the speech in this audio word for word, in the language that is spoken. "
    "Reply with only the transcript and nothing else. If there is no speech, reply with exactly: [no speech]"
)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class VoiceError(RuntimeError):
    """A voice step failed; the message is safe to show to the user."""


def _groq_key() -> str:
    key = _configured("GROQ_API_KEY")
    if not key or key.casefold().startswith(("your-", "your_")):
        raise VoiceError("Add GROQ_API_KEY to your .env file or .streamlit/secrets.toml to enable Whisper and spoken replies.")
    return key


def groq_configured() -> bool:
    try:
        _groq_key()
    except VoiceError:
        return False
    return True


# ---------------------------------------------------------------- speech to text

def _clean_transcript(text: str) -> str:
    text = _THINK_RE.sub("", text or "").strip().strip('"').strip()
    return "" if text.casefold() in {"[no speech]", "no speech"} else text


def _nvidia_transcribe(wav: bytes) -> str:
    """Ask the NVIDIA omni model to transcribe the audio. Tries the two audio content shapes it may accept."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise VoiceError("The OpenAI SDK is missing. Install the project requirements.") from exc
    try:
        settings = get_model_settings()
    except ModelConfigurationError as exc:
        raise VoiceError(str(exc)) from exc
    client = OpenAI(api_key=settings.api_key, base_url=settings.base_url, max_retries=0, timeout=90)
    model = _configured("VOICE_STT_MODEL", DEFAULT_STT_MODEL)
    encoded = base64.b64encode(wav).decode("ascii")
    audio_parts = (
        {"type": "audio_url", "audio_url": {"url": f"data:audio/wav;base64,{encoded}"}},
        {"type": "input_audio", "input_audio": {"data": encoded, "format": "wav"}},
    )
    last_error: Exception | None = None
    for part in audio_parts:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": [{"type": "text", "text": _TRANSCRIBE_PROMPT}, part]}],
                temperature=0.0,
                max_tokens=1024,
                stream=False,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            content = response.choices[0].message.content if response.choices else None
            if isinstance(content, str):
                return _clean_transcript(content)
        except Exception as exc:  # try the next audio shape, then Whisper
            last_error = exc
    raise VoiceError(f"The NVIDIA speech model could not transcribe the audio: {last_error}")


def _whisper_transcribe(wav: bytes) -> str:
    key = _groq_key()
    model = _configured("GROQ_STT_MODEL", DEFAULT_WHISPER_MODEL)
    try:
        response = httpx.post(
            f"{GROQ_BASE_URL}/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": ("voice.wav", wav, "audio/wav")},
            data={"model": model, "temperature": "0", "response_format": "json"},
            timeout=60,
        )
        response.raise_for_status()
        return _clean_transcript(str(response.json().get("text", "")))
    except httpx.HTTPError as exc:
        raise VoiceError("Whisper could not transcribe the audio. Please try again.") from exc


def transcribe_audio(wav: bytes) -> str:
    """NVIDIA Nemotron omni first; Groq Whisper (whisper-large-v3) if that fails. Returns '' when no speech was heard."""
    if not wav:
        raise VoiceError("No audio was recorded.")
    if len(wav) > MAX_AUDIO_BYTES:
        raise VoiceError("That recording is too long. Please record a shorter message.")
    try:
        return _nvidia_transcribe(wav)
    except VoiceError as nvidia_error:
        if not groq_configured():
            raise nvidia_error
    return _whisper_transcribe(wav)


# ---------------------------------------------------------------- text to speech

def speakable_text(text: str) -> str:
    """Strip markdown, emoji and symbols so the voice does not read them out."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s*(-{3,}|\*{3,})\s*$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"[*_`#>~|]+", "", text)
    text = "".join(" " if unicodedata.category(c) in {"So", "Sk", "Cs", "Co", "Cn"} else c for c in text)
    return re.sub(r"\s+", " ", text).strip()


def split_for_speech(text: str, limit: int = TTS_CHUNK_CHARS, max_chars: int = TTS_MAX_CHARS) -> list[str]:
    """Break text into sentence-sized chunks that fit the text-to-speech limit."""
    text = text[:max_chars].strip()
    chunks: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            if current:
                chunks.append(current)
                current = ""
            chunks.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if not sentence:
            continue
        if current and len(current) + 1 + len(sentence) > limit:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk]


def merge_wav(parts: list[bytes]) -> bytes:
    """Join several WAV files with the same format into one."""
    if len(parts) == 1:
        return parts[0]
    out = io.BytesIO()
    writer: wave.Wave_write | None = None
    for part in parts:
        with wave.open(io.BytesIO(part), "rb") as reader:
            if writer is None:
                writer = wave.open(out, "wb")
                writer.setparams(reader.getparams())
            writer.writeframes(reader.readframes(reader.getnframes()))
    if writer is not None:
        writer.close()
    return out.getvalue()


def voice_for(preferences: dict[str, Any] | None) -> str:
    """Pick a Groq voice: a male voice for a boyfriend, a female voice otherwise (override with GROQ_TTS_VOICE)."""
    configured = _configured("GROQ_TTS_VOICE")
    if configured:
        return configured
    preferences = preferences or {}
    if preferences.get("mode") == "Romantic" and preferences.get("partner") == "Boyfriend":
        return "troy"
    return "hannah"


def synthesize_speech(text: str, voice: str = "hannah") -> bytes:
    """Turn reply text into WAV audio with Groq text-to-speech. Raises VoiceError if it cannot."""
    chunks = split_for_speech(speakable_text(text))
    if not chunks:
        raise VoiceError("There was nothing to read aloud.")
    key = _groq_key()
    model = _configured("GROQ_TTS_MODEL", DEFAULT_TTS_MODEL)
    parts: list[bytes] = []
    try:
        for chunk in chunks:
            response = httpx.post(
                f"{GROQ_BASE_URL}/audio/speech",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "input": chunk, "voice": voice, "response_format": "wav"},
                timeout=60,
            )
            if response.status_code >= 400:
                detail = ""
                try:
                    detail = str(response.json().get("error", {}).get("message", ""))
                except Exception:
                    pass
                raise VoiceError(f"Spoken replies are unavailable right now ({detail or response.status_code}).")
            parts.append(response.content)
        return merge_wav(parts)
    except httpx.HTTPError as exc:
        raise VoiceError("Spoken replies are unavailable right now. Please try again.") from exc
    except wave.Error as exc:
        raise VoiceError("The voice service returned audio that could not be played.") from exc
