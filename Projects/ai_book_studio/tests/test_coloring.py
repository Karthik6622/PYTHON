"""Coloring books: input checks, planning, line art, pages, covers and exports. No network and no real model."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from PIL import Image

from config import COLORING_PAGE_SIZE, COMPLEXITY_EASY, COMPLEXITY_HARD, COMPLEXITY_MEDIUM, LAYOUT_PAGE_ONLY, LAYOUT_PAGE_WITH_ICON
from models.book_models import BookInput
from prompts.coloring_prompts import detail_for, page_prompt
from services.book_pipeline import BookPipeline
from services.coloring_book import generate_coloring_plan, line_key, page_key
from services.image_generator import ImageGenerator, PlaceholderImageGenerator
from services.nvidia_client import ChatResult
from utils.coloring_utils import colorize, compose_page, hollow_solid_areas, ink_ratio, is_usable_line_art, make_line_art_placeholder, to_line_art
from utils.proofread import autocorrect_text, proofread_issues
from utils.retry_utils import AIBookError
from utils.validation_utils import validate_book_input


def _scenes(count: int) -> list[dict[str, str]]:
    return [{"title": f"Dino {i}", "scene": f"A friendly dinosaur number {i} in a jungle"} for i in range(1, count + 1)]


class ColoringLLM:
    """Plans a coloring book; ``give`` pages are returned in the first reply and the rest by follow-up requests."""

    def __init__(self, give: int | None = None, title: str = "Dino Friends") -> None:
        self.give = give
        self.title = title
        self.calls: list[str] = []

    def generate(self, prompt: str, preset: Any, max_tokens: int | None = None) -> ChatResult:
        raise AssertionError("coloring books must not need free text")

    def generate_text(self, prompt: str, preset: Any, max_tokens: int | None = None) -> str:
        return self.generate(prompt, preset, max_tokens).text

    def generate_json(self, prompt: str, preset: Any, max_tokens: int | None = None, validator: Any = None) -> Any:
        name = preset if isinstance(preset, str) else preset.name
        assert name == "planning"
        self.calls.append(prompt[:40])
        if "COLORING BOOK" in prompt:
            wanted = int(prompt.split("NUMBER OF COLORING PAGES:")[1].split()[0])
            count = min(self.give or wanted, wanted)
            data = {"title": self.title, "subtitle": "Color the jungle", "description": "Big friendly dinosaurs.", "cover_concept": "Dinosaurs in a sunny jungle", "pages": _scenes(count)}
        else:  # follow-up request for more scenes
            count = int(prompt.split("Write ")[1].split()[0])
            start = 100 + len(self.calls) * 100
            data = {"pages": [{"title": f"More {start + i}", "scene": f"A different dinosaur scene {start + i}"} for i in range(count)]}
        data = json.loads(json.dumps(data))
        return validator(data) if validator else data


def _input(pages: int = 4, layout: str = LAYOUT_PAGE_ONLY, **extra: Any) -> BookInput:
    return BookInput(book_format="coloring_book", book_idea="Friendly dinosaurs in a jungle", coloring_pages=pages, coloring_layout=layout, **extra)


def _pipeline(storage, book_input: BookInput, llm=None, images: ImageGenerator | None = None) -> BookPipeline:
    project = storage.create_project(book_input)
    return BookPipeline(project, storage, llm=llm or ColoringLLM(), image_generator=images or PlaceholderImageGenerator())


# --------------------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------------------
def test_coloring_form_needs_only_a_prompt_and_pages() -> None:
    assert validate_book_input(_input()) == []  # no author, no 20-character idea, no writing style
    assert validate_book_input(BookInput(book_format="coloring_book", book_idea="  ")) != []
    assert BookInput(book_format="coloring_book", coloring_pages=9999).coloring_pages == 100
    assert BookInput(book_format="nonsense").book_format == "ebook"
    assert BookInput().is_coloring is False  # the eBook stays the default


def test_ebook_validation_is_unchanged() -> None:
    assert any("author" in problem.lower() for problem in validate_book_input(BookInput(book_idea="A lighthouse keeper protects a village.")))


# --------------------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------------------
def test_plan_has_the_requested_number_of_pages_and_cover_scene() -> None:
    plan = generate_coloring_plan(ColoringLLM(), _input(pages=6))
    assert len(plan.chapters) == 6 and [c.chapter_number for c in plan.chapters] == list(range(1, 7))
    assert plan.title == "Dino Friends" and plan.cover_concept and plan.book_type == "Coloring book"
    assert all(c.image_concept and c.requires_image for c in plan.chapters)


def test_short_reply_is_topped_up_with_follow_up_requests() -> None:
    llm = ColoringLLM(give=3)
    plan = generate_coloring_plan(llm, _input(pages=8))
    assert len(plan.chapters) == 8 and len(llm.calls) >= 2
    assert len({c.title for c in plan.chapters}) == 8


def test_garbled_model_title_is_replaced() -> None:
    plan = generate_coloring_plan(ColoringLLM(title="Dinooooo Frxxxxxnds"), _input(pages=4))
    assert "ooooo" not in plan.title and plan.title.endswith("Coloring Book")


def test_preferred_title_wins() -> None:
    plan = generate_coloring_plan(ColoringLLM(), _input(pages=4, preferred_title="My Dino Book"))
    assert plan.title == "My Dino Book"


def test_pipeline_create_plan_saves_a_planned_coloring_project(storage) -> None:
    pipeline = _pipeline(storage, _input())
    pipeline.create_plan()
    loaded = storage.load_project(pipeline.project.project_id)
    assert loaded.status.stage == "planned" and loaded.book_input.is_coloring and len(loaded.plan.chapters) == 4


# --------------------------------------------------------------------------------------
# Line art, preview and page
# --------------------------------------------------------------------------------------
def _grey_drawing() -> Image.Image:
    """A shaded picture with a light-grey background, like a model often returns."""
    image = Image.new("RGB", (300, 400), (235, 235, 235))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    for row in range(4):
        for column in range(3):
            x, y = 55 + column * 95, 55 + row * 95
            draw.ellipse((x - 38, y - 38, x + 38, y + 38), outline=(20, 20, 20), width=5, fill=(200, 200, 200))
    return image


def test_line_art_is_pure_black_and_white() -> None:
    art = to_line_art(_grey_drawing(), (600, 800))
    assert art.mode == "L" and art.size == (600, 800)
    assert {value for value, count in enumerate(art.histogram()) if count} <= {0, 255}
    assert is_usable_line_art(art)[0]
    assert not is_usable_line_art(Image.new("L", (100, 100), 255))[0]  # blank
    assert not is_usable_line_art(Image.new("L", (100, 100), 0))[0]  # solid black


def test_colored_preview_is_the_same_picture_in_color() -> None:
    art = to_line_art(_grey_drawing(), (600, 800))
    icon = colorize(art, 200)
    assert icon.mode == "RGB" and icon.size == (200, 267)
    colors = {color for _, color in icon.getcolors(maxcolors=1000)}
    assert len(colors) >= 3  # outlines, paper and at least one filled area
    # Wherever the preview is dark, the line art has a line (same picture, not a different one).
    small = art.resize(icon.size, Image.Resampling.BOX)
    dark_in_icon = sum(1 for x in range(0, 200, 7) for y in range(0, 267, 7) if sum(icon.getpixel((x, y))) < 150)
    dark_in_art = sum(1 for x in range(0, 200, 7) for y in range(0, 267, 7) if small.getpixel((x, y)) < 160)
    assert dark_in_icon > 0 and dark_in_art > 0


def _has_color(image: Image.Image) -> bool:
    data = image.convert("RGB").tobytes()
    return any(data[i] != data[i + 1] or data[i + 1] != data[i + 2] for i in range(0, len(data), 3))


def test_pages_are_print_size_and_the_icon_layout_adds_a_colored_preview_top_left() -> None:
    art = make_line_art_placeholder((1024, 1024), "x")
    plain = compose_page(art)
    with_icon = compose_page(art, with_icon=True, seed="x")
    assert plain.size == with_icon.size == COLORING_PAGE_SIZE
    assert not _has_color(plain)  # black, white and grey only
    assert _has_color(with_icon.crop((80, 80, 360, 360)))  # the preview sits in the top-left corner
    assert not _has_color(with_icon.crop((400, 60, 1275, 380)))  # nothing colored to its right
    assert not _has_color(with_icon.crop((0, 420, 1275, 1650)))  # the drawing stays black and white


def test_drawn_fallback_is_a_usable_coloring_page() -> None:
    art = make_line_art_placeholder((768, 1152), "a prompt")
    assert is_usable_line_art(art)[0] and 0.015 < ink_ratio(art) < 0.42


@pytest.mark.parametrize("level", [COMPLEXITY_EASY, COMPLEXITY_MEDIUM, COMPLEXITY_HARD])
def test_drawn_fallback_suits_every_complexity(level) -> None:
    art = make_line_art_placeholder((1100, 1100), "demo", level)
    assert is_usable_line_art(art, level)[0]


def test_harder_fallbacks_have_more_lines() -> None:
    inks = [ink_ratio(make_line_art_placeholder((1100, 1100), "demo", level)) for level in (COMPLEXITY_EASY, COMPLEXITY_MEDIUM, COMPLEXITY_HARD)]
    assert inks[0] < inks[1] < inks[2]


def test_complexity_input_defaults_and_validates() -> None:
    assert BookInput(book_format="coloring_book").coloring_complexity == COMPLEXITY_MEDIUM
    assert BookInput(book_format="coloring_book", coloring_complexity="hard").coloring_complexity == COMPLEXITY_HARD
    assert BookInput(book_format="coloring_book", coloring_complexity="nonsense").coloring_complexity == COMPLEXITY_MEDIUM


def test_solid_black_areas_become_outlines_with_room_to_color() -> None:
    from PIL import ImageDraw

    image = Image.new("L", (600, 600), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse((100, 100, 400, 400), fill=0)  # a solid black blob
    draw.line((450, 50, 450, 550), fill=0, width=5)  # a thin line
    hollow = hollow_solid_areas(image)
    assert hollow.getpixel((250, 250)) == 255  # inside the blob is white now
    assert hollow.getpixel((250, 101)) == 0  # the blob keeps its outline
    assert hollow.getpixel((450, 300)) == 0  # thin lines are untouched


def test_crowded_picture_is_rejected_for_easy_but_fine_for_hard() -> None:
    from PIL import ImageDraw

    image = Image.new("L", (600, 600), 255)
    draw = ImageDraw.Draw(image)
    for row in range(14):
        for column in range(14):
            x, y = 21 + column * 42, 21 + row * 42
            draw.ellipse((x - 19, y - 19, x + 19, y + 19), outline=0, width=4)
    assert 0.2 < ink_ratio(image) < 0.36
    assert is_usable_line_art(image, COMPLEXITY_HARD)[0]
    assert not is_usable_line_art(image, COMPLEXITY_EASY)[0]  # too many dark lines for an easy page


def test_prompts_change_with_complexity() -> None:
    easy = page_prompt("A dinosaur", "Children", COMPLEXITY_EASY)
    hard = page_prompt("A dinosaur", "Children", COMPLEXITY_HARD)
    assert easy != hard and "very simple" in easy and "intricate" in hard
    assert all("white" in text and len(text) <= 950 for text in (easy, hard))
    assert detail_for("Children", COMPLEXITY_EASY) != detail_for("Children", COMPLEXITY_HARD)
    assert detail_for("Adults")  # still works without a complexity


# --------------------------------------------------------------------------------------
# Generation and export
# --------------------------------------------------------------------------------------
class _ModelPictures(ImageGenerator):
    """Stands in for FLUX: grey, shaded pictures (never already clean line art)."""

    name = "fake model"

    def __init__(self, blank_first: int = 0) -> None:
        self.calls = 0
        self.blank_first = blank_first

    def generate_image(self, prompt: str, output_path: str | Path, orientation: str) -> Path:
        self.calls += 1
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        size = (1024, 1536) if orientation == "cover" else (768, 1152) if orientation == "portrait" else (1024, 1024)
        if self.calls <= self.blank_first:
            Image.new("RGB", size, (250, 250, 250)).save(path)
        else:
            picture = _grey_drawing().resize(size)
            picture.save(path)
        return path


@pytest.mark.parametrize("layout", [LAYOUT_PAGE_ONLY, LAYOUT_PAGE_WITH_ICON])
def test_complete_coloring_book_has_cover_pages_pdf_and_zip(storage, layout) -> None:
    pipeline = _pipeline(storage, _input(pages=4, layout=layout), images=_ModelPictures())
    pipeline.create_plan()
    summary = pipeline.generate_complete_book()
    project = pipeline.project
    assert project.status.stage == "completed" and summary.docx_path and summary.docx_no_cover_path
    assert summary.pages == 5  # cover + 4 pages
    assert len(Document(str(summary.docx_path)).inline_shapes) == 5  # the cover and 4 pages
    assert len(Document(str(summary.docx_no_cover_path)).inline_shapes) == 4  # pages only
    for number in range(1, 5):
        assert storage.image_file(project, line_key(number)) and storage.image_file(project, page_key(number))
        with Image.open(storage.image_path(project, page_key(number))) as page:
            assert page.size == COLORING_PAGE_SIZE
    with Image.open(storage.image_path(project, "cover_final")) as cover:
        assert cover.size == COLORING_PAGE_SIZE
    assert summary.pdf_path.read_bytes().startswith(b"%PDF")
    with zipfile.ZipFile(summary.zip_path) as archive:
        assert sorted(archive.namelist()) == ["cover.png", "page_01.png", "page_02.png", "page_03.png", "page_04.png"]
    assert project.chapters == {} and project.reviews == {}  # no chapters, no text


def test_blank_pictures_are_retried_then_replaced_by_a_drawn_pattern(storage) -> None:
    generator = _ModelPictures(blank_first=3)
    pipeline = _pipeline(storage, _input(pages=4), images=generator)
    pipeline.create_plan()
    entry = pipeline.generate_chapter_image(1)
    assert generator.calls == 3 and entry.status == "placeholder"
    assert is_usable_line_art(Image.open(storage.image_path(pipeline.project, line_key(1))))[0]
    again = pipeline.generate_chapter_image(1)  # the model works from now on
    assert again.status == "generated"


def test_pages_follow_the_chosen_complexity(storage) -> None:
    """The model returns a crowded picture: an easy page falls back to a drawn easy pattern, a hard page accepts it."""

    class Crowded(_ModelPictures):
        def generate_image(self, prompt: str, output_path: str | Path, orientation: str) -> Path:
            from PIL import ImageDraw

            self.calls += 1
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            image = Image.new("RGB", (1100, 1100), "white")
            draw = ImageDraw.Draw(image)
            for row in range(14):
                for column in range(14):
                    x, y = 40 + column * 77, 40 + row * 77
                    draw.ellipse((x - 33, y - 33, x + 33, y + 33), outline="black", width=7)
            image.save(path)
            return path

    easy = _pipeline(storage, _input(pages=4, coloring_complexity=COMPLEXITY_EASY), images=Crowded())
    easy.create_plan()
    assert easy.generate_chapter_image(1).status == "placeholder"
    hard = _pipeline(storage, _input(pages=4, coloring_complexity=COMPLEXITY_HARD), images=Crowded())
    hard.create_plan()
    assert hard.generate_chapter_image(1).status == "generated"


def test_docx_export_has_one_picture_per_page_with_and_without_cover(tmp_path) -> None:
    from generators.coloring_pdf import build_coloring_docx

    files = []
    for index in range(3):
        path = tmp_path / f"p{index}.png"
        Image.new("RGB", COLORING_PAGE_SIZE, "white").save(path)
        files.append(path)
    with_cover = build_coloring_docx("Book", "Me", files[0], files[1:], tmp_path / "a.docx")
    without = build_coloring_docx("Book", "Me", files[0], files[1:], tmp_path / "b.docx", include_cover=False)
    assert len(Document(str(with_cover)).inline_shapes) == 3 and len(Document(str(without)).inline_shapes) == 2
    assert Document(str(with_cover)).core_properties.title == "Book"


def test_resume_does_not_redraw_finished_pages(storage) -> None:
    generator = _ModelPictures()
    pipeline = _pipeline(storage, _input(pages=4), images=generator)
    pipeline.create_plan()
    pipeline.generate_complete_book()
    drawn = generator.calls
    pipeline.generate_complete_book()
    assert generator.calls == drawn


def test_ebook_pipeline_is_not_affected(storage, book_input) -> None:
    from tests.conftest import FakeLLM

    project = storage.create_project(book_input)
    pipeline = BookPipeline(project, storage, llm=FakeLLM(), image_generator=PlaceholderImageGenerator())
    assert pipeline.is_coloring is False
    pipeline.create_plan()
    assert project.plan.title == "The Lantern Keeper" and project.plan.chapters[0].target_words > 0


def test_unknown_page_raises_a_clear_error(storage) -> None:
    pipeline = _pipeline(storage, _input())
    pipeline.create_plan()
    with pytest.raises(AIBookError):
        pipeline.generate_chapter_image(99)


# --------------------------------------------------------------------------------------
# Proofreading (used by eBooks and coloring books)
# --------------------------------------------------------------------------------------
def test_autocorrect_fixes_only_clear_mistakes() -> None:
    assert autocorrect_text("She walked to the the harbour , and  waited.") == "She walked to the harbour, and waited."
    assert autocorrect_text("He had had enough. That that works is fine.") == "He had had enough. That that works is fine."
    code = "```\nthe the  x , y\n```"
    assert autocorrect_text(code) == code
    assert autocorrect_text("Il a dit , oui !", "French") == "Il a dit , oui !"


def test_proofread_reports_garbled_words_and_cut_off_text() -> None:
    assert proofread_issues("The harbour was quiet. Mara counted the boats home.") == []
    assert any("garbled" in issue for issue in proofread_issues("The harbour was qqqqqqq and quiet. Done."))
    assert any("middle of a sentence" in issue for issue in proofread_issues("The harbour was quiet and then Mara went down to the"))
    assert proofread_issues("## A Heading\n\n- first point\n- second point") == []
    assert proofread_issues("Ein langes Wort Zwischenraumbeschreibung steht hier", "German") == []
