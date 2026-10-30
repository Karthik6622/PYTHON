import subprocess

from studio.config import settings
from studio.services import terminal_service
from studio.services.terminal_hints import hint_for
from studio.services.terminal_service import TerminalService


def _captured_env(monkeypatch, tmp_path, command):
    seen = {}

    class Fake:
        stdout = None
        returncode = 0

        def __init__(self, *args, **kwargs):
            seen.update(kwargs.get("env", {}))
            raise OSError("stop here")

    monkeypatch.setattr(terminal_service.subprocess, "Popen", Fake)
    TerminalService(tmp_path).run(command)
    return seen


def test_plain_git_push_gets_the_github_token(monkeypatch, tmp_path):
    monkeypatch.setitem(settings._overrides, "github_token", "ghp_exampletoken1234567890")
    env = _captured_env(monkeypatch, tmp_path, "git push")
    assert env["GIT_CONFIG_COUNT"] == "2"
    assert env["GIT_CONFIG_KEY_1"] == "http.https://github.com/.extraheader"
    assert env["GIT_CONFIG_VALUE_1"].startswith("AUTHORIZATION: basic ")


def test_other_commands_never_get_the_token(monkeypatch, tmp_path):
    monkeypatch.setitem(settings._overrides, "github_token", "ghp_exampletoken1234567890")
    for command in ("git status", "git push && python evil.py", "python -c 'print(1)'", "git push; env"):
        assert "GIT_CONFIG_KEY_1" not in _captured_env(monkeypatch, tmp_path, command), command


def test_git_login_hint():
    out = "fatal: could not read Username for 'https://github.com': terminal prompts disabled"
    assert "Settings" in hint_for("git push", out, 128)
    assert "Settings" in hint_for("gh auth login", "/bin/sh: 1: gh: not found", 127)
