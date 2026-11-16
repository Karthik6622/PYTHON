"""Quota-free fallback renderer: AI key-frames with camera moves, joined by crossfades.

Each shot is a still image from the free Pollinations image API (no key, no daily GPU
quota). FFmpeg animates every still with a slow zoom or pan and crossfades the shots
into one H.264 MP4, so the app still produces a video when the video model is busy.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

import api_client
import audio_tools
import config

ProgressCallback = Callable[[float, str], None]

IMAGE_URL = "https://image.pollinations.ai/prompt/"  # anonymous: 1 image per 45 s per IP
KEYED_IMAGE_URL = "https://gen.pollinations.ai/image/"  # with a free POLLINATIONS_API_KEY
IMAGE_LONG_SIDE = 1280
IMAGE_TIMEOUT_SECONDS = 90
IMAGE_ATTEMPTS = 5
MAX_PROMPT_CHARS = 800
SHOT_SECONDS = 3.0
MAX_SHOTS = 6
MAX_SHOTS_ANONYMOUS = 3  # keeps the 45 s free-tier waits to about two minutes
CROSSFADE_SECONDS = 0.5
FPS = 24
_FFMPEG_TIMEOUT_SECONDS = 300

# Each shot gets a different framing so the cuts feel like real coverage of one scene.
SHOT_FRAMINGS = (
    "wide establishing shot",
    "medium shot, subject in sharp focus",
    "close-up detail shot, shallow depth of field",
    "low angle dramatic shot",
    "high angle cinematic shot",
    "over-the-shoulder shot, soft background blur",
)
# (zoom, x, y) expressions for ffmpeg's zoompan; ``on`` is the frame index, ``N`` the frame count.
CAMERA_MOVES = (
    ("1+0.18*on/N", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),  # push in
    ("1.15", "(iw-iw/zoom)*on/N", "ih/2-(ih/zoom/2)"),  # pan right
    ("1.18-0.18*on/N", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),  # pull out
    ("1.15", "(iw-iw/zoom)*(1-on/N)", "ih/2-(ih/zoom/2)"),  # pan left
)
_IMAGE_SIGNATURES = (b"\xff\xd8\xff", b"\x89PNG", b"RIFF")


def shot_count(duration_seconds: float, keyed: bool = True) -> int:
    return max(1, min(MAX_SHOTS if keyed else MAX_SHOTS_ANONYMOUS, round(duration_seconds / SHOT_SECONDS)))


def shot_prompt(prompt: str, index: int) -> str:
    framing = SHOT_FRAMINGS[index % len(SHOT_FRAMINGS)]
    return f"{prompt.strip()[:MAX_PROMPT_CHARS]}, {framing}, cinematic lighting, highly detailed, film still"


def image_size(width: int, height: int) -> tuple[int, int]:
    """Scale the requested size so the long side is ``IMAGE_LONG_SIDE`` (both sides even)."""
    factor = IMAGE_LONG_SIDE / max(width, height, 1)
    return round(width * factor / 2) * 2, round(height * factor / 2) * 2


def _download_image(
    prompt: str, width: int, height: int, seed: int, key: str | None, wait: Callable[[str], None]
) -> bytes:
    query = f"width={width}&height={height}&model=flux&nologo=true&enhance=false&seed={seed}"
    base = KEYED_IMAGE_URL if key else IMAGE_URL
    url = f"{base}{quote(prompt, safe='')}?{query}"
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    last_problem = "no response"
    for attempt in range(IMAGE_ATTEMPTS):
        pause = 2.0 * (attempt + 1)
        try:
            response = requests.get(
                url, headers=headers, timeout=(config.CONNECT_TIMEOUT_SECONDS, IMAGE_TIMEOUT_SECONDS)
            )
        except requests.exceptions.SSLError:
            try:  # corporate TLS proxies: trust the operating system's certificate store
                import truststore

                truststore.inject_into_ssl()
            except ImportError:
                pass
            last_problem = "TLS error"
        except requests.RequestException as error:
            last_problem = type(error).__name__
        else:
            if response.status_code == 200 and response.content.startswith(_IMAGE_SIGNATURES):
                return response.content
            last_problem = f"HTTP {response.status_code}"
            if response.status_code == 402:  # free tier: one image per 45 s per IP
                found = re.search(r"[Rr]etry after (\d+)s", response.text)
                pause = min(float(found[1]) + 1 if found else 45.0, 60.0)
                wait(f"Free image limit: next picture in {pause:.0f}s")
        time.sleep(pause)
    raise api_client.NetworkError(
        "The free image service did not return a picture.",
        hint="Try again in a minute, or set a free POLLINATIONS_API_KEY (enter.pollinations.ai) to remove the limit.",
        details=last_problem,
    )


def _run_ffmpeg(command: list[str]) -> None:
    try:
        subprocess.run(command, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT_SECONDS, check=True)
    except subprocess.CalledProcessError as error:
        tail = " ".join((error.stderr or "").strip().splitlines()[-3:])
        raise api_client.CineForgeError("FFmpeg could not build the video.", details=tail) from error
    except (OSError, subprocess.TimeoutExpired) as error:
        raise api_client.CineForgeError("FFmpeg could not be run.", details=type(error).__name__) from error


def _animate_still(ffmpeg: str, image: Path, output: Path, index: int, seconds: float, size: tuple[int, int]) -> None:
    width, height = size
    frames = max(2, round(seconds * FPS))
    zoom, x, y = (part.replace("N", str(frames)) for part in CAMERA_MOVES[index % len(CAMERA_MOVES)])
    video_filter = (
        f"scale={width * 2}:{height * 2}:flags=lanczos,"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={FPS},"
        "eq=contrast=1.05:saturation=1.1,format=yuv420p"
    )
    _run_ffmpeg(
        [ffmpeg, "-y", "-v", "error", "-i", str(image), "-vf", video_filter, "-frames:v", str(frames),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", str(output)]
    )


def _join_with_crossfades(ffmpeg: str, clips: list[Path], clip_seconds: float, output: Path) -> None:
    if len(clips) == 1:
        _run_ffmpeg([ffmpeg, "-y", "-v", "error", "-i", str(clips[0]), "-c", "copy", "-movflags", "+faststart", str(output)])
        return
    command = [ffmpeg, "-y", "-v", "error"]
    for clip in clips:
        command += ["-i", str(clip)]
    chain, label = [], "0:v"
    for position in range(1, len(clips)):
        offset = position * (clip_seconds - CROSSFADE_SECONDS)
        chain.append(
            f"[{label}][{position}:v]xfade=transition=fade:duration={CROSSFADE_SECONDS}:offset={offset:.3f}[x{position}]"
        )
        label = f"x{position}"
    command += ["-filter_complex", ";".join(chain), "-map", f"[{label}]", "-c:v", "libx264", "-preset", "medium",
                "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
    _run_ffmpeg(command)


def generate_video(
    prompt: str,
    params: Mapping[str, Any] | None,
    on_progress: ProgressCallback | None = None,
) -> api_client.VideoResult:
    """Render the prompt as a short cinematic video of AI key-frames.

    Raises:
        CineForgeError: FFmpeg is missing, or the image service failed.
    """
    progress = on_progress or (lambda _fraction, _message: None)
    options = dict(params or {})
    ffmpeg = audio_tools.ffmpeg_executable()
    if not ffmpeg:
        raise api_client.CineForgeError(
            "FFmpeg is required for the free fallback renderer.", hint="Run: pip install imageio-ffmpeg"
        )
    duration = float(options.get("duration", 6))
    key = config.get_pollinations_key()
    shots = shot_count(duration, keyed=bool(key))
    clip_seconds = (duration + (shots - 1) * CROSSFADE_SECONDS) / shots
    size = image_size(int(options.get("width", 704)), int(options.get("height", 384)))
    base_seed = int(options.get("seed") or time.time_ns() % 100000)

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="cineforge_") as folder:
        work = Path(folder)
        clips: list[Path] = []
        for index in range(shots):
            progress(0.8 * index / shots, f"Painting shot {index + 1} of {shots}")
            image = work / f"shot{index}.img"
            image.write_bytes(
                _download_image(
                    shot_prompt(prompt, index), *size, base_seed + index, key,
                    lambda message, i=index: progress(0.8 * i / shots, message),
                )
            )
            progress(0.8 * (index + 0.7) / shots, f"Adding camera motion to shot {index + 1} of {shots}")
            clip = work / f"clip{index}.mp4"
            _animate_still(ffmpeg, image, clip, index, clip_seconds, size)
            clips.append(clip)
        progress(0.9, "Joining the shots with crossfades")
        output = work / "final.mp4"
        _join_with_crossfades(ffmpeg, clips, clip_seconds, output)
        video_bytes = output.read_bytes()
    api_client.validate_mp4(video_bytes)
    progress(1.0, "Video rendered")

    metadata = {
        "status_code": 200,
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "size_bytes": len(video_bytes),
        "request_id": "",
        "response_fields": ["shots"],
        "provider": "pictures",
        "shots": shots,
        "duration_seconds": round(duration, 1),
    }
    return api_client.VideoResult(video_bytes=video_bytes, metadata=metadata)
