"""ContextEngine: picks the few repository files (and the right sections of them) that matter for one request.

The whole repository is never sent to the model. For each request the engine extracts filenames, symbols and concepts,
ranks files by filename / definition / content / dependency relevance, then loads sections within a token budget.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import settings
from .indexing_service import FileEntry, RepositoryIndex, tokenize
from .workspace_service import WorkspaceService

STOPWORDS = frozenset(
    """the and for with that this from have has had are was were been being into onto your you our can could would should will shall may might
    please make fix add update change create remove delete show explain how why what when where which who whom does did done not but any all some
    use using used need needs want wants like also just then than there their they them its it's issue problem bug error code file files function
    functions class classes method methods work works working about after before over under again more most other such only own same too very
    help look looks check find get set run test tests implement implementation write read""".split()
)
_FILENAME_RE = re.compile(r"[\w./\\\-]+\.[A-Za-z0-9]{1,6}\b")
_BACKTICK_RE = re.compile(r"`([^`\n]{2,80})`")
_IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")
MAX_FILES = 12


def estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1


@dataclass
class ContextFile:
    path: str
    reason: str
    score: float
    ranges: list[tuple[int, int]] = field(default_factory=list)
    content: str = ""

    def public(self) -> dict[str, Any]:
        return {"path": self.path, "reason": self.reason, "score": round(self.score, 1), "ranges": [list(r) for r in self.ranges]}


@dataclass
class ContextBundle:
    files: list[ContextFile]
    concepts: list[str]
    symbols: list[str]
    filenames: list[str]
    repo_map: str
    tokens: int = 0

    def to_prompt(self) -> str:
        parts = ["Repository map:\n" + self.repo_map]
        if self.files:
            parts.append(
                "Files selected by the context engine for this request. Line numbers are display-only and are not part of the file text.\n"
            )
            for item in self.files:
                parts.append(f"### {item.path}  ({item.reason})\n{item.content}")
        else:
            parts.append("The context engine found no files that clearly match this request. Use search_code / list_files to explore.")
        return "\n\n".join(parts)

    def public(self) -> list[dict[str, Any]]:
        return [item.public() for item in self.files]


def _variants(word: str) -> set[str]:
    out = {word}
    for suffix in ("ing", "ed", "es", "s", "er"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            out.add(word[: -len(suffix)])
    return out


def extract_request_terms(request: str) -> tuple[list[str], list[str], list[str]]:
    """Returns (filenames, symbols, concepts) mentioned in the request."""
    filenames = []
    for match in _FILENAME_RE.findall(request):
        cleaned = match.replace("\\", "/").strip("./") if match.startswith("./") else match.replace("\\", "/")
        if not re.fullmatch(r"\d+(\.\d+)+", cleaned) and cleaned not in filenames:
            filenames.append(cleaned)
    symbols: list[str] = []
    for item in _BACKTICK_RE.findall(request):
        for ident in _IDENT_RE.findall(item):
            if ident not in symbols:
                symbols.append(ident)
    for ident in _IDENT_RE.findall(request):
        looks_code = "_" in ident or any(c.isupper() for c in ident[1:]) or (ident[0].isupper() and any(c.islower() for c in ident))
        if looks_code and ident not in symbols and ident.lower() not in STOPWORDS:
            symbols.append(ident)
    concepts: list[str] = []
    for word in tokenize(request):
        if word in STOPWORDS or len(word) < 3:
            continue
        for variant in _variants(word):
            if variant not in STOPWORDS and variant not in concepts:
                concepts.append(variant)
    return filenames[:10], symbols[:15], concepts[:40]


class ContextEngine:
    def __init__(self, index: RepositoryIndex, workspace: WorkspaceService, repo_name: str | None = None) -> None:
        self.index = index
        self.workspace = workspace
        self.repo_name = repo_name

    # ---------------------------------------------------------------- ranking
    def rank(self, request: str) -> tuple[list[ContextFile], list[str], list[str], list[str]]:
        filenames, symbols, concepts = extract_request_terms(request)
        total = max(1, len(self.index.files))
        scores: dict[str, float] = {}
        reasons: dict[str, list[str]] = {}
        best_chunks: dict[str, list[tuple[float, int, int]]] = {}

        def add(path: str, amount: float, reason: str) -> None:
            scores[path] = scores.get(path, 0.0) + amount
            if reason not in reasons.setdefault(path, []):
                reasons[path].append(reason)

        for name in filenames:
            lowered = name.lower()
            for path in self.index.files:
                lp = path.lower()
                if lp == lowered or lp.endswith("/" + lowered):
                    add(path, 14, "named in the request")
        for symbol in symbols:
            for found in self.index.symbols.get(symbol.lower(), []):
                add(found.path, 9, f"defines {found.name}")
        concept_set = set(concepts)
        if concept_set:
            for path, entry in self.index.files.items():
                overlap = concept_set & entry.name_tokens
                if overlap:
                    add(path, min(9.0, 3.0 * len(overlap)), "path matches " + ", ".join(sorted(overlap)[:3]))
                symbol_hits = 0
                for symbol in entry.symbols:
                    lowered = symbol.name.lower()
                    if any(len(c) >= 4 and c in lowered for c in concept_set):
                        symbol_hits += 1
                if symbol_hits:
                    add(path, min(4.0, 1.5 * symbol_hits), f"{symbol_hits} related symbol(s)")
                chunk_scores = []
                for chunk in entry.chunks:
                    hit = concept_set & chunk.tokens
                    if hit:
                        weight = sum(math.log((total + 1) / (self.index.doc_freq.get(t, 0) + 1)) + 1 for t in hit)
                        chunk_scores.append((weight, chunk.start, chunk.end))
                if chunk_scores:
                    chunk_scores.sort(reverse=True)
                    value = chunk_scores[0][0] + 0.3 * (chunk_scores[1][0] if len(chunk_scores) > 1 else 0)
                    if entry.language == "markdown":
                        value *= 0.5
                    add(path, min(14.0, value * 0.7), "content matches the request")
                    best_chunks[path] = chunk_scores[:3]
        # dependency context around the strongest seeds
        seeds = sorted(scores, key=scores.get, reverse=True)[:5]  # type: ignore[arg-type]
        extra = 0
        for seed in seeds:
            entry = self.index.files.get(seed)
            if not entry:
                continue
            for dep in sorted(entry.imports)[:4]:
                if extra < 6:
                    add(dep, 2.5, f"imported by {Path(seed).name}")
                    extra += 1
            for user in sorted(self.index.imported_by.get(seed, set()))[:3]:
                if extra < 6:
                    add(user, 1.5, f"imports {Path(seed).name}")
                    extra += 1
            stem = Path(seed).stem.lower().replace("test_", "").replace("_test", "")
            for path, other in self.index.files.items():
                if "test" in path.lower() and stem and stem in other.name_tokens and path != seed:
                    add(path, 4, f"test related to {Path(seed).name}")
        ranked = [
            ContextFile(path=p, reason="; ".join(reasons[p][:3]), score=s, ranges=[(a, b) for _, a, b in best_chunks.get(p, [])])
            for p, s in sorted(scores.items(), key=lambda item: item[1], reverse=True)
            if s >= 2.0 and Path(p).name not in {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}
        ]
        return ranked[:MAX_FILES], filenames, symbols, concepts

    # ---------------------------------------------------------------- loading
    def build(self, request: str, budget_tokens: int | None = None) -> ContextBundle:
        budget = budget_tokens or settings.context_budget_tokens
        ranked, filenames, symbols, concepts = self.rank(request)
        if not ranked:
            ranked = [ContextFile(path=p, reason="entry point or key file", score=1.0) for p in self.index.important_files()[:4]]
        repo_map = self.index.repo_map(self.repo_name)
        remaining = budget - estimate_tokens(repo_map)
        loaded: list[ContextFile] = []
        for item in ranked:
            if remaining <= 400:
                break
            section = self._load(item, remaining)
            if not section:
                continue
            item.content, item.ranges = section
            remaining -= estimate_tokens(item.content)
            loaded.append(item)
        return ContextBundle(loaded, concepts, symbols, filenames, repo_map, tokens=budget - remaining)

    def _load(self, item: ContextFile, budget: int) -> tuple[str, list[tuple[int, int]]] | None:
        entry: FileEntry | None = self.index.files.get(item.path)
        try:
            text = (self.workspace.root / item.path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        lines = text.splitlines()
        if not lines:
            return None
        strong = item.score >= 9
        whole_limit = 400 if strong else 220
        if len(lines) <= whole_limit and estimate_tokens(text) <= budget:
            return self._number(lines, 1, len(lines)), [(1, len(lines))]
        windows = self._windows(item, entry, len(lines))
        pieces, used, kept = [], 0, []
        for start, end in windows:
            block = self._number(lines, start, end)
            cost = estimate_tokens(block)
            if used + cost > budget:
                break
            pieces.append(block)
            kept.append((start, end))
            used += cost
        if not pieces:
            return None
        return "\n   ...\n".join(pieces), kept

    @staticmethod
    def _windows(item: ContextFile, entry: FileEntry | None, total: int) -> list[tuple[int, int]]:
        raw = list(item.ranges) or [(1, min(total, 80))]
        if entry:
            for symbol in entry.symbols[:3]:
                if symbol.name.lower() in item.reason.lower():
                    raw.append((symbol.line, min(total, symbol.line + 60)))
        raw = sorted((max(1, a - 5), min(total, b + 5)) for a, b in raw)
        merged: list[tuple[int, int]] = []
        for start, end in raw:
            if merged and start <= merged[-1][1] + 3:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

    @staticmethod
    def _number(lines: list[str], start: int, end: int) -> str:
        return "\n".join(f"{n:>5} | {lines[n - 1]}" for n in range(start, end + 1))
