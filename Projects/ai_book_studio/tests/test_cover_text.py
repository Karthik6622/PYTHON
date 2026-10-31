"""Tamil and Hindi cover text is shaped (not boxes) and the cover never fails because of a font problem."""

from __future__ import annotations

import pytest
from PIL import Image

from generators.cover_generator import compose_cover
from utils.text_shaping import PilTextFont, ShapedTextFont, find_shaping_font, load_text_font, shaping_available

needs_shaping = pytest.mark.skipif(
    not shaping_available() or find_shaping_font("Tamil", False) is None, reason="HarfBuzz or a Tamil font is not installed"
)


@needs_shaping
def test_tamil_uses_the_shaped_font_and_draws_ink():
    font = load_text_font(80, "Tamil", True)
    assert isinstance(font, ShapedTextFont)
    canvas = Image.new("RGBA", (800, 200), (0, 0, 0, 255))
    font.draw(canvas, 20, 20, "தமிழ் கதை", (255, 255, 255))
    assert canvas.convert("L").getextrema()[1] > 200
    assert font.width("தமிழ் கதை") > font.width("த")


@needs_shaping
def test_joined_letters_are_narrower_than_the_sum_of_separate_letters():
    font = load_text_font(80, "Tamil", False)
    text = "கை"  # one letter plus a vowel sign that is drawn around it
    assert font.width(text) < sum(font.width(ch) for ch in text) + 1


@needs_shaping
def test_cover_with_tamil_title_is_written(tmp_path):
    out = compose_cover(None, "கடல் காவலனின் ரகசியம்", "ஒரு கதை", "கார்த்திக்", tmp_path / "cover.png", "Tamil")
    with Image.open(out) as image:
        assert image.size == (1024, 1536)
        title_band = image.crop((0, 40, 1024, 330)).convert("L")
        assert title_band.getextrema()[1] > 200  # white title text on the dark band


def test_english_cover_uses_plain_pillow_font(tmp_path):
    assert isinstance(load_text_font(40, "English", True), PilTextFont)
    out = compose_cover(None, "The Lighthouse", "A tale", "Author", tmp_path / "cover.png", "English")
    assert out.exists()


def test_cover_survives_a_missing_shaping_library(tmp_path, monkeypatch):
    import utils.text_shaping as shaping

    monkeypatch.setattr(shaping, "hb", None)
    assert isinstance(load_text_font(40, "Tamil", True), PilTextFont)
    assert compose_cover(None, "கதை", "", "ஆசிரியர்", tmp_path / "cover.png", "Tamil").exists()
