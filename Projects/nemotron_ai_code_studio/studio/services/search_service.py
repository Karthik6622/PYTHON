"""Fast repository search: text (ripgrep when installed, Python otherwise), filenames, symbols, references and imports."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .indexing_service import RepositoryIndex
from .workspace_service import HEAVY_DIRS, WorkspaceService

MAX_LINE_CHARS = 300
MAX_PATTERN_CHARS = 200


class SearchError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class SearchService:
    def __init__(self, workspace: WorkspaceService, index: RepositoryIndex) -> None:
        self.workspace = workspace
        self.index = index
        self._rg = shutil.which("rg")

    # ---------------------------------------------------------------- text
    def search_text(
        self, query: str, *, regex: bool = False, case_sensitive: bool = False, glob: str | None = None, max_results: int = 100
    ) -> list[dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []
        if len(query) > MAX_PATTERN_CHARS:
            raise SearchError("The search text is too long.")
        max_results = max(1, min(max_results, 500))
        pattern = query if regex else re.escape(query)
        try:
            compiled = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
        except re.error as exc:
            raise SearchError(f"Invalid regular expression: {exc}") from exc
        if self._rg and not glob:
            found = self._rg_search(pattern, case_sensitive, max_results)
            if found is not None:
                return found
        return self._python_search(compiled, glob, max_results)

    def _rg_search(self, pattern: str, case_sensitive: bool, max_results: int) -> list[dict[str, Any]] | None:
        command = [
            self._rg or "rg", "--line-number", "--no-heading", "--color", "never", "--with-filename", "--max-columns", "300",
            "--max-filesize", "1M", "--max-count", "20", "--glob", "!.git", *sum((["--glob", f"!{d}"] for d in sorted(HEAVY_DIRS)), []),
            "--regexp", pattern, *([] if case_sensitive else ["--ignore-case"]), "--", ".",
        ]
        try:
            done = subprocess.run(command, cwd=self.workspace.root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if done.returncode not in (0, 1):
            return None
        results: list[dict[str, Any]] = []
        for line in done.stdout.splitlines():
            parts = line.split(":", 2)
            if len(parts) < 3 or not parts[1].isdigit():
                continue
            path = parts[0][2:] if parts[0].startswith("./") else parts[0]
            results.append({"path": path.replace("\\", "/"), "line": int(parts[1]), "text": parts[2].strip()[:MAX_LINE_CHARS]})
            if len(results) >= max_results:
                break
        return results

    def _python_search(self, compiled: re.Pattern[str], glob: str | None, max_results: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        glob_re = re.compile(self._glob_to_regex(glob)) if glob else None
        for relative in self.index.files:
            if glob_re and not glob_re.match(relative):
                continue
            try:
                text = (self.workspace.root / relative).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if compiled.search(line):
                    results.append({"path": relative, "line": number, "text": line.strip()[:MAX_LINE_CHARS]})
                    if len(results) >= max_results:
                        return results
        return results

    @staticmethod
    def _glob_to_regex(glob: str) -> str:
        out = ""
        i = 0
        while i < len(glob):
            c = glob[i]
            if c == "*":
                if glob[i:i + 2] == "**":
                    out += ".*"
                    i += 1
                else:
                    out += "[^/]*"
            elif c == "?":
                out += "[^/]"
            else:
                out += re.escape(c)
            i += 1
        return "^" + out + "$"

    # ---------------------------------------------------------------- filenames
    def search_filename(self, query: str, max_results: int = 50) -> list[str]:
        needle = (query or "").strip().lower().replace("\\", "/")
        if not needle:
            return []
        scored: list[tuple[int, str]] = []
        for path in self.index.files:
            lowered = path.lower()
            name = Path(lowered).name
            if name == needle:
                score = 0
            elif name.startswith(needle):
                score = 1
            elif needle in name:
                score = 2
            elif needle in lowered:
                score = 3
            elif self._subsequence(needle, name):
                score = 4
            else:
                continue
            scored.append((score * 1000 + len(path), path))
        return [path for _, path in sorted(scored)[:max(1, min(max_results, 200))]]

    @staticmethod
    def _subsequence(needle: str, hay: str) -> bool:
        it = iter(hay)
        return all(ch in it for ch in needle)

    # ---------------------------------------------------------------- symbols and references
    def search_symbol(self, name: str, max_results: int = 50) -> list[dict[str, Any]]:
        key = (name or "").strip().lower()
        if not key:
            return []
        exact = self.index.symbols.get(key, [])
        others = [s for k, items in self.index.symbols.items() if k != key and (k.startswith(key) or key in k) for s in items]
        return [{"name": s.name, "kind": s.kind, "path": s.path, "line": s.line} for s in (exact + others)[:max_results]]

    def find_references(self, symbol: str, max_results: int = 100) -> dict[str, Any]:
        name = (symbol or "").strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise SearchError("A reference search needs a plain identifier such as parseConfig.")
        definitions = [s for s in self.index.symbols.get(name.lower(), []) if s.name == name]
        hits = self.search_text(rf"\b{re.escape(name)}\b", regex=True, case_sensitive=True, max_results=max_results)
        definition_keys = {(s.path, s.line) for s in definitions}
        return {
            "symbol": name,
            "definitions": [{"path": s.path, "line": s.line, "kind": s.kind} for s in definitions],
            "references": [hit for hit in hits if (hit["path"], hit["line"]) not in definition_keys],
        }

    def find_importers(self, path: str) -> list[str]:
        return sorted(self.index.imported_by.get(path, set()))
