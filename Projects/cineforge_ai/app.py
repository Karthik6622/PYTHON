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
import audio_tools
import config
import llm_client
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
K_EXAMPLE = "example_choice"
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
W_SEED = "w_seed"
W_KEEP_ORIGINAL = "w_keep_original"
W_SHOW_ENHANCED = "w_show_enhanced"
W_SAFETY = "w_safety_confirmation"
W_DIRECTOR = "w_ai_director"
W_LLM_MODEL = "w_llm_model"
W_VOICEOVER = "w_voiceover"
W_VOICE = "w_voice"
K_NARRATION = "narration_text"
MODE_SINGLE = "Single clip"
MODE_STORYBOARD = "Storyboard (experimental)"
EXAMPLE_PLACEHOLDER = "Pick an example prompt…"


def scene_key(index: int) -> str:
    """Session-state key of the editable text for scene ``index``."""
    return f"scene_text_{index}"


PERSISTENT_KEYS = [
    K_PROMPT, K_ENHANCED, K_ENHANCED_SIG, K_NEGATIVE, K_PROJECT, K_MODE, K_STORY,
    K_SCENE_COUNT, K_PREFIX, K_CROSSFADE, K_EXAMPLE, W_CONTENT, W_PLATFORM, W_DURATION,
    W_CUSTOM_DURATION, W_STYLE, W_CAMERA, W_LIGHTING, W_QUALITY, W_MOTION,
    W_CREATIVITY, W_ADHERENCE, W_SEED, W_KEEP_ORIGINAL, W_SHOW_ENHANCED, W_SAFETY,
    W_DIRECTOR, W_LLM_MODEL, W_VOICEOVER, W_VOICE, K_NARRATION,
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
        K_EXAMPLE: EXAMPLE_PLACEHOLDER,
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
        W_CUSTOM_DURATION: 6,
        W_STYLE: "Cinematic realism",
        W_CAMERA: "Slow cinematic push-in",
        W_LIGHTING: "Dramatic cinematic lighting",
        W_QUALITY: "High quality",
        W_MOTION: "Balanced",
        W_CREATIVITY: "Balanced",
        W_ADHERENCE: "Balanced",
        W_SEED: 0,
        W_KEEP_ORIGINAL: True,
        W_SHOW_ENHANCED: True,
        W_SAFETY: True,
        W_DIRECTOR: True,
        W_LLM_MODEL: config.DEFAULT_LLM_MODEL,
        W_VOICEOVER: True,
        W_VOICE: config.DEFAULT_VOICE,
        K_NARRATION: "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    for key in PERSISTENT_KEYS:
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


# --------------------------------------------------------------------------- #
# Styling: red cyberpunk                                                      #
# --------------------------------------------------------------------------- #
APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Rajdhani:wght@400;500;600;700&display=swap');
:root {--red:#FF2A4D; --red-deep:#B3001B; --cyan:#00E5FF; --panel:#10070C; --line:rgba(255,42,77,.38);}

.stApp {
  background:
    radial-gradient(1100px 560px at 88% -8%, rgba(255,42,77,.20), transparent 60%),
    radial-gradient(900px 520px at -8% 108%, rgba(0,229,255,.07), transparent 60%),
    #07040A;
}
.stApp::before {content:""; position:fixed; inset:0; pointer-events:none; z-index:0;
  background: repeating-linear-gradient(0deg, rgba(255,255,255,.022) 0 1px, transparent 1px 3px);}
.block-container {padding-top: 1.1rem; max-width: 1380px;}
header[data-testid="stHeader"] {background: transparent;}
/* hide Streamlit chrome: running indicator + Stop, Share/star/edit/GitHub toolbar, menu, deploy, Manage app */
[data-testid="stToolbar"], [data-testid="stStatusWidget"], [data-testid="stAppDeployButton"],
[data-testid="stDeployButton"], [data-testid="stMainMenu"], #MainMenu, [data-testid="stDecoration"],
[data-testid="manage-app-button"], .stDeployButton, .viewerBadge_container__r5tak,
[class*="viewerBadge"], footer {display:none !important; visibility:hidden !important;}

.stApp [data-testid="stMarkdownContainer"], .stApp label p, .stApp input, .stApp textarea,
.stApp button p, .stApp [data-baseweb="select"] div {font-family: 'Rajdhani', 'Segoe UI', sans-serif;}
.stApp label p {font-size: .95rem; letter-spacing: .04em; color:#F3D9DE;}

/* header */
.cf-brand {font-family:'Orbitron',sans-serif; font-weight:900; font-size:1.75rem; letter-spacing:.14em;
  color:#fff; text-shadow:0 0 14px rgba(255,42,77,.9);}
.cf-brand b {color: var(--red);}
.cf-brand i {color: var(--cyan); font-style:normal; text-shadow:0 0 12px rgba(0,229,255,.8);}
.cf-sub {color:#C79AA4; font-size:.82rem; letter-spacing:.24em; text-transform:uppercase; margin-top:2px;}

/* section labels, chips, badges */
.cf-kicker {font-family:'Orbitron',sans-serif; font-size:.72rem; letter-spacing:.24em; color:var(--red);
  text-transform:uppercase; margin-bottom:.15rem; text-shadow:0 0 8px rgba(255,42,77,.6);}
.cf-chip {display:inline-block; margin:2px 6px 2px 0; padding:2px 10px; font-size:.8rem; color:#9CF3FF;
  border:1px solid rgba(0,229,255,.45); background:rgba(0,229,255,.06);
  clip-path: polygon(0 0, calc(100% - 6px) 0, 100% 6px, 100% 100%, 6px 100%, 0 calc(100% - 6px));}
.cf-badge {display:inline-block; padding:5px 14px; font-size:.8rem; font-weight:700; letter-spacing:.08em;
  text-transform:uppercase; border:1px solid transparent;
  clip-path: polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px));}
.cf-ok {background:rgba(0,229,255,.10); color:#7DF3FF; border-color:rgba(0,229,255,.55);}
.cf-warn {background:rgba(255,176,32,.10); color:#FFC95C; border-color:rgba(255,176,32,.5);}
.cf-bad {background:rgba(255,42,77,.14); color:#FF8FA3; border-color:rgba(255,42,77,.65);}
.cf-empty {text-align:center; color:#C79AA4; padding:2.2rem 1rem; border:1px dashed var(--line);}
.cf-empty h4 {font-family:'Orbitron',sans-serif; color:#fff; letter-spacing:.1em;}
.cf-footer {color:#8E6A73; font-size:.76rem; text-align:center; margin-top:2rem; letter-spacing:.04em;}

/* cards */
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div[data-testid="stVerticalBlock"]) {
  border:1px solid var(--line) !important; border-radius:2px !important;
  background: linear-gradient(160deg, rgba(255,42,77,.07), rgba(16,7,12,.92) 55%);
  box-shadow: 0 0 22px rgba(255,42,77,.10), inset 0 0 0 1px rgba(255,42,77,.05);
}

/* buttons */
.stApp button[kind="primary"] {
  background: linear-gradient(90deg, #FF1744, var(--red-deep)); border:1px solid #FF5C75; color:#fff;
  font-family:'Orbitron',sans-serif; text-transform:uppercase; letter-spacing:.14em; font-weight:700;
  box-shadow: 0 0 18px rgba(255,42,77,.55); border-radius:2px;
}
.stApp button[kind="primary"]:hover {box-shadow: 0 0 30px rgba(255,42,77,.9); filter:brightness(1.12);}
.stApp button[kind="primary"]:disabled {box-shadow:none; filter:grayscale(.6) brightness(.7);}
.stApp button[kind="secondary"], .stApp [data-testid="stDownloadButton"] button {
  background: rgba(255,42,77,.06); border:1px solid var(--line); color:#FFD7DE; border-radius:2px;
}
.stApp button[kind="secondary"]:hover, .stApp [data-testid="stDownloadButton"] button:hover {
  border-color: var(--red); box-shadow: 0 0 14px rgba(255,42,77,.45); color:#fff;
}

/* inputs */
.stApp textarea, .stApp input, .stApp [data-baseweb="select"] > div {
  background-color:#0B0509 !important; border-color: rgba(255,42,77,.28) !important; border-radius:2px !important;
}
.stApp textarea:focus, .stApp input:focus {border-color: var(--red) !important; box-shadow:0 0 0 1px var(--red);}

/* tabs, sidebar, expanders */
div[data-testid="stTabs"] button[role="tab"] {font-family:'Orbitron',sans-serif; font-size:.8rem;
  letter-spacing:.12em; text-transform:uppercase;}
section[data-testid="stSidebar"] {background:#0A0509; border-right:1px solid var(--line);}
section[data-testid="stSidebar"] h3 {font-family:'Orbitron',sans-serif; letter-spacing:.12em;}
div[data-testid="stExpander"] details {border:1px solid var(--line); border-radius:2px; background:rgba(255,42,77,.03);}
div[data-testid="stExpander"] summary p {font-family:'Orbitron',sans-serif; font-size:.78rem;
  letter-spacing:.14em; text-transform:uppercase;}
hr {border-color: var(--line) !important;}
</style>
"""


def badge(text: str, tone: str) -> str:
    """Return a static HTML status badge (``tone``: ok, warn or bad)."""
    return f'<span class="cf-badge cf-{tone}">{html.escape(text)}</span>'


def kicker(text: str) -> None:
    st.markdown(f'<div class="cf-kicker">{html.escape(text)}</div>', unsafe_allow_html=True)


def chips(items: list[str]) -> None:
    st.markdown(
        "".join(f'<span class="cf-chip">{html.escape(item)}</span>' for item in items),
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Settings and records                                                        #
# --------------------------------------------------------------------------- #
def collect_settings() -> GenerationSettings:
    """Read all prompt- and API-shaping options from the session state."""
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
        seed=int(state[W_SEED]),
    )


def plan_for(settings: GenerationSettings) -> config.VideoPlan:
    """Translate UI settings into documented API parameters."""
    preset = config.PLATFORM_PRESETS[settings.platform]
    return config.plan_video(
        preset.ratio, settings.quality, settings.duration_seconds, settings.adherence, settings.seed
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
def cb_pick_example() -> None:
    choice = st.session_state[K_EXAMPLE]
    if choice in config.EXAMPLE_PROMPTS:
        st.session_state[K_PROMPT] = choice
        st.session_state[K_FORM_ERRORS] = []
    st.session_state[K_EXAMPLE] = EXAMPLE_PLACEHOLDER


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
    if not config.get_api_key() and config.api_key_required():
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


def describe_brief(settings: GenerationSettings) -> str:
    """Production brief handed to the AI Director."""
    preset = config.PLATFORM_PRESETS[settings.platform]
    return "; ".join(
        [
            config.CONTENT_TYPES[settings.content_type],
            f"{preset.ratio} {preset.orientation} frame, {preset.composition}",
            f"visual style: {config.VISUAL_STYLES[settings.style]}",
            f"camera: {config.CAMERA_MOVEMENTS[settings.camera]}",
            f"lighting: {config.LIGHTING_OPTIONS[settings.lighting]}",
            f"motion: {config.MOTION_LEVELS[settings.motion]}",
            config.CREATIVITY_LEVELS[settings.creativity],
        ]
    )


def make_job(
    label: str,
    user_prompt: str,
    final_prompt: str,
    settings: GenerationSettings,
    kind: str = "single",
    group_id: str | None = None,
    scene_index: int | None = None,
) -> dict[str, Any]:
    plan = plan_for(settings)
    return {
        "label": label,
        "user_prompt": user_prompt,
        "final_prompt": final_prompt,
        "negative_prompt": prompt_engine.sanitize_prompt(
            st.session_state[K_NEGATIVE], config.MAX_NEGATIVE_PROMPT_CHARS
        ),
        "settings": settings.to_dict(),
        "api_params": plan.params,
        "plan_summary": plan.summary,
        "kind": kind,
        "group_id": group_id,
        "scene_index": scene_index,
        "use_director": bool(st.session_state[W_DIRECTOR]),
        "director_model": st.session_state[W_LLM_MODEL],
        "brief": describe_brief(settings),
        "duration": plan.actual_seconds,
        "voiceover": bool(st.session_state[W_VOICEOVER]),
        "voice": st.session_state[W_VOICE],
        "narration": prompt_engine.sanitize_prompt(st.session_state[K_NARRATION], 400)
        if kind == "single"
        else "",
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
        [make_job("Generating video", prompt_engine.sanitize_prompt(prompt), final_prompt, settings)]
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
            settings,
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
        GenerationSettings(**record["settings"]),
    )
    job["negative_prompt"] = record["negative_prompt"]
    job["api_params"] = dict(record["api_params"])
    job["plan_summary"] = record["plan_summary"]
    job["use_director"] = False  # reuse the exact prompt and narration of the original
    job["narration"] = record["metadata"].get("narration", "")
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
        "api_params": job["api_params"],
        "plan_summary": job["plan_summary"],
        "video_path": str(video_path) if video_path else None,
        "download_name": download_name,
        "youtube": package,
        "metadata": metadata or {},
        "error": error,
    }


class JobProgress:
    """Drives one progress bar across the pipeline stages (percentages are overall)."""

    DIRECTOR = (0.00, 0.10)
    VIDEO = (0.10, 0.80)
    VOICE = (0.80, 0.88)
    EXPORT = (0.88, 0.98)

    def __init__(self, bar: Any) -> None:
        self._bar = bar
        self._last = 0.0

    def update(self, fraction: float, message: str) -> None:
        self._last = max(self._last, min(max(fraction, 0.0), 1.0))
        self._bar.progress(self._last, text=f"{int(self._last * 100)}% · {message}")

    def stage(self, window: tuple[float, float], inner: float, message: str) -> None:
        start, end = window
        self.update(start + (end - start) * inner, message)


def direct_job(job: dict[str, Any], api_key: str | None, progress: JobProgress, log: Any) -> None:
    """Let a Nemotron model write the final video prompt (and narration) for ``job``."""
    if not job["use_director"]:
        return
    progress.stage(JobProgress.DIRECTOR, 0.1, f"AI Director ({job['director_model']}) is writing the prompt")
    try:
        result = llm_client.direct_video(
            job["user_prompt"],
            job["brief"],
            job["duration"],
            api_key,
            job["director_model"],
            want_narration=job["voiceover"] and not job["narration"],
        )
    except llm_client.DirectorError as error:
        log.write(f"⚠️ AI Director skipped: {error.message} {error.hint} Using the built-in prompt builder.")
        return
    job["final_prompt"] = result.video_prompt
    job["narration"] = job["narration"] or result.narration
    job["director_used"] = result.model
    log.write(f"✍️ Prompt written by **{result.model}**")


def finish_video(job: dict[str, Any], video_path: Path, progress: JobProgress, log: Any) -> tuple[Path, dict[str, Any]]:
    """Add the voice-over and export a Full HD YouTube-ready file; degrade gracefully."""
    session_id = st.session_state[K_SESSION_ID]
    notes: dict[str, Any] = {}
    audio_path: Path | None = None
    if job["voiceover"] and job["narration"]:
        progress.stage(JobProgress.VOICE, 0.2, "Recording the voice-over")
        try:
            audio_path = audio_tools.synthesize_speech(
                job["narration"], job["voice"], video_utils.new_output_path(".mp3", session_id)
            )
            notes["voice"] = job["voice"]
        except audio_tools.AudioError as error:
            log.write(f"⚠️ Voice-over skipped: {error}")
    elif job["voiceover"]:
        log.write("⚠️ No narration text, so the video has no voice-over.")
    progress.stage(JobProgress.EXPORT, 0.1, "Mastering for YouTube (Full HD, audio mix)")
    try:
        exported = audio_tools.export_for_youtube(
            video_path, audio_path, video_utils.new_output_path(".mp4", session_id)
        )
    except audio_tools.AudioError as error:
        log.write(f"⚠️ YouTube export skipped, using the original render: {error}")
        notes.pop("voice", None)
        return video_path, notes
    finally:
        if audio_path is not None:
            video_utils.delete_video_file(audio_path)
    video_utils.delete_video_file(video_path)
    notes["export"] = "Full HD H.264/AAC"
    return exported, notes


def run_job(job: dict[str, Any], api_key: str | None) -> bool:
    """Run one generation inside an ``st.status`` block. Returns True on success."""
    with st.status(job["label"], expanded=True) as status_box:
        progress = JobProgress(st.progress(0, text="0% · Starting"))

        def on_video_progress(fraction: float, message: str) -> None:
            progress.stage(JobProgress.VIDEO, fraction, message)

        try:
            direct_job(job, api_key, progress, status_box)
            result = api_client.generate_video(
                job["final_prompt"],
                job["negative_prompt"],
                api_key,
                job["api_params"],
                on_progress=on_video_progress,
            )
            raw_path = video_utils.save_video_bytes(
                result.video_bytes, st.session_state[K_SESSION_ID]
            )
            video_path, notes = finish_video(job, raw_path, progress, status_box)
            progress.update(0.99, "Preparing preview")
            result.metadata.update(notes)
            result.metadata["narration"] = job["narration"] if "voice" in notes else ""
            result.metadata["director"] = job.get("director_used", "")
            result.metadata["size_bytes"] = video_path.stat().st_size
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
            progress.update(1.0, "Done")
            record = build_record(job, "success", video_path, result.metadata)
            add_record(record)
            if job["kind"] == "scene":
                st.session_state[K_STORY_IDS].append(record["id"])
            else:
                st.session_state[K_LAST_RESULT] = record["id"]
            status_box.update(label="Video ready", state="complete", expanded=False)
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
    with st.expander("📺 YouTube Package", expanded=False):
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
    if config.get_provider() == config.PROVIDER_HUGGINGFACE:
        tone = "warn" if connection is None else ("ok" if connection["ok"] else "bad")
        return badge("● Free LTX-Video Space", tone)
    if not config.api_key_required():
        host = config.get_api_url().split("//")[-1].split("/")[0]
        tone = "warn" if connection is None else ("ok" if connection["ok"] else "bad")
        return badge(f"● Custom endpoint · {host}", tone)
    if not config.get_api_key():
        return badge("● API key missing", "bad")
    if connection is None:
        return badge("● API key set", "warn")
    return badge("● Endpoint OK", "ok") if connection["ok"] else badge("● Endpoint issue", "bad")


def render_header() -> None:
    brand, status, action = st.columns([5, 3, 1.5], vertical_alignment="center")
    with brand:
        st.markdown(
            '<div class="cf-brand">CINE<b>FORGE</b> <i>AI</i></div>'
            f'<div class="cf-sub">{html.escape(config.app_tagline())}</div>',
            unsafe_allow_html=True,
        )
    with status:
        st.markdown(api_status_badge(), unsafe_allow_html=True)
    with action:
        st.button(
            "＋ New project",
            on_click=cb_new_project,
            disabled=st.session_state[K_BUSY],
            help="Clear the current prompt, scenes and results (history is kept).",
            width="stretch",
        )
    st.divider()


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### PROJECT")
        st.text_input("Project name", key=K_PROJECT, max_chars=60, label_visibility="collapsed")

        st.markdown("### HISTORY")
        history = st.session_state[K_HISTORY]
        if not history:
            st.caption("No generations yet.")
        for record in history[:8]:
            icon = "✅" if record["status"] == "success" else "❌"
            st.caption(f"{icon} {record['created_at'][11:]} · {preview(record['prompt'], 34)}")
        st.caption(f"{len(history)}/{config.MAX_HISTORY_ITEMS} stored this session")

        st.markdown("### TOOLS")
        st.button("Test API connection", on_click=cb_test_connection, width="stretch")
        connection = st.session_state[K_CONNECTION]
        if connection:
            (st.success if connection["ok"] else st.error)(connection["message"])
        st.checkbox("Allow deleting all videos", key=K_CONFIRM_CLEAR)
        st.button(
            "Clear temporary files",
            on_click=cb_clear_temp_files,
            disabled=not st.session_state[K_CONFIRM_CLEAR] or st.session_state[K_BUSY],
            width="stretch",
        )

        with st.expander("About"):
            nvidia = config.get_provider() == config.PROVIDER_NVIDIA
            st.markdown(
                f"**{config.APP_NAME}** turns text prompts into short AI videos with "
                + (
                    "the NVIDIA Cosmos3-Nano hosted API."
                    if nvidia
                    else "LTX-Video running on a free Hugging Face Space."
                )
            )
            st.caption(config.privacy_notice())
            if config.synthid_notice():
                st.caption(config.synthid_notice())
            st.caption(
                "Check NVIDIA's terms before any commercial use."
                if nvidia
                else "Check the LTX-Video license before any commercial use."
            )


# --------------------------------------------------------------------------- #
# Text-to-video tab                                                           #
# --------------------------------------------------------------------------- #
def render_prompt_card() -> None:
    prompt = st.session_state[K_PROMPT]
    with st.container(border=True):
        kicker("01 // Prompt")
        st.text_area(
            "Describe your video",
            key=K_PROMPT,
            height=130,
            max_chars=config.MAX_PROMPT_CHARS,
            placeholder="A sports car driving through a neon city at night…",
            label_visibility="collapsed",
        )
        counter, example = st.columns([1, 2], vertical_alignment="center")
        with counter:
            st.caption(f"{len(prompt)}/{config.MAX_PROMPT_CHARS}")
        with example:
            st.selectbox(
                "Example prompts",
                [EXAMPLE_PLACEHOLDER, *config.EXAMPLE_PROMPTS],
                key=K_EXAMPLE,
                on_change=cb_pick_example,
                label_visibility="collapsed",
            )
        enhance, reset, _ = st.columns([1.4, 1, 1.6])
        with enhance:
            st.button("✨ Enhance prompt", on_click=cb_enhance_prompt, width="stretch")
        with reset:
            st.button("Reset", on_click=cb_reset_prompt, width="stretch")

        if st.session_state[W_SHOW_ENHANCED]:
            with st.expander(
                "Enhanced prompt · editable · sent to "
                + ("NVIDIA" if config.get_provider() == config.PROVIDER_NVIDIA else "Hugging Face"),
                expanded=bool(st.session_state[K_ENHANCED]),
            ):
                if st.session_state[W_DIRECTOR] and config.get_api_key():
                    st.caption(
                        "AI Director is on: a Nemotron model writes the final prompt when you "
                        "generate. This text is only the fallback."
                    )
                st.text_area(
                    "Enhanced prompt",
                    key=K_ENHANCED,
                    height=190,
                    max_chars=config.MAX_FINAL_PROMPT_CHARS,
                    placeholder="Click “Enhance prompt” to build it, or leave empty to auto-build on generate.",
                    label_visibility="collapsed",
                )
                signature = st.session_state[K_ENHANCED_SIG]
                if st.session_state[K_ENHANCED] and signature != settings_signature(
                    prompt, collect_settings()
                ):
                    st.caption("⚠ Prompt or settings changed. Click “Enhance prompt” to refresh.")


def render_story_card() -> None:
    with st.container(border=True):
        kicker("01 // Story")
        st.info(
            "Experimental: every scene is a separate clip, so characters and objects "
            "will not be perfectly consistent between clips.",
            icon="⚠️",
        )
        st.text_area(
            "Story or concept",
            key=K_STORY,
            height=110,
            max_chars=config.MAX_PROMPT_CHARS,
            placeholder="A small robot wakes in an abandoned garden, finds a glowing flower, "
            "and carries it to the city skyline at sunrise.",
            label_visibility="collapsed",
        )
        count, build = st.columns([2, 1.4], vertical_alignment="bottom")
        with count:
            st.slider("Number of scenes", config.MIN_SCENES, config.MAX_SCENES, key=K_SCENE_COUNT)
        with build:
            st.button("Build scene cards", on_click=cb_build_scenes, width="stretch")


def render_output_card() -> None:
    with st.container(border=True):
        kicker("02 // Output")
        st.selectbox(
            "Platform",
            list(config.PLATFORM_PRESETS),
            key=W_PLATFORM,
            help="Sets the video aspect ratio (16:9, 9:16 or 1:1). 21:9 is not an API option, "
            "so it only shapes the prompt.",
        )
        quality, duration = st.columns(2)
        with quality:
            st.selectbox("Quality", list(config.QUALITY_OPTIONS), key=W_QUALITY, help=config.quality_notice())
        with duration:
            st.selectbox("Duration", list(config.DURATION_OPTIONS), key=W_DURATION, help=config.duration_notice())
        if config.DURATION_OPTIONS[st.session_state[W_DURATION]] is None:
            st.slider(
                "Custom duration (seconds)",
                config.CUSTOM_DURATION_MIN,
                config.CUSTOM_DURATION_MAX,
                key=W_CUSTOM_DURATION,
            )
        plan = plan_for(collect_settings())
        chips([plan.summary])
        for note in plan.notes:
            st.caption(f"⚠ {note}")


def render_look_card() -> None:
    with st.container(border=True):
        kicker("03 // Look")
        content, style, camera, lighting = st.columns(4)
        with content:
            st.selectbox("Content type", list(config.CONTENT_TYPES), key=W_CONTENT)
        with style:
            st.selectbox("Visual style", list(config.VISUAL_STYLES), key=W_STYLE)
        with camera:
            st.selectbox("Camera", list(config.CAMERA_MOVEMENTS), key=W_CAMERA)
        with lighting:
            st.selectbox("Lighting", list(config.LIGHTING_OPTIONS), key=W_LIGHTING)


def render_studio_card() -> None:
    director = bool(st.session_state[W_DIRECTOR])
    voiceover = bool(st.session_state[W_VOICEOVER])
    with st.container(border=True):
        kicker("04 // AI studio")
        left, right = st.columns(2)
        with left:
            st.toggle(
                "AI Director (Nemotron)", key=W_DIRECTOR,
                help="A Nemotron model rewrites your idea into a detailed cinematic prompt and "
                "writes the voice-over, so the video looks YouTube-ready.",
            )  # fmt: skip
            st.selectbox(
                "Director model", list(config.LLM_MODELS), key=W_LLM_MODEL, disabled=not director,
                help="If the chosen model is unavailable, the others are tried automatically.",
            )  # fmt: skip
            if director and not config.get_api_key():
                st.warning(
                    "NVIDIA_API_KEY is not set, so the built-in prompt builder is used. "
                    "Get a free key at build.nvidia.com and add it to the app secrets."
                )
        with right:
            st.toggle(
                "AI voice-over", key=W_VOICEOVER,
                help="Adds a spoken narration and exports Full HD H.264/AAC for YouTube.",
            )  # fmt: skip
            st.selectbox("Voice", list(config.VOICES), key=W_VOICE, disabled=not voiceover)
        if voiceover and st.session_state[K_MODE] == MODE_SINGLE:
            st.text_area(
                "Narration (optional)",
                key=K_NARRATION,
                height=80,
                max_chars=400,
                placeholder="Leave empty to let the AI Director write the narration."
                if director
                else "Type the narration to be spoken over the video.",
            )
        if not audio_tools.ffmpeg_executable():
            st.warning("FFmpeg is unavailable (pip install imageio-ffmpeg): no voice-over or Full HD export.")


def render_advanced() -> None:
    with st.expander("Advanced settings", expanded=False):
        st.text_area(
            "Negative prompt",
            key=K_NEGATIVE,
            height=80,
            max_chars=config.MAX_NEGATIVE_PROMPT_CHARS,
            help="Things the model should avoid.",
        )
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.number_input("Seed (0 = random)", min_value=0, step=1, key=W_SEED)
            st.select_slider(
                "Prompt adherence", list(config.ADHERENCE_LEVELS), key=W_ADHERENCE,
                help="Sent as guidance_scale (Flexible 4, Balanced 6, Strict 7) and as prompt wording.",
            )  # fmt: skip
        with col_b:
            st.select_slider(
                "Motion intensity", list(config.MOTION_LEVELS), key=W_MOTION,
                help="Prompt wording only.",
            )  # fmt: skip
            st.select_slider(
                "Creativity", list(config.CREATIVITY_LEVELS), key=W_CREATIVITY,
                help="Prompt wording only.",
            )  # fmt: skip
        with col_c:
            st.toggle(
                "Keep original prompt", key=W_KEEP_ORIGINAL,
                help="Keeps your exact wording at the start of the enhanced prompt.",
            )  # fmt: skip
            st.toggle(
                "Show enhanced prompt", key=W_SHOW_ENHANCED,
                help="When off, the enhanced prompt is built automatically on generate.",
            )  # fmt: skip
            st.checkbox("No confidential or personal data", key=W_SAFETY)


def render_generate_bar(
    settings: GenerationSettings, requests_count: int, label: str, callback: Any, disabled: bool
) -> None:
    plan = plan_for(settings)
    chips(
        [
            settings.content_type,
            settings.style,
            settings.camera,
            plan.summary,
            f"{requests_count} API request{'s' if requests_count != 1 else ''}",
        ]
    )
    render_form_errors()
    st.button(
        label,
        type="primary",
        on_click=callback,
        disabled=st.session_state[K_BUSY] or disabled,
        width="stretch",
    )


def render_single_results() -> None:
    record = find_record(st.session_state[K_LAST_RESULT])
    if record is None:
        if not st.session_state[K_HISTORY]:
            render_empty_state(
                "Output bay empty",
                "Describe a scene and press Generate. Your video will appear here.",
            )
        return
    with st.container(border=True):
        kicker("Output")
        if show_video(record, "latest"):
            meta = record["metadata"]
            st.caption(
                f"{record['plan_summary']} · generated in {meta.get('elapsed_seconds', '?')}s · "
                f"{meta.get('size_bytes', 0) / 1_048_576:.1f} MB"
                + (f" · {meta['export']}" if meta.get("export") else "")
                + (f" · voice-over: {meta['voice']}" if meta.get("voice") else "")
                + (f" · prompt by {meta['director']}" if meta.get("director") else "")
                + (f" · {config.synthid_notice()}" if config.synthid_notice() else "")
            )
        render_youtube_package(record)


def render_storyboard_body() -> None:
    settings = collect_settings()
    built = int(st.session_state[K_SCENES_BUILT])
    if built >= config.MIN_SCENES:
        with st.container(border=True):
            kicker("04 // Scenes")
            if built != int(st.session_state[K_SCENE_COUNT]):
                st.caption("The scene count changed. Click “Build scene cards” to rebuild.")
            st.text_area(
                "Shared style prefix (added to every scene)",
                key=K_PREFIX,
                height=80,
                max_chars=config.MAX_PROMPT_CHARS,
            )
            for row_start in range(0, built, 2):
                for offset, column in enumerate(st.columns(2)):
                    index = row_start + offset
                    if index < built:
                        with column:
                            st.text_area(
                                f"Scene {index + 1}", key=scene_key(index), height=120,
                                max_chars=config.MAX_PROMPT_CHARS,
                            )  # fmt: skip
    else:
        render_empty_state(
            "No scenes yet", "Enter a story, choose the scene count and build the scene cards."
        )
    ready = built >= config.MIN_SCENES
    render_generate_bar(
        settings,
        max(built, 0),
        f"🎬 Generate {built} scenes" if ready else "🎬 Generate scenes",
        cb_generate_storyboard,
        disabled=not ready,
    )
    render_storyboard_results()


def render_storyboard_results() -> None:
    records = [r for r in map(find_record, st.session_state[K_STORY_IDS]) if r]
    if not records:
        return
    with st.container(border=True):
        kicker("Generated scenes")
        for column, record in zip(st.columns(min(len(records), 3)), records):
            with column:
                st.markdown(f"**Scene {record['scene_index']}**")
                show_video(record, "scene")
                with st.expander("Prompt"):
                    st.write(record["final_prompt"])
    render_merge_section(records)


def render_merge_section(records: list[dict[str, Any]]) -> None:
    with st.container(border=True):
        kicker("Combine clips")
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
            help=f"Max {config.MAX_AUDIO_BYTES // (1024 * 1024)} MB. Only upload audio you have rights to use.",
        )
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
                    "⬇ Export combined MP4", data=data, file_name=merged["name"],
                    mime="video/mp4", key="merged_download",
                )  # fmt: skip


def render_text_to_video_tab() -> None:
    st.radio(
        "Mode", [MODE_SINGLE, MODE_STORYBOARD], key=K_MODE, horizontal=True,
        label_visibility="collapsed", disabled=st.session_state[K_BUSY],
    )  # fmt: skip
    storyboard = st.session_state[K_MODE] == MODE_STORYBOARD
    left, right = st.columns([7, 4], gap="medium")
    with left:
        if storyboard:
            render_story_card()
        else:
            render_prompt_card()
    with right:
        render_output_card()
    render_look_card()
    render_studio_card()
    render_advanced()
    if storyboard:
        render_storyboard_body()
    else:
        render_generate_bar(collect_settings(), 1, "🎬 Generate video", cb_generate_single, False)
        render_single_results()


# --------------------------------------------------------------------------- #
# Other tabs                                                                  #
# --------------------------------------------------------------------------- #
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
                    f"{settings['platform']} · {record['plan_summary']}"
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

    tab_text, tab_video, tab_creations = st.tabs(["Text to Video", "Video to Video", "My Creations"])
    with tab_text:
        render_text_to_video_tab()
    with tab_video:
        render_empty_state(
            "Video to Video: coming soon",
            "Video input is not implemented yet, so no controls are shown.",
        )
    with tab_creations:
        render_creations_tab()

    st.markdown(
        f'<div class="cf-footer">{html.escape(config.privacy_notice())}<br>'
        f"{html.escape(config.synthid_notice())}</div>",
        unsafe_allow_html=True,
    )


main()
