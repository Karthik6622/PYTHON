import os
import subprocess

from git import Repo

from studio.config import settings
from studio.services import terminal_service
from studio.services.git_service import auth_env
from studio.services.terminal_hints import hint_for
from studio.services.terminal_service import TerminalService, quote_python_script_path


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
    monkeypatch.setenv("STUDIO_HOSTED", "1")
    Repo.init(tmp_path)
    env = _captured_env(monkeypatch, tmp_path, "git push")
    assert env["GIT_CONFIG_COUNT"] == "4"
    assert env["GIT_CONFIG_KEY_1"] == "url.https://github.com/.insteadOf"
    assert env["GIT_CONFIG_VALUE_1"] == "git@github.com:"
    assert env["GIT_CONFIG_VALUE_2"] == "ssh://git@github.com/"
    assert env["GIT_CONFIG_KEY_3"] == "http.https://github.com/.extraheader"
    assert env["GIT_CONFIG_VALUE_3"].startswith("AUTHORIZATION: basic ")


def test_other_commands_never_get_the_token(monkeypatch, tmp_path):
    monkeypatch.setitem(settings._overrides, "github_token", "ghp_exampletoken1234567890")
    for command in ("git status", "git push", "git push && python evil.py", "python -c 'print(1)'", "git push; env"):
        assert "GIT_CONFIG_KEY_1" not in _captured_env(monkeypatch, tmp_path, command), command


def test_ssh_rewrite_uses_token_or_hosted_mode(monkeypatch):
    monkeypatch.setenv("STUDIO_HOSTED", "0")
    local = auth_env("ghp_exampletoken1234567890")
    assert local["GIT_CONFIG_COUNT"] == "3"
    assert local["GIT_CONFIG_VALUE_0"] == "git@github.com:"
    assert local["GIT_CONFIG_VALUE_1"] == "ssh://git@github.com/"
    assert local["GIT_CONFIG_KEY_2"] == "http.https://github.com/.extraheader"

    monkeypatch.setenv("STUDIO_HOSTED", "1")
    hosted = auth_env("ghp_exampletoken1234567890")
    assert hosted["GIT_CONFIG_COUNT"] == "3"
    assert hosted["GIT_CONFIG_VALUE_0"] == "git@github.com:"
    assert hosted["GIT_CONFIG_VALUE_1"] == "ssh://git@github.com/"

    monkeypatch.setenv("STUDIO_HOSTED", "0")
    without_token = auth_env("")
    assert "GIT_CONFIG_COUNT" not in without_token


def test_connected_token_rewrites_github_ssh_remote_to_https(monkeypatch, tmp_path):
    monkeypatch.setenv("STUDIO_HOSTED", "0")
    monkeypatch.setitem(settings._overrides, "github_token", "ghp_exampletoken1234567890")
    local_repo = Repo.init(tmp_path)
    local_repo.create_remote("origin", "git@github.com:owner/repo.git")
    env = os.environ.copy()
    env.update(auth_env())

    result = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=tmp_path, env=env, capture_output=True, text=True, check=True,
    )

    assert result.stdout.strip() == "https://github.com/owner/repo.git"


def test_git_login_hint():
    out = "fatal: could not read Username for 'https://github.com': terminal prompts disabled"
    assert "top bar" in hint_for("git push", out, 128)
    assert "top bar" in hint_for("gh auth login", "/bin/sh: 1: gh: not found", 127)


def test_ssh_host_key_hint_recommends_token_without_disabling_verification():
    hint = hint_for("git pull", "Host key verification failed. fatal: Could not read from remote repository.", 128)
    assert "Connect GitHub" in hint and "known_hosts" in hint and "not disabled" in hint


def test_python_command_quotes_an_existing_script_path_with_spaces(tmp_path):
    script = tmp_path / "test calculator.py"
    script.write_text("print('ok')", encoding="utf-8")
    assert quote_python_script_path("python test calculator.py", tmp_path, tmp_path) == 'python "test calculator.py"'
    assert quote_python_script_path("python test calculator.py --verbose", tmp_path, tmp_path) == "python test calculator.py --verbose"


def test_python_command_does_not_quote_ambiguous_or_shell_syntax(tmp_path):
    (tmp_path / "test").write_text("", encoding="utf-8")
    assert quote_python_script_path("python test calculator.py", tmp_path, tmp_path) == "python test calculator.py"
    assert quote_python_script_path("python test calculator.py && echo done", tmp_path, tmp_path) == "python test calculator.py && echo done"
