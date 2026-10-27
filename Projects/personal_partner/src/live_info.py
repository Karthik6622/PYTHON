"""Real-time facts (current date/time and weather) that a language model cannot know on its own."""

from __future__ import annotations

import logging
import re
import ssl
import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

import httpx


LOGGER = logging.getLogger("kindspace.live_info")

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_WEATHER_INTENT = re.compile(
    r"\b(weather|forecast|temperature|humidity|umbrella|raining|rainy|sunny|windy|will it rain|is it (?:hot|cold|raining|sunny))\b",
    re.IGNORECASE,
)
_CITY = re.compile(
    r"\b(?:in|at|for|near|around)\s+([A-Za-z][A-Za-z .'\-]{1,40}?)(?=\s*(?:\?|\.|,|!|$|\b(?:today|now|tonight|tomorrow|right now|this|please|currently)\b))",
    re.IGNORECASE,
)
_NOT_A_CITY = {"today", "tomorrow", "tonight", "now", "here", "me", "my area", "my city", "this week", "the morning", "general"}

_WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light showers", 81: "showers", 82: "heavy showers", 85: "snow showers", 86: "snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail",
}


def resolve_timezone(name: str | None) -> tuple[Any, str, bool]:
    """Return (tzinfo, label, known). Falls back to UTC when the browser timezone is unavailable."""
    if name:
        try:
            return ZoneInfo(name), name, True
        except Exception:
            pass
    return timezone.utc, "UTC", False


def current_time_note(tz_name: str | None = None) -> str:
    tzinfo, label, known = resolve_timezone(tz_name)
    now = datetime.now(tzinfo)
    stamp = f"{now.strftime('%A, %d %B %Y')}, {now.strftime('%I:%M %p').lstrip('0')} ({label})"
    note = (
        f"Current date and time for the user: {stamp}. "
        "You DO know today's date and time from this line; answer date, day, and time questions directly and "
        "work out 'tomorrow', 'yesterday', or 'next Friday' from it. Never say you lack access to the date."
    )
    if not known:
        note += " The user's timezone is unknown, so this is UTC; mention that if the exact local time matters."
    return note


def wants_weather(text: str) -> bool:
    return bool(_WEATHER_INTENT.search(text or ""))


def extract_city(text: str) -> str | None:
    for match in _CITY.finditer(text or ""):
        city = match.group(1).strip(" .,'-")
        if city and city.casefold() not in _NOT_A_CITY and len(city) >= 2:
            return city
    return None


@lru_cache(maxsize=128)
def _fetch_weather(city: str, bucket: int) -> str:  # noqa: ARG001 - bucket only expires the cache
    # The system trust store also works behind corporate proxies that re-sign HTTPS traffic.
    with httpx.Client(timeout=8, verify=ssl.create_default_context()) as client:
        geo = client.get(_GEOCODE_URL, params={"name": city, "count": 1, "language": "en", "format": "json"})
        geo.raise_for_status()
        results = geo.json().get("results") or []
        if not results:
            return f"No place called '{city}' was found by the weather service."
        place = results[0]
        forecast = client.get(
            _FORECAST_URL,
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": 3,
            },
        )
        forecast.raise_for_status()
        data = forecast.json()
    current = data.get("current", {})
    units = data.get("current_units", {})
    name = ", ".join(part for part in (place.get("name"), place.get("admin1"), place.get("country")) if part)
    lines = [
        f"Live weather for {name} (source: Open-Meteo, observed {current.get('time', 'now')} local time):",
        f"Now: {_WMO.get(current.get('weather_code'), 'unknown conditions')}, {current.get('temperature_2m')}{units.get('temperature_2m', '°C')} "
        f"(feels like {current.get('apparent_temperature')}{units.get('apparent_temperature', '°C')}), "
        f"humidity {current.get('relative_humidity_2m')}%, wind {current.get('wind_speed_10m')} {units.get('wind_speed_10m', 'km/h')}, "
        f"precipitation {current.get('precipitation')} {units.get('precipitation', 'mm')}.",
    ]
    daily = data.get("daily", {})
    for index, day in enumerate(daily.get("time", [])):
        label = ("Today", "Tomorrow", "Day after tomorrow")[index] if index < 3 else day
        lines.append(
            f"{label} ({day}): {_WMO.get(daily['weather_code'][index], 'unknown')}, "
            f"{daily['temperature_2m_min'][index]} to {daily['temperature_2m_max'][index]}{units.get('temperature_2m', '°C')}, "
            f"rain chance {daily['precipitation_probability_max'][index]}%."
        )
    return "\n".join(lines)


def weather_note(user_texts: list[str], default_city: str = "") -> str | None:
    """Build a system note with live weather when the latest user message asks about it."""
    if not user_texts or not wants_weather(user_texts[-1]):
        return None
    city = next((found for text in reversed(user_texts[-4:]) if (found := extract_city(text))), None) or default_city.strip()
    if not city:
        return (
            "The user asked about the weather but no city is known. Do not guess or invent weather. "
            "Warmly ask which city they mean (they can also save a city in Settings)."
        )
    try:
        report = _fetch_weather(city[:60], int(time.time() // 600))
    except Exception as exc:
        LOGGER.warning("Weather lookup failed: %s: %s", type(exc).__name__, exc)
        return (
            f"A live weather lookup for '{city}' failed just now. Do not invent weather. Say you couldn't fetch it "
            "right now and suggest a weather app, then offer to help with something else."
        )
    return (
        f"{report}\nUse these live numbers to answer in a friendly, natural way (convert units only if asked). "
        "Do not claim data you were not given."
    )
