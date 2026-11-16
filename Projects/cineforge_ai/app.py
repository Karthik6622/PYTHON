"""CineForge AI - Streamlit front end for NVIDIA Cosmos3-Nano text-to-video."""

from __future__ import annotations

import html
import textwrap
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

import api_client
import config
import prompt_engine
import video_utils
import youtube_tools
from prompt_engine import GenerationSettings

st.set_page_config(
    page_title=config.APP_NAME,
    page_icon=config.APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
# Session-state keys                                                          #
# --------------------------------------------------------------------------- #
K_SESSION_ID = "session_id"
K_HISTORY = "history"
K_BUSY = "busy"
K_PENDING = "pending_jobs"
K_LAST_REQUEST = "last_request_ts"
K_LAST_RESULT = "last_result_id"
K_LAST_ERROR = "last_error"
K_FORM_ERRORS = "form_errors"
K_PROMPT = "prompt_text"
K_ENHANCED = "enhanced_prompt"
K_ENHANCED_SIG = "enhanced_signature"
K_NEGATIVE = "negative_prompt"
K_PROJECT = "project_name"
K_CONNECTION = "connection_status"
K_CONFIRM_DELETE = "confirm_delete_id"
K_CONFIRM_CLEAR = "confirm_clear_files"
K_MODE = "t2v_mode"
K_STORY = "story_text"
K_SCENE_COUNT = "scene_count"
K_SCENES_BUILT = "scenes_built"
K_PREFIX = "storyboard_prefix"
K_STORY_IDS = "storyboard_clip_ids"
K_MERGED = "merged_video"
K_CROSSFADE = "merge_crossfade"
W_CONTENT = "w_content_type"
W_PLATFORM = "w_platform"
W_DURATION = "w_duration"
W_CUSTOM_DURATION = "w_custom_duration"
W_STYLE = "w_style"
W_CAMERA = "w_camera"
W_LIGHTING = "w_lighting"
W_QUALITY = "w_quality"
W_MOTION = "w_motion"
W_CREATIVITY = "w_creativity"
W_ADHERENCE = "w_adherence"
W_KEEP_ORIGINAL = "w_keep_original"
W_SHOW_ENHANCED = "w_show_enhanced"
W_SAFETY = "w_safety_confirmation"

MODE_SINGLE = "Single clip"
MODE_STORYBOARD = "Multi-Scene Storyboard (experimental)"
FEEDBACK_VIDEO_READY = "Video ready"


def scene_key(index: int) -> str:
    """Session-state key of the editable text for scene ``index``."""
    return f"scene_text_{index}"


PERSISTENT_KEYS = [
    K_PROMPT, K_ENHANCED, K_ENHANCED_SIG, K_NEGATIVE, K_PROJECT, K_MODE, K_STORY,
    K_SCENE_COUNT, K_PREFIX, K_CROSSFADE, W_CONTENT, W_PLATFORM, W_DURATION,
    W_CUSTOM_DURATION, W_STYLE, W_CAMERA, W_LIGHTING, W_QUALITY, W_MOTION,
    W_CREATIVITY, W_ADHERENCE, W_KEEP_ORIGINAL, W_SHOW_ENHANCED, W_SAFETY,
    *[scene_key(i) for i in range(config.MAX_SCENES)],
]  # fmt: skip


def init_state() -> None:
    """Create default session values and keep widget values alive across reruns.

    Streamlit discards widget state for widgets that were not rendered in a
    run (for example when switching modes), so every persistent value is
    re-assigned at the start of each run.
    """
    defaults: dict[str, Any] = {
        K_SESSION_ID: uuid.uuid4().hex,
        K_HISTORY: [],
        K_BUSY: False,
        K_PENDING: [],
        K_LAST_REQUEST: 0.0,
        K_LAST_RESULT: None,
        K_LAST_ERROR: None,
        K_FORM_ERRORS: [],
        K_PROMPT: "",
        K_ENHANCED: "",
        K_ENHANCED_SIG: None,
        K_NEGATIVE: config.DEFAULT_NEGATIVE_PROMPT,
        K_PROJECT: "Untitled project",
        K_CONNECTION: None,
        K_CONFIRM_DELETE: None,
        K_CONFIRM_CLEAR: False,
        K_MODE: MODE_SINGLE,
        K_STORY: "",
        K_SCENE_COUNT: config.DEFAULT_SCENES,
        K_SCENES_BUILT: 0,
        K_PREFIX: "",
        K_STORY_IDS: [],
        K_MERGED: None,
        K_CROSSFADE: True,
        W_CONTENT: "YouTube Video",
        W_PLATFORM: "YouTube Landscape: 16:9",
        W_DURATION: "8 seconds",
        W_CUSTOM_DURATION: 12,
        W_STYLE: "Cinematic realism",
        W_CAMERA: "Slow cinematic push-in",
        W_LIGHTING: "Dramatic cinematic lighting",
        W_QUALITY: "Standard",
        W_MOTION: "Balanced",
        W_CREATIVITY: "Balanced",
        W_ADHERENCE: "Balanced",
        W_KEEP_ORIGINAL: True,
        W_SHOW_ENHANCED: True,
        W_SAFETY: True,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    for key in PERSISTENT_KEYS:
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


# --------------------------------------------------------------------------- #
# Styling                                                                     #
# --------------------------------------------------------------------------- #
APP_CSS = """
<style>
.block-container {padding-top: 1.2rem; max-width: 1400px;}
.cf-brand {font-size: 1.7rem; font-weight: 800; letter-spacing: .3px; line-height: 1.1;}
.cf-brand span {background: linear-gradient(90deg,#8B5CF6,#22D3EE); -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;}
.cf-sub {color: #A9B4CC; font-size: .85rem; margin-top: 2px;}
.cf-badge {display:inline-block; padding: 4px 12px; border-radius: 999px; font-size: .8rem;
  font-weight: 600; border: 1px solid transparent;}
.cf-ok {background:#0F2E22; color:#6EE7B7; border-color:#14532D;}
.cf-warn {background:#33270A; color:#FCD34D; border-color:#78350F;}
.cf-bad {background:#35121A; color:#FDA4AF; border-color:#7F1D1D;}
.cf-empty {text-align:center; color:#A9B4CC; padding: 2.5rem 1rem; border: 1px dashed #2B3550;
  border-radius: 14px;}
.cf-footer {color:#8793AE; font-size:.78rem; text-align:center; margin-top: 2rem;}
div[data-testid="stTabs"] button[role="tab"] {font-weight: 600;}
</style>
"""


def badge(text: str, tone: str) -> str:
    """Return a static HTML status badge (``tone``: ok, warn or bad)."""
    return f'<span class="cf-badge cf-{tone}">{html.escape(text)}</span>'


# --------------------------------------------------------------------------- #
# Settings and records                                                        #
# --------------------------------------------------------------------------- #
def collect_settings() -> GenerationSettings:
    """Read all prompt-shaping options from the session state."""
    state = st.session_state
    seconds = config.DURATION_OPTIONS.get(state[W_DURATION])
    if seconds is None:
        seconds = int(state[W_CUSTOM_DURATION])
    return GenerationSettings(
        content_type=state[W_CONTENT],
        platform=state[W_PLATFORM],
        duration_seconds=seconds,
        style=state[W_STYLE],
        camera=state[W_CAMERA],
        lighting=state[W_LIGHTING],
        quality=state[W_QUALITY],
        motion=state[W_MOTION],
        creativity=state[W_CREATIVITY],
        adherence=state[W_ADHERENCE],
        keep_original=bool(state[W_KEEP_ORIGINAL]),
    )


def settings_signature(prompt: str, settings: GenerationSettings) -> str:
    """Fingerprint used to detect a stale enhanced prompt."""
    return repr((prompt_engine.sanitize_prompt(prompt), sorted(settings.to_dict().items())))


def find_record(record_id: str | None) -> dict[str, Any] | None:
    """Return the history record with ``record_id`` if it still exists."""
    return next((r for r in st.session_state[K_HISTORY] if r["id"] == record_id), None)


def add_record(record: dict[str, Any]) -> None:
    """Insert a record (newest first) and evict old ones beyond the history limit."""
    history: list[dict[str, Any]] = st.session_state[K_HISTORY]
    history.insert(0, record)
    while len(history) > config.MAX_HISTORY_ITEMS:
        evicted = history.pop()
        video_utils.delete_video_file(evicted.get("video_path"))


def remove_record(record_id: str) -> None:
    """Delete a record and its temporary file."""
    record = find_record(record_id)
    if record is None:
        return
    video_utils.delete_video_file(record.get("video_path"))
    st.session_state[K_HISTORY] = [r for r in st.session_state[K_HISTORY] if r["id"] != record_id]
    st.session_state[K_STORY_IDS] = [i for i in st.session_state[K_STORY_IDS] if i != record_id]
    if st.session_state[K_LAST_RESULT] == record_id:
        st.session_state[K_LAST_RESULT] = None


def preview(text: str, width: int = 90) -> str:
    """Shorten text for lists and cards."""
    return textwrap.shorten(text or "", width=width, placeholder="…")


# --------------------------------------------------------------------------- #
# Callbacks (run before the script reruns)                                    #
# --------------------------------------------------------------------------- #
def cb_use_example(example: str) -> None:
    st.session_state[K_PROMPT] = example
    st.session_state[K_FORM_ERRORS] = []


def cb_reset_prompt() -> None:
    st.session_state[K_PROMPT] = ""
    st.session_state[K_ENHANCED] = ""
    st.session_state[K_ENHANCED_SIG] = None
    st.session_state[K_NEGATIVE] = config.DEFAULT_NEGATIVE_PROMPT
    st.session_state[K_FORM_ERRORS] = []


def cb_new_project() -> None:
    cb_reset_prompt()
    st.session_state[K_STORY] = ""
    st.session_state[K_PREFIX] = ""
    st.session_state[K_SCENES_BUILT] = 0
    for index in range(config.MAX_SCENES):
        st.session_state[scene_key(index)] = ""
    st.session_state[K_LAST_RESULT] = None
    st.session_state[K_LAST_ERROR] = None
    st.session_state[K_STORY_IDS] = []
    discard_merged_video()
    st.session_state[K_PROJECT] = "Untitled project"


def cb_enhance_prompt() -> None:
    prompt = st.session_state[K_PROMPT]
    problems = prompt_engine.validate_prompt(prompt)
    if problems:
        st.session_state[K_FORM_ERRORS] = problems
        return
    settings = collect_settings()
    st.session_state[K_ENHANCED] = prompt_engine.enhance_prompt(prompt, settings)
    st.session_state[K_ENHANCED_SIG] = settings_signature(prompt, settings)
    st.session_state[K_FORM_ERRORS] = []


def cb_test_connection() -> None:
    result = api_client.check_connection(config.get_api_key())
    st.session_state[K_CONNECTION] = {"ok": result.ok, "message": result.message}


def cb_dismiss_error() -> None:
    st.session_state[K_LAST_ERROR] = None


def can_start_request() -> bool:
    """Block duplicate submissions while busy or within the cooldown window."""
    if st.session_state[K_BUSY]:
        return False
    return time.monotonic() - st.session_state[K_LAST_REQUEST] >= config.REQUEST_COOLDOWN_SECONDS


def common_form_errors() -> list[str]:
    errors: list[str] = []
    if not config.get_api_key():
        errors.append(
            "NVIDIA_API_KEY is missing. Add it to .streamlit/secrets.toml or the environment."
        )
    if not st.session_state[W_SAFETY]:
        errors.append(
            "Confirm in Advanced settings that your prompt contains no confidential or personal data."
        )
    return errors


def queue_jobs(jobs: list[dict[str, Any]]) -> None:
    st.session_state[K_PENDING] = jobs
    st.session_state[K_BUSY] = True
    st.session_state[K_LAST_REQUEST] = time.monotonic()
    st.session_state[K_LAST_ERROR] = None
    st.session_state[K_FORM_ERRORS] = []


def make_job(
    label: str,
    user_prompt: str,
    final_prompt: str,
    settings: dict[str, Any],
    kind: str = "single",
    group_id: str | None = None,
    scene_index: int | None = None,
) -> dict[str, Any]:
    return {
        "label": label,
        "user_prompt": user_prompt,
        "final_prompt": final_prompt,
        "negative_prompt": prompt_engine.sanitize_prompt(
            st.session_state[K_NEGATIVE], config.MAX_NEGATIVE_PROMPT_CHARS
        ),
        "settings": settings,
        "kind": kind,
        "group_id": group_id,
        "scene_index": scene_index,
    }


def cb_generate_single() -> None:
    if not can_start_request():
        return
    prompt = st.session_state[K_PROMPT]
    errors = prompt_engine.validate_prompt(prompt) + common_form_errors()
    if errors:
        st.session_state[K_FORM_ERRORS] = errors
        return
    settings = collect_settings()
    enhanced = prompt_engine.sanitize_prompt(
        st.session_state[K_ENHANCED], config.MAX_FINAL_PROMPT_CHARS
    )
    if st.session_state[W_SHOW_ENHANCED] and enhanced:
        final_prompt = enhanced
    else:
        final_prompt = prompt_engine.enhance_prompt(prompt, settings)
    queue_jobs(
        [make_job("Generating video", prompt_engine.sanitize_prompt(prompt), final_prompt, settings.to_dict())]
    )


def cb_build_scenes() -> None:
    story = st.session_state[K_STORY]
    problems = prompt_engine.validate_prompt(story)
    if problems:
        st.session_state[K_FORM_ERRORS] = problems
        return
    count = int(st.session_state[K_SCENE_COUNT])
    for index, text in enumerate(prompt_engine.build_scene_texts(story, count)):
        st.session_state[scene_key(index)] = text
    st.session_state[K_SCENES_BUILT] = count
    st.session_state[K_PREFIX] = prompt_engine.build_style_prefix(collect_settings())
    st.session_state[K_FORM_ERRORS] = []


def cb_generate_storyboard() -> None:
    if not can_start_request():
        return
    built = int(st.session_state[K_SCENES_BUILT])
    errors = common_form_errors()
    scenes = [st.session_state[scene_key(i)] for i in range(built)]
    for number, text in enumerate(scenes, start=1):
        errors += [f"Scene {number}: {p}" for p in prompt_engine.validate_prompt(text)]
    if built < config.MIN_SCENES:
        errors.append("Build the scene cards first.")
    if errors:
        st.session_state[K_FORM_ERRORS] = errors
        return
    settings = collect_settings()
    prefix = prompt_engine.sanitize_prompt(st.session_state[K_PREFIX], config.MAX_PROMPT_CHARS)
    group_id = uuid.uuid4().hex
    jobs = [
        make_job(
            f"Generating scene {number} of {built}",
            prompt_engine.sanitize_prompt(text),
            prompt_engine.build_scene_prompt(prefix, text, settings),
            settings.to_dict(),
            kind="scene",
            group_id=group_id,
            scene_index=number,
        )
        for number, text in enumerate(scenes, start=1)
    ]
    st.session_state[K_STORY_IDS] = []
    discard_merged_video()
    queue_jobs(jobs)


def cb_regenerate(record_id: str) -> None:
    record = find_record(record_id)
    if record is None or not can_start_request():
        return
    errors = common_form_errors()
    if errors:
        st.session_state[K_FORM_ERRORS] = errors
        return
    job = make_job(
        "Regenerating video",
        record["prompt"],
        record["final_prompt"],
        dict(record["settings"]),
    )
    job["negative_prompt"] = record["negative_prompt"]
    queue_jobs([job])


def cb_ask_delete(record_id: str) -> None:
    st.session_state[K_CONFIRM_DELETE] = record_id


def cb_cancel_delete() -> None:
    st.session_state[K_CONFIRM_DELETE] = None


def cb_confirm_delete(record_id: str) -> None:
    remove_record(record_id)
    st.session_state[K_CONFIRM_DELETE] = None


def discard_merged_video() -> None:
    merged = st.session_state.get(K_MERGED)
    if merged:
        video_utils.delete_video_file(merged["path"])
    st.session_state[K_MERGED] = None


def cb_clear_temp_files() -> None:
    video_utils.clear_generated_files(st.session_state[K_SESSION_ID])
    st.session_state[K_HISTORY] = [
        r for r in st.session_state[K_HISTORY] if r["status"] != "success"
    ]
    st.session_state[K_STORY_IDS] = []
    st.session_state[K_LAST_RESULT] = None
    st.session_state[K_MERGED] = None
    st.session_state[K_CONFIRM_CLEAR] = False


# --------------------------------------------------------------------------- #
# Generation pipeline                                                         #
# --------------------------------------------------------------------------- #
def build_record(
    job: dict[str, Any],
    status: str,
    video_path: Path | None = None,
    metadata: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a history record (never contains the API key)."""
    settings = job["settings"]
    package = youtube_tools.build_youtube_package(
        job["user_prompt"], settings["content_type"], settings["style"], settings["platform"]
    ).to_dict()
    download_name = str(package["filename"])
    if job["scene_index"]:
        download_name = download_name.removesuffix(".mp4") + f"_scene{job['scene_index']}.mp4"
    return {
        "id": uuid.uuid4().hex,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "project": st.session_state[K_PROJECT],
        "kind": job["kind"],
        "group_id": job["group_id"],
        "scene_index": job["scene_index"],
        "status": status,
        "prompt": job["user_prompt"],
        "final_prompt": job["final_prompt"],
        "negative_prompt": job["negative_prompt"],
        "settings": settings,
        "video_path": str(video_path) if video_path else None,
        "download_name": download_name,
        "youtube": package,
        "metadata": metadata or {},
        "error": error,
    }


def run_job(job: dict[str, Any], api_key: str | None) -> bool:
    """Run one generation inside an ``st.status`` block. Returns True on success."""
    with st.status(job["label"], expanded=True) as status_box:

        def on_stage(stage: str) -> None:
            status_box.write(f"**{stage}…**")

        try:
            result = api_client.generate_video(
                job["final_prompt"], job["negative_prompt"], api_key, on_stage=on_stage
            )
            on_stage(api_client.STAGE_PREVIEW)
            video_path = video_utils.save_video_bytes(
                result.video_bytes, st.session_state[K_SESSION_ID]
            )
        except api_client.CineForgeError as error:
            failure = error.to_safe_dict()
        except video_utils.VideoProcessingError as error:
            failure = api_client.InvalidVideoDataError(str(error)).to_safe_dict()
        except Exception as error:  # last-resort guard; details never include secrets
            failure = api_client.CineForgeError(
                "An unexpected error occurred.",
                details=api_client.redact_secrets(type(error).__name__, api_key),
            ).to_safe_dict()
        else:
            record = build_record(job, "success", video_path, result.metadata)
            add_record(record)
            if job["kind"] == "scene":
                st.session_state[K_STORY_IDS].append(record["id"])
            else:
                st.session_state[K_LAST_RESULT] = record["id"]
            status_box.update(label=FEEDBACK_VIDEO_READY, state="complete", expanded=False)
            return True

        add_record(build_record(job, "failed", error=failure))
        st.session_state[K_LAST_ERROR] = failure
        status_box.update(label="Generation failed", state="error", expanded=False)
        return False


def process_pending(area: Any) -> None:
    """Execute queued jobs; always release the busy flag afterwards."""
    jobs: list[dict[str, Any]] = st.session_state[K_PENDING]
    if not jobs or not st.session_state[K_BUSY]:
        st.session_state[K_BUSY] = False
        return
    st.session_state[K_PENDING] = []
    api_key = config.get_api_key()
    try:
        with area:
            succeeded = 0
            for job in jobs:
                if not run_job(job, api_key):
                    break
                succeeded += 1
            if succeeded == len(jobs):
                st.toast(f"{succeeded} video(s) generated", icon="✅")
    finally:
        st.session_state[K_BUSY] = False


# --------------------------------------------------------------------------- #
# Reusable UI pieces                                                          #
# --------------------------------------------------------------------------- #
def render_error(error: dict[str, Any]) -> None:
    st.error(f"**{error['title']}** — {error['message']}")
    if error.get("hint"):
        st.info(error["hint"])
    with st.expander("Technical details"):
        parts = [f"Type: {error['type']}"]
        if error.get("status_code"):
            parts.append(f"HTTP status: {error['status_code']}")
        parts.append(error.get("details") or "No additional details.")
        st.code("\n".join(parts), language="text")


def render_form_errors() -> None:
    for message in st.session_state[K_FORM_ERRORS]:
        st.warning(message)


def show_video(record: dict[str, Any], key_prefix: str) -> bool:
    """Render preview + download for a record. Returns False when the file is gone."""
    data = video_utils.read_video_bytes(record.get("video_path"))
    if data is None:
        st.warning("This video file is no longer available.")
        return False
    preset = config.PLATFORM_PRESETS.get(record["settings"]["platform"])
    if preset and preset.orientation in ("vertical", "square"):
        _, middle, _ = st.columns([1, 2, 1])
        with middle:
            st.video(data)
    else:
        st.video(data)
    st.download_button(
        "⬇ Download MP4",
        data=data,
        file_name=record["download_name"],
        mime="video/mp4",
        key=f"{key_prefix}_download_{record['id']}",
    )
    return True


def render_youtube_package(record: dict[str, Any]) -> None:
    package = record["youtube"]
    with st.expander("📺 YouTube Package", expanded=True):
        st.markdown("**Suggested title**")
        st.code(package["title"], language=None)
        st.markdown("**Short description**")
        st.code(package["description"], language=None)
        st.markdown("**Alternative titles**")
        st.code("\n".join(package["alternative_titles"]), language=None)
        left, right = st.columns(2)
        with left:
            st.markdown("**Hashtags**")
            st.code(" ".join(package["hashtags"]), language=None)
            st.markdown("**Opening hook**")
            st.code(package["hook"], language=None)
            st.markdown("**Filename**")
            st.code(record["download_name"], language=None)
        with right:
            st.markdown("**Tags / keywords**")
            st.code(", ".join(package["tags"]), language=None)
            st.markdown("**On-screen caption**")
            st.code(package["caption"], language=None)
            st.markdown("**Thumbnail prompt**")
            st.code(package["thumbnail_prompt"], language=None)


def render_empty_state(title: str, message: str) -> None:
    st.markdown(
        f'<div class="cf-empty"><h4>{html.escape(title)}</h4><p>{html.escape(message)}</p></div>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Header and sidebar                                                          #
# --------------------------------------------------------------------------- #
def api_status_badge() -> str:
    connection = st.session_state[K_CONNECTION]
    if not config.get_api_key():
        return badge("● API key missing", "bad")
    if connection is None:
        return badge("● API key configured", "warn")
    return badge("● Connected", "ok") if connection["ok"] else badge("● Connection issue", "bad")


def render_header() -> None:
    brand, status, action = st.columns([5, 3, 1.4], vertical_alignment="center")
    with brand:
        st.markdown(
            f'<div class="cf-brand">{config.APP_ICON} <span>{html.escape(config.APP_NAME)}</span></div>'
            f'<div class="cf-sub">{html.escape(config.APP_TAGLINE)}</div>',
            unsafe_allow_html=True,
        )
    with status:
        st.markdown(api_status_badge(), unsafe_allow_html=True)
    with action:
        st.button(
            "＋ New Project",
            on_click=cb_new_project,
            disabled=st.session_state[K_BUSY],
            help="Clear the current prompt, scenes and results (history is kept).",
            width="stretch",
        )
    st.divider()


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(f"### {config.APP_ICON} {config.APP_NAME}")

        with st.expander("Project settings", expanded=True):
            st.text_input("Project name", key=K_PROJECT, max_chars=60)
            st.caption("The project name is stored with each generation in this session.")

        with st.expander("Generation history", expanded=True):
            history = st.session_state[K_HISTORY]
            if not history:
                st.caption("No generations yet.")
            for record in history[:10]:
                icon = "✅" if record["status"] == "success" else "❌"
                st.caption(f"{icon} {record['created_at'][11:]} — {preview(record['prompt'], 38)}")
            st.caption(f"{len(history)}/{config.MAX_HISTORY_ITEMS} stored this session")

        with st.expander("API connection", expanded=False):
            st.button("Test connection", on_click=cb_test_connection, width="stretch")
            connection = st.session_state[K_CONNECTION]
            if connection:
                (st.success if connection["ok"] else st.error)(connection["message"])
            st.caption("The test makes no generation request, so it uses no trial quota.")

        with st.expander("Temporary files", expanded=False):
            st.checkbox(
                "Delete all generated videos of this session", key=K_CONFIRM_CLEAR
            )
            st.button(
                "Clear temporary files",
                on_click=cb_clear_temp_files,
                disabled=not st.session_state[K_CONFIRM_CLEAR] or st.session_state[K_BUSY],
                width="stretch",
            )

        with st.expander("About", expanded=False):
            st.markdown(
                f"**{config.APP_NAME}** turns text prompts into short AI videos with the "
                "NVIDIA Cosmos3-Nano hosted API."
            )
            st.caption(config.PRIVACY_NOTICE)
            st.caption(config.SYNTHID_NOTICE)
            st.caption("Check NVIDIA's terms before any commercial use.")


# --------------------------------------------------------------------------- #
# Text-to-video tab                                                           #
# --------------------------------------------------------------------------- #
def render_shared_options() -> None:
    """Content, platform, duration and quality (right column)."""
    st.selectbox("Content type", list(config.CONTENT_TYPES), key=W_CONTENT)
    st.selectbox(
        "Platform preset",
        list(config.PLATFORM_PRESETS),
        key=W_PLATFORM,
        help="Shapes the prompt composition. The aspect ratio is not sent to the API.",
    )
    st.selectbox("Requested duration", list(config.DURATION_OPTIONS), key=W_DURATION)
    if config.DURATION_OPTIONS[st.session_state[W_DURATION]] is None:
        st.number_input(
            "Custom duration (seconds)",
            min_value=config.CUSTOM_DURATION_MIN,
            max_value=config.CUSTOM_DURATION_MAX,
            step=1,
            key=W_CUSTOM_DURATION,
        )
    st.caption(config.DURATION_NOTICE)
    st.selectbox("Quality", list(config.QUALITY_OPTIONS), key=W_QUALITY)
    st.caption(config.QUALITY_NOTICE)


def render_look_options() -> None:
    col_style, col_camera, col_light = st.columns(3)
    with col_style:
        st.selectbox("Visual style", list(config.VISUAL_STYLES), key=W_STYLE)
    with col_camera:
        st.selectbox("Camera movement", list(config.CAMERA_MOVEMENTS), key=W_CAMERA)
    with col_light:
        st.selectbox("Lighting", list(config.LIGHTING_OPTIONS), key=W_LIGHTING)


def render_negative_and_advanced() -> None:
    st.text_area(
        "Negative prompt",
        key=K_NEGATIVE,
        height=90,
        max_chars=config.MAX_NEGATIVE_PROMPT_CHARS,
        help="Things the model should avoid. Editable.",
    )
    with st.expander("Advanced settings", expanded=False):
        col_a, col_b = st.columns(2)
        with col_a:
            st.number_input(
                "Seed",
                min_value=0,
                value=0,
                disabled=True,
                help="Not sent: the seed field is not confirmed for this Preview endpoint.",
            )
            st.caption("Seed is disabled until NVIDIA documents it for Cosmos3-Nano.")
            st.select_slider(
                "Motion intensity", list(config.MOTION_LEVELS), key=W_MOTION,
                help="Used as prompt wording only.",
            )  # fmt: skip
            st.select_slider(
                "Creativity level", list(config.CREATIVITY_LEVELS), key=W_CREATIVITY,
                help="Used as prompt wording only.",
            )  # fmt: skip
        with col_b:
            st.select_slider(
                "Prompt adherence", list(config.ADHERENCE_LEVELS), key=W_ADHERENCE,
                help="Used as prompt wording only (no guidance value is sent).",
            )  # fmt: skip
            st.toggle(
                "Keep original prompt", key=W_KEEP_ORIGINAL,
                help="Keeps your exact wording at the start of the enhanced prompt.",
            )  # fmt: skip
            st.toggle(
                "Show enhanced prompt", key=W_SHOW_ENHANCED,
                help="When off, the enhanced prompt is built automatically at generation time.",
            )  # fmt: skip
            st.checkbox(
                "I confirm this prompt contains no confidential or personal data.",
                key=W_SAFETY,
            )


def render_confirmation_summary(settings: GenerationSettings, requests_count: int) -> None:
    preset = config.PLATFORM_PRESETS[settings.platform]
    with st.container(border=True):
        st.markdown("**Confirmation summary**")
        st.markdown(
            f"- **Content:** {settings.content_type} · **Style:** {settings.style}\n"
            f"- **Platform:** {settings.platform} ({preset.ratio}, prompt-shaping only)\n"
            f"- **Camera:** {settings.camera} · **Lighting:** {settings.lighting}\n"
            f"- **Pacing hint:** about {settings.duration_seconds}s · **Quality wording:** {settings.quality}\n"
            f"- **API requests:** {requests_count} (counts toward your NVIDIA trial limits)"
        )


def render_single_mode() -> None:
    prompt = st.session_state[K_PROMPT]
    st.text_area(
        "Describe your video",
        key=K_PROMPT,
        height=140,
        max_chars=config.MAX_PROMPT_CHARS,
        placeholder="Example: A sports car driving through a city at night",
    )
    st.caption(f"{len(prompt)}/{config.MAX_PROMPT_CHARS} characters")

    st.caption("Try an example:")
    for column, example in zip(st.columns(len(config.EXAMPLE_PROMPTS)), config.EXAMPLE_PROMPTS):
        with column:
            st.button(
                preview(example, 34), key=f"example_{example}", help=example,
                on_click=cb_use_example, args=(example,), width="stretch",
            )  # fmt: skip

    col_enhance, col_reset, _ = st.columns([1.3, 1, 3])
    with col_enhance:
        st.button("✨ Enhance Prompt", on_click=cb_enhance_prompt, width="stretch")
    with col_reset:
        st.button("Reset", on_click=cb_reset_prompt, width="stretch")


def render_single_generation() -> None:
    settings = collect_settings()
    prompt = st.session_state[K_PROMPT]
    if st.session_state[W_SHOW_ENHANCED]:
        st.text_area(
            "Enhanced prompt (editable, sent to NVIDIA)",
            key=K_ENHANCED,
            height=200,
            max_chars=config.MAX_FINAL_PROMPT_CHARS,
            placeholder="Click “Enhance Prompt” to build a detailed prompt, or leave empty to auto-build it.",
        )
        signature = st.session_state[K_ENHANCED_SIG]
        if st.session_state[K_ENHANCED] and signature != settings_signature(prompt, settings):
            st.caption("⚠ Prompt or settings changed since enhancing. Click “Enhance Prompt” to refresh.")

    render_confirmation_summary(settings, 1)
    render_form_errors()
    st.button(
        "🎬 Generate Video",
        type="primary",
        on_click=cb_generate_single,
        disabled=st.session_state[K_BUSY],
        width="stretch",
    )

    record = find_record(st.session_state[K_LAST_RESULT])
    if record is None:
        if not st.session_state[K_HISTORY]:
            render_empty_state(
                "Your video will appear here",
                "Describe a scene, optionally enhance the prompt, then press Generate Video.",
            )
        return
    st.success("Video generated successfully!")
    if show_video(record, "latest"):
        meta = record["metadata"]
        st.caption(
            f"Generated in {meta.get('elapsed_seconds', '?')}s · "
            f"{meta.get('size_bytes', 0) / 1_048_576:.1f} MB · {config.SYNTHID_NOTICE}"
        )
    render_youtube_package(record)


def render_storyboard_mode() -> None:
    st.info(
        "Experimental: each scene is generated as a separate clip. Characters and objects "
        "will **not** be perfectly consistent between clips."
    )
    st.text_area(
        "Story or concept",
        key=K_STORY,
        height=120,
        max_chars=config.MAX_PROMPT_CHARS,
        placeholder="Example: A small robot wakes up in an abandoned garden. It explores, finds a "
        "glowing flower, and carries it to the city skyline at sunrise.",
    )
    col_count, col_build, _ = st.columns([2, 1.5, 2], vertical_alignment="bottom")
    with col_count:
        st.slider("Number of scenes", config.MIN_SCENES, config.MAX_SCENES, key=K_SCENE_COUNT)
    with col_build:
        st.button("Build scene cards", on_click=cb_build_scenes, width="stretch")


def render_storyboard_generation() -> None:
    settings = collect_settings()
    built = int(st.session_state[K_SCENES_BUILT])
    if built >= config.MIN_SCENES:
        if built != int(st.session_state[K_SCENE_COUNT]):
            st.caption("The scene count changed. Click “Build scene cards” to rebuild.")
        st.text_area(
            "Shared style prefix (added to every scene)",
            key=K_PREFIX,
            height=90,
            max_chars=config.MAX_PROMPT_CHARS,
        )
        for row_start in range(0, built, 2):
            columns = st.columns(2)
            for offset, column in enumerate(columns):
                index = row_start + offset
                if index < built:
                    with column, st.container(border=True):
                        st.text_area(
                            f"Scene {index + 1}", key=scene_key(index), height=130,
                            max_chars=config.MAX_PROMPT_CHARS,
                        )  # fmt: skip
        render_confirmation_summary(settings, built)
    else:
        render_empty_state(
            "No scenes yet", "Enter a story, choose the scene count and build the scene cards."
        )
    render_form_errors()
    st.button(
        f"🎬 Generate {built} scenes" if built >= config.MIN_SCENES else "🎬 Generate scenes",
        type="primary",
        on_click=cb_generate_storyboard,
        disabled=st.session_state[K_BUSY] or built < config.MIN_SCENES,
        width="stretch",
    )
    render_storyboard_results()


def render_storyboard_results() -> None:
    records = [r for r in map(find_record, st.session_state[K_STORY_IDS]) if r]
    if not records:
        return
    st.subheader("Generated scenes")
    for column, record in zip(st.columns(min(len(records), 3)), records):
        with column:
            st.markdown(f"**Scene {record['scene_index']}**")
            show_video(record, "scene")
            with st.expander("Prompt"):
                st.write(record["final_prompt"])
    render_merge_section(records)


def render_merge_section(records: list[dict[str, Any]]) -> None:
    st.subheader("Combine clips")
    if not video_utils.ffmpeg_available():
        st.info(video_utils.FFMPEG_INSTALL_HINT)
        return
    if len(records) < 2:
        st.caption("At least two generated scenes are needed to merge.")
        return
    st.checkbox("Add simple crossfades", key=K_CROSSFADE)
    audio_file = st.file_uploader(
        "Optional audio track (your own audio only)",
        type=[ext.lstrip(".") for ext in config.ALLOWED_AUDIO_EXTENSIONS],
        help=f"Max {config.MAX_AUDIO_BYTES // (1024 * 1024)} MB.",
    )
    st.warning("Only upload audio you have the rights to use. This app does not generate music.")
    if st.button("Merge clips", disabled=st.session_state[K_BUSY]):
        audio_bytes: bytes | None = None
        extension = ".mp3"
        if audio_file is not None:
            audio_bytes = audio_file.getvalue()
            extension = Path(audio_file.name).suffix.lower()
            problem = video_utils.validate_audio_upload(audio_file.name, audio_bytes)
            if problem:
                st.error(problem)
                return
        paths = [Path(r["video_path"]) for r in records if r.get("video_path")]
        with st.spinner("Merging clips with FFmpeg…"):
            try:
                output = video_utils.merge_clips(
                    paths, st.session_state[K_CROSSFADE], audio_bytes, extension,
                    st.session_state[K_SESSION_ID],
                )  # fmt: skip
            except video_utils.VideoProcessingError as error:
                st.error(str(error))
                return
        discard_merged_video()
        title = records[0]["youtube"]["title"]
        st.session_state[K_MERGED] = {
            "path": str(output),
            "name": video_utils.safe_filename(title + " combined"),
        }
    merged = st.session_state[K_MERGED]
    if merged:
        data = video_utils.read_video_bytes(merged["path"])
        if data:
            st.success("Combined video ready.")
            st.video(data)
            st.download_button(
                "⬇ Export combined MP4", data=data, file_name=merged["name"], mime="video/mp4",
                key="merged_download",
            )  # fmt: skip


def render_text_to_video_tab() -> None:
    st.radio(
        "Mode", [MODE_SINGLE, MODE_STORYBOARD], key=K_MODE, horizontal=True,
        label_visibility="collapsed", disabled=st.session_state[K_BUSY],
    )  # fmt: skip
    storyboard = st.session_state[K_MODE] == MODE_STORYBOARD
    left, right = st.columns([3, 2], gap="large")
    with left:
        if storyboard:
            render_storyboard_mode()
        else:
            render_single_mode()
        render_look_options()
    with right:
        render_shared_options()
    render_negative_and_advanced()
    if storyboard:
        render_storyboard_generation()
    else:
        render_single_generation()


# --------------------------------------------------------------------------- #
# Other tabs                                                                  #
# --------------------------------------------------------------------------- #
def render_coming_soon(title: str, detail: str) -> None:
    render_empty_state(f"{title}: coming soon", detail)


def render_creations_tab() -> None:
    history = st.session_state[K_HISTORY]
    successes = [r for r in history if r["status"] == "success"]
    if not successes:
        render_empty_state(
            "No creations yet", "Videos you generate in this session will appear here."
        )
    for record in successes:
        with st.container(border=True):
            video_col, info_col = st.columns([2, 3], gap="large")
            with video_col:
                show_video(record, "creation")
            with info_col:
                settings = record["settings"]
                st.markdown(f"**{record['youtube']['title']}**")
                st.caption(
                    f"{record['created_at']} · {settings['content_type']} · {settings['style']} · "
                    f"{settings['platform']}"
                )
                st.write(preview(record["prompt"], 220))
                regenerate_col, delete_col, _ = st.columns([1, 1, 2])
                with regenerate_col:
                    st.button(
                        "↻ Regenerate", key=f"regen_{record['id']}", on_click=cb_regenerate,
                        args=(record["id"],), disabled=st.session_state[K_BUSY], width="stretch",
                    )  # fmt: skip
                with delete_col:
                    st.button(
                        "🗑 Delete", key=f"del_{record['id']}", on_click=cb_ask_delete,
                        args=(record["id"],), width="stretch",
                    )  # fmt: skip
                if st.session_state[K_CONFIRM_DELETE] == record["id"]:
                    st.warning("Delete this video permanently?")
                    yes_col, no_col, _ = st.columns([1, 1, 2])
                    with yes_col:
                        st.button(
                            "Yes, delete", key=f"yes_{record['id']}", type="primary",
                            on_click=cb_confirm_delete, args=(record["id"],), width="stretch",
                        )  # fmt: skip
                    with no_col:
                        st.button(
                            "Cancel", key=f"no_{record['id']}", on_click=cb_cancel_delete,
                            width="stretch",
                        )  # fmt: skip
    failures = [r for r in history if r["status"] == "failed"]
    if failures:
        with st.expander(f"Failed attempts ({len(failures)})"):
            for record in failures:
                error = record["error"] or {}
                st.caption(
                    f"❌ {record['created_at']} — {preview(record['prompt'], 60)} — "
                    f"{error.get('title', 'Error')}"
                )


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #
def main() -> None:
    init_state()
    st.markdown(APP_CSS, unsafe_allow_html=True)
    render_header()

    status_area = st.container()
    process_pending(status_area)
    last_error = st.session_state[K_LAST_ERROR]
    if last_error:
        render_error(last_error)
        st.button("Dismiss error", on_click=cb_dismiss_error)

    render_sidebar()

    tab_text, tab_image, tab_video, tab_creations = st.tabs(
        ["Text to Video", "Image to Video", "Video to Video", "My Creations"]
    )
    with tab_text:
        render_text_to_video_tab()
    with tab_image:
        render_coming_soon(
            "Image to Video",
            "The confirmed request schema for image input is not available yet, so no controls are shown.",
        )
    with tab_video:
        render_coming_soon(
            "Video to Video",
            "The confirmed request schema for video input is not available yet, so no controls are shown.",
        )
    with tab_creations:
        render_creations_tab()

    st.markdown(
        f'<div class="cf-footer">{html.escape(config.PRIVACY_NOTICE)}<br>'
        f"{html.escape(config.SYNTHID_NOTICE)}</div>",
        unsafe_allow_html=True,
    )


main()
