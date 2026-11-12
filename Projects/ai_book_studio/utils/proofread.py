"""Cheap, deterministic word and sentence checks that run before (and in addition to) the editor's review.

No network and no Streamlit here. ``autocorrect_text`` fixes mistakes that can never be intentional (doubled words, spaces
before punctuation). ``proofread_issues`` reports what cannot be fixed safely by rule (garbled words, a chapter that stops
in the middle of a sentence); the pipeline then sends the text back for an automatic rewrite.

The checks are deliberately conservative: a false alarm costs one extra revision, so only clear faults are reported.
They apply to English only; other languages are checked by the editor and by ``services.language_service``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

# Words that are never repeated on purpose in prose ("that that" and "had had" are valid English, so they are not listed).
_DOUBLED = frozenset(
    "the a an and of to in for on with as at by or but from into his her their its our my your this these those".split()
)
_DOUBLED_WORDS = re.compile(r"\b(" + "|".join(sorted(_DOUBLED)) + r")(?:[ \t]+)\1\b", re.IGNORECASE)
_SPACE_BEFORE_PUNCT = re.compile(r"(?<=\w) +([,.;:!?])(?=\s|$)")
_MULTI_SPACE = re.compile(r"(?<=\S) {2,}(?=\S)")
_WORD = re.compile(r"[A-Za-z][A-Za-z'\u2019]*")
_CONSONANT_RUN = re.compile(r"[bcdfghjklmnpqrstvwxz]{7,}", re.IGNORECASE)  # "y" counts as a vowel (rhythm, symbol)
_LETTER_RUN = re.compile(r"([A-Za-z])\1{3,}")
_END_OK = tuple('.!?\u2026"\')\u201d\u2019*_:')
_FENCE = ("```", "~~~")
_LIST_ITEM = re.compile(r"(?:[-+*]|\d+[.)])\s")
_MAX_REPORTED = 5


def _is_english(language: str) -> bool:
    return (language or "English").strip().lower() == "english"


def _prose_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield (index, line) for plain prose: not headings, list items, quotes, tables, rules or code blocks."""
    in_code = False
    for index, line in enumerate(text.split("\n")):
        stripped = line.strip()
        if stripped.startswith(_FENCE):
            in_code = not in_code
            continue
        if in_code or not stripped:
            continue
        if stripped[0] in "#>|" or _LIST_ITEM.match(stripped) or set(stripped) <= set("-*_= "):
            continue
        yield index, line


def autocorrect_text(text: str, language: str = "English") -> str:
    """Fix mistakes that cannot be intentional: doubled function words, spaces before punctuation, repeated spaces.

    Only English prose is touched; code blocks, headings, lists and tables are left alone.
    """
    if not text or not _is_english(language):
        return text
    lines = text.split("\n")
    for index, line in _prose_lines(text):
        fixed = _DOUBLED_WORDS.sub(lambda m: m.group(1), line)
        fixed = _SPACE_BEFORE_PUNCT.sub(r"\1", fixed)
        lines[index] = _MULTI_SPACE.sub(" ", fixed)
    return "\n".join(lines)


def _garbled_words(prose: str) -> list[str]:
    """English words that cannot be real: seven consonants in a row, one letter repeated four times, or absurdly long."""
    found: dict[str, None] = {}
    for word in _WORD.findall(prose):
        letters = word.replace("'", "").replace("\u2019", "")
        if len(letters) > 28 or _CONSONANT_RUN.search(letters) or _LETTER_RUN.search(letters):
            found.setdefault(word, None)
    return list(found)


def proofread_issues(text: str, language: str = "English", check_ending: bool = True) -> list[str]:
    """Plain-language list of clear word and sentence problems (empty when the text looks clean).

    ``check_ending`` is turned off for short fragments such as a title, which need no final full stop.
    """
    issues: list[str] = []
    if not text or not text.strip() or not _is_english(language):
        return issues
    if "\ufffd" in text:
        issues.append("The text contains broken (replacement) characters.")
    prose_lines = [line for _, line in _prose_lines(text)]
    prose = "\n".join(prose_lines)
    garbled = _garbled_words(prose)
    if garbled:
        quoted = ", ".join(f'"{word}"' for word in garbled[:_MAX_REPORTED])
        issues.append(f"These words look misspelled or garbled; correct each one to a real English word: {quoted}.")
    repeated = _DOUBLED_WORDS.search(prose)
    if repeated:
        issues.append(f'A word is repeated by mistake: "{repeated.group(0)}".')
    if check_ending and prose_lines:
        last = prose_lines[-1].strip()
        if not last.endswith(_END_OK) and len(last.split()) >= 4:
            issues.append(f'The text stops in the middle of a sentence: "...{last[-60:]}". Finish the sentence and end the text properly.')
    return issues
