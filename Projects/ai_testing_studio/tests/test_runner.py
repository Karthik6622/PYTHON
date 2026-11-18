"""Run plans for every framework / browser combination, local and Docker. Nothing here spawns a process or touches Docker."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

import pytest

from ats.execution import runner
from ats.execution.runner import PLAYWRIGHT_CHANNEL, RunRequest, _run_local, _step_label, command_steps, docker_command, local_plan
from ats.generation.adapters.common import FRAMEWORKS, browsers_for

COMBOS = [(framework, browser) for framework in FRAMEWORKS for browser in browsers_for(framework)]
PLAYWRIGHT_JS = {"playwright_typescript", "playwright_javascript"}
ENGINES = {"chromium": "chromium", "firefox": "firefox", "webkit": "webkit", "chrome": "chromium", "edge": "chromium", "none": "chromium"}
NPM_INSTALL = ["npm", "install", "--no-audit", "--no-fund", "--loglevel=error"]


def _local_test_step(framework: str, browser: str, ids: list[str] | None = None) -> list[str]:
    """The expected local test command, written out per framework (not a copy of the runner's logic)."""
    if framework == "playwright_python":
        step = [sys.executable, "-m", "pytest", "-v", "--browser", ENGINES[browser]]
        if browser in PLAYWRIGHT_CHANNEL:
            step += ["--browser-channel", PLAYWRIGHT_CHANNEL[browser]]
        return step + (["-k", " or ".join(i.lower() for i in ids)] if ids else [])
    if framework in PLAYWRIGHT_JS:
        return ["npx", "playwright", "test"] + (["--grep", "|".join(ids)] if ids else [])
    if framework == "selenium_java":
        return ["mvn", "-B", "-q", "test", "-Dsurefire.failIfNoSpecifiedTests=false"] + (["-Dgroups=" + ",".join(ids)] if ids else [])
    return [sys.executable, "-m", "pytest", "-v"] + (["-k", " or ".join(i.lower() for i in ids)] if ids else [])  # selenium_python, api_python, appium_python


def _is_channel_install(argv: list[str]) -> bool:
    return "install" in argv and argv[-1] in PLAYWRIGHT_CHANNEL.values()


@pytest.mark.parametrize(("framework", "browser"), COMBOS)
def test_local_plan_for_every_combination(framework: str, browser: str, tmp_path: Path) -> None:
    plan = local_plan(framework, browser, None, tmp_path)  # tmp_path has no node_modules, so npm install is planned for JS/TS
    steps = [argv for argv, _ in plan]
    required = [flag for _, flag in plan]

    # only the test step (always last) is required; everything before it is an install that may fail
    assert required == [False] * (len(plan) - 1) + [True]
    assert steps[-1] == _local_test_step(framework, browser)

    # no install step ever targets a channel, uses --with-deps or needs sudo
    for argv in steps:
        assert not _is_channel_install(argv), argv
        assert "--with-deps" not in argv and "sudo" not in argv, argv

    engine_installs = [argv for argv in steps[:-1] if "playwright" in argv and "install" in argv]
    if browser in PLAYWRIGHT_CHANNEL or framework not in {"playwright_python"} | PLAYWRIGHT_JS:
        assert engine_installs == [], steps  # chrome / edge use the installed browser; Selenium and API plans install nothing
    else:
        assert len(engine_installs) == 1, steps
        expected = [sys.executable, "-m", "playwright", "install", ENGINES[browser]] if framework == "playwright_python" else ["npx", "playwright", "install", ENGINES[browser]]
        assert engine_installs[0] == expected
        assert ENGINES[browser] in {"chromium", "firefox", "webkit"}

    if framework in PLAYWRIGHT_JS:
        assert steps[0] == NPM_INSTALL


@pytest.mark.parametrize(("framework", "browser"), COMBOS)
def test_local_plan_with_test_ids(framework: str, browser: str, tmp_path: Path) -> None:
    ids = ["TC_LOG_001", "TC_LOG_002"]
    plan = local_plan(framework, browser, ids, tmp_path)
    assert plan[-1][0] == _local_test_step(framework, browser, ids)


@pytest.mark.parametrize(("framework", "browser"), COMBOS)
def test_local_plan_skips_npm_install_when_node_modules_exists(framework: str, browser: str, tmp_path: Path) -> None:
    (tmp_path / "node_modules").mkdir()
    steps = [argv for argv, _ in local_plan(framework, browser, None, tmp_path)]
    assert NPM_INSTALL not in steps


@pytest.mark.parametrize(("framework", "browser"), COMBOS)
def test_docker_plan_for_every_combination(framework: str, browser: str) -> None:
    steps = command_steps(framework, browser, None, True)
    # the Docker path is unchanged: the container runs as root, so its installs stay as they were
    container_test = [("python" if part == sys.executable else part) for part in _local_test_step(framework, browser)]
    assert steps[-1] == container_test
    assert not any(sys.executable in argv for argv in steps)

    channel = browser in PLAYWRIGHT_CHANNEL
    if framework == "playwright_python":
        assert (["python", "-m", "playwright", "install", PLAYWRIGHT_CHANNEL.get(browser, "")] in steps) is channel
    elif framework in PLAYWRIGHT_JS:
        assert steps[0] == NPM_INSTALL
        assert (["npx", "playwright", "install", PLAYWRIGHT_CHANNEL.get(browser, "")] in steps) is channel
    else:
        assert len(steps) == (2 if framework in {"selenium_python", "api_python", "appium_python"} else 1)


@pytest.mark.parametrize("framework", list(FRAMEWORKS))
def test_docker_command_runs_the_same_steps(framework: str, tmp_path: Path) -> None:
    browser = browsers_for(framework)[0]
    request = RunRequest(framework=framework, browser=browser, workdir=tmp_path, base_url="http://localhost:3000")
    argv, _ = docker_command(request, "image:tag", "http://host.docker.internal:3000")
    assert argv[-3:-1] == ["sh", "-c"]
    assert argv[-1].endswith(shlex.join(command_steps(framework, browser, None, True)[-1]))


@pytest.mark.parametrize(
    ("step", "label"),
    [
        (["npm", "install", "--no-audit"], "Installing Node dependencies"),
        (["npx", "playwright", "install", "chromium"], "Downloading the browser (first run only)"),
        ([sys.executable, "-m", "playwright", "install", "firefox"], "Downloading the browser (first run only)"),
        (["npx", "playwright", "test"], "Running tests"),
        ([sys.executable, "-m", "pytest", "-v"], "Running tests"),
    ],
)
def test_step_labels(step: list[str], label: str) -> None:
    assert _step_label(step) == label


def _request(framework: str, browser: str, workdir: Path) -> RunRequest:
    return RunRequest(framework=framework, browser=browser, workdir=workdir, base_url="http://127.0.0.1:1", timeout=60)


def test_local_run_continues_after_a_failed_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_execute(argv, env, cwd, request, say, cancel, docker_name=""):  # noqa: ANN001, ANN202
        calls.append(argv)
        return (1 if "install" in argv else 0), False, False  # every install fails, the test step passes

    monkeypatch.setattr(runner, "_execute", fake_execute)
    lines: list[str] = []
    exit_code, timed_out, cancelled = _run_local(_request("playwright_typescript", "chromium", tmp_path), {"PATH": ""}, lines.append, None)

    assert exit_code == 0 and not timed_out and not cancelled
    assert calls[-1][1:3] == ["playwright", "test"]  # the test step was executed after the failed installs
    assert len(calls) == 3  # npm install, browser install, test
    assert any("install step failed (exit 1); running the tests anyway" in line for line in lines)


def test_local_run_returns_the_test_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_execute(argv, env, cwd, request, say, cancel, docker_name=""):  # noqa: ANN001, ANN202
        calls.append(argv)
        return (1, False, False) if "pytest" in argv else (0, False, False)

    monkeypatch.setattr(runner, "_execute", fake_execute)
    exit_code, _, _ = _run_local(_request("playwright_python", "edge", tmp_path), {"PATH": ""}, lambda _line: None, None)
    assert exit_code == 1
    assert calls[-1][-2:] == ["--browser-channel", "msedge"]  # edge runs through the installed msedge channel
    assert len(calls) == 1  # no install step for edge


def test_local_run_stops_when_cancelled_during_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_execute(argv, env, cwd, request, say, cancel, docker_name=""):  # noqa: ANN001, ANN202
        calls.append(argv)
        return 1, False, True

    monkeypatch.setattr(runner, "_execute", fake_execute)
    _, _, cancelled = _run_local(_request("playwright_javascript", "webkit", tmp_path), {"PATH": ""}, lambda _line: None, None)
    assert cancelled is True
    assert len(calls) == 1
