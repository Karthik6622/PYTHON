"""Language hygiene for generated text: detect stray scripts, English leftovers and junk symbols, and clean them.

No network and no Streamlit here. The model-based rewrite lives in ``services.language_service``.
"""

from __future__ import annotations

import re
import unicodedata

NATIVE_SCRIPT_LANGUAGES = {"Tamil": "Tamil", "Hindi": "Devanagari", "Japanese": "Japanese (kana and kanji)"}

# Unicode blocks of the scripts the book languages use.
_TAMIL = "\u0B80-\u0BFF"
_DEVANAGARI = "\u0900-\u097F"
_JAPANESE = "\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF\u3000-\u303F\uFF00-\uFFEF"
_OTHER_INDIC = "\u0980-\u0B7F\u0C00-\u0DFF"  # Bengali, Gurmukhi, Gujarati, Odia, Telugu, Kannada, Malayalam, Sinhala
_OTHER = "\u0400-\u04FF\u0590-\u06FF\u0750-\u077F\u0E00-\u0E7F\u1100-\u11FF\uAC00-\uD7AF"  # Cyrillic, Hebrew, Arabic, Thai, Hangul

_FOREIGN = {
    "Tamil": re.compile(f"[{_DEVANAGARI}{_OTHER_INDIC}{_JAPANESE}{_OTHER}]"),
    "Hindi": re.compile(f"[{_TAMIL}{_OTHER_INDIC}{_JAPANESE}{_OTHER}]"),
    "Japanese": re.compile(f"[{_DEVANAGARI}{_TAMIL}{_OTHER_INDIC}{_OTHER}]"),
}
_FOREIGN_LATIN_LANGUAGES = re.compile(f"[{_DEVANAGARI}{_TAMIL}{_OTHER_INDIC}{_JAPANESE}{_OTHER}]")

_LATIN_WORD = re.compile(r"[A-Za-z\u00C0-\u024F]{2,}")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
_URL = re.compile(r"https?://\S+|www\.\S+")
_PAREN_LATIN = re.compile(r"\s*[(（\[][^()（）\[\]\u0900-\u0DFF\u3040-\u9FFF]*[A-Za-z][^()（）\[\]\u0900-\u0DFF\u3040-\u9FFF]*[)）\]]")

_KEEP_SYMBOLS = set("©®™°№§¶•·‣–—…‘’“”‹›«»¡¿₹€£¥¢±×÷≈≠≤≥%‰′″")
_KEEP_FORMAT = {"\u200c", "\u200d"}  # joiners that Indic scripts need
_REMOVE_ALWAYS = re.compile("[\u00ad\u200b\u200e\u200f\u2060\u2061-\u2064\ufeff\ufffc\ufffd\u202a-\u202e\u2066-\u2069]")
_SPACES = re.compile(r"[ \t\u00a0\u3000]{2,}")
_REPEATED_PUNCT = re.compile(r"([!?.,;:~\-_=*])\1{3,}")
_FULLWIDTH_TO_ASCII = str.maketrans("，。！？：；（）", ",.!?:;()")


def uses_native_script(language: str) -> bool:
    """True for languages that are not written in the Latin alphabet."""
    return language in NATIVE_SCRIPT_LANGUAGES


def language_rules(language: str) -> str:
    """Plain-text rules added to every writing prompt so that the model stays in one language and one script."""
    lang = (language or "English").strip() or "English"
    if lang == "English":
        return (
            "LANGUAGE RULES:\n"
            "- Write only in English. Do not use words, letters or characters from any other language or script.\n"
            "- Use plain punctuation only. No emojis, decorative symbols, arrows or stray characters."
        )
    if uses_native_script(lang):
        script = NATIVE_SCRIPT_LANGUAGES[lang]
        return (
            f"LANGUAGE RULES (strict):\n"
            f"- Write every sentence entirely in natural, fluent {lang}, using only the {script} script.\n"
            f"- Do NOT use English words, English letters or romanised {lang}. Do not add English translations or English words in brackets.\n"
            f"- Names, brands and technical terms that have no common {lang} word must be written phonetically in the {script} script.\n"
            f"- Digits and normal punctuation are allowed. No emojis, decorative symbols, arrows, stray characters or words from any other language.\n"
            f"- Write the way an educated native {lang} author writes a published book: correct grammar, correct spelling, natural vocabulary, no word-by-word translation from English."
        )
    return (
        f"LANGUAGE RULES (strict):\n"
        f"- Write every sentence entirely in natural, fluent {lang}. Do not mix in English words or any other language.\n"
        f"- Use correct spelling, accents and grammar, as a native author of a published book would.\n"
        f"- Use plain punctuation only. No emojis, decorative symbols, arrows or stray characters."
    )


def sanitize_text(text: str, language: str = "English") -> str:
    """Remove junk symbols, emojis, invisible characters and letters of scripts that do not belong to the language.

    Markdown structure (#, *, -, >, backticks) and normal punctuation are kept.
    """
    if not text:
        return ""
    foreign = _FOREIGN.get(language, _FOREIGN_LATIN_LANGUAGES)
    text = _REMOVE_ALWAYS.sub("", text).replace("\u3000", " ")
    if language != "Japanese":
        text = text.translate(_FULLWIDTH_TO_ASCII)
    out: list[str] = []
    for char in text:
        if char in _KEEP_SYMBOLS or char in "\n\t":
            out.append(char)
            continue
        category = unicodedata.category(char)
        if category in {"Co", "Cs", "Cn"}:
            continue
        if category == "Cf" and char not in _KEEP_FORMAT:
            continue
        if category == "Cc":
            out.append(" ")
            continue
        if category == "So" or (category == "Sk" and char not in "^`"):
            continue
        if foreign.match(char):
            continue
        out.append(char)
    cleaned = "".join(out)
    cleaned = _REPEATED_PUNCT.sub(lambda m: m.group(1) * 3 if m.group(1) in "-_=*" else m.group(1), cleaned)
    cleaned = "\n".join(_SPACES.sub(" ", line).rstrip() for line in cleaned.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def latin_words(text: str) -> list[str]:
    """Latin-alphabet words (2+ letters) outside URLs."""
    return _LATIN_WORD.findall(_URL.sub(" ", text))


def has_leftover_english(text: str, language: str) -> bool:
    """True when text in a non-Latin-script language still contains Latin-alphabet words."""
    return uses_native_script(language) and bool(latin_words(text))


def latin_ratio(text: str, language: str) -> float:
    """Share of Latin letters among all letters (0.0 for languages written in Latin letters)."""
    if not uses_native_script(language):
        return 0.0
    plain = _URL.sub(" ", text)
    latin = len(_LATIN_LETTER.findall(plain))
    letters = sum(1 for char in plain if char.isalpha())
    return latin / letters if letters else 0.0


def drop_latin_glosses(text: str, language: str) -> str:
    """Remove bracketed English notes such as ``(Lantern)`` that follow native-script words."""
    if not uses_native_script(language):
        return text
    return _PAREN_LATIN.sub("", text)


def split_paragraphs(text: str) -> list[str]:
    """Split on blank lines, keeping every paragraph (and fenced code block) intact."""
    return re.split(r"\n\s*\n", text.strip()) if text.strip() else []


def is_code_block(paragraph: str) -> bool:
    return paragraph.lstrip().startswith("```") or paragraph.lstrip().startswith("    ")
