"""The tools the AI agent can call, with per-mode availability and the approval rules.

Read tools run freely. Anything destructive or outward-facing (delete, commit, push, pull, checkout, package installs,
destructive shell commands, rewriting most of a file) pauses until the user approves it in the UI.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from ..config import settings
from ..security import PathSecurityError, is_sensitive_path, redact
from ..services.command_policy import classify_command
from ..services.git_service import GitError
from ..services.repository_service import ActiveRepository
from ..services.search_service import SearchError
from ..services.terminal_service import CommandResult
from ..services.workspace_service import WorkspaceError
from . import devtools

MAX_TOOL_OUTPUT = 14_000
DEFAULT_READ_LINES = 400

READ_TOOLS = {
    "list_files", "read_file", "read_files", "search_code", "search_filename", "find_references", "get_repository_tree",
    "get_file_metadata", "git_status", "git_diff", "git_log", "git_branch",
}
WRITE_TOOLS = {
    "write_file", "create_file", "edit_file", "delete_file", "rename_file", "git_create_branch", "git_checkout", "git_stage",
    "git_commit", "git_push", "git_pull", "run_command", "run_tests", "run_linter", "run_formatter",
}


@dataclass
class ApprovalRequest:
    tool: str
    title: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "tool": self.tool, "title": self.title, "reason": self.reason, "details": self.details}


@dataclass
class Blocked:
    reason: str


@dataclass
class ToolOutcome:
    content: str
    ok: bool = True
    summary: str = ""


@dataclass
class ToolContext:
    repo: ActiveRepository
    change_id: str
    mode: str = "agent"
    request_approval: Callable[[ApprovalRequest], Awaitable[bool]] | None = None
    emit_output: Callable[[str], None] | None = None
    inspected: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    tests: list[dict[str, Any]] = field(default_factory=list)
    cancel: threading.Event = field(default_factory=threading.Event)
    def note_inspected(self, path: str) -> None:
        if path and path not in self.inspected:
            self.inspected.append(path)

    def note_modified(self, path: str) -> None:
        if path and path not in self.modified:
            self.modified.append(path)


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[ToolContext, dict[str, Any]], str]
    approval: Callable[[ToolContext, dict[str, Any]], ApprovalRequest | Blocked | None] | None = None

    def schema(self) -> dict[str, Any]:
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}


def _object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


_STR = {"type": "string"}


def _s(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _clip(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit * 2 // 3] + f"\n... [{len(text) - limit} characters omitted] ...\n" + text[-limit // 3:]


def _numbered(text: str, start: int = 1) -> str:
    return "\n".join(f"{n:>5} | {line}" for n, line in enumerate(text.splitlines(), start=start))


def _str_arg(args: dict[str, Any], key: str, default: str = "") -> str:
    value = args.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"'{key}' must be a string.")
    return value


def _int_arg(args: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(args.get(key, default))
    except (TypeError, ValueError):
        raise ValueError(f"'{key}' must be a number.") from None
    return max(low, min(high, value))


def _bool_arg(args: dict[str, Any], key: str, default: bool = False) -> bool:
    value = args.get(key, default)
    return value if isinstance(value, bool) else str(value).lower() in {"1", "true", "yes"}


def _check_readable(path: str) -> None:
    if is_sensitive_path(path):
        raise WorkspaceError(f"'{Path(path.replace(chr(92), '/')).name}' may contain secrets, so the agent is not allowed to read it.", 403)


# ======================================================================= read tools
def _list_files(ctx: ToolContext, args: dict[str, Any]) -> str:
    path = _str_arg(args, "path")
    entries = ctx.repo.workspace.list_dir(path)
    if not entries:
        return "(empty directory)"
    return "\n".join(f"{'d' if e['type'] == 'dir' else 'f'}  {e['path']}{'/' if e['type'] == 'dir' else ''}" + (f"  ({e['size']} bytes)" if e["type"] == "file" else "") for e in entries[:300])


def _read_one(ctx: ToolContext, path: str, start: int, end: int | None) -> str:
    _check_readable(path)
    info = ctx.repo.workspace.read_lines(path, start, end if end else start + DEFAULT_READ_LINES - 1)
    ctx.note_inspected(info["path"])
    header = f"{info['path']}  (lines {info['start']}-{info['end']} of {info['total_lines']})"
    note = ""
    if info["end"] < info["total_lines"] and not end:
        note = f"\n[more lines follow; call read_file with start_line={info['end'] + 1}]"
    return f"{header}\n{_numbered(info['content'], info['start'])}{note}"


def _read_file(ctx: ToolContext, args: dict[str, Any]) -> str:
    path = _str_arg(args, "path")
    start = _int_arg(args, "start_line", 1, 1, 10_000_000)
    end = _int_arg(args, "end_line", 0, 0, 10_000_000) or None
    return _clip(_read_one(ctx, path, start, end), 60_000)


def _read_files(ctx: ToolContext, args: dict[str, Any]) -> str:
    paths = args.get("paths")
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
        raise ValueError("'paths' must be a non-empty list of strings.")
    parts = []
    for path in paths[:8]:
        try:
            parts.append(_read_one(ctx, path, 1, None))
        except (WorkspaceError, PathSecurityError) as exc:
            parts.append(f"{path}: ERROR: {exc}")
    return _clip("\n\n".join(parts), 60_000)


def _search_code(ctx: ToolContext, args: dict[str, Any]) -> str:
    hits = ctx.repo.search.search_text(
        _str_arg(args, "query"), regex=_bool_arg(args, "regex"), case_sensitive=_bool_arg(args, "case_sensitive"),
        glob=_str_arg(args, "glob") or None, max_results=_int_arg(args, "max_results", 40, 1, 200),
    )
    if not hits:
        return "No matches."
    return "\n".join(f"{h['path']}:{h['line']}: {h['text']}" for h in hits)


def _search_filename(ctx: ToolContext, args: dict[str, Any]) -> str:
    found = ctx.repo.search.search_filename(_str_arg(args, "query"), _int_arg(args, "max_results", 30, 1, 100))
    return "\n".join(found) if found else "No matching files."


def _find_references(ctx: ToolContext, args: dict[str, Any]) -> str:
    data = ctx.repo.search.find_references(_str_arg(args, "symbol"))
    lines = [f"Symbol: {data['symbol']}"]
    lines.append("Definitions:" if data["definitions"] else "Definitions: none found in the index")
    lines += [f"  {d['path']}:{d['line']} ({d['kind']})" for d in data["definitions"]]
    lines.append("References:" if data["references"] else "References: none")
    lines += [f"  {r['path']}:{r['line']}: {r['text']}" for r in data["references"][:80]]
    return "\n".join(lines)


def _get_repository_tree(ctx: ToolContext, args: dict[str, Any]) -> str:
    return ctx.repo.workspace.tree_text(_str_arg(args, "path"), _int_arg(args, "depth", 3, 1, 6))


def _get_file_metadata(ctx: ToolContext, args: dict[str, Any]) -> str:
    info = ctx.repo.workspace.metadata(_str_arg(args, "path"))
    entry = ctx.repo.index.files.get(info.get("path", ""))
    if entry:
        info["symbols"] = [f"{s.kind} {s.name} (line {s.line})" for s in entry.symbols[:40]]
        info["imports"] = sorted(entry.imports)[:30]
        info["imported_by"] = sorted(ctx.repo.index.imported_by.get(entry.path, set()))[:30]
    return json.dumps(info, indent=2, default=str)


# ======================================================================= git tools
def _git(ctx: ToolContext):
    if ctx.repo.git is None:
        raise GitError("This workspace is not a Git repository.", 400)
    return ctx.repo.git


def _git_status(ctx: ToolContext, args: dict[str, Any]) -> str:
    status = _git(ctx).status()
    if status["clean"]:
        return f"Branch {status['branch']}: working tree clean."
    lines = [f"Branch {status['branch']} (ahead {status['ahead']}, behind {status['behind']})"]
    lines += [f"{f['kind']:<10} {f['path']}{' (staged)' if f['staged'] else ''}" for f in status["files"][:200]]
    return "\n".join(lines)


def _git_diff(ctx: ToolContext, args: dict[str, Any]) -> str:
    text = _git(ctx).diff(_str_arg(args, "path") or None, staged=_bool_arg(args, "staged"))
    return _clip(text, 40_000) if text.strip() else "No differences."


def _git_log(ctx: ToolContext, args: dict[str, Any]) -> str:
    commits = _git(ctx).log(_int_arg(args, "count", 10, 1, 50))
    return "\n".join(f"{c['short']} {c['date'][:10]} {c['author']}: {c['message']}" for c in commits) or "No commits yet."


def _git_branch(ctx: ToolContext, args: dict[str, Any]) -> str:
    data = _git(ctx).branches()
    return f"Current: {data['current']}\nLocal: {', '.join(data['local']) or '-'}\nRemote: {', '.join(data['remote']) or '-'}"


def _git_create_branch(ctx: ToolContext, args: dict[str, Any]) -> str:
    return f"Created and switched to branch {_git(ctx).create_branch(_str_arg(args, 'name'))}."


def _git_checkout(ctx: ToolContext, args: dict[str, Any]) -> str:
    name = _git(ctx).checkout(_str_arg(args, "name"))
    _refresh_after_external_change(ctx, full=True)
    return f"Switched to branch {name}."


def _git_stage(ctx: ToolContext, args: dict[str, Any]) -> str:
    paths = args.get("paths") or []
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        raise ValueError("'paths' must be a list of strings (omit it to stage everything).")
    _git(ctx).stage(paths or None)
    return "Staged " + (", ".join(paths) if paths else "all changes") + "."


def _git_commit(ctx: ToolContext, args: dict[str, Any]) -> str:
    result = _git(ctx).commit(_str_arg(args, "message"))
    return f"Committed {result['short']}: {result['message']}"


def _git_push(ctx: ToolContext, args: dict[str, Any]) -> str:
    if ctx.repo.github.get("can_push") is False:
        raise GitError("The connected GitHub token does not have push access to this repository.", 403)
    return _git(ctx).push(_str_arg(args, "branch") or None)


def _git_pull(ctx: ToolContext, args: dict[str, Any]) -> str:
    out = _git(ctx).pull()
    _refresh_after_external_change(ctx, full=True)
    return out


# ======================================================================= write tools
def _refresh(ctx: ToolContext, path: str) -> None:
    ctx.repo.index.refresh_file(path)


def _refresh_after_external_change(ctx: ToolContext, full: bool = False) -> None:
    """Re-index after shell commands or Git changed files behind the tracker's back."""
    if full or ctx.repo.git is None:
        ctx.repo.index.build()
        return
    try:
        files = ctx.repo.git.status()["files"]
    except GitError:
        return
    for item in files[:150]:
        ctx.repo.index.refresh_file(item["path"])


def _write_file(ctx: ToolContext, args: dict[str, Any]) -> str:
    path = _str_arg(args, "path")
    content = _str_arg(args, "content")
    ws = ctx.repo.workspace
    with ctx.repo.lock:
        ws.resolve(path, allow_root=False)
        ctx.repo.tracker.snapshot(ctx.change_id, ws, path)
        existed = ws.resolve(path).is_file()
        info = ws.write_text(path, content)
        _refresh(ctx, info["path"])
    ctx.note_modified(info["path"])
    return f"{'Updated' if existed else 'Created'} {info['path']} ({content.count(chr(10)) + 1} lines)."


def _approval_write_file(ctx: ToolContext, args: dict[str, Any]) -> ApprovalRequest | Blocked | None:
    path = _str_arg(args, "path")
    content = _str_arg(args, "content")
    target = ctx.repo.workspace.resolve(path, allow_root=False)
    if not target.is_file():
        return None
    old = target.read_text(encoding="utf-8", errors="replace").splitlines()
    new = content.splitlines()
    if len(old) < 30:
        return None
    if len(old) > 2500 or len(new) > 2500:
        similarity = min(len(old), len(new)) / max(len(old), len(new))
    else:
        similarity = difflib.SequenceMatcher(None, old, new, autojunk=False).ratio()
    if similarity < 0.5:
        return ApprovalRequest("write_file", f"Rewrite {path}", f"This replaces about {round((1 - similarity) * 100)}% of a {len(old)}-line file.", {"path": path, "old_lines": len(old), "new_lines": len(new)})
    return None


def _create_file(ctx: ToolContext, args: dict[str, Any]) -> str:
    path = _str_arg(args, "path")
    ws = ctx.repo.workspace
    with ctx.repo.lock:
        ws.resolve(path, allow_root=False)
        ctx.repo.tracker.snapshot(ctx.change_id, ws, path)
        result = ws.create(path, "file", _str_arg(args, "content"))
        _refresh(ctx, result["path"])
    ctx.note_modified(result["path"])
    return f"Created {result['path']}."


def _edit_file(ctx: ToolContext, args: dict[str, Any]) -> str:
    path = _str_arg(args, "path")
    old = _str_arg(args, "old_text")
    new = _str_arg(args, "new_text")
    if not old:
        raise ValueError("'old_text' must not be empty. Use write_file to replace a whole file.")
    if old == new:
        raise ValueError("'old_text' and 'new_text' are identical.")
    ws = ctx.repo.workspace
    with ctx.repo.lock:
        info = ws.read_text(path)
        if info["binary"] or info["truncated"]:
            raise WorkspaceError("This file cannot be edited as text (binary or too large).", 415)
        text = info["content"]
        if "\r\n" in text and "\r\n" not in old:
            old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
        count = text.count(old)
        if count == 0:
            first = next((ln.strip() for ln in old.splitlines() if ln.strip()), "")
            hint = ""
            if first:
                near = [n for n, ln in enumerate(text.splitlines(), 1) if first in ln][:3]
                hint = f" The first line of old_text appears near line(s) {near}; re-read that part and copy the text exactly." if near else ""
            raise ValueError("old_text was not found in the file (it must match exactly, including whitespace)." + hint)
        replace_all = _bool_arg(args, "replace_all")
        if count > 1 and not replace_all:
            raise ValueError(f"old_text matches {count} places. Include more surrounding lines so it is unique, or set replace_all=true.")
        updated = text.replace(old, new) if replace_all else text.replace(old, new, 1)
        ctx.repo.tracker.snapshot(ctx.change_id, ws, path)
        ws.write_text(path, updated)
        _refresh(ctx, info["path"])
    ctx.note_modified(info["path"])
    return f"Edited {info['path']} ({count if replace_all else 1} replacement(s))."


def _delete_file(ctx: ToolContext, args: dict[str, Any]) -> str:
    path = _str_arg(args, "path")
    ws = ctx.repo.workspace
    with ctx.repo.lock:
        target = ws.resolve(path, allow_root=False)
        files: list[str] = []
        if target.is_dir():
            files = [ws.rel(p) for p in target.rglob("*") if p.is_file()]
            if len(files) > 500:
                raise WorkspaceError("That directory has more than 500 files; delete it yourself in the Explorer.", 400)
        else:
            files = [path]
        for relative in files:
            ctx.repo.tracker.snapshot(ctx.change_id, ws, relative)
        ws.delete(path)
        for relative in files:
            _refresh(ctx, relative)
            ctx.note_modified(relative)
    return f"Deleted {path}" + (f" ({len(files)} files)." if len(files) > 1 else ".")


def _approval_delete(ctx: ToolContext, args: dict[str, Any]) -> ApprovalRequest:
    path = _str_arg(args, "path")
    return ApprovalRequest("delete_file", f"Delete {path}", "The agent wants to delete this path. You can still reject the run to restore it.", {"path": path})


def _rename_file(ctx: ToolContext, args: dict[str, Any]) -> str:
    source, target = _str_arg(args, "from_path"), _str_arg(args, "to_path")
    ws = ctx.repo.workspace
    with ctx.repo.lock:
        if not ws.resolve(source, allow_root=False).is_file():
            raise WorkspaceError("Only files can be renamed by the agent (not directories).", 400)
        ctx.repo.tracker.snapshot(ctx.change_id, ws, source)
        ctx.repo.tracker.snapshot(ctx.change_id, ws, target)
        result = ws.rename(source, target)
        _refresh(ctx, result["from"])
        _refresh(ctx, result["to"])
    ctx.note_modified(result["from"])
    ctx.note_modified(result["to"])
    return f"Renamed {result['from']} to {result['to']}. Update imports that referenced the old path."


# ======================================================================= shell tools
def _format_result(result: CommandResult) -> str:
    status = "timed out" if result.timed_out else "cancelled" if result.cancelled else f"exit code {result.exit_code}"
    return _clip(f"$ {result.command}\n[{status}, {result.duration:.1f}s]\n{result.output}".rstrip())


def _execute(ctx: ToolContext, command: str, cwd: str = "", timeout: int | None = None, kind: str = "command") -> CommandResult:
    result = ctx.repo.terminal.run_streaming(command, cwd, timeout, on_output=ctx.emit_output, cancel=ctx.cancel)
    record = {**result.public(), "kind": kind, "output": result.output[-4000:]}
    ctx.commands.append(record)
    if kind == "tests":
        ctx.tests.append(record)
    if result.exit_code is not None:
        _refresh_after_external_change(ctx)
    return result


def _command_approval(command: str) -> ApprovalRequest | Blocked | None:
    verdict = classify_command(command)
    if verdict.level == "deny":
        return Blocked(verdict.reason)
    if verdict.level == "approve":
        return ApprovalRequest("run_command", "Run command", verdict.reason, {"command": command})
    return None


def _run_command(ctx: ToolContext, args: dict[str, Any]) -> str:
    result = _execute(ctx, _str_arg(args, "command"), _str_arg(args, "cwd"), _int_arg(args, "timeout_seconds", settings.command_timeout_seconds, 5, 600))
    return _format_result(result)


def _approval_run_command(ctx: ToolContext, args: dict[str, Any]) -> ApprovalRequest | Blocked | None:
    return _command_approval(_str_arg(args, "command"))


def _run_tests(ctx: ToolContext, args: dict[str, Any]) -> str:
    command = _str_arg(args, "command") or devtools.detect_test_command(ctx.repo, _str_arg(args, "path"))
    return _format_result(_execute(ctx, command, "", _int_arg(args, "timeout_seconds", 300, 10, 900), kind="tests"))


def _approval_run_tests(ctx: ToolContext, args: dict[str, Any]) -> ApprovalRequest | Blocked | None:
    return _command_approval(_str_arg(args, "command") or devtools.detect_test_command(ctx.repo, _str_arg(args, "path")))


def _run_linter(ctx: ToolContext, args: dict[str, Any]) -> str:
    command = _str_arg(args, "command") or devtools.detect_lint_command(ctx.repo, _str_arg(args, "path"))
    if command is None:
        result = devtools.syntax_check(ctx.repo, _str_arg(args, "path"))
        ctx.commands.append({**result.public(), "kind": "lint"})
        return _format_result(result)
    return _format_result(_execute(ctx, command, "", 180, kind="lint"))


def _approval_run_linter(ctx: ToolContext, args: dict[str, Any]) -> ApprovalRequest | Blocked | None:
    command = _str_arg(args, "command") or devtools.detect_lint_command(ctx.repo, _str_arg(args, "path"))
    return _command_approval(command) if command else None


def _format_target(ctx: ToolContext, args: dict[str, Any]) -> tuple[str, str]:
    command = _str_arg(args, "command")
    if command:
        return command, ""
    return devtools.detect_format_command(ctx.repo, _str_arg(args, "path"))


def _run_formatter(ctx: ToolContext, args: dict[str, Any]) -> str:
    command, group = _format_target(ctx, args)
    scope = devtools.files_in_scope(ctx.repo, _str_arg(args, "path"), group)
    if len(scope) > 400:
        raise ValueError("The formatter would touch more than 400 files; narrow it with 'path'.")
    with ctx.repo.lock:
        for relative in scope:
            ctx.repo.tracker.snapshot(ctx.change_id, ctx.repo.workspace, relative)
        result = _execute(ctx, command, "", 180, kind="format")
        for relative in scope:
            _refresh(ctx, relative)
        for changed in ctx.repo.tracker.summary(ctx.change_id, ctx.repo.workspace):
            ctx.note_modified(changed["path"])
    return _format_result(result)


def _approval_run_formatter(ctx: ToolContext, args: dict[str, Any]) -> ApprovalRequest | Blocked | None:
    command, group = _format_target(ctx, args)
    blocked = _command_approval(command)
    if blocked is not None:
        return blocked
    count = len(devtools.files_in_scope(ctx.repo, _str_arg(args, "path"), group))
    if count > 150:
        return ApprovalRequest("run_formatter", "Format many files", f"The formatter may rewrite up to {count} files.", {"command": command})
    return None


def _approval_git(title: str, reason: str, tool: str, detail_keys: tuple[str, ...]) -> Callable[[ToolContext, dict[str, Any]], ApprovalRequest]:
    def build(ctx: ToolContext, args: dict[str, Any]) -> ApprovalRequest:
        details = {key: args.get(key) for key in detail_keys if args.get(key) is not None}
        if tool == "git_commit" and ctx.repo.git is not None:
            try:
                details["staged_files"] = [f["path"] for f in ctx.repo.git.status()["files"] if f["staged"]][:50]
            except GitError:
                pass
        if tool == "git_push" and ctx.repo.git is not None:
            details.setdefault("branch", ctx.repo.git.current_branch())
            details["remote"] = ctx.repo.git.remote_url()
        return ApprovalRequest(tool, title, reason, details)

    return build


# ======================================================================= registry
def _build_specs() -> dict[str, ToolSpec]:
    specs = [
        ToolSpec("list_files", "List the files and folders directly inside a directory.", _object({"path": _s("Repository-relative directory; empty for the root.")}), _list_files),
        ToolSpec("read_file", "Read a file with line numbers. Long files are returned in pages.", _object({"path": _s("Repository-relative file path."), "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, ["path"]), _read_file),
        ToolSpec("read_files", "Read several small files at once (maximum 8).", _object({"paths": {"type": "array", "items": _STR}}, ["paths"]), _read_files),
        ToolSpec("search_code", "Search file contents for text or a regular expression.", _object({"query": _s("Text or regex."), "regex": {"type": "boolean"}, "case_sensitive": {"type": "boolean"}, "glob": _s("Optional path glob such as src/**/*.ts."), "max_results": {"type": "integer"}}, ["query"]), _search_code),
        ToolSpec("search_filename", "Find files by (part of) their name.", _object({"query": _STR, "max_results": {"type": "integer"}}, ["query"]), _search_filename),
        ToolSpec("find_references", "Find where a function, class or variable is defined and used.", _object({"symbol": _s("An identifier such as parseConfig.")}, ["symbol"]), _find_references),
        ToolSpec("get_repository_tree", "Show the directory tree (generated and vendor folders are skipped).", _object({"path": _STR, "depth": {"type": "integer"}}), _get_repository_tree),
        ToolSpec("get_file_metadata", "Size, language, symbols, imports and importers of one file.", _object({"path": _STR}, ["path"]), _get_file_metadata),
        ToolSpec("write_file", "Create a file or replace its entire content. Prefer edit_file for small changes.", _object({"path": _STR, "content": _s("The complete new file content.")}, ["path", "content"]), _write_file, _approval_write_file),
        ToolSpec("create_file", "Create a new file; fails if it already exists.", _object({"path": _STR, "content": _STR}, ["path"]), _create_file),
        ToolSpec("edit_file", "Replace exact text in an existing file. old_text must match exactly and be unique unless replace_all is true.", _object({"path": _STR, "old_text": _STR, "new_text": _STR, "replace_all": {"type": "boolean"}}, ["path", "old_text", "new_text"]), _edit_file),
        ToolSpec("delete_file", "Delete a file or directory. Requires user approval.", _object({"path": _STR}, ["path"]), _delete_file, _approval_delete),
        ToolSpec("rename_file", "Rename or move a file. Update imports afterwards.", _object({"from_path": _STR, "to_path": _STR}, ["from_path", "to_path"]), _rename_file),
        ToolSpec("git_status", "Show changed, staged and untracked files.", _object({}), _git_status),
        ToolSpec("git_diff", "Show the unified diff of working-tree (or staged) changes.", _object({"path": _STR, "staged": {"type": "boolean"}}), _git_diff),
        ToolSpec("git_log", "Show recent commits.", _object({"count": {"type": "integer"}}), _git_log),
        ToolSpec("git_branch", "List local and remote branches.", _object({}), _git_branch),
        ToolSpec("git_create_branch", "Create a branch and switch to it.", _object({"name": _STR}, ["name"]), _git_create_branch),
        ToolSpec("git_checkout", "Switch branches. Requires user approval.", _object({"name": _STR}, ["name"]), _git_checkout, _approval_git("Switch branch", "Switching branches changes the files on disk.", "git_checkout", ("name",))),
        ToolSpec("git_stage", "Stage files for commit (all changes when paths is omitted).", _object({"paths": {"type": "array", "items": _STR}}), _git_stage),
        ToolSpec("git_commit", "Commit the staged changes. Requires user approval.", _object({"message": _STR}, ["message"]), _git_commit, _approval_git("Commit changes", "A commit records the staged changes in the repository history.", "git_commit", ("message",))),
        ToolSpec("git_push", "Push the current branch to origin. Requires user approval; never call it unless the user asked.", _object({"branch": _STR}), _git_push, _approval_git("Push to GitHub", "This publishes commits to the remote repository.", "git_push", ("branch",))),
        ToolSpec("git_pull", "Fast-forward pull from origin. Requires user approval.", _object({}), _git_pull, _approval_git("Pull from GitHub", "Pulling updates files in the working tree.", "git_pull", ())),
        ToolSpec("run_command", "Run a shell command in the repository. Installs and destructive commands need user approval; dangerous ones are blocked.", _object({"command": _STR, "cwd": _s("Repository-relative working directory."), "timeout_seconds": {"type": "integer"}}, ["command"]), _run_command, _approval_run_command),
        ToolSpec("run_tests", "Run the repository's tests (auto-detects pytest, npm test, go test, cargo test).", _object({"command": _s("Optional explicit test command."), "path": _s("Optional test file or folder."), "timeout_seconds": {"type": "integer"}}), _run_tests, _approval_run_tests),
        ToolSpec("run_linter", "Run the configured linter (falls back to a Python syntax check).", _object({"command": _STR, "path": _STR}), _run_linter, _approval_run_linter),
        ToolSpec("run_formatter", "Run the configured code formatter (ruff, black, npm format, prettier).", _object({"command": _STR, "path": _STR}), _run_formatter, _approval_run_formatter),
    ]
    return {spec.name: spec for spec in specs}


TOOLS = _build_specs()
EXPECTED_ERRORS = (WorkspaceError, GitError, SearchError, PathSecurityError, devtools.ToolSetupError, ValueError)


def tools_for_mode(mode: str) -> list[ToolSpec]:
    if mode == "agent":
        return list(TOOLS.values())
    return [spec for name, spec in TOOLS.items() if name in READ_TOOLS]


def tool_schemas(mode: str) -> list[dict[str, Any]]:
    return [spec.schema() for spec in tools_for_mode(mode)]


async def execute_tool(ctx: ToolContext, name: str, args: dict[str, Any]) -> ToolOutcome:
    """Runs one tool call. Every failure is returned as text so the model can correct itself."""
    spec = TOOLS.get(name)
    if spec is None:
        return ToolOutcome(f"ERROR: unknown tool '{name}'.", False, "unknown tool")
    if spec.name not in {s.name for s in tools_for_mode(ctx.mode)}:
        return ToolOutcome(f"ERROR: '{name}' is not available in {ctx.mode.upper()} mode. This mode cannot modify the repository.", False, "not allowed in this mode")
    if not isinstance(args, dict):
        return ToolOutcome("ERROR: arguments must be a JSON object.", False, "bad arguments")
    try:
        if spec.approval is not None:
            need = await asyncio.to_thread(spec.approval, ctx, args)
            if isinstance(need, Blocked):
                return ToolOutcome(f"BLOCKED: {need.reason}", False, "blocked by safety policy")
            if need is not None:
                if ctx.request_approval is None or not await ctx.request_approval(need):
                    return ToolOutcome("DENIED: the user did not approve this action. Do not retry it; continue without it or ask the user.", False, "declined by user")
        text = await asyncio.to_thread(spec.handler, ctx, args)
        return ToolOutcome(redact(text), True, _summary(name, args))
    except EXPECTED_ERRORS as exc:
        message = getattr(exc, "message", None) or str(exc)
        return ToolOutcome(f"ERROR: {redact(message)}", False, _summary(name, args))
    except Exception as exc:  # a tool bug must not end the agent run
        return ToolOutcome(f"ERROR: the tool failed unexpectedly ({exc.__class__.__name__}).", False, _summary(name, args))


def _summary(name: str, args: dict[str, Any]) -> str:
    for key in ("path", "command", "query", "symbol", "name", "from_path", "message"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return redact(value)[:120]
    return ""
