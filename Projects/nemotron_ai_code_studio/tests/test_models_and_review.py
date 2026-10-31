import json

import httpx
import pytest

from studio.config import settings
from studio.models import available_models, default_model_id, get_model
from studio.services.change_tracker import ChangeTracker
from studio.services.nvidia_service import NvidiaService


def sse(*chunks):
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})


@pytest.fixture()
def key():
    settings.set_secrets(nvidia_api_key="nvapi-test-key-abcdefghijklmnopqrstuv")
    yield
    settings.set_secrets(nvidia_api_key="")


def test_catalog_has_the_seven_models_best_coder_first():
    ids = [m.id for m in available_models()]
    assert default_model_id() in ids
    assert ids[0] == "nvidia/nemotron-3-ultra-550b-a55b"
    assert ids[:7] == [
        "nvidia/nemotron-3-ultra-550b-a55b", "deepseek-ai/deepseek-v4.1-flash", "minimaxai/minimax-m3.1-flash",
        "poolside/laguna-xs-2.1", "nvidia/nemotron-3.5-super-vl-120b-a12b", "nvidia/nemotron-3.5-lightning-30b-a3b",
        "meta/muse-glimmer-30b",
    ]


def test_extra_models_from_environment(monkeypatch):
    monkeypatch.setenv("NVIDIA_MODELS", "acme/custom-1, acme/custom-2")
    ids = [m.id for m in available_models()]
    assert "acme/custom-1" in ids and "acme/custom-2" in ids
    assert get_model("acme/unknown").id == "acme/unknown"


@pytest.mark.parametrize("model_id", [m.id for m in available_models()])
def test_request_body_uses_the_selected_model(key, model_id):
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return sse({"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]})

    async def go():
        service = NvidiaService(transport=httpx.MockTransport(handler))
        async for _ in service.stream_chat([{"role": "user", "content": "hi"}], model=model_id):
            pass

    import asyncio
    asyncio.run(go())
    assert seen["body"]["model"] == model_id
    info = get_model(model_id)
    if info.top_p is not None:
        assert seen["body"]["top_p"] == info.top_p
    for name, value in info.extra_body.items():
        assert seen["body"][name] == value


def test_keep_and_revert_single_files(active):
    tracker, ws = ChangeTracker(), active.workspace
    cid = tracker.begin()
    tracker.snapshot(cid, ws, "app/utils.py")
    tracker.snapshot(cid, ws, "brand_new.py")
    original = ws.read_text("app/utils.py")["content"]
    ws.write_text("app/utils.py", "def slugify(t):\n    return t\n")
    ws.write_text("brand_new.py", "x = 1\n")

    assert "+x = 1" in tracker.file_diff(cid, ws, "brand_new.py")
    assert tracker.revert_file(cid, ws, "brand_new.py") is True
    assert not (ws.root / "brand_new.py").exists()
    assert tracker.revert_file(cid, ws, "brand_new.py") is False

    tracker.keep_file(cid, "app/utils.py")
    assert ws.read_text("app/utils.py")["content"] != original
    assert tracker.summary(cid, ws) == []
