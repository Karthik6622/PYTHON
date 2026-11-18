"""Streamlit side of background jobs: start a job, watch its progress, follow it to the next page when it finishes."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import streamlit as st

from ats.jobs import TERMINAL, JobContext
from ats.repository import Project
from ats.services import Services
from ats.ui.session import go_to, notify, owner_id

KIND_PAGE = {
    "discovery": "discovery", "scenarios": "scenarios", "testcases": "test-cases", "automation": "automation", "github": "github",
    "execution": "execute", "analysis": "results", "reports": "reports", "api_import": "api", "mobile_analysis": "mobile",
}  # fmt: skip
STATUS_LABEL = {"queued": "Queued", "running": "Running", "completed": "Done", "failed": "Failed", "cancelled": "Cancelled", "interrupted": "Interrupted"}


def elapsed_text(job: dict[str, Any]) -> str:
    start = job.get("started_at") or job.get("created_at")
    if not start:
        return ""
    try:
        began = datetime.fromisoformat(start)
        end = datetime.fromisoformat(job["finished_at"]) if job.get("finished_at") else datetime.now(timezone.utc)
        seconds = max(int((end - began).total_seconds()), 0)
    except ValueError:
        return ""
    return f"{seconds // 60}m {seconds % 60:02d}s" if seconds >= 60 else f"{seconds}s"


def start_job(
    svc: Services, project: Project, kind: str, title: str, work: Callable[[JobContext], dict[str, Any] | None], *, next_page: str = "", notice: str = ""
) -> None:
    """Run ``work`` in the background (it survives closing the browser) and show its progress."""
    svc.jobs.submit(project.id, owner_id(), kind, title, work, next_page=next_page, notice=notice)
    st.rerun()


def active_job(svc: Services, project_id: str, kinds: tuple[str, ...] | None = None) -> dict[str, Any] | None:
    for job in svc.repo.active_jobs(project_id):
        if (kinds is None or job["kind"] in kinds) and svc.jobs.alive(job["id"]):
            return job
    return None


def card(job: dict[str, Any], key: str) -> None:
    """One job: title, big progress bar, elapsed time and status line."""
    percent = int(max(0.0, min(float(job["progress"]), 1.0)) * 100)
    state = job["status"]
    colour = {"running": "blue", "queued": "gray", "completed": "green", "failed": "red", "cancelled": "gray", "interrupted": "orange"}.get(state, "gray")
    st.markdown(f"**{job['title']}** :{colour}-badge[{STATUS_LABEL.get(state, state)}] <span class='ats-card-meta'>{elapsed_text(job)}</span>", unsafe_allow_html=True)
    st.progress(float(job["progress"]), text=f"{percent}%  |  {job['message'] or 'Working...'}")


@st.fragment(run_every="1.5s")
def watch(svc: Services, job_id: str) -> None:
    """Live view of one job. Polls the database, so it also works after a reconnect or in a different browser tab."""
    job = svc.repo.get_job(job_id)
    if job is None:
        return
    if job["status"] in TERMINAL:
        st.session_state["_finished_job"] = job_id
        st.rerun()
    with st.container(border=True):
        card(job, job_id)
        st.caption("This keeps running on the server if you close the tab, lock the screen or lose the connection. Come back any time.")
        left, right = st.columns([3, 1])
        with left.expander("Live log", expanded=False):
            st.code("\n".join(job["log"][-14:]) or "Starting...", language="text")
        if job["activity"]:
            with left.expander("AI model activity", expanded=False):
                st.code(job["activity"][-900:], language="text")
        if right.button("Cancel", key=f"cancel_{job_id}", width="stretch"):
            svc.jobs.cancel(job_id)


def running_panel(svc: Services, project: Project, kinds: tuple[str, ...], heading: str = "In progress") -> bool:
    """Show the live view when a job of these kinds is running. Returns True so the page can skip its own controls."""
    job = active_job(svc, project.id, kinds)
    if job is None:
        return False
    st.subheader(heading)
    watch(svc, job["id"])
    return True


def last_problem(svc: Services, project: Project, kinds: tuple[str, ...]) -> None:
    """Explain the most recent job of these kinds when it failed or was interrupted (until a newer one succeeds)."""
    for job in svc.repo.list_jobs(project.id, kinds, limit=5):
        if job["status"] in {"failed", "interrupted"}:
            st.error(f"{job['title']}: {job['error'] or job['message']}")
        if job["status"] in {"failed", "interrupted", "completed", "running", "queued"}:
            break


def follow_finished(svc: Services) -> None:
    """Call once per run, before the page: when a job this session was watching has just finished, report it and move on."""
    job_id = st.session_state.pop("_finished_job", None)
    if not job_id:
        return
    job = svc.repo.get_job(job_id)
    if job is None:
        return
    if job["status"] == "completed":
        notice = job["notice"] or f"{job['title']} finished."
        try:
            notice = notice.format(**job["result"])
        except (KeyError, IndexError, ValueError):
            pass
        notify(notice)
        if job["next_page"]:
            go_to(job["next_page"])
    elif job["status"] == "cancelled":
        notify(f"{job['title']} was cancelled.", "warning")
    else:
        notify(f"{job['title']} did not finish: {job['error'] or job['message']}", "error")


@st.fragment(run_every="3s")
def sidebar_activity(svc: Services, project_id: str) -> None:
    """Small progress bars for everything running in this project, visible from every page."""
    jobs = [j for j in svc.repo.active_jobs(project_id) if svc.jobs.alive(j["id"])]
    if not jobs:
        return
    st.markdown('<div class="ats-card-meta">RUNNING IN THE BACKGROUND</div>', unsafe_allow_html=True)
    for job in jobs:
        st.progress(float(job["progress"]), text=f"{job['title']} ({int(float(job['progress']) * 100)}%)")
        if st.button("Open", key=f"open_job_{job['id']}", width="stretch"):
            go_to(KIND_PAGE.get(job["kind"], "projects"))
