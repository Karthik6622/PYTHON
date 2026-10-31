"""Runs a generated automation project in Docker (default) or locally, streaming a masked log."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from ats.config import ROOT_DIR, get_settings
from ats.logging_setup import get_logger
from ats.security import mask

LOGGER = get_logger("runner")
RUNNERS_DIR = ROOT_DIR / "docker" / "runners"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}  # noqa: S104 - compared, never bound
ID_RE = re.compile(r"^TC_[A-Z0-9]{2,6}_\d{3}$")
DOCKERFILES = {"selenium_python": "Dockerfile.selenium-python", "selenium_java": "Dockerfile.selenium-java"}
PLAYWRIGHT_ENGINE = {"chromium": "chromium", "chrome": "chromium", "edge": "chromium", "firefox": "firefox", "webkit": "webkit"}
PLAYWRIGHT_CHANNEL = {"chrome": "chrome", "edge": "msedge"}
LogCallback = Callable[[str], None]


@dataclass
class RunRequest:
    framework: str
    browser: str
    workdir: Path
    base_url: str
    env: dict[str, str] = field(default_factory=dict, repr=False)  # includes secrets; values are never logged
    test_case_ids: list[str] | None = None
    ignore_https_errors: bool = False
    timeout: int = 1800
    mode: str = "docker"
    name: str = "ats-run"


@dataclass
class RunOutcome:
    exit_code: int = 0
    timed_out: bool = False
    cancelled: bool = False
    runner: str = ""
    image: str = ""
    error: str = ""  # infrastructure problem (Docker missing, tool missing, ...). Test failures are not errors.
    log: str = ""


# ----------------------------------------------------------------------------------------
# commands
# ----------------------------------------------------------------------------------------
def docker_base_url(url: str) -> tuple[str, bool]:
    """Containers cannot reach the host through localhost; rewrite it to ``host.docker.internal``."""
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() in LOCAL_HOSTS:
        netloc = "host.docker.internal" + (f":{parsed.port}" if parsed.port else "")
        return urlunparse(parsed._replace(netloc=netloc)), True
    return url, False


def _safe_ids(ids: list[str] | None) -> list[str]:
    return [i for i in (ids or []) if ID_RE.match(i)]


def command_steps(framework: str, browser: str, ids: list[str] | None, in_container: bool) -> list[list[str]]:
    """Ordered argv lists. The last one runs the tests; earlier ones prepare the environment."""
    ids = _safe_ids(ids)
    steps: list[list[str]] = []
    if framework == "playwright_python":
        if in_container:
            steps.append(["python", "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", "requirements.txt"])
            if browser in PLAYWRIGHT_CHANNEL:
                steps.append(["python", "-m", "playwright", "install", PLAYWRIGHT_CHANNEL[browser]])
        test = [sys.executable if not in_container else "python", "-m", "pytest", "--browser", PLAYWRIGHT_ENGINE.get(browser, "chromium")]
        if browser in PLAYWRIGHT_CHANNEL:
            test += ["--browser-channel", PLAYWRIGHT_CHANNEL[browser]]
        if ids:
            test += ["-k", " or ".join(i.lower() for i in ids)]
        steps.append(test)
    elif framework in {"playwright_typescript", "playwright_javascript"}:
        if in_container:
            steps.append(["npm", "install", "--no-audit", "--no-fund", "--loglevel=error"])
            if browser in PLAYWRIGHT_CHANNEL:
                steps.append(["npx", "playwright", "install", PLAYWRIGHT_CHANNEL[browser]])
        test = ["npx", "playwright", "test"]
        if ids:
            test += ["--grep", "|".join(ids)]
        steps.append(test)
    elif framework == "selenium_python":
        if in_container:
            steps.append(["python", "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", "requirements.txt"])
        test = [sys.executable if not in_container else "python", "-m", "pytest"]
        if ids:
            test += ["-k", " or ".join(i.lower() for i in ids)]
        steps.append(test)
    elif framework == "selenium_java":
        test = ["mvn", "-B", "-q", "test", "-Dsurefire.failIfNoSpecifiedTests=false"]
        if ids:
            test.append("-Dgroups=" + ",".join(ids))
        steps.append(test)
    else:
        raise ValueError(f"Unsupported framework: {framework}")
    return steps


def image_for(framework: str) -> str:
    images = get_settings().execution.images
    return images["playwright_node" if framework in {"playwright_typescript", "playwright_javascript"} else framework]


def run_env(request: RunRequest, base_url: str) -> dict[str, str]:
    env = {
        "BASE_URL": base_url, "BROWSER": request.browser, "HEADLESS": "1", "CI": "1", "PYTHONUNBUFFERED": "1",
        "IGNORE_HTTPS_ERRORS": "1" if request.ignore_https_errors else "0",
    }  # fmt: skip
    env.update(request.env)
    return env


# ----------------------------------------------------------------------------------------
# docker helpers
# ----------------------------------------------------------------------------------------
def _run_quiet(argv: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")  # noqa: S603
    except (OSError, subprocess.TimeoutExpired):
        return None


def docker_status() -> tuple[bool, str]:
    if not shutil.which("docker"):
        return False, "Docker is not installed or not on PATH."
    result = _run_quiet(["docker", "version", "--format", "{{.Server.Version}}"], 15)
    if result is None or result.returncode != 0:
        return False, "The Docker daemon is not running. Start Docker Desktop (or the docker service) and try again."
    return True, f"Docker {result.stdout.strip()}"


def image_present(image: str) -> bool:
    result = _run_quiet(["docker", "image", "inspect", image], 20)
    return bool(result and result.returncode == 0)


def ensure_image(framework: str, say: LogCallback) -> str:
    """Make sure the runner image exists locally (pull Microsoft images, build the Selenium images)."""
    image = image_for(framework)
    if image_present(image):
        return image
    if framework in DOCKERFILES:
        dockerfile = RUNNERS_DIR / DOCKERFILES[framework]
        say(f"Building runner image {image} (first run only, this can take several minutes)")
        _stream_to(["docker", "build", "-t", image, "-f", str(dockerfile), str(RUNNERS_DIR)], say, timeout=1800)
    else:
        say(f"Pulling runner image {image} (first run only)")
        _stream_to(["docker", "pull", image], say, timeout=1800)
    if not image_present(image):
        raise RuntimeError(f"The runner image {image} could not be prepared. See the log for details.")
    return image


def _stream_to(argv: list[str], say: LogCallback, timeout: int) -> int:
    process = subprocess.Popen(  # noqa: S603
        argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace"
    )
    timer = threading.Timer(timeout, process.kill)
    timer.start()
    try:
        assert process.stdout is not None
        for line in process.stdout:
            if line.strip():
                say(line.rstrip())
        return process.wait()
    finally:
        timer.cancel()


def docker_command(request: RunRequest, image: str, base_url: str) -> tuple[list[str], dict[str, str]]:
    settings = get_settings().execution
    env = run_env(request, base_url)
    script = " && ".join(shlex.join(step) for step in command_steps(request.framework, request.browser, request.test_case_ids, True))
    argv = [
        "docker", "run", "--rm", "--init", "--name", request.name, "--cpus", settings.docker_cpus, "--memory", settings.docker_memory,
        "--shm-size", settings.docker_shm_size, "--network", settings.docker_network, "--add-host", "host.docker.internal:host-gateway",
        "-v", f"{request.workdir.resolve()}:/work", "-w", "/work",
        "-v", "ats-npm-cache:/root/.npm", "-v", "ats-m2-cache:/root/.m2", "-v", "ats-pip-cache:/root/.cache/pip",
    ]  # fmt: skip
    for name in env:  # values are inherited from the process environment so they never appear in the argument list
        argv += ["-e", name]
    argv += [image, "sh", "-c", script]
    return argv, env


# ----------------------------------------------------------------------------------------
# local runner
# ----------------------------------------------------------------------------------------
def local_requirements(framework: str) -> str:
    """Explain what is missing for a local run, or return an empty string."""
    if framework in {"playwright_python", "selenium_python"}:
        module = "playwright" if framework == "playwright_python" else "selenium"
        probe = _run_quiet([sys.executable, "-c", f"import pytest, {module}"], 30)
        if probe is None or probe.returncode != 0:
            extra = "pytest-playwright" if module == "playwright" else "selenium"
            return f"Local mode needs pytest and {extra} installed for this Python ({sys.executable}). Run: python -m pip install pytest {extra}"
    elif framework in {"playwright_typescript", "playwright_javascript"}:
        if not shutil.which("npx") or not shutil.which("npm"):
            return "Local mode needs Node.js (npm and npx) on PATH."
    elif framework == "selenium_java" and not (shutil.which("mvn") and shutil.which("java")):
        return "Local mode needs Java 17+ and Maven (mvn) on PATH."
    return ""


def _kill_tree(process: subprocess.Popen[str]) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, timeout=15)  # noqa: S603,S607
        else:
            process.kill()
    except (OSError, subprocess.TimeoutExpired):
        pass


# ----------------------------------------------------------------------------------------
# entry point
# ----------------------------------------------------------------------------------------
def run_project(request: RunRequest, on_log: LogCallback | None = None, on_phase: Callable[[str], None] | None = None, cancel: threading.Event | None = None) -> RunOutcome:
    """Execute the project. Never raises for test failures; infrastructure problems are returned in ``error``."""
    lines: list[str] = []

    def say(text: str) -> None:
        clean = mask(text)
        lines.append(clean)
        if on_log:
            on_log(clean)

    def phase(text: str) -> None:
        if on_phase:
            on_phase(text)

    outcome = RunOutcome(runner=request.mode)
    try:
        if request.mode == "docker":
            phase("Checking Docker")
            ok, message = docker_status()
            if not ok:
                outcome.error = message
                return outcome
            phase("Preparing runner image")
            outcome.image = ensure_image(request.framework, say)
            base_url, rewritten = docker_base_url(request.base_url)
            if rewritten:
                say(f"BASE_URL points at this machine; the container will use {base_url}")
            argv, env = docker_command(request, outcome.image, base_url)
            process_env = {**os.environ, **env}
            cwd = None
        else:
            problem = local_requirements(request.framework)
            if problem:
                outcome.error = problem
                return outcome
            env = run_env(request, request.base_url)
            process_env = {**os.environ, **env}
            cwd = str(request.workdir)
            argv = None
        phase("Running tests")
        started = time.time()
        if request.mode == "docker":
            outcome.exit_code, outcome.timed_out, outcome.cancelled = _execute(argv, process_env, cwd, request, say, cancel, docker_name=request.name)
        else:
            outcome.exit_code, outcome.timed_out, outcome.cancelled = _run_local(request, process_env, say, cancel)
        say(f"Runner finished with exit code {outcome.exit_code} after {time.time() - started:.0f}s")
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Runner failed")
        outcome.error = mask(str(exc))[:400] or "The runner failed unexpectedly."
    finally:
        outcome.log = "\n".join(lines[-4000:])
    return outcome


def _run_local(request: RunRequest, env: dict[str, str], say: LogCallback, cancel: threading.Event | None) -> tuple[int, bool, bool]:
    steps = command_steps(request.framework, request.browser, request.test_case_ids, False)
    if request.framework in {"playwright_typescript", "playwright_javascript"} and not (request.workdir / "node_modules").exists():
        steps.insert(0, ["npm", "install", "--no-audit", "--no-fund", "--loglevel=error"])
    exit_code, timed_out, cancelled = 0, False, False
    for index, step in enumerate(steps):
        resolved = [shutil.which(step[0]) or step[0], *step[1:]]
        exit_code, timed_out, cancelled = _execute(resolved, env, str(request.workdir), request, say, cancel)
        if index < len(steps) - 1 and exit_code != 0:
            break
        if timed_out or cancelled:
            break
    return exit_code, timed_out, cancelled


def _execute(
    argv: list[str], env: dict[str, str], cwd: str | None, request: RunRequest, say: LogCallback, cancel: threading.Event | None, docker_name: str = ""
) -> tuple[int, bool, bool]:
    process = subprocess.Popen(  # noqa: S603 - argv list, no shell
        argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace"
    )
    state = {"timed_out": False, "cancelled": False}

    def stop(reason: str) -> None:
        state[reason] = True
        if docker_name:
            _run_quiet(["docker", "kill", docker_name], 20)
        _kill_tree(process)

    timer = threading.Timer(request.timeout, stop, args=("timed_out",))
    timer.start()
    watcher_done = threading.Event()

    def watch() -> None:
        while not watcher_done.wait(1.0):
            if cancel is not None and cancel.is_set():
                stop("cancelled")
                return

    threading.Thread(target=watch, daemon=True).start()
    try:
        assert process.stdout is not None
        for line in process.stdout:
            if line.strip():
                say(line.rstrip())
        code = process.wait()
    finally:
        timer.cancel()
        watcher_done.set()
    return code, state["timed_out"], state["cancelled"]
