"""Background generation job: live status, chapter phases and stopping."""

from __future__ import annotations

import time

from services.book_pipeline import BookPipeline
from services.image_generator import PlaceholderImageGenerator
from services.job_runner import GenerationJob

from conftest import FakeLLM


def _job(storage, book_input, phases: list[tuple[int, str]]):
    project = storage.create_project(book_input)
    BookPipeline(project, storage, llm=FakeLLM(), image_generator=PlaceholderImageGenerator()).create_plan()

    def build(progress, chapter_event, should_stop):
        def event(number, phase):
            phases.append((number, phase))
            chapter_event(number, phase)

        return BookPipeline(
            project,
            storage,
            llm=FakeLLM(),
            image_generator=PlaceholderImageGenerator(),
            progress=progress,
            chapter_event=event,
            should_stop=should_stop,
        )

    return GenerationJob(build), project


def _wait(job: GenerationJob) -> None:
    deadline = time.time() + 60
    while job.running and time.time() < deadline:
        time.sleep(0.05)
    assert not job.running


def test_job_completes_with_phases(storage, book_input):
    phases: list[tuple[int, str]] = []
    job, project = _job(storage, book_input, phases)
    job.start()
    _wait(job)
    assert job.summary is not None and job.error is None and not job.stopped
    assert project.status.stage == "completed"
    seen = {phase.split()[0] for _, phase in phases}
    assert {"writing", "testing", "illustrating", "done"} <= seen
    assert job.log_lines()


def test_job_can_be_stopped_and_continued(storage, book_input):
    job, project = _job(storage, book_input, [])
    job.request_stop()  # stop is honoured at the first step boundary
    job.start()
    _wait(job)
    assert job.stopped and job.summary is None
    assert project.status.stage == "stopped"

    resumed = GenerationJob(lambda p, c, s: BookPipeline(project, storage, llm=FakeLLM(), image_generator=PlaceholderImageGenerator(), progress=p, chapter_event=c, should_stop=s))
    resumed.start()
    _wait(resumed)
    assert project.status.stage == "completed"
