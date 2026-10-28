"""Audio tab: narrate the written book with NVIDIA Magpie TTS Zeroshot. It is separate from writing and exporting the book."""

from __future__ import annotations

import streamlit as st

from components.state import current_project, get_storage, guarded, job_running
from components.styles import pill
from config import get_tts_settings
from models.book_models import BookProject
from services.audio_book import (
    VOICE_PROMPT_NAME,
    AudiobookBuilder,
    AudioJob,
    MagpieTTS,
    audio_dir,
    build_sections,
    existing_audio,
    language_code_for,
    split_for_speech,
    validate_voice_prompt,
    voice_tag,
)
from utils.text_utils import count_words

_WORDS_PER_MINUTE = 150


@st.cache_resource
def _audio_registry() -> dict[str, AudioJob]:
    """Background audiobook jobs, outside any one session so they survive reruns and reconnects."""
    return {}


def _clock(seconds: float) -> str:
    seconds = int(seconds)
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _folder(project: BookProject):
    return audio_dir(get_storage().project_dir(project.project_id))


def _start(project: BookProject, include_front: bool, include_back: bool) -> bool:
    settings = get_tts_settings()
    code = language_code_for(project.plan.language)
    folder = _folder(project)
    prompt = folder / VOICE_PROMPT_NAME
    engine = MagpieTTS(settings, prompt)
    sections = build_sections(project, include_front, include_back)
    builder = AudiobookBuilder(
        project,
        folder,
        engine,
        code,
        sections,
        voice=voice_tag(settings.voice, prompt if prompt.exists() else None),
        workers=settings.workers,
    )
    job = AudioJob(builder)
    job.start()
    _audio_registry()[project.project_id] = job
    return True


def _live_body(job: AudioJob) -> None:
    if not job.running and not job.handled:
        st.rerun()  # finished: refresh the page once so the result is shown
    st.progress(min(max(job.fraction, 0.0), 1.0), text=f"{job.message}  ({job.fraction * 100:.0f}%)")
    st.caption(f"Running for {_clock(job.elapsed_seconds)}. You can leave this tab; narration continues in the background.")
    if job.running:
        label = "⏹ Stopping..." if job.stopping else "⏹ Stop audiobook"
        if st.button(label, key="ab_stop", disabled=job.stopping, width="stretch"):
            job.request_stop()
        with st.expander("Activity log", expanded=False):
            st.code("\n".join(reversed(job.log_lines())) or "Starting...", language=None)


def _show_result(job: AudioJob) -> None:
    job.handled = True
    if job.summary is not None:
        st.success(f"Your audiobook is ready: {len(job.summary.files)} sections, about {_clock(job.summary.seconds)} of audio.")
    elif job.stopped:
        st.warning("Audio generation was stopped. Finished sections are saved; press Continue to carry on.")
    elif job.error:
        st.error(f"{job.error} Finished sections are saved; press Continue to carry on.")


def _voice_sample_section(project: BookProject) -> None:
    folder = _folder(project)
    prompt = folder / VOICE_PROMPT_NAME
    with st.expander("Voice (optional): speak in a voice from a short sample", expanded=prompt.exists()):
        st.caption(
            "Magpie TTS Zeroshot can copy a voice from a short, clear recording of about 5 seconds "
            "(WAV, mono, 16-bit, 22.05 kHz or higher). Only use recordings of voices you have the right to use."
        )
        if prompt.exists():
            st.audio(prompt.read_bytes(), format="audio/wav")
            if st.button("Remove the voice sample", key="ab_remove_sample"):
                prompt.unlink(missing_ok=True)
                st.rerun()
        upload = st.file_uploader("Voice sample (WAV)", type=["wav"], key="up_sample")
        if upload is not None and st.button("Use this voice sample", key="ab_save_sample"):
            data = upload.getvalue()
            problem = validate_voice_prompt(data)
            if problem:
                st.error(problem)
            else:
                folder.mkdir(parents=True, exist_ok=True)
                prompt.write_bytes(data)
                st.rerun()


def _library(project: BookProject) -> None:
    files = existing_audio(_folder(project))
    if not files:
        return
    st.markdown("##### Listen and download")
    total = sum(item.seconds for item in files)
    st.caption(f"{len(files)} sections, about {_clock(total)} in total. Each section is a separate WAV file.")
    st.dataframe(
        [{"Section": item.title, "Length": _clock(item.seconds), "Size (MB)": round(item.path.stat().st_size / 1_048_576, 1)} for item in files],
        hide_index=True,
        width="stretch",
    )
    chosen = st.selectbox("Play a section", files, format_func=lambda item: item.title, key="ab_play")
    data = chosen.path.read_bytes()
    st.audio(data, format="audio/wav")
    st.download_button("⬇️ Download this section (WAV)", data, file_name=f"{chosen.key}.wav", mime="audio/wav", key=f"ab_dl_{chosen.key}")


def render() -> None:
    project = current_project()
    if project is None or project.plan is None or not project.chapters:
        st.info("Write your book first (Plan and Chapters tabs). The audiobook is narrated from the finished chapters.")
        return
    plan = project.plan
    settings = get_tts_settings()
    code = language_code_for(plan.language)
    st.subheader("Audiobook")
    st.markdown(
        '<p class="section-note">Narrates your book with NVIDIA Magpie TTS Zeroshot using your NVIDIA API key. '
        "It is separate from the PDF and DOCX export, so you can create it whenever you like.</p>",
        unsafe_allow_html=True,
    )

    job = _audio_registry().get(project.project_id)
    if job is not None and not job.running and not job.handled:
        _show_result(job)
    if job is not None and (job.running or not job.handled):
        st.fragment(run_every=2 if job.running else None)(_live_body)(job)

    if code is None:
        st.warning(f"Magpie TTS Zeroshot speaks English, Spanish and French. {plan.language} audio is not available.")
        _library(project)
        return
    if not settings.configured:
        st.markdown(pill("Speech not configured", "warn"), unsafe_allow_html=True)
        st.info(
            "Add the Magpie function id to `.streamlit/secrets.toml` as `NVIDIA_TTS_FUNCTION_ID` "
            "(build.nvidia.com, magpie-tts-zeroshot, Python example, the value after `function-id`). "
            "The same `NVIDIA_API_KEY` as the text model is used."
        )
        _library(project)
        return

    st.markdown(pill(f"Voice: {settings.voice}", "ok"), unsafe_allow_html=True)
    running = bool(job and job.running)
    if job_running(project):
        st.info("The book is still being generated. Create the audiobook when it has finished.")
        running = True

    c1, c2 = st.columns(2)
    include_front = c1.checkbox("Read the dedication, preface and introduction", value=True, key="au_front", disabled=running)
    include_back = c2.checkbox("Read the conclusion", value=True, key="au_back", disabled=running)
    sections = build_sections(project, include_front, include_back)
    words = sum(count_words(section.text) for section in sections)
    parts = sum(len(split_for_speech(section.text)) for section in sections)
    m1, m2, m3 = st.columns(3)
    m1.metric("Sections", len(sections))
    m2.metric("Words", f"{words:,}")
    m3.metric("Audio length", f"~{_clock(words / _WORDS_PER_MINUTE * 60)}")
    st.caption(f"The text is spoken in {parts:,} short parts ({settings.workers} at a time). Long books take a while; progress is saved after every section.")

    have_audio = bool(existing_audio(_folder(project)))
    label = "🎧 Continue / update audiobook" if have_audio else "🎧 Create audiobook"
    if st.button(label, type="primary", width="stretch", disabled=running or not sections, key="ab_start"):
        started = False
        with guarded("Starting the audiobook"):
            started = _start(project, include_front, include_back)
        if started:
            st.rerun()

    _voice_sample_section(project)
    _library(project)
