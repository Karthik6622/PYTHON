"""Voice-over synthesis and the YouTube-ready final export (FFmpeg)."""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import config

_FFMPEG_TIMEOUT_SECONDS = 600
_VOICE_LEAD_IN_SECONDS = 0.5
_MAX_TEMPO = 1.25


class AudioError(Exception):
    """Raised when speech synthesis or the final export fails."""


@dataclass(frozen=True)
class MediaInfo:
    width: int
    height: int
    duration: float


def ffmpeg_executable() -> str | None:
    """Return a usable ffmpeg path: a system install, else the bundled imageio-ffmpeg binary."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # package missing or binary unavailable
        return None


def probe_media(ffmpeg: str, path: Path) -> MediaInfo:
    """Read size and duration from ``ffmpeg -i`` output (works without ffprobe)."""
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    text = result.stderr
    duration = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    size = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", text)
    seconds = (
        int(duration[1]) * 3600 + int(duration[2]) * 60 + float(duration[3]) if duration else 0.0
    )
    return MediaInfo(int(size[1]) if size else 0, int(size[2]) if size else 0, seconds)


def synthesize_speech(text: str, voice_label: str, output: Path) -> Path:
    """Create an MP3 narration with a Microsoft neural voice (free, needs internet)."""
    voice = config.VOICES.get(voice_label, config.VOICES[config.DEFAULT_VOICE])
    cleaned = " ".join((text or "").split())
    if not cleaned:
        raise AudioError("The narration text is empty.")
    try:
        import edge_tts
    except ImportError as error:
        raise AudioError("The 'edge-tts' package is not installed (pip install -r requirements.txt).") from error

    async def _run() -> None:
        await edge_tts.Communicate(cleaned, voice, rate="-4%").save(str(output))

    def _attempt() -> None:
        asyncio.run(asyncio.wait_for(_run(), timeout=60))

    try:
        try:
            _attempt()
        except Exception as error:
            if "CERTIFICATE_VERIFY_FAILED" not in repr(error):
                raise
            # Corporate TLS proxies: retry using the operating system's certificate store.
            import ssl

            import edge_tts.communicate as edge_communicate
            import truststore

            edge_communicate._SSL_CTX = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            _attempt()
    except Exception as error:
        raise AudioError(f"Speech synthesis failed ({type(error).__name__}).") from error
    if not output.is_file() or output.stat().st_size == 0:
        raise AudioError("Speech synthesis produced no audio.")
    return output


def _target_size(width: int, height: int) -> tuple[int, int]:
    """Full HD for the video's orientation (1080p for square clips); both sides even."""
    if not width or not height:
        return 0, 0
    ratio = width / height
    for standard_ratio, size in ((16 / 9, (1920, 1080)), (9 / 16, (1080, 1920))):
        if abs(ratio / standard_ratio - 1) < 0.04:  # the model pads sides to multiples of 32
            return size
    long_side = config.EXPORT_LONG_SIDE if width != height else 1080
    factor = long_side / max(width, height)
    return round(width * factor / 2) * 2, round(height * factor / 2) * 2


def export_for_youtube(video: Path, audio: Path | None, output: Path) -> Path:
    """Upscale to Full HD, add the narration and encode H.264/AAC for YouTube.

    Raises:
        AudioError: FFmpeg is unavailable or failed.
    """
    ffmpeg = ffmpeg_executable()
    if not ffmpeg:
        raise AudioError("FFmpeg is not available (pip install imageio-ffmpeg).")
    info = probe_media(ffmpeg, video)
    width, height = _target_size(info.width, info.height)
    video_filter = "format=yuv420p"
    if width:
        video_filter = (
            f"scale={width}:{height}:flags=lanczos:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},unsharp=5:5:0.5:5:5:0.0,format=yuv420p"
        )
    command = [ffmpeg, "-y", "-v", "error", "-i", str(video)]
    if audio is not None:
        command += ["-i", str(audio)]
        speech = probe_media(ffmpeg, audio).duration
        room = max(info.duration - _VOICE_LEAD_IN_SECONDS - 0.3, 1.0)
        tempo = min(_MAX_TEMPO, speech / room) if info.duration and speech > room else 1.0
        delay_ms = int(_VOICE_LEAD_IN_SECONDS * 1000)
        chain = f"[1:a]atempo={tempo:.3f},adelay={delay_ms}|{delay_ms},loudnorm=I=-16:TP=-1.5:LRA=11,apad[a]"
        command += ["-filter_complex", chain, "-map", "0:v", "-map", "[a]", "-shortest",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    else:
        command += ["-an"]
    command += ["-vf", video_filter, "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                "-r", "24", "-movflags", "+faststart", str(output)]
    try:
        subprocess.run(
            command, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT_SECONDS, check=True
        )
    except subprocess.CalledProcessError as error:
        tail = (error.stderr or "").strip().splitlines()[-3:]
        raise AudioError("FFmpeg failed to export the video. " + " ".join(tail)) from error
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AudioError("FFmpeg could not be run.") from error
    return output
