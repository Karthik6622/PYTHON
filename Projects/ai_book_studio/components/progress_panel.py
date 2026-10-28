"""Live generation status shared by the Plan tab, the Chapters tab and the sidebar."""

from __future__ import annotations

import streamlit as st

from components.state import current_project, image_if_exists, job_for, job_running, plan_job_here, start_generation, stop_generation
from components.styles import pill
from models.book_models import BookProject
from services.job_runner import GenerationJob
from utils.text_utils import count_words

_PHASE_TEXT = {
    "writing": "✍️ Writing",
    "testing": "🧪 Testing quality",
    "summarising": "📝 Summarising",
    "illustrating": "🖼️ Adding image",
}

# (progress fraction where the step starts, text) - must match the fractions reported by BookPipeline.create_plan
_PLAN_STEPS = (
    (0.0, "Checking your request"),
    (0.15, "Designing the chapters, themes and illustration ideas with Nemotron"),
    (0.85, "Checking and balancing the plan (chapter count, word targets, illustrations)"),
    (0.95, "Saving the plan"),
)


def stage_pill(project: BookProject) -> str:
    stage = project.status.stage
    if stage == "running" and not job_running(project):
        return pill("Interrupted - press Continue", "bad")
    mapping = {
        "new": ("Not started", "info"),
        "planned": ("Plan ready", "info"),
        "running": ("Generating...", "warn"),
        "stopped": ("Stopped - press Continue", "warn"),
        "failed": ("Stopped by an error - press Continue", "bad"),
        "completed": ("Completed", "ok"),
    }
    text, kind = mapping.get(stage, ("Unknown", "info"))
    return pill(text, kind)


def _clock(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def chapter_status(project: BookProject, job: GenerationJob | None, number: int) -> str:
    """Plain-language status of one chapter."""
    running = bool(job and job.running)
    phase = job.phase_of(number) if running and job else ""
    if phase and phase != "done":
        if phase.startswith("revising"):
            return f"🔧 Revising ({phase.split()[-1]}/2)"
        return _PHASE_TEXT.get(phase, phase)
    review = project.reviews.get(number)
    if project.chapter_done(number):
        return "✅ Passed" if review and review.passed else "⚠️ Needs attention"
    if project.chapters.get(number, "").strip():
        return "In progress"
    return "⏳ Waiting" if running else "Not started"


def chapter_rows(project: BookProject, job: GenerationJob | None) -> list[dict[str, object]]:
    plan = project.plan
    assert plan is not None
    rows = []
    for chapter in plan.chapters:
        n = chapter.chapter_number
        review = project.reviews.get(n)
        if not chapter.requires_image:
            image = "-"
        else:
            image = "Done" if image_if_exists(project, f"chapter_{n:02d}") else "Pending"
        rows.append(
            {
                "Chapter": n,
                "Title": chapter.title,
                "Status": chapter_status(project, job, n),
                "Words": count_words(project.chapters.get(n, "")),
                "Target": chapter.target_words,
                "Quality score": review.score if review else None,
                "Passed": ("Yes" if review.passed else "No") if review else "-",
                "Revisions": review.revisions if review else None,
                "Image": image,
            }
        )
    return rows


def _resume_hint(project: BookProject) -> str:
    next_chapter = next((n for n in project.chapter_numbers if not project.chapter_done(n)), None)
    return f"Continues from chapter {next_chapter}." if next_chapter else "Continues with the images and the export."


def controls(project: BookProject, where: str) -> None:
    """The one place with Start / Stop / Continue buttons."""
    job = job_for(project)
    stage = project.status.stage
    if job and job.running:
        label = "⏹ Stopping..." if job.stopping else "⏹ Stop generation"
        if st.button(label, key=f"{where}_stop", disabled=job.stopping, width="stretch"):
            stop_generation(project)
        return
    if stage == "completed":
        flagged = [n for n in project.chapter_numbers if not ((r := project.reviews.get(n)) and r.passed)]
        if not flagged:
            st.success("The book is complete and every chapter passed the quality check. Open the Preview and Export tabs.")
            return
        st.success("The book is complete. Open the Preview and Export tabs.")
        st.warning(f"{len(flagged)} chapter(s) did not pass the quality check yet.")
        if st.button(f"🔧 Fix {len(flagged)} chapter(s) that need attention", key=f"{where}_improve", type="primary", width="stretch"):
            if start_generation(project):
                st.rerun()
        return
    started = bool(project.chapters) or stage in {"running", "stopped", "failed"}
    if started:
        if stage == "failed" and project.status.error:
            st.error(f"Stopped by an error: {project.status.error}")
        elif stage == "stopped":
            st.warning("Generation was stopped. Your progress is saved.")
        elif stage == "running":
            st.warning("The previous run was interrupted (for example the server restarted). Your progress is saved.")
        st.caption(_resume_hint(project))
        label = "▶️ Continue generation"
    else:
        label = "🚀 Generate Complete Book"
    if st.button(label, key=f"{where}_start", type="primary", width="stretch"):
        if start_generation(project):
            st.rerun()


def _live_body() -> None:
    project = current_project()
    if project is None or project.plan is None:
        return
    job = job_for(project)
    running = bool(job and job.running)
    plan = project.plan
    numbers = project.chapter_numbers
    done = [n for n in numbers if project.chapter_done(n)]
    passed = [n for n in done if (r := project.reviews.get(n)) and r.passed]
    flagged = [n for n in done if n not in passed]
    images_needed = [c.chapter_number for c in plan.chapters if c.requires_image]
    images_done = [n for n in images_needed if image_if_exists(project, f"chapter_{n:02d}")]

    st.markdown(stage_pill(project), unsafe_allow_html=True)
    fraction = job.fraction if running and job else project.status.progress
    message = (job.message if running and job else project.status.message) or "Waiting to start"
    st.progress(min(max(fraction, 0.0), 1.0), text=f"{message}  ({fraction * 100:.0f}%)")
    if running and job:
        st.caption(f"Running for {_clock(job.elapsed_seconds)}. You can switch tabs or leave this page open; generation continues in the background.")

    a, b, c, d = st.columns(4)
    a.metric("Chapters written", f"{len(done)} / {len(numbers)}")
    b.metric("Quality passed", len(passed))
    c.metric("Need attention", len(flagged))
    d.metric("Images", f"{len(images_done)} / {len(images_needed)}")

    controls(project, "live")

    rows = chapter_rows(project, job)
    st.dataframe(rows, hide_index=True, width="stretch", height=min(38 * (len(rows) + 1), 480))

    if running and job:
        with st.expander("Activity log", expanded=False):
            st.code("\n".join(reversed(job.log_lines())) or "Starting...", language=None)
    elif job is not None and not getattr(job, "handled", True):
        st.rerun()  # the job just finished: refresh the whole page once


def render_live() -> None:
    """Self-refreshing status block (every 2 seconds while a job runs)."""
    project = current_project()
    interval = 2 if job_running(project) else None
    st.fragment(run_every=interval)(_live_body)()


def _plan_checklist(fraction: float, finished: bool) -> str:
    current = max(i for i, (start, _) in enumerate(_PLAN_STEPS) if fraction >= start)
    lines = []
    for i, (_, text) in enumerate(_PLAN_STEPS):
        if finished or i < current:
            mark = "✅"
        elif i == current:
            mark = "⏳"
        else:
            mark = "⬜"
        lines.append(f"{mark} {text}")
    return "\n\n".join(lines)


def _plan_live_body(job: GenerationJob) -> None:
    if not job.running and not job.handled:
        st.rerun()  # the plan job just finished: refresh the page so it can be adopted
    running = job.running
    fraction = job.estimated_fraction(0.85, 90) if running else job.fraction
    st.markdown("##### Creating the book plan")
    if running:
        st.progress(min(max(fraction, 0.0), 1.0), text=f"{job.message}  ({fraction * 100:.0f}%)")
        st.caption(f"Running for {_clock(job.elapsed_seconds)}. The chapter design step is the longest; this page updates by itself.")
    elif job.error:
        st.error(job.error)
    st.markdown(_plan_checklist(job.fraction, finished=job.plan_ready))
    if running:
        with st.expander("Activity log", expanded=False):
            st.code("\n".join(reversed(job.log_lines())) or "Starting...", language=None)


def render_plan_live(job: GenerationJob) -> None:
    """Step-by-step status for a plan being created (refreshes every 2 seconds while it runs)."""
    st.fragment(run_every=2 if job.running else None)(_plan_live_body)(job)


def _sidebar_plan_body(job: GenerationJob) -> None:
    fraction = job.estimated_fraction(0.85, 90)
    st.markdown(pill("Creating the plan...", "warn"), unsafe_allow_html=True)
    st.progress(min(max(fraction, 0.0), 1.0))
    st.caption(job.message)
    st.caption(_plan_checklist(job.fraction, finished=False).replace("\n\n", " · "))
    st.caption(f"Running for {_clock(job.elapsed_seconds)}")


def _sidebar_body() -> None:
    plan_job = plan_job_here()
    if plan_job is not None:
        if plan_job.running:
            _sidebar_plan_body(plan_job)
            return
        if not plan_job.handled:
            st.rerun()  # the plan just finished: refresh the page once so it is adopted
    project = current_project()
    if project is None:
        st.caption("No book open.")
        return
    job = job_for(project)
    running = bool(job and job.running)
    st.markdown(stage_pill(project), unsafe_allow_html=True)
    fraction = job.fraction if running and job else project.status.progress
    st.progress(min(max(fraction, 0.0), 1.0))
    message = job.message if running and job else project.status.message
    if message:
        st.caption(message)
    if project.status.total_chapters or project.plan:
        total = len(project.chapter_numbers)
        done = sum(1 for n in project.chapter_numbers if project.chapter_done(n))
        st.caption(f"Chapters complete: {done} / {total}")
    if running and job:
        st.caption(f"Running for {_clock(job.elapsed_seconds)}")
    elif project.status.stage in {"running", "stopped", "failed"}:
        st.caption("Open the Chapters tab and press Continue generation.")
        if project.status.error:
            st.error(project.status.error)
    elif job is not None and not getattr(job, "handled", True):
        st.rerun()


def render_sidebar_status() -> None:
    plan_job = plan_job_here()
    interval = 2 if (job_running(current_project()) or (plan_job is not None and plan_job.running)) else None
    st.fragment(run_every=interval)(_sidebar_body)()
