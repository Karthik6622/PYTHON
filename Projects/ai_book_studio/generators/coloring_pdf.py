"""Coloring-book exports: a print-ready PDF (cover first, one picture per US Letter page), a ZIP of the pages and the cover image."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from utils.retry_utils import ExportError

_DOCX_MAX_WIDTH_IN = 7.6  # 8.5 in page minus 0.45 in margins on each side
_DOCX_MAX_HEIGHT_IN = 10.1  # 11 in page minus 0.45 in margins top and bottom


def _fit_in_box(sheet: Path, box_w: float, box_h: float) -> tuple[float, float, float, float]:
    """Largest size of ``sheet`` that fits inside the box, keeping its proportions, and the offset that centers it."""
    image_w, image_h = ImageReader(str(sheet)).getSize()
    scale = min(box_w / image_w, box_h / image_h)
    width, height = image_w * scale, image_h * scale
    return (box_w - width) / 2, (box_h - height) / 2, width, height


def build_coloring_pdf(title: str, author: str, cover: Path | None, pages: list[Path], output_path: Path) -> int:
    """Write the PDF and return the number of pages in it. Each image is fitted to a US Letter page by its proportions, centered, never stretched."""
    sheets = ([cover] if cover else []) + list(pages)
    if not sheets:
        raise ExportError("There are no coloring pages to export yet.")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(output_path.stem + ".tmp.pdf")
    width, height = letter
    try:
        pdf = canvas.Canvas(str(temp), pagesize=letter, pageCompression=1)
        pdf.setTitle(title)
        if author:
            pdf.setAuthor(author)
        pdf.setCreator("AI Book Studio")
        for sheet in sheets:
            x, y, fit_w, fit_h = _fit_in_box(sheet, width, height)
            pdf.drawImage(ImageReader(str(sheet)), x, y, width=fit_w, height=fit_h)
            pdf.showPage()
        pdf.save()
        os.replace(temp, output_path)
    except OSError as exc:
        raise ExportError(f"The PDF could not be written ({type(exc).__name__}).") from exc
    return len(sheets)


def build_coloring_docx(
    title: str, author: str, cover: Path | None, pages: list[Path], output_path: Path, include_cover: bool = True
) -> Path:
    """A Word document with one picture per US Letter page (the cover first unless ``include_cover`` is False)."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt

    sheets = ([cover] if cover and include_cover else []) + list(pages)
    if not sheets:
        raise ExportError("There are no coloring pages to export yet.")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(output_path.stem + ".tmp.docx")
    try:
        document = Document()
        section = document.sections[0]
        section.page_width, section.page_height = Inches(8.5), Inches(11)
        for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
            setattr(section, side, Inches(0.45))
        document.core_properties.title = title
        document.core_properties.author = author or "AI Book Studio"
        for index, sheet in enumerate(sheets):
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_before = 0
            paragraph.paragraph_format.space_after = 0
            paragraph.paragraph_format.page_break_before = index > 0
            _, _, fit_w, _ = _fit_in_box(sheet, _DOCX_MAX_WIDTH_IN * inch, _DOCX_MAX_HEIGHT_IN * inch)
            paragraph.add_run().add_picture(str(sheet), width=Pt(fit_w))
        document.save(str(temp))
        os.replace(temp, output_path)
    except OSError as exc:
        raise ExportError(f"The DOCX could not be written ({type(exc).__name__}).") from exc
    return output_path


def build_pages_zip(pages: list[Path], output_path: Path, cover: Path | None = None, front: list[Path] | None = None) -> Path:
    """A ZIP with every page as a separate PNG (page_01.png ...), the cover (cover.png) and any extra front pages (front_01.png ...)."""
    if not pages:
        raise ExportError("There are no coloring pages to export yet.")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(output_path.stem + ".tmp.zip")
    try:
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_STORED) as archive:  # PNG is already compressed
            if cover:
                archive.write(cover, "cover.png")
            for index, sheet in enumerate(front or [], start=1):
                archive.write(sheet, f"front_{index:02d}.png")
            for index, page in enumerate(pages, start=1):
                archive.write(page, f"page_{index:02d}.png")
        os.replace(temp, output_path)
    except OSError as exc:
        raise ExportError(f"The ZIP file could not be written ({type(exc).__name__}).") from exc
    return output_path
