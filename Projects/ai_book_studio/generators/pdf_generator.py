"""Build the book PDF with ReportLab (6x9 inch trade format, real page numbers in the table of contents)."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
)
from reportlab.platypus.tableofcontents import TableOfContents

from generators import ExportAssets, ExportResult
from models.book_models import BookProject
from services.chapter_writer import author_page_text
from utils.image_utils import iter_font_families, script_for
from utils.retry_utils import ExportError, redact
from utils.text_utils import (
    Block,
    chapter_label,
    label,
    parse_blocks,
    remove_control_chars,
    split_inline,
    words_per_page,
)

LOGGER = logging.getLogger("ai_book_studio.pdf")

PAGE_W, PAGE_H = 6 * inch, 9 * inch
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 0.8 * inch, 0.9 * inch, 0.85 * inch
FRAME_W = PAGE_W - 2 * MARGIN_X
FRAME_H = PAGE_H - MARGIN_TOP - MARGIN_BOTTOM

NAVY = colors.HexColor("#1E1B4B")
INDIGO = colors.HexColor("#4F46E5")
INK = colors.HexColor("#1F2937")
GREY = colors.HexColor("#6B7280")


@dataclass
class FontSet:
    """Registered font names for the four text variants."""

    regular: str
    bold: str
    italic: str
    bold_italic: str
    builtin: bool = False
    warning: str = ""


def register_fonts(language: str) -> FontSet:
    """Register a Unicode TrueType family for the language, or fall back with a clear warning."""
    script = script_for(language)
    for family in iter_font_families(language):
        try:
            names: dict[str, str] = {}
            for variant in ("regular", "bold", "italic", "bold_italic"):
                path = family.get(variant)
                if not path or not path.exists():
                    path = family["regular"]
                name = f"Book-{script}-{variant}"
                extra = {"subfontIndex": 0} if path.suffix.lower() == ".ttc" else {}
                pdfmetrics.registerFont(TTFont(name, str(path), **extra))
                names[variant] = name
            pdfmetrics.registerFontFamily(
                f"Book-{script}",
                normal=names["regular"],
                bold=names["bold"],
                italic=names["italic"],
                boldItalic=names["bold_italic"],
            )
            note = ""
            if script in {"tamil", "devanagari"}:
                note = (
                    f"{language} text is embedded with a Unicode font, but ReportLab does not shape complex scripts, "
                    "so some letter combinations may look different in the PDF. The DOCX export renders them in Word."
                )
            return FontSet(names["regular"], names["bold"], names["italic"], names["bold_italic"], False, note)
        except Exception as exc:  # noqa: BLE001 - try the next installed family
            LOGGER.warning("Could not register font family: %s", redact(exc))
    if script == "latin":
        return FontSet("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic", True)
    return FontSet(
        "Helvetica",
        "Helvetica-Bold",
        "Helvetica-Oblique",
        "Helvetica-BoldOblique",
        True,
        f"No installed font supports {language}. Add a Noto font to assets/fonts (see README). "
        "The PDF may show missing characters; the DOCX export is unaffected.",
    )


def _layout(words_per_page_value: int) -> tuple[float, float]:
    """Font size and leading chosen so a page holds roughly the planned number of words."""
    if words_per_page_value <= 100:
        return 14.5, 23.0
    if words_per_page_value <= 150:
        return 13.0, 20.0
    if words_per_page_value <= 300:
        return 11.0, 15.5
    if words_per_page_value <= 350:
        return 10.5, 14.5
    return 10.0, 13.5


def _make_styles(fonts: FontSet, size: float, leading: float, language: str) -> dict[str, ParagraphStyle]:
    latin = script_for(language) == "latin"
    wrap = "CJK" if language == "Japanese" else None
    common = {"fontName": fonts.regular, "textColor": INK, "wordWrap": wrap, "bulletFontName": fonts.regular}

    def style(name: str, **overrides) -> ParagraphStyle:
        return ParagraphStyle(name, **{**common, **overrides})

    body = style(
        "Body",
        fontSize=size,
        leading=leading,
        alignment=TA_JUSTIFY if latin else TA_LEFT,
        firstLineIndent=size * 1.2,
        spaceAfter=2,
    )
    styles = {
        "Body": body,
        "BodyFirst": ParagraphStyle("BodyFirst", parent=body, firstLineIndent=0),
        "H2": style("H2", fontName=fonts.bold, fontSize=size + 4, leading=leading + 6, textColor=NAVY, spaceBefore=16, spaceAfter=6, keepWithNext=1),
        "H3": style("H3", fontName=fonts.bold, fontSize=size + 1.5, leading=leading + 3, textColor=INDIGO, spaceBefore=10, spaceAfter=4, keepWithNext=1),
        "Bullet": style("Bullet", fontSize=size, leading=leading, leftIndent=18, bulletIndent=5, spaceAfter=3, bulletFontSize=size),
        "Quote": style("Quote", fontName=fonts.italic, fontSize=size, leading=leading, leftIndent=22, rightIndent=22, spaceBefore=4, spaceAfter=6, textColor=GREY),
        "Code": ParagraphStyle("Code", fontName="Courier", fontSize=size - 2, leading=leading - 3, leftIndent=8, spaceBefore=4, spaceAfter=6, textColor=NAVY),
        "Break": style("Break", fontSize=size, leading=leading, alignment=TA_CENTER, spaceBefore=6, spaceAfter=6, textColor=INDIGO),
        "ChapterLabel": style("ChapterLabel", fontName=fonts.bold, fontSize=11, leading=14, alignment=TA_CENTER, textColor=INDIGO, spaceAfter=6, keepWithNext=1),
        "ChapterTitle": style("ChapterTitle", fontName=fonts.bold, fontSize=24, leading=30, alignment=TA_CENTER, textColor=NAVY, spaceAfter=12, keepWithNext=1),
        "SectionTitle": style("SectionTitle", fontName=fonts.bold, fontSize=22, leading=28, alignment=TA_CENTER, textColor=NAVY, spaceAfter=16, keepWithNext=1),
        "FrontTitle": style("FrontTitle", fontName=fonts.bold, fontSize=22, leading=28, alignment=TA_CENTER, textColor=NAVY, spaceAfter=16),
        "BookTitle": style("BookTitle", fontName=fonts.bold, fontSize=30, leading=36, alignment=TA_CENTER, textColor=NAVY, spaceAfter=10),
        "BookSubtitle": style("BookSubtitle", fontName=fonts.italic, fontSize=15, leading=21, alignment=TA_CENTER, textColor=GREY, spaceAfter=18),
        "BookAuthor": style("BookAuthor", fontName=fonts.bold, fontSize=15, leading=20, alignment=TA_CENTER, textColor=INDIGO, spaceBefore=14),
        "Small": style("Small", fontSize=9, leading=13.5, alignment=TA_LEFT, textColor=GREY, spaceAfter=6),
        "Dedication": style("Dedication", fontName=fonts.italic, fontSize=size + 1.5, leading=leading + 4, alignment=TA_CENTER, leftIndent=24, rightIndent=24),
        "TOCEntry": style("TOCEntry", fontSize=size, leading=leading + 1, leftIndent=4, rightIndent=4, spaceBefore=4),
    }
    return styles


def _clean(text: str, fonts: FontSet) -> str:
    text = remove_control_chars(text)
    return text.encode("cp1252", "replace").decode("cp1252") if fonts.builtin else text


def _inline(text: str, fonts: FontSet) -> str:
    """Convert inline Markdown to ReportLab markup with all user text escaped."""
    parts: list[str] = []
    for chunk, bold, italic in split_inline(_clean(text, fonts)):
        piece = escape(chunk)
        if bold:
            piece = f"<b>{piece}</b>"
        if italic:
            piece = f"<i>{piece}</i>"
        parts.append(piece)
    return "".join(parts)


def _scaled_image(path: Path, max_width: float, max_height: float) -> Image:
    """Image scaled to fit the box while keeping its aspect ratio."""
    with PILImage.open(path) as picture:
        width, height = picture.size
    scale = min(max_width / width, max_height / height)
    flowable = Image(str(path), width=width * scale, height=height * scale)
    flowable.hAlign = "CENTER"
    return flowable


def _body_flowables(text: str, styles: dict[str, ParagraphStyle], fonts: FontSet) -> list:
    """Convert chapter Markdown into flowables, avoiding first-line indent right after headings."""
    flowables: list = []
    fresh = True
    for block in parse_blocks(text):
        if block.kind in {"h1", "h2"}:
            flowables.append(Paragraph(_inline(block.text, fonts), styles["H2"]))
            fresh = True
        elif block.kind == "h3":
            flowables.append(Paragraph(_inline(block.text, fonts), styles["H3"]))
            fresh = True
        elif block.kind == "p":
            flowables.append(Paragraph(_inline(block.text, fonts), styles["BodyFirst" if fresh else "Body"]))
            fresh = False
        elif block.kind == "bullet":
            flowables.append(Paragraph(_inline(block.text, fonts), styles["Bullet"], bulletText="•"))
        elif block.kind == "number":
            flowables.append(Paragraph(_inline(block.text, fonts), styles["Bullet"], bulletText=f"{block.number}."))
        elif block.kind == "quote":
            flowables.append(Paragraph(_inline(block.text, fonts), styles["Quote"]))
        elif block.kind == "code":
            flowables.append(Preformatted(_clean(block.text, fonts), styles["Code"]))
        elif block.kind == "break":
            flowables.append(Paragraph("* &nbsp; * &nbsp; *", styles["Break"]))
            fresh = True
    return flowables


class _BookDoc(BaseDocTemplate):
    """Document with cover, front-matter and body page templates plus table-of-contents notifications."""

    def __init__(self, path: str, project: BookProject, fonts: FontSet, cover_path: Path | None) -> None:
        plan = project.plan
        assert plan is not None
        super().__init__(
            path,
            pagesize=(PAGE_W, PAGE_H),
            title=_clean(plan.title, fonts),
            author=_clean(plan.author, fonts),
            subject=_clean(plan.subtitle or plan.description[:120], fonts),
            creator="AI Book Studio",
            leftMargin=MARGIN_X,
            rightMargin=MARGIN_X,
            topMargin=MARGIN_TOP,
            bottomMargin=MARGIN_BOTTOM,
        )
        self._fonts = fonts
        self._title = _clean(plan.title, fonts)
        self._cover_path = cover_path
        self._sequence = 0
        self.chapters_seen: list[str] = []
        body_frame = Frame(MARGIN_X, MARGIN_BOTTOM, FRAME_W, FRAME_H, id="body", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        cover_frame = Frame(0, 0, PAGE_W, PAGE_H, id="cover", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates(
            [
                PageTemplate(id="Cover", frames=[cover_frame], onPage=self._draw_cover),
                PageTemplate(id="Front", frames=[body_frame]),
                PageTemplate(id="Body", frames=[body_frame], onPage=self._draw_body),
            ]
        )

    def _draw_cover(self, canvas, doc) -> None:
        canvas.saveState()
        if self._cover_path and Path(self._cover_path).exists():
            canvas.drawImage(str(self._cover_path), 0, 0, width=PAGE_W, height=PAGE_H, preserveAspectRatio=True, anchor="c")
        else:
            canvas.setFillColor(NAVY)
            canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        canvas.restoreState()

    def _draw_body(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont(self._fonts.regular, 8)
        canvas.setFillColor(GREY)
        canvas.drawCentredString(PAGE_W / 2, PAGE_H - 0.55 * inch, self._title[:80])
        canvas.setStrokeColor(colors.HexColor("#D1D5DB"))
        canvas.setLineWidth(0.4)
        canvas.line(MARGIN_X, PAGE_H - 0.62 * inch, PAGE_W - MARGIN_X, PAGE_H - 0.62 * inch)
        canvas.drawCentredString(PAGE_W / 2, 0.5 * inch, str(canvas.getPageNumber()))
        canvas.restoreState()

    def afterFlowable(self, flowable) -> None:
        text = getattr(flowable, "_toc_text", None)
        if not text:
            return
        key = f"toc{self._sequence}"
        self._sequence += 1
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, 0, 0)
        self.notify("TOCEntry", (0, escape(text), self.page, key))
        if flowable.style.name == "ChapterTitle":
            self.chapters_seen.append(text)


def _tagged(text: str, style: ParagraphStyle, toc_text: str, fonts: FontSet) -> Paragraph:
    paragraph = Paragraph(_inline(text, fonts), style)
    paragraph._toc_text = _clean(toc_text, fonts)  # read by _BookDoc.afterFlowable
    return paragraph


def _build_story(
    project: BookProject,
    assets: ExportAssets,
    fonts: FontSet,
    styles: dict[str, ParagraphStyle],
    with_page_numbers: bool,
) -> list:
    plan = project.plan
    assert plan is not None
    options = project.book_input
    language = plan.language
    sections: list[tuple[str, list]] = []

    if options.has("title_page"):
        sections.append(
            (
                "Front",
                [
                    Spacer(1, 1.9 * inch),
                    Paragraph(_inline(plan.title, fonts), styles["BookTitle"]),
                    *([Paragraph(_inline(plan.subtitle, fonts), styles["BookSubtitle"])] if plan.subtitle else []),
                    HRFlowable(width="35%", thickness=1.2, color=INDIGO, spaceBefore=6, spaceAfter=10, hAlign="CENTER"),
                    Paragraph(_inline(plan.author, fonts), styles["BookAuthor"]),
                ],
            )
        )
    if options.has("copyright_page"):
        year = datetime.now().year
        sections.append(
            (
                "Front",
                [
                    Spacer(1, 4.4 * inch),
                    Paragraph(escape(_clean(f"Copyright © {year} {plan.author}", fonts)), styles["Small"]),
                    Paragraph("All rights reserved.", styles["Small"]),
                    Spacer(1, 6),
                    Paragraph("This book was created with AI-assisted tools and reviewed by the author.", styles["Small"]),
                ],
            )
        )
    if options.has("dedication") and project.front_matter.get("dedication", "").strip():
        sections.append(
            ("Front", [Spacer(1, 2.6 * inch), Paragraph(_inline(project.front_matter["dedication"].strip(), fonts), styles["Dedication"])])
        )

    def text_section(key: str, text: str) -> tuple[str, list]:
        title = label(key, language)
        return ("Body", [_tagged(title, styles["SectionTitle"], title, fonts), *_body_flowables(text, styles, fonts)])

    for key in ("preface", "introduction"):
        if options.has(key) and project.front_matter.get(key, "").strip():
            sections.append(text_section(key, project.front_matter[key]))

    chapters = [c for c in plan.chapters if project.chapters.get(c.chapter_number, "").strip()]
    if options.has("table_of_contents"):
        heading = Paragraph(_inline(label("table_of_contents", language), fonts), styles["FrontTitle"])
        if with_page_numbers:
            toc = TableOfContents()
            toc.levelStyles = [styles["TOCEntry"]]
            toc.dotsMinLevel = 0
            toc_flowables: list = [toc]
        else:
            toc_flowables = []
            for chapter in chapters:
                entry = f"{chapter_label(chapter.chapter_number, language)}: {chapter.title}"
                toc_flowables.append(Paragraph(_inline(entry, fonts), styles["TOCEntry"]))
        sections.append(("Body", [heading, Spacer(1, 6), *toc_flowables]))

    for chapter in chapters:
        number = chapter.chapter_number
        entry_text = f"{chapter_label(number, language)}: {chapter.title}"
        flow: list = [
            Spacer(1, 0.45 * inch),
            Paragraph(_inline(chapter_label(number, language), fonts), styles["ChapterLabel"]),
            _tagged(chapter.title, styles["ChapterTitle"], entry_text, fonts),
            HRFlowable(width="30%", thickness=1.2, color=INDIGO, spaceBefore=2, spaceAfter=14, hAlign="CENTER"),
        ]
        image_path = assets.chapter_images.get(number)
        if image_path and Path(image_path).exists():
            flow.extend([_scaled_image(Path(image_path), FRAME_W, 3.5 * inch), Spacer(1, 12)])
        flow.extend(_body_flowables(project.chapters[number], styles, fonts))
        sections.append(("Body", flow))

    for key in ("conclusion", "glossary"):
        if options.has(key) and project.front_matter.get(key, "").strip():
            sections.append(text_section(key, project.front_matter[key]))
    if options.has("author_page"):
        sections.append(text_section("author_page", author_page_text(project)))

    story: list = [Spacer(1, 1)]
    for template, flowables in sections:
        story.extend([NextPageTemplate(template), PageBreak(), *flowables])
    return story


def estimate_layout_words_per_page(project: BookProject) -> int:
    """Planned words per page for the project (used for display)."""
    options = project.book_input
    return words_per_page(options.effective_book_type, options.writing_style, options.illustration_frequency)


def build_pdf(project: BookProject, assets: ExportAssets, output_path: Path) -> ExportResult:
    """Create and validate the PDF. Raises ``ExportError`` when it cannot be produced."""
    plan = project.plan
    if plan is None:
        raise ExportError("PDF generation failed: the book has no plan.")
    fonts = register_fonts(plan.language)
    size, leading = _layout(estimate_layout_words_per_page(project))
    styles = _make_styles(fonts, size, leading, plan.language)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(output_path.stem + ".tmp.pdf")
    warnings: list[str] = [fonts.warning] if fonts.warning else []
    expected = [c for c in plan.chapters if project.chapters.get(c.chapter_number, "").strip()]
    use_numbers = project.book_input.has("table_of_contents")

    doc: _BookDoc | None = None
    for attempt in (True, False) if use_numbers else (False,):
        try:
            doc = _BookDoc(str(temp_path), project, fonts, assets.cover_path)
            story = _build_story(project, assets, fonts, styles, with_page_numbers=attempt and use_numbers)
            if attempt and use_numbers:
                doc.multiBuild(story)
            else:
                doc.build(story)
            break
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("PDF build failed (page numbers=%s): %s: %s", attempt, type(exc).__name__, redact(exc))
            temp_path.unlink(missing_ok=True)
            if not attempt or not use_numbers:
                raise ExportError(f"PDF generation failed: {type(exc).__name__}. See the log for details.") from exc
            warnings.append("Page numbers could not be calculated, so the table of contents lists chapters without page numbers.")
    assert doc is not None

    if not temp_path.exists() or temp_path.stat().st_size < 1500 or temp_path.read_bytes()[:5] != b"%PDF-":
        temp_path.unlink(missing_ok=True)
        raise ExportError("PDF generation failed: the file is empty or invalid.")
    if len(doc.chapters_seen) != len(expected):
        temp_path.unlink(missing_ok=True)
        raise ExportError(
            f"PDF generation failed: expected {len(expected)} chapters but {len(doc.chapters_seen)} were written."
        )
    temp_path.replace(output_path)
    pages = int(doc.page)
    if math.isfinite(pages) and pages > 0:
        requested = project.book_input.pages
        if abs(pages - requested) > max(2, requested * 0.1):
            warnings.append(
                f"The PDF has {pages} pages; you requested about {requested}. Final page counts vary with fonts, images, "
                "spacing, headings and paragraph lengths."
            )
    return ExportResult(path=output_path, pages=pages, warnings=warnings)
