"""Book-planning prompt."""

PLANNING_PROMPT = """You are an expert author, developmental editor, publishing planner, and book architect.

Create a complete and coherent book plan from the information below.

BOOK IDEA:
{book_idea}

PREFERRED TITLE:
{preferred_title}

AUTHOR:
{author_name}

BOOK TYPE:
{book_type}

TARGET AUDIENCE:
{audience}

WRITING STYLE:
{writing_style}

LANGUAGE:
{language}

TARGET PAGE COUNT:
{page_count}

ESTIMATED TARGET WORD COUNT:
{target_word_count}

RECOMMENDED NUMBER OF CHAPTERS:
{recommended_chapters}

ILLUSTRATION FREQUENCY:
{illustration_frequency}

IMAGE STYLE:
{image_style}

CONTENT OPTIONS:
{selected_content_options}

Instructions:

1. Create an engaging and relevant title unless the user supplied a preferred title.
2. Create an optional subtitle.
3. Write a short description suitable for the back cover.
4. Define the primary theme, tone, and intended reader experience.
5. Select an appropriate number of chapters for the available word count.
6. Create a logical chapter sequence.
7. Give every chapter:
   - chapter number
   - chapter title
   - chapter objective
   - short chapter summary
   - key topics, scenes, or concepts
   - target word count
   - whether an illustration is required
   - illustration concept
8. Make the chapters collectively tell a complete story or explain the full subject.
9. Avoid duplicate chapter themes and repeated explanations.
10. Maintain logical progression between chapters.
11. Ensure the sum of chapter word targets is close to the requested target word count.
12. Create one consistent visual-style description for all images.
13. For fiction, establish the beginning, development, conflict, climax, and resolution.
14. For nonfiction, establish a logical educational progression from fundamentals to advanced or practical content.
15. Ensure the book has a satisfying ending or conclusion.
16. Do not write the chapters yet.
17. Return valid JSON only.
18. Do not wrap the JSON in Markdown.
19. Do not add commentary before or after the JSON.
20. Write all text values (title, chapter titles, summaries and so on) in the requested language. Keep the JSON keys in English.

Return this schema:

{
  "title": "",
  "subtitle": "",
  "author": "",
  "book_type": "",
  "audience": "",
  "language": "",
  "writing_style": "",
  "description": "",
  "main_theme": "",
  "tone": "",
  "estimated_pages": 0,
  "estimated_words": 0,
  "visual_style": "",
  "chapters": [
    {
      "chapter_number": 1,
      "title": "",
      "objective": "",
      "summary": "",
      "key_topics": [],
      "target_words": 0,
      "requires_image": true,
      "image_concept": ""
    }
  ]
}"""
