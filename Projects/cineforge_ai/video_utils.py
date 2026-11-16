"""Filesystem and (optional) FFmpeg helpers for generated videos."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

import config

FFMPEG_INSTALL_HINT = (
    "FFmpeg was not found. Install it to merge clips: Windows `winget install Gyan.FFmpeg`, "
    "macOS `brew install ffmpeg`, Debian/Ubuntu `sudo apt install ffmpeg`. "
    "Then restart the app. Individual clip downloads keep working without FFmpeg."
)
_FFMPEG_TIMEOUT_SECONDS = 600
_OUTPUT_FPS = 24


class VideoProcessingError(Exception):
    """Raised when merging or probing video files fails."""


# --------------------------------------------------------------------------- #
# Filenames and storage                                                       #
# --------------------------------------------------------------------------- #
def safe_filename(name: str, extension: str = ".mp4", max_length: int = 60) -> str:
    """Return a filesystem-safe filename derived from arbitrary text."""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()[:max_length].strip("_")
    return f"{slug or 'cineforge_video'}{extension}"


def _session_dir(session_id: str | None) -> Path:
    if session_id is None:
        return config.GENERATED_DIR
    if not re.fullmatch(r"[A-Za-z0-9]{8,64}", session_id):
        raise VideoProcessingError("Invalid session identifier.")
    return config.GENERATED_DIR / session_id


def ensure_generated_dir(session_id: str | None = None) -> Path:
    """Create (if needed) and return the generated-videos directory.

    Passing a ``session_id`` isolates files per browser session so that one
    user can never delete another user's videos on a shared server.
    """
    directory = _session_dir(session_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def new_output_path(extension: str = ".mp4", session_id: str | None = None) -> Path:
    """Return a unique UUID-named path inside the generated-videos directory."""
    return ensure_generated_dir(session_id) / f"{uuid.uuid4().hex}{extension}"


def is_managed_path(path: str | Path) -> bool:
    """True only for files that live inside the generated-videos directory."""
    try:
        Path(path).resolve().relative_to(config.GENERATED_DIR.resolve())
    except (ValueError, OSError):
        return False
    return True


def save_video_bytes(video_bytes: bytes, session_id: str | None = None) -> Path:
    """Persist MP4 bytes under a unique UUID filename and return the path."""
    if not video_bytes:
        raise VideoProcessingError("Refusing to save an empty video.")
    if len(video_bytes) > config.MAX_VIDEO_BYTES:
        raise VideoProcessingError("The generated video exceeds the maximum allowed size.")
    path = new_output_path(session_id=session_id)
    path.write_bytes(video_bytes)
    return path


def read_video_bytes(path: str | Path | None) -> bytes | None:
    """Read a managed video file, or return ``None`` if it is gone."""
    if not path or not is_managed_path(path):
        return None
    try:
        return Path(path).read_bytes()
    except OSError:
        return None


def delete_video_file(path: str | Path | None) -> bool:
    """Delete a managed file; paths outside the generated directory are ignored."""
    if not path or not is_managed_path(path):
        return False
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        return False
    return True


def clear_generated_files(session_id: str | None = None) -> int:
    """Delete the generated files of one session and return how many were removed."""
    directory = _session_dir(session_id)
    if not directory.exists():
        return 0
    removed = 0
    for item in directory.iterdir():
        if item.is_file() and delete_video_file(item):
            removed += 1
    return removed


# --------------------------------------------------------------------------- #
# Audio validation                                                            #
# --------------------------------------------------------------------------- #
def validate_audio_upload(file_name: str, data: bytes) -> str | None:
    """Return an error message for an invalid uploaded audio file, else ``None``."""
    extension = Path(file_name).suffix.lower()
    if extension not in config.ALLOWED_AUDIO_EXTENSIONS:
        return "Unsupported audio type. Use: " + ", ".join(config.ALLOWED_AUDIO_EXTENSIONS) + "."
    if not data:
        return "The audio file is empty."
    if len(data) > config.MAX_AUDIO_BYTES:
        return f"The audio file is larger than {config.MAX_AUDIO_BYTES // (1024 * 1024)} MB."
    head = data[:12]
    looks_valid = {
        ".mp3": head.startswith(b"ID3") or (head[:1] == b"\xff" and (head[1] & 0xE0) == 0xE0),
        ".wav": head[:4] == b"RIFF" and head[8:12] == b"WAVE",
        ".m4a": head[4:8] == b"ftyp",
        ".aac": head[:1] == b"\xff" or head.startswith(b"ADIF"),
    }[extension]
    if not looks_valid:
        return "The file content does not match its audio extension."
    return None


# --------------------------------------------------------------------------- #
# FFmpeg                                                                      #
# --------------------------------------------------------------------------- #
def ffmpeg_tools() -> tuple[str, str] | None:
    """Return ``(ffmpeg, ffprobe)`` executable paths, or ``None`` if unavailable."""
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    return (ffmpeg, ffprobe) if ffmpeg and ffprobe else None


def ffmpeg_available() -> bool:
    """True when both ffmpeg and ffprobe are installed."""
    return ffmpeg_tools() is not None


@dataclass(frozen=True)
class ClipInfo:
    """Basic stream facts needed to merge clips."""

    duration: float
    width: int
    height: int


def probe_clip(ffprobe: str, path: Path) -> ClipInfo:
    """Read duration and resolution of a clip with ffprobe."""
    command = [
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "json", str(path),
    ]  # fmt: skip
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=60, check=True
        )
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        return ClipInfo(
            duration=float(data["format"]["duration"]),
            width=int(stream["width"]),
            height=int(stream["height"]),
        )
    except (subprocess.SubprocessError, OSError, KeyError, IndexError, ValueError) as error:
        raise VideoProcessingError(f"Could not read clip information for {path.name}.") from error


def build_merge_command(
    ffmpeg: str,
    clips: list[Path],
    infos: list[ClipInfo],
    output: Path,
    crossfade: bool,
    audio_path: Path | None = None,
    fade_seconds: float = config.CROSSFADE_SECONDS,
) -> list[str]:
    """Build the ffmpeg command that merges clips (optionally with crossfades/audio)."""
    if len(clips) < 2 or len(clips) != len(infos):
        raise VideoProcessingError("At least two clips are required to merge.")
    if crossfade and min(info.duration for info in infos) <= fade_seconds * 2:
        raise VideoProcessingError("Clips are too short for the selected crossfade.")

    width = infos[0].width - infos[0].width % 2
    height = infos[0].height - infos[0].height % 2
    filters = [
        f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={_OUTPUT_FPS},"
        f"format=yuv420p[v{index}]"
        for index in range(len(clips))
    ]
    if crossfade:
        current, elapsed = "v0", infos[0].duration
        for index in range(1, len(clips)):
            label = "outv" if index == len(clips) - 1 else f"x{index}"
            offset = elapsed - fade_seconds
            filters.append(
                f"[{current}][v{index}]xfade=transition=fade:"
                f"duration={fade_seconds}:offset={offset:.3f}[{label}]"
            )
            current, elapsed = label, offset + infos[index].duration
    else:
        joined = "".join(f"[v{index}]" for index in range(len(clips)))
        filters.append(f"{joined}concat=n={len(clips)}:v=1:a=0[outv]")

    command = [ffmpeg, "-y", "-v", "error"]
    for clip in clips:
        command += ["-i", str(clip)]
    if audio_path is not None:
        command += ["-i", str(audio_path)]
    command += ["-filter_complex", ";".join(filters), "-map", "[outv]"]
    if audio_path is not None:
        command += ["-map", f"{len(clips)}:a:0", "-c:a", "aac", "-shortest"]
    else:
        command += ["-an"]
    command += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
    ]  # fmt: skip
    return command


def merge_clips(
    clip_paths: list[Path],
    crossfade: bool = False,
    audio_bytes: bytes | None = None,
    audio_extension: str = ".mp3",
    session_id: str | None = None,
) -> Path:
    """Merge clips into one MP4 stored in the generated directory."""
    tools = ffmpeg_tools()
    if tools is None:
        raise VideoProcessingError(FFMPEG_INSTALL_HINT)
    ffmpeg, ffprobe = tools
    if any(not is_managed_path(path) or not Path(path).exists() for path in clip_paths):
        raise VideoProcessingError("One or more clips are no longer available.")

    infos = [probe_clip(ffprobe, Path(path)) for path in clip_paths]
    output = new_output_path(session_id=session_id)
    audio_path: Path | None = None
    if audio_bytes:
        audio_path = new_output_path(audio_extension, session_id)
        audio_path.write_bytes(audio_bytes)
    try:
        command = build_merge_command(
            ffmpeg, [Path(p) for p in clip_paths], infos, output, crossfade, audio_path
        )
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        delete_video_file(output)
        tail = (error.stderr or "").strip().splitlines()[-3:]
        raise VideoProcessingError("FFmpeg failed to merge the clips. " + " ".join(tail)) from error
    except (subprocess.SubprocessError, OSError) as error:
        delete_video_file(output)
        raise VideoProcessingError("FFmpeg could not be run.") from error
    except VideoProcessingError:
        delete_video_file(output)
        raise
    finally:
        if audio_path is not None:
            delete_video_file(audio_path)
    return output
