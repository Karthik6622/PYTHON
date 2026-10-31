"""Chapter quality-check prompt."""

REVIEW_PROMPT = """You are a fair, experienced book editor. Decide whether the chapter below is ready to publish and, if it is not, tell the author exactly what to fix.

BOOK PLAN:
{book_plan_json}

BOOK BIBLE:
{book_bible_json}

PREVIOUS CHAPTER SUMMARIES:
{previous_chapter_summaries}

CHAPTER BEING REVIEWED: number {chapter_number}, "{chapter_title}"
CHAPTER OBJECTIVE: {chapter_objective}
EXPECTED TOPICS OR SCENES: {key_topics}

CURRENT CHAPTER:
{chapter_content}

{recheck_block}

What to check:

1. The chapter fulfils its objective and covers the expected topics or scenes.
2. Continuity, character, timeline and terminology agree with the bible and the earlier chapters.
3. No harmful repetition, contradictions, filler or content that clearly belongs to another chapter.
4. Paragraphs are complete and the chapter ends properly (no cut-off text or abrupt ending).
5. Writing quality and suitability for the audience.

6. Check the language: the chapter must be entirely in the book's language. Report English words, mixed scripts or garbled characters as an issue.

How to judge:

- Judge quality, never length. The chapter may be shorter or LONGER than any word target. Do not lower the score or list an issue because of its length.
- Report only problems a reader would really notice. Do not penalise personal taste, small wording choices or details the plan leaves open.
- List at most 6 issues, most important first. For each issue say where it is (quote a short phrase) and what is wrong.
- For every issue give one concrete change in "corrections_required" that would resolve it.
- A critical problem is a clear contradiction of established facts or a chapter that misses its objective altogether.

Scoring guide:

- 90-100: excellent.
- 80-89: good and publishable with only minor polish (minor polish alone is not a reason to fail).
- 60-79: real problems that must be fixed (list them).
- Below 60: serious problems such as off-topic, incomplete or contradictory content.

The chapter passes (passed = true) only when the score is 80 or above and there is no critical problem.

Return JSON only:

{
  "passed": true,
  "score": 0,
  "issues": [],
  "corrections_required": [],
  "editor_summary": ""
}

Use an integer score from 0 to 100. "editor_summary" is one or two sentences explaining the verdict.

Format rules (important):
- Write the report itself in English, even when the chapter is in another language. Quote only very short phrases from the chapter.
- Keep it short: each issue and each correction is one sentence.
- Return one complete JSON object with double-quoted strings and no trailing commas. No Markdown and no commentary."""

RECHECK_BLOCK = """THIS IS A RE-CHECK. The chapter was revised after you asked for these changes:

{required_changes}

First verify each change. A problem that was fixed must not be reported again and must not lower the score. Report a new problem only if it is serious (a real contradiction, a missing objective or an incomplete passage); do not add new stylistic preferences. If the requested changes were made and nothing serious remains, the chapter should pass with a score of 80 or above."""
