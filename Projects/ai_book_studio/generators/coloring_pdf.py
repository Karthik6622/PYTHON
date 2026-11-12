"""Coloring-book exports: a print-ready PDF (cover first, one picture per US Letter page), a ZIP of the pages and the cover image."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from utils.retry_utils import ExportError


def build_coloring_pdf(title: str, author: str, cover: Path | None, pages: list[Path], output_path: Path) -> int:
    """Write the PDF and return the number of pages in it. Every image fills a whole page (the images are 8.5x11 in at 150 dpi)."""
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
            pdf.drawImage(ImageReader(str(sheet)), 0, 0, width=width, height=height)
            pdf.showPage()
        pdf.save()
        os.replace(temp, output_path)
    except OSError as exc:
        raise ExportError(f"The PDF could not be written ({type(exc).__name__}).") from exc
    return len(sheets)


def build_pages_zip(pages: list[Path], output_path: Path, cover: Path | None = None) -> Path:
    """A ZIP with every page as a separate PNG (page_01.png ...) and the cover (cover.png)."""
    if not pages:
        raise ExportError("There are no coloring pages to export yet.")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(output_path.stem + ".tmp.zip")
    try:
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_STORED) as archive:  # PNG is already compressed
            if cover:
                archive.write(cover, "cover.png")
            for index, page in enumerate(pages, start=1):
                archive.write(page, f"page_{index:02d}.png")
        os.replace(temp, output_path)
    except OSError as exc:
        raise ExportError(f"The ZIP file could not be written ({type(exc).__name__}).") from exc
    return output_path
