"""Tests for CineForge AI: API client, prompt engine, helpers and the end-to-end UI flow."""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import api_client  # noqa: E402
import config  # noqa: E402
import prompt_engine  # noqa: E402
import video_utils  # noqa: E402
import youtube_tools  # noqa: E402

FAKE_KEY = "nvapi-TESTKEY1234567890"
FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 64
FAKE_B64 = base64.b64encode(FAKE_MP4).decode()


def fake_response(status: int = 200, json_body=None, text: str = "") -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.text = text or str(json_body)
    response.headers = {"nvcf-reqid": "req-1"}
    if isinstance(json_body, Exception):
        response.json.side_effect = json_body
    else:
        response.json.return_value = json_body
    return response


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    monkeypatch.setenv("NVIDIA_API_KEY", FAKE_KEY)
    monkeypatch.setenv("VIDEO_PROVIDER", "nvidia")


# ------------------------- Hugging Face (free) provider ------------------------- #
def test_huggingface_is_default_provider_and_needs_no_key(monkeypatch):
    monkeypatch.delenv("VIDEO_PROVIDER")
    monkeypatch.delenv("NVIDIA_API_KEY")
    assert config.get_provider() == config.PROVIDER_HUGGINGFACE
    assert not config.api_key_required()


def test_huggingface_plan_snaps_sizes_and_clamps_duration(monkeypatch):
    monkeypatch.delenv("VIDEO_PROVIDER")
    plan = config.plan_video("9:16", "Standard", 15, "Balanced", seed=7)
    assert (plan.params["width"], plan.params["height"]) == (384, 704)
    assert plan.params["duration"] == config.HF_MAX_SECONDS and plan.notes
    assert plan.params["seed"] == 7 and plan.params["improve_texture"]
    assert not config.plan_video("16:9", "Draft", 5, "Balanced").params["improve_texture"]


def test_huggingface_generate_video(monkeypatch, tmp_path):
    monkeypatch.delenv("VIDEO_PROVIDER")
    video = tmp_path / "out.mp4"
    video.write_bytes(FAKE_MP4)
    job = MagicMock()
    job.result.return_value = ({"video": str(video), "subtitles": None}, 123)
    client = MagicMock()
    client.submit.return_value = job
    monkeypatch.setitem(sys.modules, "gradio_client", MagicMock(Client=MagicMock(return_value=client)))

    result = api_client.generate_video(
        "A car driving", "blurry", None, {"width": 704, "height": 384, "duration": 3.0, "seed": 5}
    )

    assert result.video_bytes == FAKE_MP4 and result.metadata["seed"] == 123
    sent = client.submit.call_args.kwargs
    assert sent["mode"] == "text-to-video" and sent["api_name"] == config.HF_API_NAME
    assert (sent["width_ui"], sent["height_ui"], sent["duration_ui"]) == (704, 384, 3.0)
    assert sent["seed_ui"] == 5 and sent["randomize_seed"] is False


def test_huggingface_quota_error_is_mapped_and_redacted(monkeypatch):
    monkeypatch.delenv("VIDEO_PROVIDER")
    token = "hf_" + "a" * 20
    monkeypatch.setenv("HF_TOKEN", token)
    client = MagicMock()
    client.submit.side_effect = RuntimeError(f"ZeroGPU quota exceeded for {token}")
    monkeypatch.setitem(sys.modules, "gradio_client", MagicMock(Client=MagicMock(return_value=client)))

    with pytest.raises(api_client.RateLimitError) as caught:
        api_client.generate_video("A car driving", "", None)
    assert token not in caught.value.details


# ------------------------------- api_client -------------------------------- #
def test_generate_video_success_sends_only_documented_fields(monkeypatch):
    post = MagicMock(return_value=fake_response(200, {"b64_video": "data:video/mp4;base64," + FAKE_B64}))
    monkeypatch.setattr(api_client.requests, "post", post)
    stages: list[str] = []

    result = api_client.generate_video(
        "A car driving", "blurry", FAKE_KEY, {"seed": 5, "num_frames": 49, "bogus": 1}, on_stage=stages.append
    )

    assert result.video_bytes == FAKE_MP4
    assert stages == [
        api_client.STAGE_PREPARING,
        api_client.STAGE_CONNECTING,
        api_client.STAGE_GENERATING,
        api_client.STAGE_DECODING,
    ]
    sent = post.call_args.kwargs
    assert sent["json"] == {
        "model_mode": "text2video", "prompt": "A car driving", "negative_prompt": "blurry",
        "seed": 5, "num_frames": 49,
    }
    assert sent["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"
    assert post.call_args.args[0] == config.DEFAULT_API_URL


@pytest.mark.parametrize(
    ("status", "error_class"),
    [
        (400, api_client.BadRequestError),
        (401, api_client.AuthenticationError),
        (403, api_client.AccessDeniedError),
        (404, api_client.EndpointNotFoundError),
        (422, api_client.InvalidRequestFieldError),
        (429, api_client.RateLimitError),
        (503, api_client.ServerError),
    ],
)
def test_http_errors_are_mapped_and_redacted(monkeypatch, status, error_class):
    body = fake_response(status, {}, text=f"denied for {FAKE_KEY}")
    monkeypatch.setattr(api_client.requests, "post", MagicMock(return_value=body))
    with pytest.raises(error_class) as caught:
        api_client.generate_video("A car driving", "", FAKE_KEY)
    assert FAKE_KEY not in str(caught.value.to_safe_dict())
    assert caught.value.status_code == status


def test_missing_key_and_network_failures(monkeypatch):
    with pytest.raises(api_client.MissingApiKeyError):
        api_client.generate_video("A car driving", "", None)

    monkeypatch.setattr(api_client.requests, "post", MagicMock(side_effect=requests.Timeout()))
    with pytest.raises(api_client.RequestTimeoutError):
        api_client.generate_video("A car driving", "", FAKE_KEY)

    monkeypatch.setattr(
        api_client.requests, "post", MagicMock(side_effect=requests.ConnectionError(f"boom {FAKE_KEY}"))
    )
    with pytest.raises(api_client.NetworkError) as caught:
        api_client.generate_video("A car driving", "", FAKE_KEY)
    assert FAKE_KEY not in caught.value.details


@pytest.mark.parametrize(
    ("body", "error_class"),
    [
        ({}, api_client.ResponseFormatError),
        ({"b64_video": "!!!not base64!!!"}, api_client.InvalidVideoDataError),
        ({"b64_video": base64.b64encode(b"not an mp4 at all").decode()}, api_client.UnsupportedVideoFormatError),
        (ValueError("bad json"), api_client.ResponseFormatError),
    ],
)
def test_bad_success_bodies(monkeypatch, body, error_class):
    monkeypatch.setattr(api_client.requests, "post", MagicMock(return_value=fake_response(200, body)))
    with pytest.raises(error_class):
        api_client.generate_video("A car driving", "", FAKE_KEY)


def test_config_drops_unconfirmed_parameters():
    payload = config.build_payload("prompt", "", {"seed": 1, "fps": 24, "motion": 3})
    assert payload == {"model_mode": "text2video", "prompt": "prompt", "seed": 1, "fps": 24}


def test_url_override_is_used(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_URL", "https://example.test/v1/infer")
    post = MagicMock(return_value=fake_response(200, {"b64_video": FAKE_B64}))
    monkeypatch.setattr(api_client.requests, "post", post)
    api_client.generate_video("A car driving", "", FAKE_KEY)
    assert post.call_args.args[0] == "https://example.test/v1/infer"


def test_connection_check_detects_missing_route(monkeypatch):
    monkeypatch.setattr(api_client.requests, "post", MagicMock(return_value=fake_response(404)))
    status = api_client.check_connection(FAKE_KEY)
    assert not status.ok and "NVIDIA_API_URL" in status.message
    monkeypatch.setattr(api_client.requests, "post", MagicMock(return_value=fake_response(401)))
    assert api_client.check_connection(FAKE_KEY).ok


def test_plan_video_maps_options_and_clamps():
    plan = config.plan_video("9:16", "Standard", 8, "Strict", seed=7)
    assert plan.params == {
        "resolution": "480_9_16", "num_frames": 192, "fps": 24,
        "num_inference_steps": 35, "guidance_scale": 7.0, "seed": 7,
    }
    high = config.plan_video("21:9", "High quality", 15, "Balanced")
    assert high.params["resolution"] == "720_16_9" and high.params["num_frames"] == 197
    assert "seed" not in high.params and len(high.notes) == 2
    assert config.plan_video("1:1", "Draft", 1, "Flexible").params["num_frames"] == config.MIN_FRAMES


# ------------------------------ prompt engine ------------------------------ #
def test_prompt_validation_and_sanitizing():
    assert prompt_engine.validate_prompt("hi")
    assert not prompt_engine.validate_prompt("A sports car driving in a city")
    assert prompt_engine.sanitize_prompt("a\x00  b\n\nc") == "a b c"


def test_enhance_prompt_reflects_settings():
    settings = prompt_engine.GenerationSettings(
        platform="YouTube Shorts: 9:16", camera="Orbit shot", lighting="Neon lighting", duration_seconds=10
    )
    text = prompt_engine.enhance_prompt("A sports car driving in a city", settings)
    assert text.startswith("A sports car driving in a city.")
    for expected in ("9:16", "orbit shot", "neon lighting", "10-second"):
        assert expected in text.lower()
    assert len(text) <= config.MAX_FINAL_PROMPT_CHARS


@pytest.mark.parametrize(("story", "count"), [("A robot explores a garden.", 4), ("One. Two. Three. Four. Five.", 3)])
def test_scene_splitting_returns_requested_count(story, count):
    scenes = prompt_engine.build_scene_texts(story, count)
    assert len(scenes) == count and all(scenes)


def test_youtube_package_is_complete():
    package = youtube_tools.build_youtube_package(
        "A sports car driving through a city at night", "YouTube Short", "Cinematic realism", "YouTube Shorts: 9:16"
    )
    assert len(package.alternative_titles) == 5
    assert "#Shorts" in package.hashtags
    assert package.filename.endswith(".mp4") and " " not in package.filename
    assert all(len(title) <= 100 for title in [package.title, *package.alternative_titles])


# ------------------------------- video utils ------------------------------- #
def test_storage_is_session_scoped_and_safe(tmp_path):
    session = "a" * 16
    path = video_utils.save_video_bytes(FAKE_MP4, session)
    assert path.parent.name == session and video_utils.read_video_bytes(path) == FAKE_MP4
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"x")
    assert not video_utils.delete_video_file(outside) and outside.exists()
    assert video_utils.clear_generated_files(session) == 1
    with pytest.raises(video_utils.VideoProcessingError):
        video_utils.clear_generated_files("../evil")


def test_audio_validation():
    assert video_utils.validate_audio_upload("song.mp3", b"ID3" + b"\x00" * 20) is None
    assert video_utils.validate_audio_upload("song.exe", b"x")
    assert video_utils.validate_audio_upload("song.wav", b"not wav data....")


def test_merge_command_builds_crossfade_chain():
    infos = [video_utils.ClipInfo(5.0, 1280, 720)] * 3
    clips = [Path(f"c{i}.mp4") for i in range(3)]
    command = video_utils.build_merge_command("ffmpeg", clips, infos, Path("out.mp4"), True)
    graph = command[command.index("-filter_complex") + 1]
    assert "xfade=transition=fade:duration=0.5:offset=4.500[x1]" in graph
    assert "offset=9.000[outv]" in graph
    plain = video_utils.build_merge_command("ffmpeg", clips, infos, Path("out.mp4"), False, Path("a.mp3"))
    assert "concat=n=3" in plain[plain.index("-filter_complex") + 1] and "3:a:0" in plain


# --------------------------- end-to-end UI flow ---------------------------- #
def _click(at, label_part: str):
    button = next(b for b in at.button if label_part in b.label)
    button.click()
    return at.run(timeout=30)


def _new_app():
    """App with the optional AI Director and voice-over off, so only the video API is called."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=30)
    at.session_state["w_ai_director"] = False
    at.session_state["w_voiceover"] = False
    return at


def test_text_to_video_flow_end_to_end(monkeypatch):
    post = MagicMock(return_value=fake_response(200, {"b64_video": FAKE_B64}))
    monkeypatch.setattr(api_client.requests, "post", post)

    at = _new_app().run()
    assert not at.exception

    at.text_area(key="prompt_text").set_value("A sports car driving through a neon city").run()
    at = _click(at, "Enhance prompt")
    assert "sports car" in at.text_area(key="enhanced_prompt").value

    at = _click(at, "Generate video")
    assert not at.exception, at.exception
    assert post.call_count == 1
    sent = post.call_args.kwargs["json"]
    assert {"model_mode", "prompt", "negative_prompt", "resolution", "num_frames", "fps"} <= set(sent)
    assert sent["resolution"] == "720_16_9" and sent["num_frames"] == 192
    assert sent["prompt"] == at.session_state["enhanced_prompt"]

    history = at.session_state["history"]
    assert history[0]["status"] == "success"
    assert Path(history[0]["video_path"]).read_bytes() == FAKE_MP4
    assert FAKE_KEY not in repr(history) + repr(at.session_state["last_error"])
    assert not at.session_state["busy"]


def test_short_prompt_is_rejected_without_api_call(monkeypatch):
    post = MagicMock()
    monkeypatch.setattr(api_client.requests, "post", post)
    at = _new_app().run()
    at.text_area(key="prompt_text").set_value("hi").run()
    at = _click(at, "Generate video")
    post.assert_not_called()
    assert any("at least" in w.value for w in at.warning)


def test_api_failure_is_shown_without_leaking_key(monkeypatch):
    body = fake_response(403, {}, text=f"forbidden {FAKE_KEY}")
    monkeypatch.setattr(api_client.requests, "post", MagicMock(return_value=body))
    at = _new_app().run()
    at.text_area(key="prompt_text").set_value("A sports car driving through a neon city").run()
    at = _click(at, "Generate video")
    assert any("Access denied" in e.value for e in at.error)
    assert FAKE_KEY not in repr(at.session_state["last_error"])


def test_storyboard_regenerate_and_delete(monkeypatch):
    post = MagicMock(return_value=fake_response(200, {"b64_video": FAKE_B64}))
    monkeypatch.setattr(api_client.requests, "post", post)
    monkeypatch.setattr(config, "REQUEST_COOLDOWN_SECONDS", 0.0)
    at = _new_app().run()

    at.radio(key="t2v_mode").set_value("Storyboard (experimental)").run()
    at.text_area(key="story_text").set_value("A robot wakes in a garden. It finds a flower.").run()
    at.slider(key="scene_count").set_value(2).run()
    at = _click(at, "Build scene cards")
    at = _click(at, "Generate 2 scenes")
    assert not at.exception, at.exception
    assert post.call_count == 2
    assert len(at.session_state["storyboard_clip_ids"]) == 2
    prompts = [call.kwargs["json"]["prompt"] for call in post.call_args_list]
    assert all(p.startswith("Consistent visual style") for p in prompts)

    at = _click(at, "Regenerate")
    assert post.call_count == 3
    assert len([r for r in at.session_state["history"] if r["status"] == "success"]) == 3

    at = _click(at, "Delete")
    at = _click(at, "Yes, delete")
    assert len(at.session_state["history"]) == 2


# ------------------------- AI Director and audio helpers ------------------------- #
def _chat_reply(content: str, status: int = 200):
    return fake_response(status, {"choices": [{"message": {"content": content}}]}, text=content)


def test_director_parses_json_trims_narration_and_sends_model(monkeypatch):
    import llm_client

    reply = (
        '<think>planning</think>```json\n{"video_prompt": "' + "A detailed cinematic shot of a car. " * 3
        + '", "narration": "' + " ".join(["word"] * 40) + '"}\n```'
    )
    post = MagicMock(return_value=_chat_reply(reply))
    monkeypatch.setattr(llm_client.requests, "post", post)

    result = llm_client.direct_video("A car", "cinematic", 8, FAKE_KEY, "Nemotron 3.5 Lightning 30B")

    assert result.model == "Nemotron 3.5 Lightning 30B"
    assert len(result.narration.split()) <= llm_client.narration_word_limit(8)
    assert post.call_args.kwargs["json"]["model"] == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert post.call_args.kwargs["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"


def test_director_falls_back_to_next_model_and_requires_key(monkeypatch):
    import llm_client

    good = '{"video_prompt": "' + "A detailed cinematic shot of a car. " * 3 + '", "narration": "Hello."}'
    post = MagicMock(side_effect=[_chat_reply("nope", 500), _chat_reply(good)])
    monkeypatch.setattr(llm_client.requests, "post", post)
    result = llm_client.direct_video("A car", "cinematic", 8, FAKE_KEY)
    assert result.model == list(config.LLM_MODELS)[1] and post.call_count == 2

    with pytest.raises(llm_client.DirectorError):
        llm_client.direct_video("A car", "cinematic", 8, None)
    monkeypatch.setattr(llm_client.requests, "post", MagicMock(return_value=_chat_reply("x", 401)))
    with pytest.raises(llm_client.DirectorError) as caught:
        llm_client.direct_video("A car", "cinematic", 8, FAKE_KEY)
    assert caught.value.status_code == 401


def test_export_size_is_full_hd_and_even():
    import audio_tools

    assert audio_tools._target_size(960, 544) == (1920, 1080)
    assert audio_tools._target_size(544, 960) == (1080, 1920)
    assert audio_tools._target_size(704, 704) == (1080, 1080)


def test_huggingface_progress_is_reported(monkeypatch, tmp_path):
    monkeypatch.delenv("VIDEO_PROVIDER")
    video = tmp_path / "out.mp4"
    video.write_bytes(FAKE_MP4)
    job = MagicMock()
    job.done.side_effect = [False, False, True]
    job.result.return_value = ({"video": str(video)}, 1)
    client = MagicMock()
    client.submit.return_value = job
    monkeypatch.setitem(sys.modules, "gradio_client", MagicMock(Client=MagicMock(return_value=client)))
    monkeypatch.setattr(api_client.time, "sleep", lambda _s: None)
    updates: list[tuple[float, str]] = []

    api_client.generate_video("A car driving", "", None, {}, on_progress=lambda f, m: updates.append((f, m)))

    fractions = [f for f, _ in updates]
    assert fractions == sorted(fractions) and fractions[-1] == 1.0 and 0 < fractions[-2] < 1


def test_self_hosted_endpoint_needs_no_key(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("NVIDIA_API_URL", "http://localhost:8000/v1/infer")
    post = MagicMock(return_value=fake_response(200, {"b64_video": FAKE_B64}))
    monkeypatch.setattr(api_client.requests, "post", post)
    assert not config.api_key_required()
    assert api_client.generate_video("A car driving", "", None).video_bytes == FAKE_MP4
    assert "Authorization" not in post.call_args.kwargs["headers"]
    monkeypatch.setenv("NVIDIA_API_URL", config.DEFAULT_API_URL)
    with pytest.raises(api_client.MissingApiKeyError):
        api_client.generate_video("A car driving", "", None)
