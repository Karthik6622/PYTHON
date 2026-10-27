"""Tavily web search for questions that need current information."""

from __future__ import annotations

import logging
import os
import re
import ssl
import time
from functools import lru_cache
from typing import Any

import httpx
import streamlit as st

from .classifier import needs_current_info


LOGGER = logging.getLogger("kindspace.web_search")

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
_MAX_RESULTS = 5
_SNIPPET_CHARS = 500
_CACHE_SECONDS = 900  # 15 minutes; repeated questions reuse the same results


def tavily_api_key() -> str:
    """Read TAVILY_API_KEY from Streamlit secrets first, then from the environment (.env)."""
    try:
        value = st.secrets.get("TAVILY_API_KEY")
    except Exception:
        value = None
    key = str(value if value not in (None, "") else os.environ.get("TAVILY_API_KEY", "")).strip()
    if not key or key.casefold().startswith(("your-", "tvly-your")):
        return ""
    return key


@lru_cache(maxsize=128)
def _search_cached(query: str, bucket: int) -> tuple[dict[str, Any], ...]:  # noqa: ARG001 - bucket only expires the cache
    key = tavily_api_key()
    if not key:
        raise RuntimeError("TAVILY_API_KEY is not configured")
    with httpx.Client(timeout=15, verify=ssl.create_default_context()) as client:
        response = client.post(
            TAVILY_SEARCH_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "query": query,
                "search_depth": "basic",
                "max_results": _MAX_RESULTS,
                "include_answer": False,
            },
        )
        response.raise_for_status()
        results = response.json().get("results") or []
    return tuple(
        {
            "title": str(item.get("title", "")).strip(),
            "url": str(item.get("url", "")).strip(),
            "content": " ".join(str(item.get("content", "")).split())[:_SNIPPET_CHARS],
            "published": str(item.get("published_date") or "").strip(),
        }
        for item in results[:_MAX_RESULTS]
        if isinstance(item, dict)
    )


def _with_city(query: str, default_city: str) -> str:
    """Add the saved city to weather questions that do not name a place."""
    city = default_city.strip()
    if city and re.search(r"\b(weather|forecast|temperature)\b", query, re.IGNORECASE) and not re.search(
        r"\bin\s+[a-z]", query, re.IGNORECASE
    ):
        return f"{query} in {city}"
    return query


def current_info_note(user_texts: list[str], default_city: str = "") -> str | None:
    """Return a system note with Tavily results when the latest question needs current information.

    Returns None for questions that Nemotron should answer alone.
    """
    if not user_texts:
        return None
    latest = " ".join(user_texts[-1].split())
    previous = user_texts[-2] if len(user_texts) > 1 else None
    if not needs_current_info(latest, previous):
        return None

    query = latest
    if previous and len(latest.split()) < 5 and needs_current_info(previous):
        query = f"{previous} {latest}"  # short follow-up: search with the earlier question for context
    query = _with_city(query[:300], default_city)

    if not tavily_api_key():
        return (
            "Live web search is not set up (TAVILY_API_KEY is missing). The user asked something that needs current "
            "information. Do not guess or present old facts as current; say honestly that you can't check live "
            "information right now."
        )
    try:
        results = _search_cached(query, int(time.time() // _CACHE_SECONDS))
    except Exception as exc:
        LOGGER.warning("Tavily search failed: %s: %s", type(exc).__name__, exc)
        return (
            "A live web search for this question failed just now. Do not guess or present old facts as current; "
            "say you couldn't check the latest information right now."
        )
    if not results:
        return (
            "A live web search found no results for this question. Say you couldn't find current information "
            "rather than guessing."
        )

    lines = [f'Current web results (Tavily search, fetched just now for: "{query}").']
    for index, item in enumerate(results, start=1):
        published = f" (published {item['published']})" if item["published"] else ""
        lines.append(f"{index}. {item['title']}{published} - {item['url']}\n   {item['content']}")
    lines.append(
        "Use these results to answer the user's current question directly and naturally. Name the people, films, "
        "or facts they give, mention the source site briefly, and say so if the results do not fully answer it. "
        "Do not claim anything the results do not say."
    )
    return "\n".join(lines)
