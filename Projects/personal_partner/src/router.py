"""Nemotron routing: the model decides whether a message needs a live web search, and writes the query."""

from __future__ import annotations

import json
import re
from typing import Any

from .live_info import current_time_note
from .model_client import complete_text


ROUTER_PROMPT = """You are the routing step of a chat assistant. Decide whether the assistant can answer the user's latest message from its own built-in knowledge, or whether it must first run a live web search.

Choose SEARCH when:
- the answer may have changed since your training data: who holds an office or role, a person's current work or details, news, events, elections, sports results, prices, rates, weather, new releases, schedules, rankings, company leaders;
- the question is about a person, place, product, film, or organisation you do not know well or are not sure about;
- the user asks for latest, current, today, now, or recent information;
- you would have to guess, or you could be out of date.

Choose ANSWER when:
- the answer is stable general knowledge you know well (history, science, definitions, facts that do not change);
- it is reasoning, maths, writing, coding, translation, advice, planning, or opinions;
- it is small talk, feelings, companionship, role-play, or a question about this conversation;
- it asks for the date or time (the current date and time are given below).

Resolve follow-up messages such as "and before him?" using the earlier conversation. When you choose SEARCH, write a short, specific search query in English that would find the answer. For local weather or local news, add the user's saved city if one is given.

Reply with only one JSON object and nothing else:
{"action": "ANSWER"}
or
{"action": "SEARCH", "query": "<search query>"}"""

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_TRANSCRIPT_MESSAGES = 6
_TRANSCRIPT_CHARS = 400


def parse_decision(reply: str, latest: str) -> str | None:
    """Return the search query when the model chose SEARCH, otherwise None (answer directly)."""
    reply = (reply or "").strip()
    match = _JSON_OBJECT.search(reply)
    if match:
        try:
            data = json.loads(match.group(0))
        except ValueError:
            data = None
        if isinstance(data, dict):
            if str(data.get("action", "")).strip().upper() != "SEARCH":
                return None
            query = " ".join(str(data.get("query") or latest).split())
            return query[:200] or None
    # Fallback when the model writes the bare word instead of JSON.
    if reply.upper().startswith("SEARCH"):
        return " ".join(latest.split())[:200] or None
    return None


def _transcript(messages: list[dict[str, Any]]) -> str:
    lines = []
    for item in messages[-_TRANSCRIPT_MESSAGES:]:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            lines.append(f"{role}: {' '.join(content.split())[:_TRANSCRIPT_CHARS]}")
    return "\n".join(lines)


def decide_search(
    messages: list[dict[str, Any]],
    preferences: dict[str, Any] | None = None,
    timezone_name: str | None = None,
) -> str | None:
    """Ask Nemotron whether the latest user message needs live web information.

    Returns the search query to run with Tavily, or None when Nemotron should answer alone.
    """
    preferences = preferences or {}
    latest = next(
        (
            str(item.get("content", ""))
            for item in reversed(messages)
            if item.get("role") == "user" and isinstance(item.get("content"), str)
        ),
        "",
    )
    if not latest.strip():
        return None
    city = str(preferences.get("city", "")).strip()
    system = "\n\n".join(
        [
            ROUTER_PROMPT,
            current_time_note(timezone_name),
            f"User's saved city: {city}" if city else "User's saved city: not set.",
        ]
    )
    reply = complete_text(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": "Conversation so far:\n" + _transcript(messages)},
        ],
        max_tokens=200,
    )
    return parse_decision(reply, latest)
