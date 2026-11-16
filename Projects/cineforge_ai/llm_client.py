"""AI Director: asks an NVIDIA Nemotron model to write the video prompt and voice-over.

The model returns a production-grade text-to-video prompt plus a short narration
script. Models are tried in order (the chosen one first), and callers fall back
to the local prompt engine when no model can be reached.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import requests

import api_client
import config

_WORDS_PER_SECOND = 2.3  # natural narration pace
_MAX_VIDEO_PROMPT_CHARS = 1800

SYSTEM_PROMPT = """You are an award-winning film director and prompt engineer for an AI text-to-video model (LTX-Video).
Turn the user's idea into a video that looks professional enough to publish on YouTube.

Write "video_prompt" as ONE flowing paragraph of 5-8 sentences, present tense, in chronological order:
1. the main subject with concrete visual details (materials, colors, clothing, textures, scale),
2. the action and how it evolves over the clip,
3. the environment, time of day and atmosphere,
4. the camera: lens feel, framing and movement, as requested,
5. the lighting and color grade, and the overall mood and visual style.
Be specific and visual; avoid abstract words, brand names, on-screen text, subtitles, logos and real people's names.
Keep one coherent scene with physically plausible motion.

Write "narration" as a short voice-over spoken by a professional narrator: a strong hook, then one vivid idea,
ending cleanly. It must fit the word limit given by the user, use plain spoken English and no stage directions.

Reply with ONLY a JSON object: {"video_prompt": "...", "narration": "..."}"""


class DirectorError(api_client.CineForgeError):
    title = "AI Director unavailable"
    hint = "The video will use the built-in prompt builder instead."


@dataclass(frozen=True)
class DirectorResult:
    video_prompt: str
    narration: str
    model: str


def narration_word_limit(duration_seconds: float) -> int:
    """Maximum narration words that fit in the clip with a short lead-in and tail."""
    return max(6, int((duration_seconds - 1.0) * _WORDS_PER_SECOND))


def _extract_json(text: str) -> dict[str, str]:
    cleaned = re.sub(r"(?is)<think>.*?</think>", "", text or "").strip()
    cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned.strip(), flags=re.MULTILINE).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise DirectorError("The model reply did not contain JSON.")
    try:
        data = json.loads(cleaned[start : end + 1])
    except ValueError as error:
        raise DirectorError("The model reply was not valid JSON.") from error
    if not isinstance(data, dict):
        raise DirectorError("The model reply had an unexpected structure.")
    return data


def _trim_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text.strip()
    trimmed = " ".join(words[:limit]).rstrip(",;:")
    return trimmed if trimmed.endswith((".", "!", "?")) else trimmed + "."


def _ask_model(model: str, messages: list[dict[str, str]], api_key: str, timeout: int) -> str:
    try:
        response = requests.post(
            config.LLM_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "top_p": 0.95,
                "max_tokens": 2048,
                "stream": False,
            },
            timeout=(config.CONNECT_TIMEOUT_SECONDS, timeout),
        )
    except requests.Timeout as error:
        raise DirectorError(f"{model} timed out.") from error
    except requests.RequestException as error:
        raise DirectorError(
            f"Could not reach NVIDIA ({type(error).__name__}).",
            details=api_client.redact_secrets(str(error), api_key),
        ) from error
    if response.status_code == 401:
        raise DirectorError(
            "The NVIDIA API key was rejected.",
            hint="Create a new key on build.nvidia.com and update NVIDIA_API_KEY.",
            status_code=401,
        )
    if response.status_code != 200:
        raise DirectorError(
            f"{model} returned HTTP {response.status_code}.",
            status_code=response.status_code,
            details=api_client.redact_secrets(response.text[:500], api_key),
        )
    try:
        message = response.json()["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise DirectorError(f"{model} returned an unexpected response.") from error
    return str(message.get("content") or "")


def direct_video(
    user_prompt: str,
    brief: str,
    duration_seconds: float,
    api_key: str | None,
    model_label: str | None = None,
    want_narration: bool = True,
    timeout: int = config.LLM_TIMEOUT_SECONDS,
) -> DirectorResult:
    """Return an optimized video prompt (and narration) written by a Nemotron model.

    Args:
        user_prompt: the user's idea.
        brief: production settings (style, camera, lighting, platform ...) as text.
        duration_seconds: clip length, used to size the narration.
        model_label: key of ``config.LLM_MODELS``; remaining models are used as fallbacks.

    Raises:
        DirectorError: no key, or every model failed.
    """
    if not api_key:
        raise DirectorError(
            "No NVIDIA API key is configured for the AI Director.",
            hint="Add NVIDIA_API_KEY to the app secrets (free at build.nvidia.com).",
        )
    limit = narration_word_limit(duration_seconds)
    request_text = (
        f"Idea: {user_prompt}\n\nProduction brief: {brief}\n\n"
        f"Clip length: {duration_seconds:g} seconds. "
        + (f"Narration limit: {limit} words." if want_narration else 'Set "narration" to an empty string.')
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": request_text},
    ]
    order = [model_label] if model_label in config.LLM_MODELS else []
    order += [label for label in config.LLM_MODELS if label not in order]

    failures: list[str] = []
    for label in order:
        model = config.LLM_MODELS[label]
        try:
            data = _extract_json(_ask_model(model, messages, api_key, timeout))
            prompt = " ".join(str(data.get("video_prompt", "")).split())
            if len(prompt) < 40:
                raise DirectorError(f"{label} returned an empty video prompt.")
            narration = " ".join(str(data.get("narration", "")).split()) if want_narration else ""
            return DirectorResult(
                video_prompt=prompt[:_MAX_VIDEO_PROMPT_CHARS],
                narration=_trim_words(narration, limit) if narration else "",
                model=label,
            )
        except DirectorError as error:
            if error.status_code == 401:
                raise
            failures.append(f"{label}: {error.message}")
    raise DirectorError("No Nemotron model could write the prompt.", details="\n".join(failures))
