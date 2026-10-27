"""Story and content bible prompt."""

BIBLE_PROMPT = """You are creating a continuity bible for a professionally published book.

BOOK PLAN:
{book_plan_json}

Create a detailed continuity bible that will be supplied while writing every chapter.

For fiction, include characters, physical appearance, clothing, personality, motivation, relationships, locations, chronology, world rules, important objects, conflicts, and character arcs.

For nonfiction, include terminology, definitions, assumptions, learning objectives, example conventions, chapter dependencies, and consistency rules.

Use these JSON keys.
Fiction:
  "characters": [{"name", "role", "appearance", "clothing", "personality", "motivation", "relationships"}],
  "locations": [{"name", "description", "significance"}],
  "timeline": [], "world_rules": [], "important_objects": [], "main_conflict": "", "character_arcs": [],
  "ending_constraints": [], "terms_and_naming": []
Nonfiction:
  "terminology": [{"term", "definition"}], "style_guidelines": [], "important_concepts": [], "source_requirements": [],
  "assumptions": [], "learning_outcomes": [], "example_conventions": [], "chapter_dependencies": [], "consistency_rules": [],
  "characters": [], "locations": []

Write the values in the language of the book ({language}). Keep the JSON keys in English.

Return valid JSON only.
Do not include Markdown or additional commentary."""
