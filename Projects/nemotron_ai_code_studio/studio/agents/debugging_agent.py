"""Debugging agent: turns failing output into a focused brief (failing locations plus the code around them) for the model."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..services.repository_service import ActiveRepository
from ..tools.devtools import parse_problems

_PY_FRAME = re.compile(r'File "(?P<path>[^"]+)", line (?P<line>\d+)')
_PYTEST_FAIL = re.compile(r"^(?:FAILED|ERROR)\s+(?P<path>[\w./\\\-]+\.py)::")
SNIPPET_RADIUS = 12
MAX_LOCATIONS = 6


@dataclass
class DebugBrief:
    text: str
    locations: list[tuple[str, int]] = field(default_factory=list)


class DebuggingAgent:
    def locate(self, repo: ActiveRepository, output: str) -> list[tuple[str, int]]:
        found: list[tuple[str, int]] = []

        def add(raw_path: str, line: int) -> None:
            normalized = raw_path.replace("\\", "/")
            match = next((p for p in repo.index.files if p == normalized or normalized.endswith("/" + p) or p.endswith("/" + normalized)), None)
            if match and (match, line) not in found:
                found.append((match, line))

        for hit in _PY_FRAME.finditer(output):  # the last frames are the most relevant, so they are added last and sorted first below
            add(hit.group("path").replace(str(repo.path).replace("\\", "/") + "/", ""), int(hit.group("line")))
        for problem in parse_problems(output):
            add(problem["path"], problem["line"])
        for raw in output.splitlines():
            match = _PYTEST_FAIL.match(raw.strip())
            if match:
                add(match.group("path"), 1)
        return list(reversed(found))[:MAX_LOCATIONS]

    def diagnose(self, repo: ActiveRepository, output: str) -> DebugBrief:
        locations = self.locate(repo, output)
        parts = ["Failure output (trimmed):", output.strip()[-5000:]]
        for path, line in locations:
            try:
                lines = (repo.path / path).read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            start, end = max(1, line - SNIPPET_RADIUS), min(len(lines), line + SNIPPET_RADIUS)
            snippet = "\n".join(f"{n:>5} | {lines[n - 1]}" for n in range(start, end + 1))
            parts.append(f"\nCode around {path}:{line}\n{snippet}")
        return DebugBrief("\n".join(parts), locations)
