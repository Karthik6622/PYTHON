"""Runs book generation in a background thread so it survives Streamlit reruns and browser disconnects.

This module never imports Streamlit. The interface polls ``GenerationJob`` for live status.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable

from services.book_pipeline import BookPipeline, ChapterEventCallback, ExportSummary, GenerationStopped, ProgressCallback
from utils.retry_utils import AIBookError, redact

LOGGER = logging.getLogger("ai_book_studio.job")
PipelineFactory = Callable[[ProgressCallback, ChapterEventCallback, Callable[[], bool]], BookPipeline]


class GenerationJob:
    """One background generation run for one project."""

    def __init__(self, build: PipelineFactory) -> None:
        self._build = build
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.pipeline: BookPipeline | None = None
        self.fraction = 0.0
        self.message = "Starting..."
        self.chapter_phase: dict[int, str] = {}
        self.log: deque[str] = deque(maxlen=40)
        self.started_at = 0.0
        self.finished_at = 0.0
        self.error: str | None = None
        self.stopped = False
        self.summary: ExportSummary | None = None

    # ------------------------------------------------------------------ control
    def start(self) -> None:
        """Create the pipeline (so a missing key is reported immediately) and start the thread."""
        self.pipeline = self._build(self._on_progress, self._on_chapter, self._stop.is_set)
        _ = self.pipeline.llm
        _ = self.pipeline.images
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._run, name="book-generation", daemon=True)
        self._thread.start()

    def request_stop(self) -> None:
        self._stop.set()
        self._on_progress(self.fraction, "Stopping after the current step...")

    @property
    def project(self):
        return self.pipeline.project if self.pipeline else None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def stopping(self) -> bool:
        return self.running and self._stop.is_set()

    @property
    def elapsed_seconds(self) -> int:
        end = self.finished_at or time.time()
        return int(max(end - self.started_at, 0)) if self.started_at else 0

    # ------------------------------------------------------------------ callbacks (called from the worker thread)
    def _on_progress(self, fraction: float, message: str) -> None:
        with self._lock:
            self.fraction = fraction
            if message != self.message:
                self.log.append(f"{time.strftime('%H:%M:%S')}  {message}")
            self.message = message

    def _on_chapter(self, number: int, phase: str) -> None:
        with self._lock:
            self.chapter_phase[number] = phase

    def phase_of(self, number: int) -> str:
        with self._lock:
            return self.chapter_phase.get(number, "")

    def log_lines(self) -> list[str]:
        with self._lock:
            return list(self.log)

    def _run(self) -> None:
        assert self.pipeline is not None
        try:
            self.summary = self.pipeline.generate_complete_book()
            self._on_progress(1.0, "Your book is ready.")
        except GenerationStopped:
            self.stopped = True
            self._on_progress(self.fraction, "Stopped. Progress is saved.")
        except AIBookError as exc:
            self.error = exc.user_message
            LOGGER.warning("Background generation stopped: %s", type(exc).__name__)
        except Exception as exc:  # noqa: BLE001
            self.error = f"Generation stopped unexpectedly ({type(exc).__name__}). Your progress is saved."
            LOGGER.error("Background generation crashed: %s: %s", type(exc).__name__, redact(exc), exc_info=True)
        finally:
            self.finished_at = time.time()
