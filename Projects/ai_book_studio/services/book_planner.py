"""Step 2-3: generate and validate the book plan."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from config import CONTENT_OPTIONS
from models.book_models import BookInput, BookPlan
from prompts.planning_prompts import PLANNING_PROMPT
from services.language_service import clean_structure
from services.nvidia_client import LLMClient
from utils.language_utils import language_rules, uses_native_script
from utils.retry_utils import ContentPolicyError, PlanValidationError
from utils.text_utils import PageBudget, compute_budget, render_template
from utils.validation_utils import normalize_plan, validate_plan


def apply_illustration_policy(plan: BookPlan, frequency: str) -> BookPlan:
    """Set ``requires_image`` on each chapter from the chosen illustration frequency."""
    for chapter in plan.chapters:
        number = chapter.chapter_number
        if frequency in {"Cover only", "No images"}:
            chapter.requires_image = False
        elif frequency == "One image every two chapters":
            chapter.requires_image = number % 2 == 1
        else:  # one image every chapter, image-heavy
            chapter.requires_image = True
    return plan


def _selected_options(book_input: BookInput) -> str:
    chosen = [label for label, key in CONTENT_OPTIONS.items() if book_input.has(key)]
    return ", ".join(chosen) if chosen else "None"


def _validate_model_plan(data: dict[str, Any]) -> BookPlan:
    if data.get("refused"):
        raise ContentPolicyError(str(data.get("reason") or "The model declined this request."))
    if not isinstance(data.get("chapters"), list) or not data["chapters"]:
        raise ValueError("The plan has no chapters (the reply was probably cut off).")
    return BookPlan.model_validate(data)


def generate_plan(
    llm: LLMClient,
    book_input: BookInput,
    budget: PageBudget | None = None,
    on_step: Callable[[str], None] | None = None,
) -> BookPlan:
    """Ask the model for a plan, then enforce the user's choices and repair the structure.

    ``on_step`` is told "designing" before the model call and "checking" after it.
    """
    budget = budget or compute_budget(book_input)
    prompt = render_template(
        PLANNING_PROMPT,
        book_idea=book_input.book_idea.strip(),
        preferred_title=book_input.preferred_title.strip() or "None (create a title)",
        author_name=book_input.author_name.strip(),
        book_type=book_input.effective_book_type,
        audience=book_input.audience,
        writing_style=book_input.writing_style,
        language=book_input.language,
        page_count=book_input.pages,
        target_word_count=budget.target_words,
        recommended_chapters=budget.recommended_chapters,
        illustration_frequency=book_input.illustration_frequency,
        image_style=book_input.image_style,
        selected_content_options=_selected_options(book_input),
        language_rules=language_rules(book_input.language),
    )
    plan_tokens = min(16000, max(6000, 3000 + 450 * budget.recommended_chapters))
    if book_input.language != "English":
        plan_tokens = min(16384, int(plan_tokens * 1.8))
    if on_step:
        on_step("designing")
    plan: BookPlan = llm.generate_json(
        prompt, "planning", max_tokens=plan_tokens, validator=_validate_model_plan
    )
    if on_step:
        on_step("checking")

    if uses_native_script(book_input.language):
        # Chapter titles, objectives and summaries feed every later prompt, so wrong-language words are repaired here.
        skip = {"author", "book_type", "audience", "language", "writing_style", "visual_style", "image_concept"}
        if book_input.preferred_title.strip():
            skip.add("title")
        plan = BookPlan.model_validate(clean_structure(llm, plan.model_dump(), book_input.language, frozenset(skip)))
    # The user's selections always win over whatever the model echoed back.
    plan.author = book_input.author_name.strip()
    plan.book_type = book_input.effective_book_type
    plan.audience = book_input.audience
    plan.language = book_input.language
    plan.writing_style = book_input.writing_style
    plan.estimated_pages = book_input.pages
    if book_input.preferred_title.strip():
        plan.title = book_input.preferred_title.strip()
    if not plan.visual_style.strip():
        plan.visual_style = book_input.image_style
    elif book_input.image_style.lower() not in plan.visual_style.lower():
        plan.visual_style = f"{book_input.image_style}. {plan.visual_style}"

    normalize_plan(plan, budget.target_words)
    apply_illustration_policy(plan, book_input.illustration_frequency)
    report = validate_plan(plan, budget.target_words)
    if not report.ok:
        raise PlanValidationError("The generated plan is not valid: " + " ".join(report.errors))
    return plan
