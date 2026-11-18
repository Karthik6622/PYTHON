"""Background jobs: long work (discovery, AI generation, test runs) runs in a server thread, not in the browser session.

A Streamlit script stops the moment its browser tab disconnects (laptop locked, tab throttled, network blip). Jobs therefore
live here: the work runs in a daemon thread of the server process, its progress is written to the ``jobs`` table, and any
page - in this session or a new one - just reads that row. This module never imports Streamlit.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from typing import Any

from ats.errors import StudioError
from ats.logging_setup import get_logger
from ats.models import utc_now
from ats.progress import reporter
from ats.repository import Repository
from ats.security import mask

LOGGER = get_logger("jobs")
LOG_LINES = 60
TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
FLUSH_SECONDS = 0.6


class JobCancelled(Exception):
    """Raised inside the work function when the person pressed Cancel."""


class JobContext:
    """What a work function uses to report progress. Safe to call from the worker thread."""

    def __init__(self, repo: Repository, job_id: str, cancel: threading.Event) -> None:
        self.repo, self.job_id, self.cancel_event = repo, job_id, cancel
        self.fraction = 0.0
        self.message = "Starting..."
        self.log: list[str] = []
        self.started = time.time()
        self.phase_started = time.time()
        self.activity = {"reasoning": "", "content": ""}
        self.ceiling: float | None = None  # while a long model call runs the bar creeps towards this value
        self.expected_seconds = 60.0
        self._last_flush = 0.0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ reporting
    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def check(self) -> None:
        if self.cancelled:
            raise JobCancelled()

    @property
    def reporter(self):  # noqa: ANN201
        """``progress(message, fraction, ceiling)`` callable to pass to services (see ats.progress.report)."""
        return reporter(lambda message, fraction=None, ceiling=None: self.say(message, fraction, ceiling))

    def say(self, message: str, fraction: float | None = None, ceiling: float | None = None) -> None:
        """New status line. ``fraction`` (0..1) sets the bar; without it the bar creeps forward a little so it never looks frozen."""
        message = mask(str(message))[:300]
        with self._lock:
            self.ceiling = ceiling
            if message != self.message:
                self.log.append(f"{time.strftime('%H:%M:%S')}  {message}")
                self.log = self.log[-LOG_LINES:]
                self.phase_started = time.time()
            self.message = message
            if fraction is None:
                fraction = self.fraction + (0.97 - self.fraction) * 0.06
            self.fraction = min(max(self.fraction, fraction), 0.99)
        self.flush(force=True)

    def progress(self, fraction: float) -> None:
        with self._lock:
            self.fraction = min(max(self.fraction, fraction), 0.99)
        self.flush()

    def creep(self, ceiling: float, expected_seconds: float) -> None:
        """Move the bar from where it is towards ``ceiling`` while one long call runs (never reaching it)."""
        with self._lock:
            base, waited = self.fraction, time.time() - self.phase_started
        if ceiling > base:
            self.progress(base + (ceiling - base) * (1 - math.exp(-waited / max(expected_seconds, 1.0))) * 0.98)

    def on_event(self, kind: str, text: str) -> None:
        """Model stream callback (``ModelStream`` compatible): keeps the latest reasoning/content for the activity panel."""
        with self._lock:
            self.activity[kind] = (self.activity.get(kind, "") + text)[-1500:]
            ceiling = self.ceiling
        if ceiling is not None:
            self.creep(ceiling, self.expected_seconds)
        self.flush()

    def flush(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last_flush < FLUSH_SECONDS:
            return
        self._last_flush = now
        with self._lock:
            reasoning, content = self.activity["reasoning"][-500:], self.activity["content"][-500:]
            activity = (f"Reasoning: {reasoning}\n\n" if reasoning else "") + content
            fields = {"progress": self.fraction, "message": self.message, "log": list(self.log), "activity": mask(activity)}
        try:
            self.repo.update_job(self.job_id, **fields)
        except Exception:  # noqa: BLE001 - reporting must never break the work itself
            LOGGER.warning("Could not store job progress", exc_info=True)


Work = Callable[[JobContext], "dict[str, Any] | None"]


class JobManager:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        interrupted = repo.interrupt_stale_jobs()
        if interrupted:
            LOGGER.info("Marked %s job(s) left over from a previous server run as interrupted", interrupted)

    def submit(
        self, project_id: str, owner_id: str, kind: str, title: str, work: Work, *, next_page: str = "", notice: str = "", single: bool = True
    ) -> str:
        """Start ``work`` in the background and return the job id. With ``single`` an already running job of that kind is reused."""
        if single:
            for job in self.repo.active_jobs(project_id):
                if job["kind"] == kind and self.alive(job["id"]):
                    return job["id"]
        job_id = self.repo.create_job(project_id, owner_id, kind, title, next_page, notice)
        if project_id:
            self.repo.touch(project_id)  # the project in use is the one a new session opens with
        cancel = threading.Event()
        with self._lock:
            self._cancel[job_id] = cancel
        threading.Thread(target=self._run, args=(job_id, work, cancel), name=f"job-{job_id}", daemon=True).start()
        return job_id

    def alive(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancel

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            event = self._cancel.get(job_id)
        if event is None:
            return False
        event.set()
        self.repo.update_job(job_id, message="Cancelling after the current step...")
        return True

    def _run(self, job_id: str, work: Work, cancel: threading.Event) -> None:
        context = JobContext(self.repo, job_id, cancel)
        self.repo.update_job(job_id, status="running", started_at=utc_now())
        try:
            result = work(context) or {}
            if cancel.is_set():
                raise JobCancelled()
            context.say("Done", 1.0)
            context.fraction = 1.0
            self.repo.update_job(job_id, status="completed", progress=1.0, result=result, finished_at=utc_now(), message="Done")
        except JobCancelled:
            self.repo.update_job(job_id, status="cancelled", message="Cancelled.", finished_at=utc_now())
        except StudioError as exc:
            self.repo.update_job(job_id, status="failed", error=exc.user_message, message="Failed", finished_at=utc_now())
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Job %s crashed", job_id)
            self.repo.update_job(job_id, status="failed", error=f"Unexpected error: {mask(str(exc))[:200]}", message="Failed", finished_at=utc_now())
        finally:
            try:  # keep the final log and activity; status and message were already stored above
                self.repo.update_job(job_id, log=list(context.log))
            except Exception:  # noqa: BLE001
                pass
            with self._lock:
                self._cancel.pop(job_id, None)
