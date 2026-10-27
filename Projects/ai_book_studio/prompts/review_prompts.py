"""Chapter quality-check prompt."""

REVIEW_PROMPT = """You are a strict book editor.

Evaluate the current chapter against the approved book plan and continuity bible.

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

Check:

1. Chapter objective completion
2. Coverage of expected topics or scenes
3. Continuity
4. Character consistency
5. Timeline consistency
6. Terminology consistency
7. Repetition
8. Contradictions
9. Writing quality
10. Age and audience suitability
11. Incomplete paragraphs
12. Abrupt ending
13. Unnecessary filler
14. Content that belongs in another chapter

Return JSON only:

{
  "passed": true,
  "score": 0,
  "issues": [],
  "corrections_required": [],
  "editor_summary": ""
}

Use an integer score from 0 to 100.

A chapter passes only when its score is 80 or above and there are no critical continuity errors."""
