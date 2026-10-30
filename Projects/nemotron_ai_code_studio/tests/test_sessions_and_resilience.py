"""Per-visitor isolation, chat persistence, model retry/fallback, undo of the last commit and GitHub device sign-in."""

import asyncio
import json
import threading

import httpx
import pytest
from git import Repo

from studio import chat_store, config
from studio.agents import coding_agent
from studio.agents.coding_agent import CodingAgent, ConversationStore
from studio.approvals import ApprovalBroker
from studio.chat import ChangeSet, ChatMessage, TextBlock, ToolCall, apply_event
from studio.config import settings
from studio.models import fallback_model
from studio.services import github_auth, repository_service
from studio.services.git_service import GitError, GitService
from studio.services.nvidia_service import NvidiaError


# ------------------------------------------------------------------ chat persistence
def test_chat_roundtrip_drops_unfinished_reply(tmp_path):
    done = ChatMessage(role="assistant", text="Done")
    done.blocks.append(TextBlock("Done"))
    done.blocks.append(ToolCall(id="t1", name="read_file", args={"path": "a.py"}, output="x", done=True))
    done.changes = ChangeSet(change_id="c1", files=[{"path": "a.py"}], diffs={"a.py": "+x"})
    messages = [ChatMessage(role="user", text="hi"), done, ChatMessage(role="user", text="more"), ChatMessage(role="assistant", streaming=True)]
    chat_store.save_chat("win12345", messages, tmp_path)
    loaded = chat_store.load_chat("win12345", tmp_path)
    assert [m.role for m in loaded] == ["user", "assistant"]  # the question that is still being answered is rebuilt from the run
    assert loaded[1].changes.diffs == {"a.py": "+x"} and loaded[1].blocks[1].name == "read_file"
    assert loaded[1].id != done.id
    assert not loaded[1].streaming


def test_chat_store_rejects_unsafe_ids(tmp_path):
    chat_store.save_chat("../evil", [ChatMessage(role="user", text="x")], tmp_path)
    assert list(tmp_path.iterdir()) == [] and chat_store.load_chat("../evil", tmp_path) == []


def test_conversation_store_survives_restart(tmp_path):
    first = ConversationStore(folder=tmp_path)
    first.add("win12345", "make a file", "done")
    second = ConversationStore(folder=tmp_path)  # a new process
    assert second.history("win12345") == [{"role": "user", "content": "make a file"}, {"role": "assistant", "content": "done"}]
    second.clear("win12345")
    assert ConversationStore(folder=tmp_path).history("win12345") == []


def test_retract_event_removes_partial_text():
    message = ChatMessage(role="assistant", streaming=True)
    apply_event(message, {"type": "token", "text": "partial"}, {})
    apply_event(message, {"type": "retract", "text": 7, "reasoning": 0}, {})
    assert message.text == "" and message.blocks == []


# ------------------------------------------------------------------ model retry and fallback
class _FakeNvidia:
    def __init__(self, script):
        self.script, self.models = list(script), []

    async def agent_chat(self, messages, schemas, model=None):
        self.models.append(model)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            yield {"type": "content", "text": "abc"}
            raise step
        yield {"type": "done", "result": step}


@pytest.fixture()
def no_sleep(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(coding_agent.asyncio, "sleep", instant)


def _turn(script):
    agent = CodingAgent(_FakeNvidia(script), ApprovalBroker())
    events = []
    run_model = {"id": "nvidia/nemotron-3-ultra-550b-a55b", "tried": set()}
    result = asyncio.run(agent._model_turn([], [], run_model, events.append))
    return agent, run_model, events, result


def test_dropped_connection_is_retried(no_sleep):
    agent, run_model, events, result = _turn([NvidiaError("dropped", 502, transient=True, partial=True), "OK"])
    assert result == "OK" and len(agent.nvidia.models) == 2 and run_model["id"] == agent.nvidia.models[0]
    assert any(e["type"] == "retract" and e["text"] == 3 for e in events)


def test_timeout_switches_to_the_next_model_with_a_notice(no_sleep):
    agent, run_model, events, result = _turn([NvidiaError("slow", 504, transient=True), "OK"])
    assert result == "OK" and run_model["id"] == fallback_model("nvidia/nemotron-3-ultra-550b-a55b").id
    assert any(e["type"] == "model" for e in events) and any(e["type"] == "notice" for e in events)


def test_permanent_error_is_not_retried(no_sleep):
    with pytest.raises(NvidiaError):
        _turn([NvidiaError("bad key", 401)])


# ------------------------------------------------------------------ undo the last commit
def _git(path):
    repo = Repo.init(path)
    (path / "a.txt").write_text("1", encoding="utf-8")
    repo.git.add("-A")
    repo.git.execute(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "first"])
    return repo, GitService(path)


def test_undo_last_commit_keeps_changes_staged(tmp_path):
    repo, git = _git(tmp_path)
    (tmp_path / "b.txt").write_text("2", encoding="utf-8")
    repo.git.add("-A")
    git.commit("second")
    assert git.last_commit()["message"] == "second"
    assert git.undo_last_commit()["message"] == "second"
    assert git.last_commit()["message"] == "first"
    assert "b.txt" in repo.git.diff("--cached", "--name-only")


def test_undo_root_commit_and_nothing_to_undo(tmp_path):
    repo, git = _git(tmp_path)
    git.undo_last_commit()
    assert git.last_commit() is None and "a.txt" in repo.git.diff("--cached", "--name-only")
    with pytest.raises(GitError):
        git.undo_last_commit()


def test_pushed_commit_cannot_be_undone(tmp_path):
    remote = tmp_path / "remote.git"
    Repo.init(remote, bare=True)
    work = tmp_path / "work"
    work.mkdir()
    repo, git = _git(work)
    repo.create_remote("origin", str(remote))
    repo.git.push("origin", "HEAD:refs/heads/main")
    repo.git.fetch("origin")
    assert git.last_commit()["pushed"] is True
    with pytest.raises(GitError):
        git.undo_last_commit()


# ------------------------------------------------------------------ one visitor never sees another's keys
def test_secrets_are_per_window_when_hosted(monkeypatch):
    monkeypatch.setattr(config, "is_hosted", lambda: True)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    alice, bob = settings.session_store("alice-window"), settings.session_store("bob-window")
    assert alice is not bob and alice is settings.session_store("alice-window")
    settings.bind_session(alice)
    settings.set_secrets(github_token="ghp_alice_token_123456")
    assert settings.github_token == "ghp_alice_token_123456"
    settings.bind_session(bob)
    assert settings.github_token == ""
    settings.bind_session(None)


def test_shared_env_token_is_ignored_when_hosted(monkeypatch):
    monkeypatch.setattr(config, "is_hosted", lambda: True)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_owner_token_123456")
    settings.bind_session(settings.session_store("visitor-1"))
    try:
        assert settings.github_token == ""
        monkeypatch.setenv("ALLOW_SHARED_GITHUB_TOKEN", "1")
        assert settings.github_token == "ghp_owner_token_123456"
    finally:
        settings.bind_session(None)


def test_run_threads_use_the_visitors_keys(monkeypatch):
    monkeypatch.setattr(config, "is_hosted", lambda: True)
    store = settings.session_store("thread-window")
    settings.bind_session(store)
    settings.set_secrets(github_token="ghp_thread_token_123456")
    seen = {}

    def worker(bound):
        settings.bind_session(bound)
        seen["token"] = settings.github_token

    thread = threading.Thread(target=worker, args=(settings.current_session(),))
    thread.start()
    thread.join()
    settings.bind_session(None)
    assert seen["token"] == "ghp_thread_token_123456"


def test_hosted_windows_get_their_own_scratch_folder(monkeypatch):
    monkeypatch.setattr(repository_service, "is_hosted", lambda: True)
    first = repository_service.repositories.open_scratch(window="winaaaaa")
    second = repository_service.repositories.open_scratch(window="winbbbbb")
    assert first.path != second.path and first.path.name == "winaaaaa"


def test_tracker_is_kept_for_the_same_window_and_folder(active):
    again = repository_service.repositories._activate(active.path, active.name)
    repository_service.repositories.adopt_tracker("winaaaaa", active)
    repository_service.repositories.adopt_tracker("winaaaaa", again)
    assert again.tracker is active.tracker


# ------------------------------------------------------------------ sign in with GitHub
def _transport(handler):
    return httpx.MockTransport(handler)


def test_device_flow_start_and_poll():
    answers = iter([{"error": "authorization_pending"}, {"error": "slow_down", "interval": 10}, {"access_token": "gho_abc"}, {"error": "access_denied"}])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/device/code"):
            return httpx.Response(200, json={"device_code": "dc", "user_code": "ABCD-1234", "verification_uri": "https://github.com/login/device", "interval": 5, "expires_in": 900})
        return httpx.Response(200, json=next(answers))

    transport = _transport(handler)
    started = github_auth.start("client", transport=transport)
    assert started["user_code"] == "ABCD-1234" and started["interval"] == 5
    assert github_auth.poll("client", "dc", transport)["status"] == "pending"
    assert github_auth.poll("client", "dc", transport) == {"status": "slow_down", "interval": 10}
    assert github_auth.poll("client", "dc", transport) == {"status": "ok", "token": "gho_abc"}
    assert github_auth.poll("client", "dc", transport)["status"] == "denied"


def test_device_flow_disabled_is_explained():
    transport = _transport(lambda request: httpx.Response(200, json={"error": "device_flow_disabled"}))
    with pytest.raises(github_auth.DeviceFlowError) as info:
        github_auth.start("client", transport=transport)
    assert "Device Flow" in info.value.message
    json.dumps(info.value.message)
