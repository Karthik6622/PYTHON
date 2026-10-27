"""Export builders (cover, PDF, DOCX)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExportAssets:
    """Files the exporters embed in the book."""

    cover_path: Path | None = None
    chapter_images: dict[int, Path] = field(default_factory=dict)


@dataclass
class ExportResult:
    """Outcome of one export."""

    path: Path
    pages: int = 0
    warnings: list[str] = field(default_factory=list)
