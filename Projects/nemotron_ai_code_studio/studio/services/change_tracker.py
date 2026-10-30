"""Remembers what the AI agent changed so the user can accept it or reject (revert) it after reviewing the diff."""

from __future__ import annotations

import difflib
import threading
import time
import uuid
from dataclasses import dataclass, field

from .workspace_service import WorkspaceError, WorkspaceService


@dataclass
class _Snapshot:
    existed: bool
    content: bytes | None


@dataclass
class ChangeSet:
    id: str
    snapshots: dict[str, _Snapshot] = field(default_factory=dict)
    status: str = "open"  # open | accepted | rejected
    created_at: float = field(default_factory=time.time)


def _decode(data: bytes | None) -> list[str] | None:
    if data is None:
        return []
    try:
        return data.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return None


class ChangeTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sets: dict[str, ChangeSet] = {}

    def begin(self) -> str:
        change_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._sets[change_id] = ChangeSet(change_id)
            if len(self._sets) > 50:
                oldest = sorted(self._sets.values(), key=lambda item: item.created_at)[0]
                self._sets.pop(oldest.id, None)
        return change_id

    def get(self, change_id: str) -> ChangeSet | None:
        return self._sets.get(change_id)

    def snapshot(self, change_id: str, workspace: WorkspaceService, relative: str) -> None:
        """Record the file as it is now, once, before the agent first touches it."""
        changes = self._sets.get(change_id)
        if changes is None or relative in changes.snapshots:
            return
        path = workspace.resolve(relative, allow_root=False)
        if path.is_file():
            changes.snapshots[relative] = _Snapshot(True, path.read_bytes())
        else:
            changes.snapshots[relative] = _Snapshot(False, None)

    def summary(self, change_id: str, workspace: WorkspaceService) -> list[dict]:
        changes = self._sets.get(change_id)
        if changes is None:
            return []
        result = []
        for relative, snap in changes.snapshots.items():
            path = workspace.resolve(relative, allow_root=False)
            now = path.read_bytes() if path.is_file() else None
            if snap.existed and now is None:
                status = "deleted"
            elif not snap.existed and now is not None:
                status = "added"
            elif snap.content != now:
                status = "modified"
            else:
                continue
            before, after = _decode(snap.content), _decode(now)
            adds = dels = 0
            if before is not None and after is not None:
                for line in difflib.unified_diff(before, after, n=0):
                    if line.startswith("+") and not line.startswith("+++"):
                        adds += 1
                    elif line.startswith("-") and not line.startswith("---"):
                        dels += 1
            result.append({"path": relative, "status": status, "additions": adds, "deletions": dels})
        return sorted(result, key=lambda item: item["path"])

    def file_diff(self, change_id: str, workspace: WorkspaceService, relative: str, max_chars: int = 60_000) -> str:
        """Unified diff of one tracked file against its state before the run."""
        changes = self._sets.get(change_id)
        snap = changes.snapshots.get(relative) if changes is not None else None
        if snap is None:
            return ""
        path = workspace.resolve(relative, allow_root=False)
        now = path.read_bytes() if path.is_file() else None
        if snap.content == now:
            return ""
        before, after = _decode(snap.content), _decode(now)
        if before is None or after is None:
            return f"Binary file {relative} changed\n"
        lines = difflib.unified_diff(
            before, after,
            fromfile="/dev/null" if not snap.existed else f"a/{relative}",
            tofile="/dev/null" if now is None else f"b/{relative}",
        )
        return "".join(line if line.endswith("\n") else line + "\n" for line in lines)[:max_chars]

    def diff_text(self, change_id: str, workspace: WorkspaceService, max_chars: int = 200_000) -> str:
        changes = self._sets.get(change_id)
        if changes is None:
            return ""
        parts: list[str] = []
        for relative, snap in changes.snapshots.items():
            path = workspace.resolve(relative, allow_root=False)
            now = path.read_bytes() if path.is_file() else None
            before, after = _decode(snap.content), _decode(now)
            if snap.content == now:
                continue
            if before is None or after is None:
                parts.append(f"Binary file {relative} changed\n")
                continue
            parts.extend(difflib.unified_diff(
                before, after,
                fromfile="/dev/null" if not snap.existed else f"a/{relative}",
                tofile="/dev/null" if now is None else f"b/{relative}",
            ))
            if parts and not parts[-1].endswith("\n"):
                parts.append("\n")
        return "".join(parts)[:max_chars]

    def accept(self, change_id: str) -> bool:
        changes = self._sets.get(change_id)
        if changes is None:
            return False
        changes.status = "accepted"
        return True

    def reject(self, change_id: str, workspace: WorkspaceService) -> list[str]:
        """Restore every file the agent touched to the state it had before the run."""
        changes = self._sets.get(change_id)
        if changes is None:
            raise WorkspaceError("Unknown change set.", 404)
        restored: list[str] = []
        for relative, snap in changes.snapshots.items():
            path = workspace.resolve(relative, allow_root=False)
            if snap.existed and snap.content is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.is_file() or path.read_bytes() != snap.content:
                    path.write_bytes(snap.content)
                    restored.append(relative)
            elif path.is_file():
                path.unlink()
                restored.append(relative)
        changes.status = "rejected"
        return restored

    def keep_file(self, change_id: str, relative: str) -> None:
        """The user keeps this file's changes: forget its snapshot so it no longer shows as pending."""
        changes = self._sets.get(change_id)
        if changes is not None:
            changes.snapshots.pop(relative, None)

    def revert_file(self, change_id: str, workspace: WorkspaceService, relative: str) -> bool:
        """Restore a single file to the state it had before the run, then forget its snapshot."""
        changes = self._sets.get(change_id)
        snap = changes.snapshots.get(relative) if changes is not None else None
        if changes is None or snap is None:
            return False
        path = workspace.resolve(relative, allow_root=False)
        if snap.existed and snap.content is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(snap.content)
        elif path.is_file():
            path.unlink()
        changes.snapshots.pop(relative, None)
        return True
