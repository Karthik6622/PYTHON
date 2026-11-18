"""Background jobs: they run in a server thread, report progress to the database and survive without any browser session."""

from __future__ import annotations

import threading
import time

from ats.errors import GenerationError
from ats.jobs import JobCancelled, JobManager
from ats.progress import report


def wait_for(repo, job_id: str, seconds: float = 10) -> dict:
    end = time.time() + seconds
    while time.time() < end:
        job = repo.get_job(job_id)
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_job_runs_in_the_background_and_stores_progress_and_result(repo):
    manager = JobManager(repo)
    release = threading.Event()

    def work(ctx):
        ctx.say("Step one", 0.3)
        release.wait(5)
        report(ctx.reporter, "Step two", 0.8)
        return {"count": 4}

    job_id = manager.submit("p1", "owner", "scenarios", "Designing", work, next_page="test-cases", notice="{count} done")
    time.sleep(0.4)
    running = repo.get_job(job_id)
    assert running["status"] == "running" and running["message"] == "Step one" and 0.25 <= running["progress"] <= 0.35
    assert manager.alive(job_id) and repo.active_jobs("p1")[0]["id"] == job_id
    release.set()
    done = wait_for(repo, job_id)
    assert done["status"] == "completed" and done["progress"] == 1.0 and done["result"] == {"count": 4}
    assert done["next_page"] == "test-cases" and done["notice"] == "{count} done"
    assert [line.split("  ", 1)[1] for line in done["log"]][:2] == ["Step one", "Step two"]
    assert not manager.alive(job_id)


def test_failures_are_reported_with_a_safe_message(repo):
    manager = JobManager(repo)

    def studio_error(ctx):
        raise GenerationError("The model returned nothing usable.")

    def crash(ctx):
        raise RuntimeError("boom with token ghp_exampletoken1234567890abcdef")

    first = wait_for(repo, manager.submit("p1", "owner", "scenarios", "A", studio_error))
    second = wait_for(repo, manager.submit("p1", "owner", "testcases", "B", crash))
    assert first["status"] == "failed" and first["error"] == "The model returned nothing usable."
    assert second["status"] == "failed" and second["error"].startswith("Unexpected error") and "ghp_example" not in second["error"]


def test_cancel_stops_a_job_and_single_reuses_the_running_one(repo):
    manager = JobManager(repo)
    started = threading.Event()

    def work(ctx):
        started.set()
        while not ctx.cancelled:
            time.sleep(0.02)
        raise JobCancelled()

    job_id = manager.submit("p1", "owner", "discovery", "Discovery", work)
    started.wait(5)
    assert manager.submit("p1", "owner", "discovery", "Discovery again", work) == job_id  # no duplicate run of the same kind
    assert manager.cancel(job_id) and wait_for(repo, job_id)["status"] == "cancelled"
    assert manager.cancel(job_id) is False


def test_jobs_left_by_a_dead_server_process_are_marked_interrupted(repo):
    stale = repo.create_job("p1", "owner", "execution", "Test execution")
    repo.update_job(stale, status="running")
    JobManager(repo)  # a new server process starts
    job = repo.get_job(stale)
    assert job["status"] == "interrupted" and "restarted" in job["message"]


def test_progress_creeps_but_never_reaches_the_ceiling(repo):
    manager = JobManager(repo)
    seen: list[float] = []

    def work(ctx):
        ctx.say("Long model call", 0.1, 0.9)
        for _ in range(4):
            ctx.phase_started -= 60  # pretend a minute passed
            ctx.on_event("reasoning", "thinking...")
            seen.append(ctx.fraction)
        return {}

    wait_for(repo, manager.submit("p1", "owner", "scenarios", "Creep", work))
    assert seen == sorted(seen) and 0.1 < seen[-1] < 0.9
