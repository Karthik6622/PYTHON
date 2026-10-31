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


def _horde(session, **settings):
    settings.setdefault("ai_horde_model", "SDXL 1.0, AlbedoBase XL 3.1, AlbedoBase XL (SDXL)")  # the SDXL path; FLUX is the default
    return AIHordeImageGenerator(ImageSettings(api_key="", ai_horde_key="horde-key", **settings), session)


def test_ai_horde_generates_image(tmp_path):
    session = _HordeSession()
    path = _horde(session).generate_image("a lantern", tmp_path / "x.webp", "portrait")
    assert path.read_bytes() == b"fake-image-bytes"
    method, url, headers, body = session.calls[0]
    assert (method, url) == ("POST", "https://aihorde.net/api/v2/generate/async")
    assert headers["apikey"] == "horde-key" and headers["Client-Agent"].startswith("AI-Book-Studio")
    assert body["prompt"] == "a lantern" and body["models"] == ["SDXL 1.0", "AlbedoBase XL 3.1", "AlbedoBase XL (SDXL)"]
    assert body["params"]["width"] == 640 and body["params"]["height"] == 896 and body["censor_nsfw"] is True
    assert all(w * h <= 774 * 774 for w, h in AIHordeImageGenerator._DIMENSIONS.values())
    assert body["params"]["steps"] == 16 and "cfg_scale" not in body["params"] and body["slow_workers"] is True  # fast-only would demand upfront kudos
    assert session.checks == 2


def test_ai_horde_flux_uses_flux_parameters(tmp_path):
    session = _HordeSession()
    settings = ImageSettings(api_key="", ai_horde_key="k", ai_horde_model="Flux.1-Schnell fp8 (Compact)", ai_horde_steps=25)
    AIHordeImageGenerator(settings, session).generate_image("p", tmp_path / "f.webp", "square")
    body = session.calls[0][3]
    assert body["models"] == ["Flux.1-Schnell fp8 (Compact)"]
    assert body["params"]["steps"] == 4 and body["params"]["cfg_scale"] == 1
    assert (body["params"]["width"], body["params"]["height"]) == (640, 640)


def test_ai_horde_defaults_to_flux_with_small_fast_images(tmp_path):
    session = _HordeSession()
    AIHordeImageGenerator(ImageSettings(api_key="", ai_horde_key="k"), session).generate_image("p", tmp_path / "d.webp", "portrait")
    params = session.calls[0][3]["params"]
    assert session.calls[0][3]["models"] == ["Flux.1-Schnell fp8 (Compact)"]
    assert (params["width"], params["height"], params["steps"]) == (576, 768, 4)


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
    _horde(session, ai_horde_fast_only=True).generate_image("p", tmp_path / "s.webp", "square")
    submitted = [call[3] for call in session.calls if call[0] == "POST"]
    assert [body["slow_workers"] for body in submitted] == [False, True]


def test_ai_horde_fast_only_needing_kudos_falls_back_to_slow_workers(tmp_path):
    class FastNeedsKudos(_HordeSession):
        def request(self, method, url, headers=None, timeout=None, json=None):
            if json is not None and url.endswith("/generate/async") and json.get("slow_workers") is False:
                self.calls.append((method, url, headers, json))
                return _Response({"message": "the client needs to already have the required kudos"}, 403)
            return super().request(method, url, headers=headers, timeout=timeout, json=json)

    session = FastNeedsKudos()
    _horde(session, ai_horde_fast_only=True).generate_image("p", tmp_path / "fk.webp", "square")
    submitted = [call[3] for call in session.calls if call[0] == "POST"]
    assert [body["slow_workers"] for body in submitted] == [False, True]


def test_ai_horde_shrinks_when_kudos_are_required(tmp_path):
    message = "for requests over 500x500 or over the applicable first-order-equivalent sampler work budget the client needs kudos."

    class KudosLimited(_HordeSession):
        def request(self, method, url, headers=None, timeout=None, json=None):
            if json is not None and url.endswith("/generate/async"):
                self.calls.append((method, url, headers, json))
                if json["params"]["width"] * json["params"]["height"] > 500 * 500:
                    return _Response({"message": message}, 403)
                return _Response({"id": "req-1"})
            return super().request(method, url, headers=headers, timeout=timeout, json=json)

    session = KudosLimited()
    generator = _horde(session)
    generator.generate_image("p", tmp_path / "k.webp", "portrait")
    sizes = [(c[3]["params"]["width"], c[3]["params"]["height"]) for c in session.calls if c[0] == "POST"]
    assert sizes[0] == (640, 896) and sizes[-1][0] * sizes[-1][1] <= 500 * 500
    assert generator._pixel_limit == 500 * 500

    later = [c for c in session.calls if c[0] == "POST"]
    generator.generate_image("p", tmp_path / "k2.webp", "portrait")
    assert len([c for c in session.calls if c[0] == "POST"]) == len(later) + 1  # learned the limit: no failed attempt


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


# ---------------------------------------------------------------- Cloudflare + fallback
class _CloudflareSession:
    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = payload if payload is not None else {"success": True, "result": {"image": "aGVsbG8="}}
        self.calls: list[tuple] = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append((url, json, headers))
        return _Response(self.payload, self.status)


def _cloudflare(session, **settings):
    from services.image_generator import CloudflareImageGenerator

    return CloudflareImageGenerator(ImageSettings(api_key="", cloudflare_account_id="acc", cloudflare_token="tok", **settings), session)


def test_cloudflare_generates_image(tmp_path):
    session = _CloudflareSession()
    path = _cloudflare(session).generate_image("a lantern", tmp_path / "c.png", "portrait")
    assert path.read_bytes() == b"hello"
    url, body, headers = session.calls[0]
    assert url.endswith("/accounts/acc/ai/run/@cf/black-forest-labs/flux-1-schnell")
    assert body == {"prompt": "a lantern", "steps": 6}  # no seed or size fields: Cloudflare rejects them
    assert headers["Authorization"] == "Bearer tok"


def test_cloudflare_limit_switches_to_ai_horde_and_skips_cloudflare_afterwards(tmp_path):
    from services.image_generator import FallbackImageGenerator

    limited = _CloudflareSession(status=429)
    horde_session = _HordeSession()
    generator = FallbackImageGenerator(_cloudflare(limited), _horde(horde_session))
    generator.generate_image("p", tmp_path / "f1.webp", "square")
    generator.generate_image("p", tmp_path / "f2.webp", "square")
    assert len(limited.calls) == 1  # second image goes straight to AI Horde
    assert len([c for c in horde_session.calls if c[0] == "POST"]) == 2


def test_cloudflare_used_first_when_available(tmp_path):
    from services.image_generator import FallbackImageGenerator

    horde_session = _HordeSession()
    FallbackImageGenerator(_cloudflare(_CloudflareSession()), _horde(horde_session)).generate_image("p", tmp_path / "g.png", "square")
    assert horde_session.calls == []


def test_provider_selection_prefers_cloudflare_with_horde_backup():
    from services.image_generator import AIHordeImageGenerator, CloudflareImageGenerator, FallbackImageGenerator, get_image_generator

    both = ImageSettings(api_key="", ai_horde_key="k", cloudflare_account_id="a", cloudflare_token="t")
    assert isinstance(get_image_generator(both), FallbackImageGenerator) and both.provider_label == "Cloudflare FLUX (AI Horde backup)"
    only_cf = ImageSettings(api_key="", cloudflare_account_id="a", cloudflare_token="t")
    assert isinstance(get_image_generator(only_cf), CloudflareImageGenerator)
    assert isinstance(get_image_generator(ImageSettings(api_key="", ai_horde_key="k")), AIHordeImageGenerator)


# --------------------------------------------------------------------------------------
# Retry when an image fails or is blurry
# --------------------------------------------------------------------------------------
class _ScriptedGenerator:
    """Returns one scripted outcome per call: 'sharp', 'blurry', 'error' or 'garbage'."""

    name = "scripted"

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.prompts: list[str] = []

    def generate_image(self, prompt, output_path, orientation):
        import random

        from PIL import Image, ImageFilter

        self.prompts.append(prompt)
        kind = self.outcomes.pop(0)
        if kind == "error":
            from utils.retry_utils import ImageGenerationError

            raise ImageGenerationError("The provider is busy.")
        if kind == "garbage":
            output_path.write_bytes(b"not an image")
            return output_path
        rng = random.Random(len(self.prompts))
        image = Image.new("RGB", (256, 256))
        image.putdata([(rng.randrange(256),) * 3 for _ in range(256 * 256)])
        if kind == "blurry":
            image = image.filter(ImageFilter.GaussianBlur(25))
        image.save(output_path, "PNG")
        return output_path


def _illustrate(generator, tmp_path, retries=2):
    from services.image_generator import generate_illustration

    return generate_illustration(generator, "a lighthouse", tmp_path / "i.png", "square", retries=retries, min_sharpness=25.0)


def test_first_good_image_is_used_without_retry(tmp_path):
    generator = _ScriptedGenerator("sharp")
    result = _illustrate(generator, tmp_path)
    assert result.attempts == 1 and not result.placeholder_used and not result.warning
    assert len(generator.prompts) == 1


def test_failed_first_image_is_retried(tmp_path):
    generator = _ScriptedGenerator("error", "sharp")
    result = _illustrate(generator, tmp_path)
    assert result.attempts == 2 and not result.placeholder_used
    assert generator.prompts[1].startswith("a lighthouse") and "sharp focus" in generator.prompts[1]


def test_blurry_image_is_retried_up_to_two_times(tmp_path):
    generator = _ScriptedGenerator("blurry", "blurry", "sharp")
    result = _illustrate(generator, tmp_path)
    assert result.attempts == 3 and not result.placeholder_used and not result.warning


def test_all_blurry_keeps_the_sharpest_not_a_placeholder(tmp_path):
    generator = _ScriptedGenerator("blurry", "blurry", "blurry")
    result = _illustrate(generator, tmp_path)
    assert not result.placeholder_used and "sharpest" in result.warning
    assert (tmp_path / "i.png").exists()


def test_placeholder_only_after_every_attempt_fails(tmp_path):
    generator = _ScriptedGenerator("error", "garbage", "error")
    result = _illustrate(generator, tmp_path)
    assert result.placeholder_used and result.attempts == 3 and "3 attempt" in result.warning


def test_zero_retries_means_one_attempt(tmp_path):
    generator = _ScriptedGenerator("error")
    result = _illustrate(generator, tmp_path, retries=0)
    assert result.placeholder_used and len(generator.prompts) == 1


def test_placeholder_provider_is_not_retried(tmp_path):
    from services.image_generator import PlaceholderImageGenerator, generate_illustration

    result = generate_illustration(PlaceholderImageGenerator(), "x", tmp_path / "p.png", "square")
    assert result.attempts == 1 and not result.placeholder_used
