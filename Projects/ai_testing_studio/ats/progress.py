"""Progress reporting shared by services: a plain ``progress(message)`` callback still works, a job reporter also gets a fraction."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

ProgressFn = Callable[..., None]


def report(progress: ProgressFn | None, message: str, fraction: float | None = None, ceiling: float | None = None) -> None:
    """Send a status line. ``fraction`` (0..1) is where the bar should be; ``ceiling`` is how far it may creep while a long call runs."""
    if progress is None:
        return
    if getattr(progress, "supports_fraction", False):
        progress(message, fraction, ceiling)
    else:
        progress(message)


def reporter(say: Callable[[str, float | None, float | None], None]) -> Any:
    """Mark ``say`` as able to receive fractions."""
    say.supports_fraction = True  # type: ignore[attr-defined]
    return say
