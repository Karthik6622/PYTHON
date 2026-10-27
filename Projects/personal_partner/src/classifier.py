"""Question classifier: decides whether a message needs live web information (Tavily) or only the model (Nemotron)."""

from __future__ import annotations

import re


# Questions about the clock or calendar are answered from the current date/time note, not the web.
_DATE_TIME = re.compile(
    r"\b(what(?:'s| is)?\s+(?:the\s+)?(?:date|day|time)\b|what\s+time\b|today'?s\s+date|what\s+day\s+is|which\s+day\s+is)",
    re.IGNORECASE,
)

# Words and years that signal information which changes over time.
_CURRENT = re.compile(
    r"\b("
    r"current|currently|latest|recent|recently|newest|upcoming|breaking|news|headlines|"
    r"right now|today|tonight|yesterday|this week|this month|this year|last week|"
    r"weather|forecast|temperature|"
    r"price|prices|stock|stocks|exchange rate|live scores?|match score|"
    r"who won|election results?|released|new release|release date|box office|"
    r"prime minister|president|governor|mayor|ceo|chief minister"
    r")\b"
    r"|\b20(?:2[4-9]|[3-9]\d)\b",
    re.IGNORECASE,
)

# "cm" is a role only when it is not a measurement such as "10 cm" or "10cm".
_CM_ROLE = re.compile(r"(?<!\d\s)(?<!\d)\bcm\b", re.IGNORECASE)

_FOLLOW_UP_START = re.compile(r"^(and|also|what|who|how|which|when|where|why|then)\b", re.IGNORECASE)


def needs_current_info(text: str, previous: str | None = None) -> bool:
    """Return True when the message needs live web results.

    `previous` is the message before this one. Short follow-ups such as "and before him?"
    inherit the answer type of the previous message.
    """
    text = " ".join((text or "").split())
    if not text or _DATE_TIME.search(text):
        return False
    if _CURRENT.search(text) or _CM_ROLE.search(text):
        return True
    is_follow_up = len(text.split()) < 5 and (text.endswith("?") or bool(_FOLLOW_UP_START.match(text)))
    if previous and is_follow_up:
        return needs_current_info(previous)
    return False
