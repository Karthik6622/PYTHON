"""Safe merge of generated channel files into an automation branch. Pure functions: no network, no disk.

The studio records what it generated in ``.ats/manifest.json`` (path -> git blob sha, per channel). Files that are not in the
manifest belong to the user and are never overwritten or deleted. Shared files (requirements, pytest.ini, ...) are merged, never replaced.
"""

from __future__ import annotations

import configparser
import hashlib
import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from ats.automation.bundle_store import EXCLUDED_DIRS, is_secret

MANIFEST_PATH = ".ats/manifest.json"
MANIFEST_VERSION = 1
SHARED_FILES = ("requirements.txt", "pytest.ini", ".gitignore", "README.md", ".env.example")
HEADER = "# AI Autonomous Testing Studio"
COMMON_IGNORES = ("__pycache__/", ".pytest_cache/", "*.pyc", ".venv/", ".env", "storage_state*", "reports/", "logs/", "*.log")
MOBILE_IGNORES = ("*.apk", "*.aab", "*.ipa", "appium*.log", "screenshots/")
BLOCKED_DIRS = EXCLUDED_DIRS | {"reports", "logs", "allure-results"}
BLOCKED_SUFFIXES = (".apk", ".aab", ".ipa", ".log", ".keystore", ".jks", ".pfx", ".p12", ".pem", ".key")
TOKEN_NAMES = re.compile(r"^(\.?tokens?(\.\w+)?|.*\.token|credentials(\.\w+)?|\.netrc|id_rsa|id_ed25519)$")
SECRET_CONTENT = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}|\bAKIA[0-9A-Z]{16}\b|\bxox[bpas]-[A-Za-z0-9-]{20,}"
)


# ----------------------------------------------------------------------------------------
# hashing and safety
# ----------------------------------------------------------------------------------------
def blob_sha(text: str | bytes) -> str:
    """The git blob id of a file's content: what GitHub's tree listing reports, so unchanged files never need downloading."""
    data = text.encode("utf-8") if isinstance(text, str) else text
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()  # noqa: S324 - git object id, not a security hash


def is_blocked(rel: str, content: str = "") -> bool:
    """Files that are never committed: secrets, tokens, app binaries, run output, logs."""
    if rel == MANIFEST_PATH:
        return False
    path = PurePosixPath(rel)
    name = path.name.lower()
    if is_secret(rel) or name.startswith("storage_state") or name.endswith(BLOCKED_SUFFIXES) or TOKEN_NAMES.match(name):
        return True
    if any(part in BLOCKED_DIRS for part in path.parts[:-1]):
        return True
    return bool(content) and SECRET_CONTENT.search(content) is not None


# ----------------------------------------------------------------------------------------
# manifest
# ----------------------------------------------------------------------------------------
@dataclass
class Manifest:
    channels: dict[str, dict[str, Any]] = field(default_factory=dict)  # channel -> {"framework": str, "files": {path: blob sha}}

    @classmethod
    def parse(cls, text: str | None) -> Manifest:
        try:
            data = json.loads(text or "")
            channels = data.get("channels", {}) if isinstance(data, dict) else {}
        except ValueError:
            return cls()
        clean: dict[str, dict[str, Any]] = {}
        for channel, entry in (channels or {}).items():
            if isinstance(entry, dict) and isinstance(entry.get("files"), dict):
                clean[str(channel)] = {**entry, "files": {str(p): str(h) for p, h in entry["files"].items()}}
        return cls(clean)

    def dumps(self) -> str:
        return json.dumps({"version": MANIFEST_VERSION, "generator": "ai-testing-studio", "channels": self.channels}, indent=2, sort_keys=True) + "\n"

    def files_of(self, channel: str) -> dict[str, str]:
        return dict(self.channels.get(channel, {}).get("files", {}))

    def framework_of(self, channel: str) -> str:
        return str(self.channels.get(channel, {}).get("framework", ""))

    def owner_of(self, path: str) -> str | None:
        return next((c for c, entry in self.channels.items() if path in entry["files"]), None)


# ----------------------------------------------------------------------------------------
# shared files
# ----------------------------------------------------------------------------------------
def _eol(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _append(text: str, lines: list[str], eol: str | None = None) -> str:
    if not lines:
        return text
    eol = eol or _eol(text)
    if text and not text.endswith(("\n", "\r")):
        text += eol
    return text + eol.join(lines) + eol


def _req_key(line: str) -> str | None:
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    if text.startswith("-"):
        return f"option:{text}"
    match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", text)
    return re.sub(r"[-_.]+", "-", match.group(0)).lower() if match else None


def merge_requirements(existing: str, incoming: str) -> str:
    """Add the requirement lines whose package is missing. Existing lines (pins, comments, order) are never touched."""
    seen = {key for line in existing.splitlines() if (key := _req_key(line))}
    added: list[str] = []
    for line in incoming.splitlines():
        key = _req_key(line)
        if key and key not in seen:
            seen.add(key)
            added.append(line.strip())
    return _append(existing, added)


def _ini_entries(lines: list[str]) -> tuple[int, int, dict[str, tuple[int, int]]]:
    """``[pytest]`` section as (first line, end line, {key: (start, end)}); (-1, -1, {}) when there is none."""
    start = next((i for i, line in enumerate(lines) if line.strip() == "[pytest]"), -1)
    if start < 0:
        return -1, -1, {}
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("[")), len(lines))
    entries: dict[str, tuple[int, int]] = {}
    i = start + 1
    while i < end:
        match = re.match(r"([A-Za-z_][\w.-]*)\s*[=:]", lines[i])
        if not match:
            i += 1
            continue
        j = i + 1
        while j < end and lines[j][:1] in (" ", "\t") and lines[j].strip():
            j += 1
        entries[match.group(1)] = (i, j)
        i = j
    return start, end, entries


def _entry_value(lines: list[str], span: tuple[int, int]) -> list[str]:
    first = re.sub(r"^[^=:]*[=:]", "", lines[span[0]], count=1).strip()
    return [part for part in [first, *[line.strip() for line in lines[span[0] + 1 : span[1]]]] if part]


def _opt_units(text: str) -> list[str]:
    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = text.split()
    units: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in {"-p", "-o", "-c", "-m", "-k"} and i + 1 < len(tokens):
            units.append(f"{token} {tokens[i + 1]}")
            i += 2
        else:
            units.append(token)
            i += 1
    return units


def _unit_key(unit: str) -> str:
    return unit if unit.startswith(("-p ", "-o ", "-c ", "-m ", "-k ")) else unit.split("=", 1)[0]


def _marker_name(line: str) -> str:
    return re.split(r"[(:\s]", line.strip(), maxsplit=1)[0]


def _collapse_paths(paths: list[str]) -> list[str]:
    """Keep a folder and drop the sub-folders listed next to it (pytest would collect them twice)."""
    kept: list[str] = []
    for path in paths:
        norm = path.rstrip("/")
        if any(norm == k.rstrip("/") or norm.startswith(k.rstrip("/") + "/") for k in kept):
            continue
        kept = [k for k in kept if not k.rstrip("/").startswith(norm + "/")] + [path]
    return kept


def merge_pytest_ini(existing: str, incoming: str) -> str:
    """Union of ``markers``, ``addopts`` options and ``testpaths``; keys and values that already exist win."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # type: ignore[assignment, method-assign]
    try:
        parser.read_string(incoming)
        wanted = dict(parser["pytest"]) if parser.has_section("pytest") else {}
    except configparser.Error:
        return existing
    if not wanted:
        return existing
    eol = _eol(existing)
    lines = existing.splitlines()
    if _ini_entries(lines)[0] < 0:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("[pytest]")
    for key, value in wanted.items():
        start, end, entries = _ini_entries(lines)
        parts = [p.strip() for p in value.splitlines() if p.strip()]
        if key not in entries:
            at = end
            while at > start + 1 and not lines[at - 1].strip():
                at -= 1
            block = [f"{key} = {parts[0]}"] if len(parts) == 1 else [f"{key} =", *[f"    {p}" for p in parts]]
            lines[at:at] = block
            continue
        span = entries[key]
        current = _entry_value(lines, span)
        if key == "addopts":
            have = {_unit_key(u) for u in _opt_units(" ".join(current))}
            new = [u for u in _opt_units(" ".join(parts)) if _unit_key(u) not in have]
            if new:
                lines[span[1] - 1] = lines[span[1] - 1].rstrip() + " " + " ".join(new)
        elif key == "markers":
            have = {_marker_name(p) for p in current}
            new = [p for p in parts if _marker_name(p) not in have]
            if new:
                indent = re.match(r"\s*", lines[span[1] - 1]).group(0) if span[1] - span[0] > 1 else "    "  # type: ignore[union-attr]
                lines[span[1] : span[1]] = [f"{indent or '    '}{p}" for p in new]
        elif key == "testpaths":
            merged = _collapse_paths([*" ".join(current).split(), *" ".join(parts).split()])
            if merged != " ".join(current).split():
                lines[span[0] : span[1]] = [f"{key} = {' '.join(merged)}"]
    return eol.join(lines) + eol


def _rule_key(rule: str) -> str:
    negated = rule.startswith("!")
    return ("!" if negated else "") + rule.lstrip("!").strip().lstrip("/").rstrip("/")


def merge_gitignore(existing: str, incoming: str | list[str] | tuple[str, ...]) -> str:
    """Append the rules that are missing (``/x`` and ``x/`` count as present when ``x`` is). Nothing is ever removed."""
    rules = incoming.splitlines() if isinstance(incoming, str) else list(incoming)
    have = {_rule_key(line) for line in existing.splitlines() if line.strip() and not line.lstrip().startswith("#")}
    added: list[str] = []
    for rule in (r.strip() for r in rules):
        if rule and not rule.startswith("#") and _rule_key(rule) not in have:
            have.add(_rule_key(rule))
            added.append(rule)
    if not added:
        return existing
    eol = _eol(existing)
    head = [] if HEADER in existing else ([""] if existing.strip() else []) + [HEADER]
    return _append(existing, [*head, *added], eol)


ENV_KEY = re.compile(r"^\s*#?\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def merge_env_example(existing: str, incoming: str) -> str:
    """Append the keys that are missing (with the comment lines above them); existing keys and values are kept."""
    have = {m.group(1) for line in existing.splitlines() if (m := ENV_KEY.match(line))}
    comments_present = {line.strip() for line in existing.splitlines()}
    added: list[str] = []
    pending: list[str] = []
    for line in incoming.splitlines():
        match = ENV_KEY.match(line)
        if line.strip().startswith("#") and not match:
            pending.append(line)
        elif match and not line.strip().startswith("#"):
            if match.group(1) not in have:
                have.add(match.group(1))
                added += [c for c in pending if c.strip() not in comments_present] + [line]
            pending = []
        else:
            pending = []
    if added and existing.strip():
        added = ["", *added]
    return _append(existing, added)


def readme_markers(channel: str) -> tuple[str, str]:
    return f"<!-- ats:{channel}:begin -->", f"<!-- ats:{channel}:end -->"


def _demote(body: str) -> str:
    out, fenced = [], False
    for line in body.strip().splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        out.append("#" + line if not fenced and re.match(r"#{1,5}\s", line) else line)
    return "\n".join(out)


def merge_readme(existing: str | None, channel: str, body: str, title: str = "") -> str:
    """Write the channel's README text between ``<!-- ats:<channel>:begin/end -->``; everything outside the markers is untouched."""
    begin, end = readme_markers(channel)
    eol = _eol(existing or "")
    section = eol.join([begin, *_demote(body).splitlines(), end])
    text = existing or ""
    a, b = text.find(begin), text.find(end)
    if 0 <= a < b:
        return text[:a] + section + text[b + len(end) :]
    if not text.strip():
        return (f"# {title}{eol}{eol}" if title else "") + section + eol
    return text.rstrip() + eol + eol + section + eol


# ----------------------------------------------------------------------------------------
# plan
# ----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ChannelFiles:
    channel: str
    framework: str
    files: dict[str, str]


@dataclass(frozen=True)
class Conflict:
    path: str
    channel: str
    reason: str  # "user_file" | "user_edited" | "other_channel"

    @property
    def message(self) -> str:
        return {
            "user_file": "A file that is not managed by the studio already exists here; it was kept.",
            "user_edited": "The generated file was edited since it was published; the edited version was kept.",
            "other_channel": "The file belongs to another channel; the existing version was kept.",
        }[self.reason]


@dataclass(frozen=True)
class SharedMerge:
    path: str
    action: str  # "create" | "merge" | "unchanged"
    detail: str = ""


@dataclass
class Plan:
    add: dict[str, str] = field(default_factory=dict)
    update: dict[str, str] = field(default_factory=dict)
    skip: dict[str, str] = field(default_factory=dict)  # path -> why nothing is written (identical content)
    conflicts: list[Conflict] = field(default_factory=list)
    shared: list[SharedMerge] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)  # published earlier, not generated now: left in place
    manifest: Manifest = field(default_factory=Manifest)
    manifest_text: str | None = None  # None: the manifest on the branch is already current

    @property
    def changes(self) -> dict[str, str]:
        return {**self.add, **self.update}

    def commit_files(self) -> dict[str, str]:
        return {**self.changes, **({MANIFEST_PATH: self.manifest_text} if self.manifest_text is not None else {})}

    @property
    def empty(self) -> bool:
        return not self.commit_files()

    def summary(self) -> dict[str, int]:
        return {
            "add": len(self.add), "update": len(self.update), "keep": len(self.skip) + len(self.conflicts) + len(self.stale),
            "conflicts": len(self.conflicts), "shared": sum(1 for s in self.shared if s.action != "unchanged"), "blocked": len(self.blocked),
        }  # fmt: skip


def _is_blank_init(rel: str, content: str) -> bool:
    return PurePosixPath(rel).name == "__init__.py" and not content.strip()


def _line_delta(old: str, new: str) -> str:
    old_lines = {line.strip() for line in old.splitlines()}
    count = sum(1 for line in new.splitlines() if line.strip() and line.strip() not in old_lines)
    return f"{count} line(s) added"


def plan_publish(
    tree: dict[str, str], channels: list[ChannelFiles], manifest: Manifest, shared_texts: dict[str, str], *, title: str = "Automated tests"
) -> Plan:
    """What publishing ``channels`` onto a branch would do.

    ``tree`` maps every file of the branch to its blob sha (empty for a new branch); ``shared_texts`` holds the current text of the
    shared files that exist. Nothing outside the generated paths and the shared files is ever touched."""
    plan = Plan()
    incoming: dict[str, list[tuple[str, str]]] = {}  # shared file -> [(channel, text)]
    claimed = {path for c in channels for path in c.files}
    new_manifest = Manifest(json.loads(json.dumps(manifest.channels)))
    for item in channels:
        previous = manifest.files_of(item.channel)
        owned = dict(previous)
        generated: set[str] = set()
        for path, content in sorted(item.files.items()):
            if is_blocked(path, content):
                plan.blocked.append(path)
                continue
            if path in SHARED_FILES:
                incoming.setdefault(path, []).append((item.channel, content))
                continue
            generated.add(path)
            if _is_blank_init(path, content):  # package markers: created when missing, never compared
                if path not in tree and path not in plan.add:
                    plan.add[path] = content
                    plan.shared.append(SharedMerge(path, "create"))
                continue
            sha, current = blob_sha(content), tree.get(path)
            if current is None:
                plan.add[path] = content
                owned[path] = sha
            elif current == sha:
                plan.skip[path] = "already up to date"
                if manifest.owner_of(path) in (None, item.channel):
                    owned[path] = sha
            elif path in previous and current == previous[path]:
                plan.update[path] = content
                owned[path] = sha
            elif path in previous:
                plan.conflicts.append(Conflict(path, item.channel, "user_edited"))
            else:
                plan.conflicts.append(Conflict(path, item.channel, "other_channel" if manifest.owner_of(path) else "user_file"))
        plan.stale += [p for p in previous if p not in claimed and p in tree]
        new_manifest.channels[item.channel] = {
            "framework": item.framework, "files": {p: h for p, h in sorted(owned.items()) if p in generated or p in tree},
        }  # fmt: skip

    ignores = list(COMMON_IGNORES) + (list(MOBILE_IGNORES) if any(c.channel == "mobile" for c in channels) else [])
    for path in SHARED_FILES:
        texts = incoming.get(path, [])
        if not texts and path != ".gitignore":
            continue
        existed = path in tree
        current = shared_texts.get(path, "") if existed else ""
        merged = current
        if path == ".gitignore":
            for _, text in texts:
                merged = merge_gitignore(merged, text)
            merged = merge_gitignore(merged, ignores)
        for channel, text in texts:
            if path == "requirements.txt":
                merged = merge_requirements(merged, text)
            elif path == "pytest.ini":
                merged = merge_pytest_ini(merged, text) if merged.strip() else text
            elif path == ".env.example":
                merged = merge_env_example(merged, text)
            elif path == "README.md":
                merged = merge_readme(merged, channel, text, title)
        if existed and merged == current:
            plan.shared.append(SharedMerge(path, "unchanged"))
        elif existed:
            plan.update[path] = merged
            plan.shared.append(SharedMerge(path, "merge", _line_delta(current, merged)))
        else:
            plan.add[path] = merged
            plan.shared.append(SharedMerge(path, "create"))

    plan.manifest = new_manifest
    if MANIFEST_PATH not in tree or new_manifest.dumps() != manifest.dumps():
        plan.manifest_text = new_manifest.dumps()
    return plan
