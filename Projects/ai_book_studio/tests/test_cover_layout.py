from __future__ import annotations

from PIL import Image

from generators.cover_generator import compose_coloring_cover, compose_cover
from generators.cover_layout import CoverLayout, layout_from_prompt


def test_from_dict_clamps_bad_values():
    layout = CoverLayout.from_dict({"structure": "weird", "title_zone": "left", "title_scale": 9, "frame": "x", "unknown": 1})
    assert layout.structure == "bands"
    assert layout.title_zone == "top"
    assert layout.title_scale == 1.25
    assert layout.frame == "double"
    assert CoverLayout.from_dict(None).is_default


def test_different_prompts_give_different_layouts():
    calm = layout_from_prompt("a quiet misty morning lake, soft pastel watercolor", "ebook")
    dark = layout_from_prompt("a dark gothic haunted castle at midnight with ghosts", "ebook")
    assert calm.to_dict() != dark.to_dict()
    assert layout_from_prompt("a dark gothic haunted castle", "ebook") == layout_from_prompt("a dark gothic haunted castle", "ebook")


def test_dynamic_ebook_cover_renders(tmp_path):
    art = tmp_path / "art.png"
    Image.new("RGB", (800, 1200), (40, 90, 160)).save(art)
    for structure, zone in (("overlay", "center"), ("poster", "bottom"), ("overlay", "top")):
        layout = CoverLayout(structure=structure, title_zone=zone, align="left", palette="gold", frame="corners")
        out = compose_cover(art, "The Lighthouse Keeper", "A tale", "Author", tmp_path / f"{structure}{zone}.png", "English", layout)
        with Image.open(out) as image:
            assert image.size == (1024, 1536)


def test_layout_changes_the_cover_pixels(tmp_path):
    art = tmp_path / "art.png"
    Image.new("RGB", (800, 1200), (40, 90, 160)).save(art)
    classic = compose_cover(art, "Title", "", "Author", tmp_path / "a.png")
    dynamic = compose_cover(art, "Title", "", "Author", tmp_path / "b.png", layout=CoverLayout(structure="overlay", title_zone="bottom", align="right"))
    assert classic.read_bytes() != dynamic.read_bytes()


def test_default_layout_equals_classic(tmp_path):
    art = tmp_path / "art.png"
    Image.new("RGB", (800, 1200), (200, 200, 220)).save(art)
    plain = compose_cover(art, "Title", "Sub", "Author", tmp_path / "a.png")
    default = compose_cover(art, "Title", "Sub", "Author", tmp_path / "b.png", layout=CoverLayout())
    assert plain.read_bytes() == default.read_bytes()


def test_dynamic_coloring_cover_renders(tmp_path):
    for zone in ("top", "center", "bottom"):
        layout = CoverLayout(structure="overlay", title_zone=zone, palette="ice", frame="single")
        out = compose_coloring_cover(None, "Ocean Friends", "Color along", "Author", tmp_path / f"{zone}.png", badge="20 coloring pages", layout=layout)
        with Image.open(out) as image:
            assert image.size == (1275, 1650)
