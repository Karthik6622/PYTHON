"""Image-prompt generation prompts (Nemotron writes the prompts; a separate service draws the pictures)."""

CHAPTER_IMAGE_PROMPT = """Create one detailed image-generation prompt for an illustration accompanying this book chapter.

BOOK TITLE:
{book_title}

BOOK TYPE:
{book_type}

TARGET AUDIENCE:
{audience}

APPROVED VISUAL STYLE:
{visual_style}

CHARACTER AND LOCATION CONTINUITY:
{relevant_book_bible_information}

CHAPTER TITLE:
{chapter_title}

CHAPTER SUMMARY:
{chapter_summary}

IMAGE CONCEPT:
{image_concept}

Create a detailed visual prompt containing:

- Main subject
- Character appearance
- Clothing
- Environment
- Important objects
- Composition
- Camera angle
- Lighting
- Color palette
- Mood
- Image style
- Aspect ratio ({orientation})
- Age suitability

Requirements:

- Preserve character and location consistency.
- The image must represent the chapter accurately.
- Do not include text.
- Do not include numbers.
- Do not include a book title.
- Do not include captions.
- Do not include logos.
- Do not include signatures.
- Do not include watermarks.
- Do not include unreadable background letters.
- Write the prompt in English, whatever the language of the book.
- Return only the image-generation prompt."""

COVER_IMAGE_PROMPT = """Create a professional, publishing-quality front-cover artwork prompt.

BOOK TITLE:
{book_title}

BOOK DESCRIPTION:
{book_description}

BOOK TYPE:
{book_type}

TARGET AUDIENCE:
{audience}

MAIN THEME:
{main_theme}

VISUAL STYLE:
{visual_style}

CHARACTER AND LOCATION DETAILS:
{relevant_book_bible_information}

Create an eye-catching vertical composition suitable for a commercial book cover.

The artwork must include:

- A strong focal subject
- A clear foreground, middle ground, and background where appropriate
- Professional lighting
- A consistent color palette
- Sufficient visual contrast
- Genre-appropriate mood
- Space in the composition where the application can later add title and author text

Composition rules (important):

- The main character or focal subject must be centred in the middle of the frame, with the head and face fully visible, sharp and unobstructed.
- Keep the top 25% of the image and the bottom 12% free of faces and key details (calm sky, soft background or plain scenery), because title and author bands are added there.
- Show the character from the waist or knees up, not cropped at the head, and facing the viewer or in a three-quarter view.
- One clear focal point; no clutter around the face.
Requirements:

- Do not render the book title.
- Do not render the subtitle.
- Do not render the author name.
- Do not include letters.
- Do not include logos.
- Do not include a watermark.
- Do not include a signature.
- Use a portrait book-cover aspect ratio.
- Write the prompt in English, whatever the language of the book.
- Return only the image-generation prompt.

Generate the artwork without text."""

NO_TEXT_SUFFIX = (
    " Strictly no text, no letters, no numbers, no captions, no logos, no signatures and no watermarks anywhere in the image."
)
