"""Prompt that repairs text with words or characters of the wrong language."""

LANGUAGE_FIX_PROMPT = """You are a native {language} copy editor. The passage below belongs to a published book written in {language}, but it contains English words, romanised text, words of another language or stray symbols.

Rewrite the passage so that it is correct, natural {language}:

1. Every word must be {language}, written only in the {script} script. Replace each English or foreign word with the natural {language} word.
2. A name, brand or technical term with no common {language} word must be written phonetically in the {script} script.
3. Do not add English translations, English words in brackets, notes or explanations.
4. Keep the meaning, the tone, the order of ideas, the paragraph breaks and the Markdown (## headings, - bullets, *emphasis*) exactly as they are.
5. Digits and normal punctuation are allowed. Use no emojis and no decorative symbols.
6. Return only the corrected passage.

PASSAGE:
{passage}"""
