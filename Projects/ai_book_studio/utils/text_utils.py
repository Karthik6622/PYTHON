"""Text, page-budget and markdown helpers (no Streamlit, no network)."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from config import FICTION_TYPES, MAX_OUTPUT_TOKENS, MIN_OUTPUT_TOKENS

if TYPE_CHECKING:
    from models.book_models import BookInput, ChapterSummary


# --------------------------------------------------------------------------------------
# Prompt templates
# --------------------------------------------------------------------------------------
_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


def render_template(template: str, **values: Any) -> str:
    """Fill ``{name}`` placeholders. JSON braces in the template are left untouched."""
    return _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), template)


def compact_json(data: Any, limit: int | None = None) -> str:
    """Serialise to compact JSON, optionally truncating to ``limit`` characters."""
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if limit and len(text) > limit:
        return text[: limit - 1] + "…"
    return text


# --------------------------------------------------------------------------------------
# Cleaning
# --------------------------------------------------------------------------------------
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def strip_reasoning(text: str) -> str:
    """Remove ``<think>`` blocks (and a dangling closing tag) from model output."""
    text = _THINK.sub("", text or "")
    if "</think>" in text.lower():
        text = re.split(r"</think>", text, flags=re.IGNORECASE)[-1]
    return text.strip()


def remove_control_chars(text: str) -> str:
    """Strip characters that are invalid in XML and PDF text."""
    return _CONTROL.sub("", text or "")


def count_words(text: str) -> int:
    """Count words; CJK characters are counted at roughly 1.6 characters per word."""
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    return len(_CJK.sub(" ", text).split()) + math.ceil(cjk / 1.6)


def _plain_heading(line: str) -> str:
    text = re.sub(r"^[#>*\s]+|[*\s]+$", "", line)
    text = re.sub(r"(?i)^(chapter|capítulo|chapitre|kapitel)\s*\d+\s*[:.\-–—]*\s*", "", text)
    return re.sub(r"\s+", " ", text).strip(" :.-–—").lower()


def clean_chapter_text(text: str, number: int, title: str) -> str:
    """Remove reasoning, code fences, duplicate chapter headings and meta lines from chapter text."""
    cleaned = strip_reasoning(text)
    cleaned = re.sub(r"^```[a-zA-Z]*\s*\n|\n```\s*$", "", cleaned.strip())
    lines = cleaned.split("\n")
    wanted = title.strip().lower()
    for _ in range(3):
        while lines and not lines[0].strip():
            lines.pop(0)
        if not lines:
            break
        first = lines[0].strip()
        plain = _plain_heading(first)
        if (
            not plain
            or plain == wanted
            or re.match(rf"(?i)^[#*\s]*(chapter|capítulo|chapitre|kapitel)\s*{number}\b", first)
        ):
            lines.pop(0)
        else:
            break
    kept = [line for line in lines if not re.match(r"(?i)^\s*[\[(]?\s*(word count|words)\s*[:=]", line)]
    return remove_control_chars("\n".join(kept)).strip()


# --------------------------------------------------------------------------------------
# Markdown parsing shared by the PDF and DOCX builders
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Block:
    """A parsed Markdown block."""

    kind: str  # h1 h2 h3 p bullet number quote code break
    text: str = ""
    number: int = 0


_BREAK = re.compile(r"^(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")


def parse_blocks(text: str) -> list[Block]:
    """Parse the Markdown subset used in chapters into blocks."""
    blocks: list[Block] = []
    paragraph: list[str] = []
    code: list[str] = []
    in_code = False

    def flush() -> None:
        if paragraph:
            blocks.append(Block("p", " ".join(paragraph)))
            paragraph.clear()

    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        stripped = raw.strip()
        if stripped.startswith("```"):
            flush()
            if in_code:
                blocks.append(Block("code", "\n".join(code)))
                code = []
            in_code = not in_code
            continue
        if in_code:
            code.append(raw.rstrip())
            continue
        if not stripped:
            flush()
            continue
        if _BREAK.match(stripped):
            flush()
            blocks.append(Block("break"))
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            flush()
            blocks.append(Block(f"h{min(len(heading.group(1)), 3)}", heading.group(2).strip("*# ").strip()))
            continue
        bullet = re.match(r"^[-*•]\s+(.*)$", stripped)
        if bullet:
            flush()
            blocks.append(Block("bullet", bullet.group(1)))
            continue
        numbered = re.match(r"^(\d{1,3})[.)]\s+(.*)$", stripped)
        if numbered:
            flush()
            blocks.append(Block("number", numbered.group(2), int(numbered.group(1))))
            continue
        if stripped.startswith(">"):
            flush()
            blocks.append(Block("quote", stripped.lstrip("> ").strip()))
            continue
        paragraph.append(stripped)
    flush()
    if in_code and code:
        blocks.append(Block("code", "\n".join(code)))
    return blocks


_INLINE = re.compile(r"\*\*\*(?!\s)(.+?)(?<!\s)\*\*\*|\*\*(?!\s)(.+?)(?<!\s)\*\*|\*(?!\s)(.+?)(?<!\s)\*")


def split_inline(text: str) -> list[tuple[str, bool, bool]]:
    """Split inline Markdown into ``(text, bold, italic)`` runs."""
    runs: list[tuple[str, bool, bool]] = []
    position = 0
    for match in _INLINE.finditer(text):
        if match.start() > position:
            runs.append((text[position : match.start()], False, False))
        if match.group(1) is not None:
            runs.append((match.group(1), True, True))
        elif match.group(2) is not None:
            runs.append((match.group(2), True, False))
        else:
            runs.append((match.group(3), False, True))
        position = match.end()
    if position < len(text):
        runs.append((text[position:], False, False))
    return [(part.replace("`", ""), bold, italic) for part, bold, italic in runs if part]


# --------------------------------------------------------------------------------------
# Page and word budget
# --------------------------------------------------------------------------------------
@dataclass
class PageBudget:
    """Python-side estimate of the pages and words available for the chapters."""

    selected_pages: int
    reserved_pages: int
    content_pages: int
    words_per_page: int
    target_words: int
    recommended_chapters: int
    section_pages: dict[str, int] = field(default_factory=dict)
    clamped: bool = False

    @property
    def front_matter_pages(self) -> int:
        return self.reserved_pages


def words_per_page(book_type: str, writing_style: str, illustration_frequency: str) -> int:
    """Approximate words per content page."""
    if book_type == "Children's Book":
        return 100
    if illustration_frequency == "Image-heavy book":
        return 150
    if book_type in FICTION_TYPES:
        return 300
    if book_type == "Technology" or writing_style in {"Technical", "Academic"}:
        return 400
    return 350


def compute_budget(book_input: "BookInput") -> PageBudget:
    """Estimate reserved pages, content pages, word target and chapter count."""
    pages = book_input.pages
    wpp = words_per_page(book_input.effective_book_type, book_input.writing_style, book_input.illustration_frequency)
    small, medium = pages < 40, pages < 100
    sections: dict[str, int] = {"cover": 1}
    if book_input.has("title_page"):
        sections["title_page"] = 1
    if book_input.has("copyright_page"):
        sections["copyright_page"] = 1
    if book_input.has("dedication"):
        sections["dedication"] = 1
    if book_input.has("preface"):
        sections["preface"] = 1 if small else 2
    if book_input.has("table_of_contents"):
        sections["table_of_contents"] = 1 if pages <= 60 else 2 if pages <= 130 else 3
    if book_input.has("introduction"):
        sections["introduction"] = 1 if small else 2 if medium else 3
    if book_input.has("conclusion"):
        sections["conclusion"] = 1 if small else 2
    if book_input.has("glossary"):
        sections["glossary"] = 1 if pages < 60 else 2 if pages < 130 else 3
    if book_input.has("author_page"):
        sections["author_page"] = 1
    reserved = sum(sections.values())
    raw_content = pages - reserved
    content = max(3, raw_content)
    if book_input.book_type == "Children's Book":
        pages_per_chapter = 2
    elif book_input.illustration_frequency == "Image-heavy book":
        pages_per_chapter = 4
    else:
        pages_per_chapter = 6
    chapters = max(3, min(30, round(content / pages_per_chapter)))
    return PageBudget(
        selected_pages=pages,
        reserved_pages=reserved,
        content_pages=content,
        words_per_page=wpp,
        target_words=content * wpp,
        recommended_chapters=chapters,
        section_pages=sections,
        clamped=raw_content < 3,
    )


def estimate_pdf_pages(book_input: "BookInput", chapter_word_counts: list[int]) -> int:
    """Rough PDF page estimate from the actual chapter lengths."""
    budget = compute_budget(book_input)
    body = sum(max(1, math.ceil(words / budget.words_per_page)) for words in chapter_word_counts)
    return budget.reserved_pages + body


def section_words(budget: PageBudget, section: str, minimum: int = 80) -> int:
    """Word target for a front or back matter section."""
    pages = budget.section_pages.get(section, 1)
    return max(minimum, int(pages * budget.words_per_page * 0.8))


_TOKENS_PER_WORD = {
    "English": 1.5,
    "Spanish": 1.9,
    "French": 1.9,
    "German": 2.1,
    "Hindi": 4.0,
    "Tamil": 5.0,
    "Japanese": 3.0,
}


def chapter_max_tokens(target_words: int, language: str) -> int:
    """Output-token limit for a chapter, clamped to the supported range."""
    factor = _TOKENS_PER_WORD.get(language, 2.0)
    tokens = int(max(target_words, 50) * factor * 1.3) + 200
    return max(MIN_OUTPUT_TOKENS, min(tokens, MAX_OUTPUT_TOKENS))


def format_previous_summaries(summaries: "dict[int, ChapterSummary]", before: int, limit: int = 7000) -> str:
    """Format the summaries of chapters before ``before``, newest first until ``limit`` characters."""
    entries: list[str] = []
    used = 0
    summaries = dict(summaries)  # snapshot: other chapter workers may add summaries while this runs
    for number in sorted((n for n in summaries if n < before), reverse=True):
        summary = summaries[number]
        text = (
            f"Chapter {number} - {summary.chapter_title}\n"
            f"  Events/points: {'; '.join(summary.important_events_or_points)}\n"
            f"  Character changes: {'; '.join(summary.character_changes)}\n"
            f"  New locations: {'; '.join(summary.new_locations)}\n"
            f"  New terms: {'; '.join(summary.new_terms)}\n"
            f"  Unresolved: {'; '.join(summary.unresolved_items)}\n"
            f"  Notes for next chapter: {'; '.join(summary.continuity_notes_for_next_chapter)}"
        )
        if used + len(text) > limit and entries:
            break
        entries.append(text)
        used += len(text)
    if not entries:
        return "None. This is the first chapter."
    return "\n".join(reversed(entries))


# --------------------------------------------------------------------------------------
# Localised labels for generated pages
# --------------------------------------------------------------------------------------
LANGUAGE_ORDER = ["English", "Spanish", "French", "German", "Hindi", "Tamil", "Japanese"]
_LABELS: dict[str, tuple[str, ...]] = {
    "chapter": ("Chapter", "Capítulo", "Chapitre", "Kapitel", "अध्याय", "அத்தியாயம்", "第{n}章"),
    "table_of_contents": ("Table of Contents", "Índice", "Table des matières", "Inhaltsverzeichnis", "विषय सूची", "உள்ளடக்கம்", "目次"),
    "dedication": ("Dedication", "Dedicatoria", "Dédicace", "Widmung", "समर्पण", "சமர்ப்பணம்", "献辞"),
    "preface": ("Preface", "Prefacio", "Préface", "Vorwort", "प्रस्तावना", "முன்னுரை", "まえがき"),
    "introduction": ("Introduction", "Introducción", "Introduction", "Einleitung", "परिचय", "அறிமுகம்", "はじめに"),
    "conclusion": ("Conclusion", "Conclusión", "Conclusion", "Fazit", "निष्कर्ष", "முடிவுரை", "おわりに"),
    "glossary": ("Glossary", "Glosario", "Glossaire", "Glossar", "शब्दावली", "சொற்களஞ்சியம்", "用語集"),
    "author_page": ("About the Author", "Acerca del autor", "À propos de l'auteur", "Über den Autor", "लेखक के बारे में", "ஆசிரியர் பற்றி", "著者について"),
}


def label(key: str, language: str) -> str:
    """Localised heading for a book section."""
    options = _LABELS[key]
    index = LANGUAGE_ORDER.index(language) if language in LANGUAGE_ORDER else 0
    return options[index]


def chapter_label(number: int, language: str) -> str:
    """Localised "Chapter N" label."""
    text = label("chapter", language)
    return text.replace("{n}", str(number)) if "{n}" in text else f"{text} {number}"

