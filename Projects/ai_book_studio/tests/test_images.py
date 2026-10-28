"""AI Horde image provider tests with a fake HTTP session (no network)."""

from __future__ import annotations

import pytest

from config import ImageSettings
from services.image_generator import AIHordeImageGenerator
from utils.retry_utils import AIBookError


class _Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.ok = status < 400
        self.text = ""

    def json(self):
        return self._payload


class _Download:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield self.data


class _HordeSession:
    """Fakes the AI Horde queue: the first check says not done, the second says done."""

    def __init__(self, generation=None, submit_status=200, submit_payload=None):
        self.generation = generation if generation is not None else {"img": "https://cdn.example/x.webp", "censored": False}
        self.submit_status = submit_status
        self.submit_payload = submit_payload if submit_payload is not None else {"id": "req-1"}
        self.calls: list[tuple] = []
        self.checks = 0

    def request(self, method, url, headers=None, timeout=None, json=None):
        self.calls.append((method, url, headers, json))
        if url.endswith("/generate/async"):
            return _Response(self.submit_payload, self.submit_status)
        if "/generate/check/" in url:
            self.checks += 1
            return _Response({"done": self.checks >= 2, "queue_position": 3})
        return _Response({"generations": [self.generation]})

    def get(self, url, timeout=None, stream=False):
        self.calls.append(("GET-IMAGE", url, None, None))
        return _Download(b"fake-image-bytes")

    def delete(self, url, headers=None, timeout=None):
        self.calls.append(("DELETE", url, None, None))


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    monkeypatch.setattr(AIHordeImageGenerator, "_sleep", staticmethod(lambda seconds: None))


def _horde(session):
    return AIHordeImageGenerator(ImageSettings(api_key="", ai_horde_key="horde-key"), session)


def test_ai_horde_generates_image(tmp_path):
    session = _HordeSession()
    path = _horde(session).generate_image("a lantern", tmp_path / "x.webp", "portrait")
    assert path.read_bytes() == b"fake-image-bytes"
    method, url, headers, body = session.calls[0]
    assert (method, url) == ("POST", "https://aihorde.net/api/v2/generate/async")
    assert headers["apikey"] == "horde-key" and headers["Client-Agent"].startswith("AI-Book-Studio")
    assert body["prompt"] == "a lantern" and body["models"] == ["AlbedoBase XL (SDXL)", "AlbedoBase XL 3.1"]
    assert body["params"]["width"] == 640 and body["params"]["height"] == 960 and body["censor_nsfw"] is True
    assert all(w * h <= 836 * 836 for w, h in AIHordeImageGenerator._DIMENSIONS.values())
    assert body["params"]["steps"] == 20 and body["slow_workers"] is False
    assert session.checks == 2


def test_ai_horde_flux_uses_flux_parameters(tmp_path):
    session = _HordeSession()
    settings = ImageSettings(api_key="", ai_horde_key="k", ai_horde_model="Flux.1-Schnell fp8 (Compact)", ai_horde_steps=25)
    AIHordeImageGenerator(settings, session).generate_image("p", tmp_path / "f.webp", "square")
    body = session.calls[0][3]
    assert body["models"] == ["Flux.1-Schnell fp8 (Compact)"]
    assert body["params"]["steps"] == 8 and body["params"]["cfg_scale"] == 1


def test_ai_horde_falls_back_to_slow_workers(tmp_path):
    class NoFastWorkers(_HordeSession):
        def request(self, method, url, headers=None, timeout=None, json=None):
            if json is not None and url.endswith("/generate/async") and json.get("slow_workers") is False:
                self.calls.append((method, url, headers, json))
                return _Response({"id": "fast-only"})
            if url.endswith("/generate/check/fast-only"):
                return _Response({"done": False, "is_possible": False})
            return super().request(method, url, headers=headers, timeout=timeout, json=json)

    session = NoFastWorkers()
    _horde(session).generate_image("p", tmp_path / "s.webp", "square")
    submitted = [call[3] for call in session.calls if call[0] == "POST"]
    assert [body["slow_workers"] for body in submitted] == [False, True]


def test_ai_horde_settings():
    settings = ImageSettings(api_key="", ai_horde_key="k")
    assert settings.use_ai_horde and settings.configured and settings.provider_label.startswith("AI Horde")
    assert not ImageSettings(api_key="").use_ai_horde


def test_ai_horde_censored_image_is_refused(tmp_path):
    session = _HordeSession(generation={"img": "https://cdn.example/x.webp", "censored": True})
    with pytest.raises(AIBookError, match="safety filter"):
        _horde(session).generate_image("p", tmp_path / "a.webp", "square")


def test_ai_horde_rejected_key(tmp_path):
    session = _HordeSession(submit_status=401, submit_payload={"message": "bad"})
    with pytest.raises(AIBookError, match="API key"):
        _horde(session).generate_image("p", tmp_path / "b.webp", "square")
