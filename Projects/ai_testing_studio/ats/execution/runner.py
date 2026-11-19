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
HEARTBEAT_SECONDS = 15
MOBILE_DOCKER_MESSAGE = (
    "Mobile tests need the Android emulator or device attached to this machine, so they cannot run in Docker. "
    "Set the execution mode to local (EXECUTION_MODE=local or auto)."
)


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
    api_base_url: str = ""  # API projects: where the tests send requests (the application URL is used when empty)


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
        test = [sys.executable if not in_container else "python", "-m", "pytest", "-v", "--browser", PLAYWRIGHT_ENGINE.get(browser, "chromium")]
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
    elif framework in {"selenium_python", "api_python", "appium_python"}:
        if in_container:
            steps.append(["python", "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", "requirements.txt"])
        test = [sys.executable if not in_container else "python", "-m", "pytest", "-v"]
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


def _available_memory_gb() -> float | None:
    """Memory this process may still use: the container limit when there is one (Streamlit Cloud, Docker), else the machine's free memory."""
    try:
        limit = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        if limit.isdigit():
            used = int(Path("/sys/fs/cgroup/memory.current").read_text().strip())
            return max(int(limit) - used, 0) / 1024**3
    except OSError:
        pass
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024**2
    except OSError:
        pass
    if os.name == "nt":
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), *[(n, ctypes.c_ulonglong) for n in ("total", "avail", "page_total", "page_avail", "virtual_total", "virtual_avail", "extended")]]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.avail / 1024**3
    return None


def default_workers() -> int:
    """How many browsers run tests side by side. ``EXECUTION_WORKERS`` wins; otherwise about one per 0.6 GB of free memory, 1..4.

    Tests mostly wait for the application, so a few parallel browsers cut the run time several-fold even on a 2-CPU host."""
    configured = os.environ.get("EXECUTION_WORKERS", "").strip()
    if configured.isdigit() and int(configured) > 0:
        return min(int(configured), 8)
    free = _available_memory_gb()
    by_memory = int(free / 0.6) if free is not None else 3
    return max(1, min(4, by_memory, (os.cpu_count() or 2) * 2))


XDIST_FRAMEWORKS = {"playwright_python", "selenium_python"}  # their generated requirements include pytest-xdist
_XDIST_LOCAL: list[bool] = []


def xdist_available_locally() -> bool:
    if not _XDIST_LOCAL:
        probe = _run_quiet([sys.executable, "-c", "import xdist"], 30)
        _XDIST_LOCAL.append(bool(probe and probe.returncode == 0))
    return _XDIST_LOCAL[0]


def can_run_parallel(request: RunRequest) -> bool:
    """Local runs use this Python (pytest-xdist must be importable); containers install the project's own requirements, so a project
    generated before parallel runs existed (no pytest-xdist in requirements.txt) keeps running one test at a time."""
    if request.framework not in XDIST_FRAMEWORKS:
        return False
    if request.mode == "docker":
        try:
            return "pytest-xdist" in (request.workdir / "requirements.txt").read_text(encoding="utf-8")
        except OSError:
            return False
    return xdist_available_locally()


def run_env(request: RunRequest, base_url: str, api_base_url: str = "") -> dict[str, str]:
    workers = default_workers()
    env = {
        "BASE_URL": base_url, "BROWSER": request.browser, "HEADLESS": "1", "CI": "1", "PYTHONUNBUFFERED": "1",
        "IGNORE_HTTPS_ERRORS": "1" if request.ignore_https_errors else "0",
        "WORKERS": str(workers),
    }  # fmt: skip
    if workers > 1 and can_run_parallel(request):
        env["PYTEST_ADDOPTS"] = f"-n {workers}"  # pytest-xdist: one browser per worker process
    if api_base_url:
        env["API_BASE_URL"] = api_base_url
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


_MODE_CACHE: dict[str, tuple[float, str]] = {}


def resolve_mode(mode: str, framework: str = "") -> str:
    """``auto`` means Docker when its daemon answers, otherwise a local process (e.g. Streamlit Community Cloud).

    Mobile tests need the emulator/device attached to this machine, so for them ``auto`` always means local."""
    if mode != "auto":
        return mode
    if framework == "appium_python":
        return "local"
    cached = _MODE_CACHE.get("auto")
    if cached and time.time() - cached[0] < 60:
        return cached[1]
    chosen = "docker" if docker_status()[0] else "local"
    _MODE_CACHE["auto"] = (time.time(), chosen)
    return chosen


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


def docker_command(request: RunRequest, image: str, base_url: str, api_base_url: str = "") -> tuple[list[str], dict[str, str]]:
    settings = get_settings().execution
    env = run_env(request, base_url, api_base_url)
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
NODE_TOOLS = ("node", "npm", "npx")


def node_shim_dir() -> Path | None:
    """Directory that makes node / npm / npx available, or ``None`` when the system already has them (or no Node can be provided).

    Machines without Node.js (a fresh PC, Streamlit Community Cloud) use the private Node of the ``nodejs-wheel-binaries`` pip
    package: small launcher scripts in the studio's data folder put its ``node``, ``npm`` and ``npx`` on the PATH of test runs."""
    if all(shutil.which(tool) for tool in NODE_TOOLS):
        return None
    try:
        from nodejs_wheel import executable
    except ImportError:
        return None
    root = Path(executable.ROOT_DIR)
    node = root / ("node.exe" if os.name == "nt" else "bin/node")
    cli = root / "lib" / "node_modules" / "npm" / "bin"
    if not node.is_file() or not (cli / "npm-cli.js").is_file():
        return None
    shims = get_settings().data_dir / "node_shims"
    shims.mkdir(parents=True, exist_ok=True)
    launchers = {"node": f'"{node}"', "npm": f'"{node}" "{cli / "npm-cli.js"}"', "npx": f'"{node}" "{cli / "npx-cli.js"}"'}
    for tool, command in launchers.items():
        path = shims / (f"{tool}.cmd" if os.name == "nt" else tool)
        text = f"@echo off\r\n{command} %*\r\n" if os.name == "nt" else f'#!/bin/sh\nexec {command} "$@"\n'
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8", newline="")
            if os.name != "nt":
                path.chmod(0o755)
    return shims


def with_node(env: dict[str, str]) -> dict[str, str]:
    """``env`` with the private Node on the PATH when the system has none."""
    shims = node_shim_dir()
    return {**env, "PATH": str(shims) + os.pathsep + env.get("PATH", os.environ.get("PATH", ""))} if shims else env


def local_requirements(framework: str) -> str:
    """Explain what is missing for a local run, or return an empty string."""
    if framework == "api_python":
        probe = _run_quiet([sys.executable, "-c", "import pytest, httpx, jsonschema"], 30)
        if probe is None or probe.returncode != 0:
            return f"Local mode needs pytest, httpx and jsonschema installed for this Python ({sys.executable}). Run: python -m pip install pytest httpx jsonschema"
    elif framework in {"playwright_python", "selenium_python"}:
        module = "playwright" if framework == "playwright_python" else "selenium"
        probe = _run_quiet([sys.executable, "-c", f"import pytest, {module}" + (", pytest_playwright" if module == "playwright" else "")], 30)
        if probe is None or probe.returncode != 0:
            extra = "pytest-playwright" if module == "playwright" else "selenium"
            return f"Local mode needs pytest and {extra} installed for this Python ({sys.executable}). Run: python -m pip install pytest {extra}"
    elif framework == "appium_python":
        probe = _run_quiet([sys.executable, "-c", "import pytest, appium, selenium"], 30)
        if probe is None or probe.returncode != 0:
            return f"Mobile tests need pytest and the Appium Python client installed for this Python ({sys.executable}). Run: python -m pip install pytest Appium-Python-Client"
    elif framework in {"playwright_typescript", "playwright_javascript"}:
        if node_shim_dir() is None and not all(shutil.which(tool) for tool in NODE_TOOLS):
            return "Node.js is not available. Install Node.js 18+ (npm and npx on PATH), or run: python -m pip install nodejs-wheel-binaries (the studio then uses its private Node)."
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
        if request.mode == "docker" and request.framework == "appium_python":
            outcome.error = MOBILE_DOCKER_MESSAGE
            return outcome
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
            api_url = docker_base_url(request.api_base_url)[0] if request.api_base_url else ""
            argv, env = docker_command(request, outcome.image, base_url, api_url)
            process_env = {**os.environ, **env}
            cwd = None
        else:
            problem = local_requirements(request.framework)
            if problem:
                outcome.error = problem
                return outcome
            env = run_env(request, request.base_url, request.api_base_url)
            process_env = {**os.environ, **env}
            if request.framework in {"playwright_typescript", "playwright_javascript"}:
                process_env = with_node(process_env)
            cwd = str(request.workdir)
            argv = None
        phase("Running tests")
        started = time.time()
        if request.mode == "docker":
            outcome.exit_code, outcome.timed_out, outcome.cancelled = _execute(argv, process_env, cwd, request, say, cancel, docker_name=request.name)
        else:
            outcome.exit_code, outcome.timed_out, outcome.cancelled = _run_local(request, process_env, say, cancel, phase)
        say(f"Runner finished with exit code {outcome.exit_code} after {time.time() - started:.0f}s")
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Runner failed")
        outcome.error = mask(str(exc))[:400] or "The runner failed unexpectedly."
    finally:
        outcome.log = "\n".join(lines[-4000:])
    return outcome


def _step_label(step: list[str]) -> str:
    if step[:2] == ["npm", "install"]:
        return "Installing Node dependencies"
    if step[:3] == ["npx", "playwright", "install"] or step[1:4] == ["-m", "playwright", "install"]:
        return "Downloading the browser (first run only)"
    return "Running tests"


def local_plan(framework: str, browser: str, ids: list[str] | None, workdir: Path) -> list[tuple[list[str], bool]]:
    """Local run as ``(argv, required)`` pairs. Only the test step is required; a failed install is logged and the tests still run.

    Chrome and Edge use the browser already installed on this machine (a Playwright channel), so nothing is installed for them.
    The bundled engines are installed without ``--with-deps``: that needs root (sudo) and cannot work in an unattended run."""
    plan: list[tuple[list[str], bool]] = []
    if framework in {"playwright_typescript", "playwright_javascript"}:
        if not (workdir / "node_modules").exists():
            plan.append((["npm", "install", "--no-audit", "--no-fund", "--loglevel=error"], False))
        if browser not in PLAYWRIGHT_CHANNEL:
            plan.append((["npx", "playwright", "install", PLAYWRIGHT_ENGINE.get(browser, "chromium")], False))  # skips what is already present
    elif framework == "playwright_python" and browser not in PLAYWRIGHT_CHANNEL:
        plan.append(([sys.executable, "-m", "playwright", "install", PLAYWRIGHT_ENGINE.get(browser, "chromium")], False))
    plan += [(step, True) for step in command_steps(framework, browser, ids, False)]
    return plan


def _run_local(
    request: RunRequest, env: dict[str, str], say: LogCallback, cancel: threading.Event | None, phase: Callable[[str], None] | None = None
) -> tuple[int, bool, bool]:
    exit_code, timed_out, cancelled = 0, False, False
    for step, required in local_plan(request.framework, request.browser, request.test_case_ids, request.workdir):
        label = _step_label(step)
        if phase:
            phase(label)
        say(f"> {label}: {' '.join(step[:4])}")
        resolved = [shutil.which(step[0], path=env.get("PATH")) or step[0], *step[1:]]
        exit_code, timed_out, cancelled = _execute(resolved, env, str(request.workdir), request, say, cancel)
        if cancelled:
            break
        if not required:  # the test step reports the real problem, so an install failure must not hide it
            if exit_code != 0:
                say(f"{label}: install step failed (exit {exit_code}); running the tests anyway")
            continue
        if timed_out or exit_code != 0:
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
    last_output = [time.time()]

    def watch() -> None:
        began = time.time()
        while not watcher_done.wait(1.0):
            if cancel is not None and cancel.is_set():
                stop("cancelled")
                return
            if time.time() - last_output[0] >= HEARTBEAT_SECONDS:  # slow installs and browser downloads print nothing: show it is alive
                last_output[0] = time.time()
                say(f"... still working ({int(time.time() - began)}s)")

    threading.Thread(target=watch, daemon=True).start()
    try:
        assert process.stdout is not None
        for line in process.stdout:
            last_output[0] = time.time()
            if line.strip():
                say(line.rstrip())
        code = process.wait()
    finally:
        timer.cancel()
        watcher_done.set()
    return code, state["timed_out"], state["cancelled"]
