"""Repository intelligence: file inventory, languages, frameworks, entry points, symbols, imports and searchable chunks.

The index respects .gitignore (it asks Git for the file list when the workspace is a repository) and skips binary files,
dependency folders and build output. A tree-sitter/AST indexer can later replace `_extract_symbols` without touching callers.
"""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from ..security import is_sensitive_path
from .workspace_service import BINARY_EXTENSIONS, HEAVY_DIRS, WorkspaceService, language_for, looks_binary

MAX_INDEXED_FILES = 6_000
MAX_INDEXED_BYTES = 400_000
CHUNK_LINES = 60
CHUNK_OVERLAP = 10
LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock", "Cargo.lock", "composer.lock", "go.sum", "uv.lock"}
SKIP_LANGUAGES = {"plaintext"}  # still searchable, just not chunked by symbol

DEPENDENCY_FILES = {"package.json", "pyproject.toml", "Pipfile", "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile", "composer.json", "setup.py"}
CONFIG_FILE_PATTERNS = [
    r"tsconfig.*\.json", r"vite\.config\.\w+", r"webpack\.config\.\w+", r"\.eslintrc.*", r"eslint\.config\.\w+", r"\.prettierrc.*",
    r"pyproject\.toml", r"setup\.cfg", r"tox\.ini", r"pytest\.ini", r"Dockerfile.*", r"docker-compose.*\.ya?ml", r"\.env\.example",
    r"Makefile", r"tailwind\.config\.\w+", r"babel\.config\.\w+", r"jest\.config\.\w+", r"vitest\.config\.\w+", r"\.gitignore",
    r"next\.config\.\w+", r"nuxt\.config\.\w+", r"ruff\.toml", r"\.flake8", r"mypy\.ini", r"\.editorconfig",
]
_CONFIG_RE = re.compile("^(?:" + "|".join(CONFIG_FILE_PATTERNS) + ")$", re.IGNORECASE)
ENTRY_NAMES = {
    "main.py", "app.py", "manage.py", "__main__.py", "server.py", "wsgi.py", "asgi.py", "run.py", "index.js", "index.ts", "server.js",
    "server.ts", "main.ts", "main.js", "main.tsx", "index.tsx", "app.tsx", "app.js", "app.ts", "main.go", "main.rs", "program.cs", "main.java",
}
FRAMEWORK_HINTS = {
    "fastapi": "FastAPI", "flask": "Flask", "django": "Django", "streamlit": "Streamlit", "sqlalchemy": "SQLAlchemy", "pydantic": "Pydantic",
    "pytest": "pytest", "celery": "Celery", "numpy": "NumPy", "pandas": "pandas", "torch": "PyTorch", "tensorflow": "TensorFlow",
    '"react"': "React", '"next"': "Next.js", '"vue"': "Vue", '"svelte"': "Svelte", '"@angular/core"': "Angular", '"express"': "Express",
    '"vite"': "Vite", '"tailwindcss"': "Tailwind CSS", '"@nestjs/core"': "NestJS", '"jest"': "Jest", '"vitest"': "Vitest",
    '"typescript"': "TypeScript", '"electron"': "Electron", "gin-gonic": "Gin", "spring-boot": "Spring Boot", "actix": "Actix", "tokio": "Tokio",
}

_PY_SYMBOLS = [("function", re.compile(r"^\s*(?:async\s+)?def\s+(\w+)")), ("class", re.compile(r"^\s*class\s+(\w+)"))]
_JS_SYMBOLS = [
    ("function", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\*?\s+(\w+)")),
    ("class", re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)")),
    ("function", re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*(?::[^=]+)?=>")),
    ("function", re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function")),
    ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+(\w+)")),
    ("type", re.compile(r"^\s*(?:export\s+)?type\s+(\w+)\s*[=<]")),
    ("enum", re.compile(r"^\s*(?:export\s+)?(?:const\s+)?enum\s+(\w+)")),
]
_GO_SYMBOLS = [("function", re.compile(r"^func\s+(?:\([^)]*\)\s*)?(\w+)")), ("type", re.compile(r"^type\s+(\w+)\s+(?:struct|interface)"))]
_RUST_SYMBOLS = [("function", re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)")), ("type", re.compile(r"^\s*(?:pub\s+)?(?:struct|enum|trait)\s+(\w+)"))]
_OOP_SYMBOLS = [("class", re.compile(r"^\s*(?:public\s+|private\s+|protected\s+|internal\s+|abstract\s+|final\s+|static\s+|sealed\s+|data\s+)*(?:class|interface|enum|record|object)\s+(\w+)"))]
_RUBY_SYMBOLS = [("function", re.compile(r"^\s*def\s+(?:self\.)?(\w+)")), ("class", re.compile(r"^\s*(?:class|module)\s+(\w+)"))]
_PHP_SYMBOLS = [("function", re.compile(r"^\s*(?:public\s+|private\s+|protected\s+|static\s+)*function\s+(\w+)")), ("class", re.compile(r"^\s*(?:abstract\s+|final\s+)?(?:class|interface|trait)\s+(\w+)"))]
SYMBOL_PATTERNS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "python": _PY_SYMBOLS, "javascript": _JS_SYMBOLS, "typescript": _JS_SYMBOLS, "go": _GO_SYMBOLS, "rust": _RUST_SYMBOLS,
    "java": _OOP_SYMBOLS, "kotlin": _OOP_SYMBOLS, "csharp": _OOP_SYMBOLS, "ruby": _RUBY_SYMBOLS, "php": _PHP_SYMBOLS,
}

_PY_IMPORT = re.compile(r"^\s*(?:from\s+([.\w]+)\s+import\s+|import\s+([\w., ]+))", re.MULTILINE)
_JS_IMPORT = re.compile(r"""(?:from\s+|require\(\s*|import\(\s*|import\s+)['"]([^'"\n]+)['"]""")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_SPLIT_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")


def tokenize(text: str) -> set[str]:
    """Lower-case identifiers plus their camelCase/snake_case parts."""
    tokens: set[str] = set()
    for ident in _IDENT.findall(text):
        lowered = ident.lower()
        tokens.add(lowered)
        if "_" in ident or any(c.isupper() for c in ident[1:]):
            for part in ident.replace("_", " ").split():
                for sub in _SPLIT_CAMEL.findall(part):
                    if len(sub) >= 3:
                        tokens.add(sub.lower())
    return tokens


@dataclass
class Symbol:
    name: str
    kind: str
    path: str
    line: int


@dataclass
class Chunk:
    start: int
    end: int
    tokens: frozenset[str]


@dataclass
class FileEntry:
    path: str
    size: int
    language: str
    lines: int
    symbols: list[Symbol] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    imports: set[str] = field(default_factory=set)  # resolved repository paths
    raw_imports: list[str] = field(default_factory=list)
    name_tokens: frozenset[str] = frozenset()
    has_main_guard: bool = False


class RepositoryIndex:
    def __init__(self, workspace: WorkspaceService, git: Any | None = None) -> None:
        self.workspace = workspace
        self.git = git
        self.files: dict[str, FileEntry] = {}
        self.imported_by: dict[str, set[str]] = defaultdict(set)
        self.symbols: dict[str, list[Symbol]] = defaultdict(list)
        self.doc_freq: Counter[str] = Counter()
        self.skipped = 0
        self.built = False

    # ---------------------------------------------------------------- building
    def build(self) -> None:
        self.files.clear()
        self.imported_by.clear()
        self.symbols.clear()
        self.doc_freq.clear()
        self.skipped = 0
        paths = self._list_paths()
        for relative in paths[:MAX_INDEXED_FILES]:
            self._index_file(relative)
        self.skipped += max(0, len(paths) - MAX_INDEXED_FILES)
        self._resolve_imports()
        self.built = True

    def refresh_file(self, relative: str) -> None:
        """Re-index one file after it was written, created, renamed or deleted."""
        old = self.files.pop(relative, None)
        if old:
            for chunk in old.chunks:
                self.doc_freq.subtract(chunk.tokens)
            self.symbols = defaultdict(list, {n: [s for s in items if s.path != relative] for n, items in self.symbols.items()})
            for target in old.imports:
                self.imported_by[target].discard(relative)
        path = self.workspace.root / relative
        if path.is_file():
            self._index_file(relative)
            entry = self.files.get(relative)
            if entry:
                self._resolve_imports([entry])

    def _list_paths(self) -> list[str]:
        names: list[str] = []
        if self.git is not None:
            try:
                output = self.git.repo.git.execute(["git", "-C", str(self.workspace.root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"])
                names = [item for item in output.split("\0") if item]
            except Exception:
                names = []
        if not names:
            for current, dirs, files in os.walk(self.workspace.root):
                dirs[:] = [d for d in dirs if d != ".git" and d not in HEAVY_DIRS]
                for name in files:
                    names.append(Path(current, name).relative_to(self.workspace.root).as_posix())
        kept = []
        for name in names:
            parts = PurePosixPath(name).parts
            if any(part in HEAVY_DIRS for part in parts[:-1]) or parts[0] == ".git":
                continue
            if Path(name).suffix.lower() in BINARY_EXTENSIONS or is_sensitive_path(name):
                self.skipped += 1
                continue
            kept.append(name)
        # shallow, source-like files first so the cap keeps the most useful ones
        kept.sort(key=lambda item: (item.count("/"), item.lower()))
        return kept

    def _index_file(self, relative: str) -> None:
        if is_sensitive_path(relative):
            return
        path = self.workspace.root / relative
        try:
            size = path.stat().st_size
            if size > MAX_INDEXED_BYTES or not path.is_file():
                self.skipped += 1
                return
            data = path.read_bytes()
        except OSError:
            return
        if looks_binary(data):
            self.skipped += 1
            return
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        language = language_for(relative)
        entry = FileEntry(path=relative, size=size, language=language, lines=len(lines))
        entry.name_tokens = frozenset(tokenize(PurePosixPath(relative).stem) | {p.lower() for p in PurePosixPath(relative).parts[:-1] if len(p) > 2})
        if Path(relative).name in LOCKFILES:
            self.files[relative] = entry
            return
        entry.symbols = self._extract_symbols(relative, language, lines)
        for symbol in entry.symbols:
            self.symbols[symbol.name.lower()].append(symbol)
        for start in range(0, max(len(lines), 1), CHUNK_LINES - CHUNK_OVERLAP):
            block = lines[start:start + CHUNK_LINES]
            if not block:
                break
            tokens = frozenset(tokenize("\n".join(block)))
            entry.chunks.append(Chunk(start + 1, start + len(block), tokens))
            self.doc_freq.update(tokens)
            if start + CHUNK_LINES >= len(lines):
                break
        entry.raw_imports = self._extract_imports(language, text)
        entry.has_main_guard = language == "python" and "__name__" in text and "__main__" in text
        self.files[relative] = entry

    @staticmethod
    def _extract_symbols(relative: str, language: str, lines: list[str]) -> list[Symbol]:
        patterns = SYMBOL_PATTERNS.get(language)
        if not patterns:
            return []
        found: list[Symbol] = []
        for number, line in enumerate(lines, start=1):
            if len(line) > 400:
                continue
            for kind, pattern in patterns:
                match = pattern.match(line)
                if match:
                    found.append(Symbol(match.group(1), kind, relative, number))
                    break
        return found

    @staticmethod
    def _extract_imports(language: str, text: str) -> list[str]:
        if language == "python":
            raw: list[str] = []
            for match in _PY_IMPORT.finditer(text):
                if match.group(1):
                    raw.append(match.group(1))
                elif match.group(2):
                    raw.extend(part.strip().split(" as ")[0].strip() for part in match.group(2).split(",") if part.strip())
            return raw
        if language in {"javascript", "typescript", "html"}:
            return [item for item in _JS_IMPORT.findall(text)]
        return []

    def _resolve_imports(self, only: list[FileEntry] | None = None) -> None:
        by_module: dict[str, str] = {}
        for rel in self.files:
            if rel.endswith(".py"):
                module = rel[:-3].replace("/", ".")
                if module.endswith(".__init__"):
                    module = module[: -len(".__init__")]
                by_module[module] = rel
        for entry in only if only is not None else list(self.files.values()):
            entry.imports = set()
            for raw in entry.raw_imports:
                target = self._resolve_python(raw, entry.path, by_module) if entry.language == "python" else self._resolve_js(raw, entry.path)
                if target and target != entry.path:
                    entry.imports.add(target)
                    self.imported_by[target].add(entry.path)

    def _resolve_python(self, module: str, from_file: str, by_module: dict[str, str]) -> str | None:
        if module.startswith("."):
            dots = len(module) - len(module.lstrip("."))
            base = PurePosixPath(from_file).parent
            for _ in range(dots - 1):
                base = base.parent
            candidate = ".".join([*base.parts, *[p for p in module.lstrip(".").split(".") if p]])
            return by_module.get(candidate) or by_module.get(candidate + ".__init__")
        if module in by_module:
            return by_module[module]
        suffix = "." + module
        for known, rel in by_module.items():  # src/ layouts: package.module lives under a prefix folder
            if known.endswith(suffix):
                return rel
        return None

    def _resolve_js(self, spec: str, from_file: str) -> str | None:
        if spec.startswith("@/") or spec.startswith("~/"):
            candidates_base = ["src/" + spec[2:], spec[2:]]
        elif spec.startswith("."):
            candidates_base = [(PurePosixPath(from_file).parent / spec).as_posix()]
        else:
            return None
        for base in candidates_base:
            normalized = os.path.normpath(base).replace("\\", "/")
            for suffix in ("", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".vue", ".svelte", "/index.ts", "/index.tsx", "/index.js", "/index.jsx"):
                if normalized + suffix in self.files:
                    return normalized + suffix
        return None

    # ---------------------------------------------------------------- summaries
    def language_counts(self) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for entry in self.files.values():
            if entry.language not in SKIP_LANGUAGES and entry.language not in {"json", "markdown", "yaml", "ini", "xml"}:
                counts[entry.language] += entry.lines
        return dict(counts.most_common(8))

    def detect_frameworks(self) -> list[str]:
        found: list[str] = []
        for relative, entry in self.files.items():
            name = Path(relative).name
            if name in DEPENDENCY_FILES or (name.startswith("requirements") and name.endswith(".txt")):
                try:
                    text = (self.workspace.root / relative).read_text(encoding="utf-8", errors="ignore").lower()
                except OSError:
                    continue
                for hint, label in FRAMEWORK_HINTS.items():
                    if hint in text and label not in found:
                        found.append(label)
        return found

    def dependency_files(self) -> list[str]:
        return sorted(p for p in self.files if Path(p).name in DEPENDENCY_FILES or (Path(p).name.startswith("requirements") and p.endswith(".txt")))

    def config_files(self) -> list[str]:
        return sorted(p for p in self.files if _CONFIG_RE.match(Path(p).name) or p.startswith(".github/workflows/"))[:40]

    def entry_points(self) -> list[str]:
        result = [p for p, entry in self.files.items() if Path(p).name.lower() in ENTRY_NAMES or entry.has_main_guard]
        return sorted(result, key=lambda item: (item.count("/"), item))[:12]

    def important_files(self) -> list[str]:
        ranked: list[str] = []
        for group in (self.entry_points(), self.dependency_files(), [p for p in self.files if Path(p).name.lower().startswith("readme")]):
            for item in group:
                if item not in ranked:
                    ranked.append(item)
        return ranked[:14]

    def summary(self) -> dict[str, Any]:
        return {
            "files": len(self.files), "skipped": self.skipped, "languages": self.language_counts(), "frameworks": self.detect_frameworks(),
            "entry_points": self.entry_points(), "important_files": self.important_files(), "dependency_files": self.dependency_files(),
            "config_files": self.config_files(), "symbols": sum(len(v) for v in self.symbols.values()),
        }

    def repo_map(self, name: str | None = None) -> str:
        info = self.summary()
        lines = [f"Repository:\n{name or self.workspace.root.name}", ""]
        lines += ["Languages:", *(info["languages"] and list(info["languages"]) or ["(none detected)"]), ""]
        lines += ["Detected frameworks:", *(info["frameworks"] or ["(none detected)"]), ""]
        lines += ["Important files:", *(info["important_files"] or ["(none)"]), ""]
        if info["config_files"]:
            lines += ["Configuration files:", *info["config_files"][:10], ""]
        lines += [f"Indexed files: {info['files']} (skipped {info['skipped']})"]
        return "\n".join(lines)
