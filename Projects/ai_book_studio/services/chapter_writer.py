"""Steps 6-7: write chapters one at a time, revise them, and write front and back matter."""

from __future__ import annotations

from config import preset_for
from models.book_models import BookBible, BookPlan, BookProject, ChapterPlan, QualityReport
from prompts.chapter_prompts import (
    CHAPTER_PROMPT,
    CONTINUE_PROMPT,
    FRONT_MATTER_PROMPT,
    GLOSSARY_PROMPT,
    REVISION_PROMPT,
    SECTION_TASKS,
)
from services.language_service import ensure_language
from services.nvidia_client import LLMClient
from utils.language_utils import language_rules
from utils.retry_utils import EmptyResponseError
from utils.text_utils import (
    PageBudget,
    chapter_max_tokens,
    clean_chapter_text,
    compact_json,
    compute_budget,
    format_previous_summaries,
    label,
    render_template,
    section_words,
    strip_reasoning,
)

_BIBLE_LIMIT = 9000
_OUTLINE_LIMIT = 6000


def _bible_json(bible: BookBible | None, limit: int = _BIBLE_LIMIT) -> str:
    return compact_json(bible, limit) if bible is not None else "{}"


def _outline_json(plan: BookPlan, limit: int = _OUTLINE_LIMIT) -> str:
    outline = [
        {"chapter_number": c.chapter_number, "title": c.title, "summary": c.summary} for c in plan.chapters
    ]
    return compact_json(outline, limit)


def write_chapter(llm: LLMClient, project: BookProject, chapter: ChapterPlan) -> str:
    """Write one chapter with its own API request (plus one continuation if the reply was cut off)."""
    plan = project.plan
    assert plan is not None
    prompt = render_template(
        CHAPTER_PROMPT,
        book_title=plan.title,
        book_description=plan.description,
        book_type=plan.book_type,
        audience=plan.audience,
        writing_style=plan.writing_style,
        language=plan.language,
        main_theme=plan.main_theme,
        tone=plan.tone,
        book_bible_json=_bible_json(project.bible),
        book_outline_json=_outline_json(plan),
        previous_chapter_summaries=format_previous_summaries(project.summaries, chapter.chapter_number),
        chapter_number=chapter.chapter_number,
        chapter_title=chapter.title,
        chapter_objective=chapter.objective,
        chapter_summary=chapter.summary,
        key_topics="; ".join(chapter.key_topics) or "Follow the chapter summary.",
        target_words=chapter.target_words,
        language_rules=language_rules(plan.language),
    )
    limit = chapter_max_tokens(int(chapter.target_words * 1.5), plan.language)
    result = llm.generate(prompt, preset_for("chapter", plan.language), max_tokens=limit)
    text = result.text
    if result.truncated:
        tail = text[-2500:]
        follow_up = render_template(
            CONTINUE_PROMPT,
            chapter_objective=chapter.objective,
            language=plan.language,
            chapter_tail=tail,
            language_rules=language_rules(plan.language),
        )
        more = llm.generate(follow_up, preset_for("chapter", plan.language), max_tokens=max(1024, limit // 2))
        text = f"{text.rstrip()}\n\n{more.text.lstrip()}"
    cleaned = clean_chapter_text(text, chapter.chapter_number, chapter.title)
    cleaned = ensure_language(llm, cleaned, plan.language)
    if not cleaned:
        raise EmptyResponseError(f"Chapter {chapter.chapter_number} came back empty.")
    return cleaned


def _fix_list(report: QualityReport, earlier: list[QualityReport]) -> str:
    """Numbered problems and required changes: the newest report first, then anything still open from earlier ones."""
    problems: list[str] = []
    changes: list[str] = []
    for item in [report, *reversed(earlier)]:
        for text, bucket in ((item.issues, problems), (item.corrections_required, changes)):
            for entry in text:
                if entry.strip() and entry.strip().lower() not in {existing.lower() for existing in bucket}:
                    bucket.append(entry.strip())
    lines: list[str] = []
    if problems:
        lines.append("Problems found:")
        lines += [f"{i}. {entry}" for i, entry in enumerate(problems, 1)]
    if changes:
        lines.append("Required changes:")
        lines += [f"{i}. {entry}" for i, entry in enumerate(changes, 1)]
    return "\n".join(lines) or "Improve the overall quality, continuity and completeness of the chapter."


def revise_chapter(
    llm: LLMClient,
    project: BookProject,
    chapter: ChapterPlan,
    content: str,
    report: QualityReport,
    earlier: list[QualityReport] | None = None,
) -> str:
    """Fix the problems the editor found (and any still open from earlier checks). The chapter may grow longer."""
    plan = project.plan
    assert plan is not None
    prompt = render_template(
        REVISION_PROMPT,
        book_plan_json=compact_json(plan, _OUTLINE_LIMIT + 3000),
        book_bible_json=_bible_json(project.bible),
        previous_chapter_summaries=format_previous_summaries(project.summaries, chapter.chapter_number, 4000),
        chapter_number=chapter.chapter_number,
        chapter_title=chapter.title,
        chapter_objective=chapter.objective,
        key_topics="; ".join(chapter.key_topics) or "Follow the chapter summary.",
        chapter_content=content,
        editor_summary=report.editor_summary or "The chapter needs the changes listed below.",
        fix_list=_fix_list(report, earlier or []),
        language=plan.language,
        language_rules=language_rules(plan.language),
    )
    limit = chapter_max_tokens(int(max(chapter.target_words, len(content.split())) * 1.3), plan.language)
    result = llm.generate(prompt, preset_for("revision", plan.language), max_tokens=limit)
    cleaned = clean_chapter_text(result.text, chapter.chapter_number, chapter.title)
    cleaned = ensure_language(llm, cleaned, plan.language)
    return cleaned or content


def write_front_section(
    llm: LLMClient, project: BookProject, section: str, budget: PageBudget | None = None
) -> str:
    """Write a dedication, preface, introduction or conclusion."""
    plan = project.plan
    assert plan is not None
    budget = budget or compute_budget(project.book_input)
    words = 40 if section == "dedication" else section_words(budget, section)
    summaries = format_previous_summaries(project.summaries, before=10_000, limit=5000)
    prompt = render_template(
        FRONT_MATTER_PROMPT,
        section_name=label(section, "English").lower(),
        book_title=plan.title,
        book_description=plan.description,
        book_type=plan.book_type,
        audience=plan.audience,
        writing_style=plan.writing_style,
        language=plan.language,
        main_theme=plan.main_theme,
        tone=plan.tone,
        book_outline_json=_outline_json(plan),
        book_bible_json=_bible_json(project.bible, 5000),
        chapter_summaries=summaries if project.summaries else "Chapters are not written yet; do not describe their details.",
        section_task=SECTION_TASKS[section],
        target_words=words,
        language_rules=language_rules(plan.language),
    )
    result = llm.generate(prompt, preset_for("front_matter", plan.language), max_tokens=chapter_max_tokens(words, plan.language))
    return ensure_language(llm, strip_reasoning(result.text), plan.language)


def collect_glossary_terms(project: BookProject, limit: int = 60) -> list[str]:
    """Unique terms reported in the chapter summaries (in chapter order)."""
    seen: dict[str, None] = {}
    for number in sorted(project.summaries):
        for term in project.summaries[number].new_terms:
            seen.setdefault(term.strip(), None)
    return [term for term in seen if term][:limit]


def write_glossary(llm: LLMClient, project: BookProject) -> str:
    """Build the glossary from terms found in the finished chapters. Returns '' when no terms exist."""
    plan = project.plan
    assert plan is not None
    terms = collect_glossary_terms(project)
    bible = _bible_json(project.bible, 4000)
    if not terms and bible in {"", "{}"}:
        return ""
    prompt = render_template(
        GLOSSARY_PROMPT,
        book_title=plan.title,
        book_type=plan.book_type,
        language=plan.language,
        terms="\n".join(f"- {term}" for term in terms) or "None listed; use the bible.",
        book_bible_json=bible,
        language_rules=language_rules(plan.language),
    )
    result = llm.generate(prompt, "front_matter", max_tokens=max(3000, chapter_max_tokens(600, plan.language)))
    return ensure_language(llm, strip_reasoning(result.text), plan.language)


def author_page_text(project: BookProject) -> str:
    """About-the-author text built only from what the user supplied. Nothing is invented."""
    author = project.book_input.author_name.strip()
    bio = project.book_input.author_bio.strip()
    if bio:
        return bio
    return f"{author} is the author of *{project.title}*."
