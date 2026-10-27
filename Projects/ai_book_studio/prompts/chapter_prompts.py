"""Chapter, continuity-summary, revision and front/back-matter prompts."""

CHAPTER_PROMPT = """You are an experienced professional author writing one chapter of a complete book.

BOOK TITLE:
{book_title}

BOOK DESCRIPTION:
{book_description}

BOOK TYPE:
{book_type}

TARGET AUDIENCE:
{audience}

WRITING STYLE:
{writing_style}

LANGUAGE:
{language}

MAIN THEME:
{main_theme}

TONE:
{tone}

STORY OR CONTENT BIBLE:
{book_bible_json}

COMPLETE BOOK OUTLINE:
{book_outline_json}

PREVIOUS CHAPTER SUMMARIES:
{previous_chapter_summaries}

CURRENT CHAPTER NUMBER:
{chapter_number}

CURRENT CHAPTER TITLE:
{chapter_title}

CURRENT CHAPTER OBJECTIVE:
{chapter_objective}

CURRENT CHAPTER SUMMARY:
{chapter_summary}

KEY TOPICS OR SCENES:
{key_topics}

TARGET LENGTH:
At least about {target_words} words. Go longer whenever the story or subject needs it; quality and completeness matter more than any exact length.

Write the complete chapter.

Requirements:

1. Write polished, publication-quality content.
2. Follow the selected language and writing style.
3. Stay focused on the current chapter.
4. Fulfil the chapter objective.
5. Cover every required topic or scene.
6. Maintain continuity with previous chapters.
7. Preserve character, location, timeline, and terminology consistency.
8. Avoid repeating content from previous chapters.
9. Use meaningful headings and sections when appropriate.
10. For nonfiction, include clear explanations and practical examples where useful.
11. For fiction, include natural descriptions, dialogue, emotion, action, and scene transitions where appropriate.
12. Avoid filler written only to increase length.
13. Do not mention AI, prompts, tokens, models, word targets, or the generation process.
14. Do not write content belonging to future chapters.
15. Do not include the chapter number or title because the application will add them during formatting.
16. Return only the chapter content.
17. The content must be original and must not imitate a living author's distinctive writing style.
18. Use Markdown only for headings (##), bullet lists, emphasis and scene breaks (a line with ---). Separate paragraphs with a blank line."""

CONTINUE_PROMPT = """The chapter below was cut off before it finished. Continue it from exactly where it stops and bring the chapter to a complete, satisfying end.

CURRENT CHAPTER OBJECTIVE:
{chapter_objective}

LANGUAGE:
{language}

CHAPTER SO FAR (last part):
{chapter_tail}

Return only the continuation text. Do not repeat anything that is already written."""

SUMMARY_PROMPT = """Create a continuity summary for the following completed chapter.

BOOK BIBLE:
{book_bible_json}

CHAPTER NUMBER:
{chapter_number}

CHAPTER TITLE:
{chapter_title}

CHAPTER CONTENT:
{chapter_content}

Return JSON containing:

{
  "chapter_number": 0,
  "chapter_title": "",
  "important_events_or_points": [],
  "character_changes": [],
  "new_locations": [],
  "new_terms": [],
  "unresolved_items": [],
  "continuity_notes_for_next_chapter": []
}

Write the values in {language}. Return valid JSON only.
Do not include Markdown or additional commentary."""

REVISION_PROMPT = """You are the author revising one chapter after an editor's review. Fix exactly what the editor found and keep everything that already works.

BOOK PLAN:
{book_plan_json}

BOOK BIBLE:
{book_bible_json}

PREVIOUS CHAPTER SUMMARIES:
{previous_chapter_summaries}

CHAPTER: number {chapter_number}, "{chapter_title}"
CHAPTER OBJECTIVE: {chapter_objective}
EXPECTED TOPICS OR SCENES: {key_topics}

CURRENT CHAPTER:
{chapter_content}

WHY THE EDITOR DID NOT PASS IT:
{editor_summary}

PROBLEMS FOUND AND CHANGES REQUIRED:
{fix_list}

Method:

1. For every item above, find the passage involved and rewrite or add what is needed to resolve it properly. Add missing scenes or topics in full, remove or merge repeated parts, correct contradictions using the bible and the earlier summaries, finish incomplete passages and give the chapter a complete ending.
2. Keep every passage that was not criticised exactly as it is.
3. Length is not a problem: the chapter may become longer than before. Never cut good material just to be shorter.
4. Maintain continuity and the approved tone and writing style.
5. Write in {language}.
6. Do not include the chapter number or title.
7. Do not mention the editor, the review or the generation process.
8. Return only the complete revised chapter."""

FRONT_MATTER_PROMPT = """You are an experienced professional author writing the {section_name} of a complete book.

BOOK TITLE:
{book_title}

BOOK DESCRIPTION:
{book_description}

BOOK TYPE:
{book_type}

TARGET AUDIENCE:
{audience}

WRITING STYLE:
{writing_style}

LANGUAGE:
{language}

MAIN THEME:
{main_theme}

TONE:
{tone}

BOOK OUTLINE:
{book_outline_json}

STORY OR CONTENT BIBLE:
{book_bible_json}

CHAPTER SUMMARIES:
{chapter_summaries}

TASK:
{section_task}

Requirements:
- Approximately {target_words} words.
- Write in {language} in the approved tone.
- Do not include the section heading; the application adds it.
- Do not mention AI, prompts or the generation process.
- Do not invent facts about the author, real people or events.
- Return only the {section_name} text."""

SECTION_TASKS = {
    "dedication": (
        "Write a short, warm dedication. Keep it generic enough to suit the author, for example dedicating the book "
        "to readers, curiosity or the people who inspire us. Do not name real people."
    ),
    "preface": (
        "Write a preface that explains why this book exists, what the reader will experience, and how to approach it. "
        "Do not reveal major plot twists or later chapter content. Do not claim personal experiences for the author."
    ),
    "introduction": (
        "Write an introduction that sets up the world, subject or problem, previews the journey without spoiling it, "
        "and prepares the reader for Chapter 1."
    ),
    "conclusion": (
        "Write a conclusion that brings the book to a satisfying close, reflects on the main theme, and (for nonfiction) "
        "summarises key takeaways and next steps. Stay consistent with the chapter summaries."
    ),
}

GLOSSARY_PROMPT = """Create a glossary for a book.

BOOK TITLE:
{book_title}

BOOK TYPE:
{book_type}

LANGUAGE:
{language}

TERMS FOUND IN THE CHAPTERS:
{terms}

BOOK BIBLE:
{book_bible_json}

Rules:
- Use only terms from the list or the bible. Choose the 10 to 30 most useful ones.
- Define each term clearly and briefly in {language}, consistent with the book.
- For nonfiction do not invent facts, sources or quotations. For fiction define in-world terms as the book uses them.
- Sort alphabetically.
- Format every entry as a Markdown bullet: - **Term**: definition
- Return only the list."""
