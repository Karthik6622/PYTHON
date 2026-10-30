import asyncio
import json

import httpx
import pytest

from studio.config import settings
from studio.services.nvidia_service import ChatResult, NvidiaError, NvidiaService, ToolCall, fit_messages, messages_tokens, parse_tool_arguments
from studio.tools.registry import ToolContext, execute_tool, tool_schemas


def run(coro):
    return asyncio.run(coro)


def make_ctx(active, mode="agent", approve=None):
    asked = []

    async def request(req):
        asked.append(req)
        return approve if approve is not None else False

    ctx = ToolContext(repo=active, change_id=active.tracker.begin(), mode=mode, request_approval=request)
    ctx.asked = asked
    return ctx


def call(ctx, _tool, **args):
    return run(execute_tool(ctx, _tool, args))


# ------------------------------------------------------------------ tools
def test_ask_mode_cannot_modify(active):
    ctx = make_ctx(active, "ask")
    assert {t["function"]["name"] for t in tool_schemas("ask")}.isdisjoint({"write_file", "edit_file", "delete_file", "run_command", "git_push"})
    out = call(ctx, "write_file", path="x.txt", content="x")
    assert not out.ok and "not available" in out.content
    assert not (active.path / "x.txt").exists()


def test_read_tracks_inspected_and_blocks_secrets(active):
    ctx = make_ctx(active)
    out = call(ctx, "read_file", path="app/auth.py")
    assert out.ok and "login_user" in out.content and ctx.inspected == ["app/auth.py"]
    secret = call(ctx, "read_file", path=".env")
    assert not secret.ok and "nvapi-super-secret" not in secret.content
    assert not call(ctx, "read_file", path="../outside.txt").ok
    assert not call(ctx, "read_file", path="nope.py").ok


def test_edit_file_rules(active):
    ctx = make_ctx(active)
    assert not call(ctx, "edit_file", path="app/auth.py", old_text="does not exist", new_text="x").ok
    assert "matches 2" in call(ctx, "edit_file", path="app/auth.py", old_text="bool(", new_text="bool (").content
    ok = call(ctx, "edit_file", path="app/auth.py", old_text="return bool(user) and bool(password)", new_text="return user == password")
    assert ok.ok and ctx.modified == ["app/auth.py"]
    assert "user == password" in (active.path / "app/auth.py").read_text(encoding="utf-8")
    summary = active.tracker.summary(ctx.change_id, active.workspace)
    assert summary[0]["status"] == "modified"
    active.tracker.reject(ctx.change_id, active.workspace)
    assert "bool(user)" in (active.path / "app/auth.py").read_text(encoding="utf-8")


def test_delete_needs_approval(active):
    declined = make_ctx(active, approve=False)
    out = call(declined, "delete_file", path="app/utils.py")
    assert not out.ok and out.content.startswith("DENIED") and (active.path / "app/utils.py").exists()
    assert declined.asked[0].tool == "delete_file"
    approved = make_ctx(active, approve=True)
    assert call(approved, "delete_file", path="app/utils.py").ok
    assert not (active.path / "app/utils.py").exists()
    active.tracker.reject(approved.change_id, active.workspace)
    assert (active.path / "app/utils.py").exists()


def test_commands_policy(active):
    ctx = make_ctx(active, approve=False)
    blocked = call(ctx, "run_command", command="rm -rf /")
    assert blocked.content.startswith("BLOCKED") and not ctx.asked
    install = call(ctx, "run_command", command="pip install requests")
    assert install.content.startswith("DENIED") and len(ctx.asked) == 1
    safe = call(ctx, "run_command", command="echo hello")
    assert safe.ok and "hello" in safe.content and len(ctx.asked) == 1


def test_git_actions_need_approval(active):
    ctx = make_ctx(active, approve=False)
    for name, args in [("git_commit", {"message": "x"}), ("git_push", {}), ("git_checkout", {"name": "main"}), ("git_pull", {})]:
        out = call(ctx, name, **args)
        assert out.content.startswith("DENIED"), name
    assert [r.tool for r in ctx.asked] == ["git_commit", "git_push", "git_checkout", "git_pull"]


def test_large_rewrite_needs_approval(active):
    big = "\n".join(f"line {i}" for i in range(60)) + "\n"
    (active.path / "big.txt").write_text(big, encoding="utf-8")
    ctx = make_ctx(active, approve=False)
    out = call(ctx, "write_file", path="big.txt", content="completely different\n")
    assert out.content.startswith("DENIED") and (active.path / "big.txt").read_text(encoding="utf-8") == big
    small = call(ctx, "write_file", path="big.txt", content=big + "extra\n")
    assert small.ok


def test_linter_fallback_finds_syntax_errors(active):
    ctx = make_ctx(active)
    call(ctx, "write_file", path="app/broken.py", content="def x(:\n    pass\n")
    out = call(ctx, "run_linter")
    assert "app/broken.py" in out.content and "SyntaxError" in out.content


# ------------------------------------------------------------------ nvidia service
def sse(*chunks):
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})


@pytest.fixture()
def key():
    settings.set_secrets(nvidia_api_key="nvapi-test-key-abcdefghijklmnopqrstuv")
    yield
    settings.set_secrets(nvidia_api_key="")


def collect(service, messages=None, tools=None):
    async def go():
        events = []
        async for event in service.stream_chat(messages or [{"role": "user", "content": "hi"}], tools=tools):
            events.append(event)
        return events
    return run(go())


def test_stream_text_and_tool_calls(key):
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return sse(
            {"choices": [{"delta": {"reasoning_content": "thinking"}}]},
            {"choices": [{"delta": {"content": "Hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "read_file", "arguments": "{\"path\": \"a"}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": ".py\"}"}}]}, "finish_reason": "tool_calls"}]},
        )

    events = collect(NvidiaService(transport=httpx.MockTransport(handler)), tools=tool_schemas("ask"))
    result = events[-1]["result"]
    assert [e["type"] for e in events[:3]] == ["reasoning", "content", "content"]
    assert result.content == "Hello" and result.finish_reason == "tool_calls"
    assert result.tool_calls[0].name == "read_file" and result.tool_calls[0].arguments == {"path": "a.py"}
    assert seen["auth"].startswith("Bearer nvapi-test") and seen["body"]["model"] == settings.nvidia_model and seen["body"]["stream"] is True


def test_retry_on_rate_limit_then_success(key):
    calls = []
    slept = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, json={"error": {"message": "slow down"}}) if len(calls) < 3 else sse({"choices": [{"delta": {"content": "ok"}}]})

    async def fake_sleep(seconds):
        slept.append(seconds)

    events = collect(NvidiaService(transport=httpx.MockTransport(handler), sleep=fake_sleep))
    assert events[-1]["result"].content == "ok" and len(calls) == 3 and len(slept) == 2


@pytest.mark.parametrize("status,fragment", [(401, "rejected the API key"), (404, "could not find the model"), (400, "rejected the request")])
def test_errors_are_friendly_and_not_retried(key, status, fragment):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json={"error": {"message": "bad"}})

    with pytest.raises(NvidiaError) as info:
        collect(NvidiaService(transport=httpx.MockTransport(handler)))
    assert fragment in info.value.message and len(calls) == 1


def test_missing_key_and_network_failure():
    with pytest.raises(NvidiaError) as info:
        collect(NvidiaService(transport=httpx.MockTransport(lambda r: sse())))
    assert "NVIDIA_API_KEY" in info.value.message
    settings.set_secrets(nvidia_api_key="nvapi-test-key-abcdefghijklmnopqrstuv")
    try:
        def boom(request):
            raise httpx.ConnectError("down")

        async def no_sleep(_):
            pass

        with pytest.raises(NvidiaError) as net:
            collect(NvidiaService(transport=httpx.MockTransport(boom), sleep=no_sleep))
        assert "Could not reach" in net.value.message
    finally:
        settings.set_secrets(nvidia_api_key="")


def test_tool_argument_parsing_and_context_fitting():
    assert parse_tool_arguments('{"a": 1}') == ({"a": 1}, "")
    assert parse_tool_arguments("{bad")[1] and parse_tool_arguments("[1]")[1]
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "first"}]
    for i in range(30):
        messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": f"c{i}", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]})
        messages.append({"role": "tool", "tool_call_id": f"c{i}", "content": "x" * 20_000})
    messages.append({"role": "user", "content": "latest question"})
    fitted = fit_messages(messages, limit=30_000, reserve=2_000)
    assert messages_tokens(fitted) <= 30_000
    assert fitted[0]["role"] == "system" and fitted[-1]["content"] == "latest question"
    ids = {m["tool_call_id"] for m in fitted if m["role"] == "tool"}
    called = {tc["id"] for m in fitted if m.get("tool_calls") for tc in m["tool_calls"]}
    assert ids <= called  # never an orphan tool result
