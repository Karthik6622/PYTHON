"""Durable copy of the studio's data (accounts, projects, generated files) for hosts that lose their disk when they restart.

Streamlit Community Cloud, Heroku-style hosts and most containers start every restart (and every redeploy) with an empty disk, so the
SQLite files and project folders in ``DATA_DIR`` vanish. This module keeps a copy outside the host:

* a background thread writes a compressed snapshot whenever the data changed (at most once per ``MIN_INTERVAL`` seconds);
* on start-up, when the local data folder is empty, the newest snapshot is restored before anything opens the databases.

Where the copy goes is configured with ``BACKUP_DIR`` (a folder, for example a synced drive) or an S3-compatible bucket
(``BACKUP_S3_BUCKET`` plus its keys; works with AWS S3, Cloudflare R2, Backblaze B2, Supabase Storage, MinIO). Nothing is uploaded
unless one of them is set. Old snapshots are kept (``KEEP``) so a bad snapshot never destroys the only good one, and uploads stop
for the rest of the process when a restore failed, so an empty start cannot overwrite a good backup.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tarfile
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from ats.logging_setup import get_logger

LOGGER = get_logger("persistence")
PREFIX = "snapshot-"
SUFFIX = ".tar.gz"
KEEP = 10  # snapshots kept; older ones are deleted after a successful upload
MIN_INTERVAL = 60  # seconds between two uploads
POLL_INTERVAL = 20  # seconds between two checks for changes
MAX_FILE_BYTES = 25 * 1024 * 1024  # larger single files (APK uploads, videos) stay out of the snapshot
FOLDERS = ("projects", "secure")  # data sub-folders that are part of the snapshot (run workspaces are temporary and excluded)


# ----------------------------------------------------------------------------------------
# backends
# ----------------------------------------------------------------------------------------
class Backend(Protocol):
    label: str

    def put(self, name: str, source: Path) -> None: ...

    def get(self, name: str, target: Path) -> None: ...

    def names(self) -> list[str]: ...

    def delete(self, name: str) -> None: ...


class FolderBackend:
    """A folder on a disk that survives restarts (a mounted volume, a synced cloud drive)."""

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        self.label = f"folder {self.folder}"

    def put(self, name: str, source: Path) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        partial = self.folder / (name + ".partial")
        shutil.copyfile(source, partial)
        os.replace(partial, self.folder / name)  # a half-written file is never listed as a snapshot

    def get(self, name: str, target: Path) -> None:
        shutil.copyfile(self.folder / name, target)

    def names(self) -> list[str]:
        return sorted(p.name for p in self.folder.glob(f"{PREFIX}*{SUFFIX}")) if self.folder.is_dir() else []

    def delete(self, name: str) -> None:
        (self.folder / name).unlink(missing_ok=True)


class S3Backend:
    """An S3-compatible bucket. ``boto3`` is imported only when this backend is used."""

    def __init__(self, bucket: str, prefix: str, endpoint: str, region: str, key_id: str, secret: str) -> None:
        import boto3  # noqa: PLC0415 - optional dependency

        self.bucket = bucket
        self.prefix = prefix.strip("/") + "/" if prefix.strip("/") else ""
        self.client = boto3.client(
            "s3", endpoint_url=endpoint or None, region_name=region or None, aws_access_key_id=key_id or None, aws_secret_access_key=secret or None
        )
        self.label = f"bucket {bucket}" + (f" ({endpoint})" if endpoint else "")

    def put(self, name: str, source: Path) -> None:
        self.client.upload_file(str(source), self.bucket, self.prefix + name)

    def get(self, name: str, target: Path) -> None:
        self.client.download_file(self.bucket, self.prefix + name, str(target))

    def names(self) -> list[str]:
        found: list[str] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix + PREFIX):
            found += [item["Key"][len(self.prefix) :] for item in page.get("Contents", [])]
        return sorted(n for n in found if n.startswith(PREFIX) and n.endswith(SUFFIX))

    def delete(self, name: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self.prefix + name)


def backend_from_settings(lookup) -> Backend | None:  # noqa: ANN001 - ``lookup`` is ``ats.config.lookup_secret``
    """The configured backend, or ``None`` when no durable storage is set up."""
    folder = lookup("BACKUP_DIR").strip()
    if folder:
        return FolderBackend(Path(folder))
    bucket = lookup("BACKUP_S3_BUCKET").strip()
    if bucket:
        return S3Backend(
            bucket, lookup("BACKUP_S3_PREFIX") or "rk-testing-studio", lookup("BACKUP_S3_ENDPOINT").strip(), lookup("BACKUP_S3_REGION").strip(),
            lookup("BACKUP_S3_ACCESS_KEY_ID").strip(), lookup("BACKUP_S3_SECRET_ACCESS_KEY").strip(),
        )  # fmt: skip
    return None


# ----------------------------------------------------------------------------------------
# snapshot and restore
# ----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Layout:
    """Where the studio keeps its data. Passed in (not read from the settings here) so the logic is testable."""

    data_dir: Path
    db: Path  # studio database
    users_db: Path  # accounts database

    def databases(self) -> dict[str, Path]:
        return {"db/studio.db": self.db, "db/users.db": self.users_db}

    def is_fresh(self) -> bool:
        """True on a host that lost its disk: neither database exists yet."""
        return not self.db.exists() and not self.users_db.exists()


def _copy_database(source: Path, target: Path) -> None:
    """Consistent copy of a live SQLite file (the backup API handles pending WAL pages and concurrent writers)."""
    reader = sqlite3.connect(source, timeout=30)
    writer = sqlite3.connect(target)
    try:
        reader.backup(writer)
    finally:
        writer.close()
        reader.close()


def _files(layout: Layout) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    for folder in FOLDERS:
        root = layout.data_dir / folder
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            try:
                if path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_FILE_BYTES:
                    found.append((path, f"files/{folder}/{path.relative_to(root).as_posix()}"))
            except OSError:
                continue
    return found


def signature(layout: Layout) -> tuple:
    """Cheap fingerprint of everything a snapshot contains; equal fingerprints mean nothing changed."""
    parts: list[tuple] = []
    for path in [*layout.databases().values(), *(Path(str(p) + "-wal") for p in layout.databases().values())]:
        try:
            info = path.stat()
            parts.append((str(path), info.st_mtime_ns, info.st_size))
        except OSError:
            parts.append((str(path), 0, 0))
    files = _files(layout)
    newest = 0
    for path, _ in files:
        try:
            newest = max(newest, path.stat().st_mtime_ns)
        except OSError:
            pass
    return (tuple(parts), len(files), newest)


def make_snapshot(layout: Layout, target: Path) -> int:
    """Write the snapshot archive to ``target``; returns the number of files in it."""
    count = 0
    with tempfile.TemporaryDirectory(prefix="ats_snapshot_") as scratch, tarfile.open(target, "w:gz") as archive:
        for arcname, path in layout.databases().items():
            if not path.exists():
                continue
            copy = Path(scratch) / arcname.replace("/", "_")
            _copy_database(path, copy)
            archive.add(copy, arcname=arcname)
            count += 1
        for path, arcname in _files(layout):
            try:
                archive.add(path, arcname=arcname, recursive=False)
                count += 1
            except OSError:  # a file removed while the snapshot was being written
                continue
    return count


def _safe_target(layout: Layout, name: str) -> Path | None:
    """Where an archive member may be written, or ``None`` when it is not one of the known locations (path traversal, stray files)."""
    if name.startswith("/") or ".." in Path(name).parts:
        return None
    databases = layout.databases()
    if name in databases:
        return databases[name]
    for folder in FOLDERS:
        marker = f"files/{folder}/"
        if name.startswith(marker) and len(name) > len(marker):
            return layout.data_dir / folder / name[len(marker) :]
    return None


def restore_snapshot(layout: Layout, archive_path: Path) -> int:
    """Unpack a snapshot into ``layout``; returns the number of files restored. Databases are swapped in atomically."""
    restored = 0
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive:
            target = _safe_target(layout, member.name)
            if target is None or not member.isfile():
                continue
            source = archive.extractfile(member)
            if source is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(target.name + ".restoring")
            with source, open(partial, "wb") as out:
                shutil.copyfileobj(source, out)
            if member.name.startswith("db/"):
                for extra in ("-wal", "-shm"):
                    Path(str(target) + extra).unlink(missing_ok=True)  # leftovers of an older file must not be replayed into the restored one
            os.replace(partial, target)
            restored += 1
    return restored


# ----------------------------------------------------------------------------------------
# the running service
# ----------------------------------------------------------------------------------------
@dataclass
class Status:
    configured: bool = False
    backend: str = ""
    ephemeral_host: bool = False
    restored_from: str = ""
    restore_error: str = ""
    last_snapshot_at: float = 0.0
    last_snapshot_name: str = ""
    last_error: str = ""
    uploads_enabled: bool = False
    snapshots: list[str] = field(default_factory=list)


class Durable:
    def __init__(self, layout: Layout, backend: Backend | None, ephemeral_host: bool = False) -> None:
        self.layout, self.backend = layout, backend
        self.status = Status(configured=backend is not None, backend=backend.label if backend else "", ephemeral_host=ephemeral_host)
        self._lock = threading.Lock()
        self._last_signature: tuple | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ start-up
    def restore_if_fresh(self) -> None:
        """Bring the data back on a host with an empty disk. Must run before any database is opened."""
        if self.backend is None:
            return
        if not self.layout.is_fresh():
            self.status.uploads_enabled = True  # the local data is the newest truth
            return
        try:
            names = self.backend.names()
            if not names:
                self.status.uploads_enabled = True  # a first start: nothing to restore
                return
            newest = names[-1]
            with tempfile.TemporaryDirectory(prefix="ats_restore_") as scratch:
                archive = Path(scratch) / newest
                self.backend.get(newest, archive)
                files = restore_snapshot(self.layout, archive)
            self.status.restored_from = newest
            self.status.uploads_enabled = True
            LOGGER.info("Restored %s files from %s", files, newest)
        except Exception as exc:  # noqa: BLE001 - whatever failed, uploading an empty start over the good backup would be worse
            self.status.restore_error = f"{type(exc).__name__}: {str(exc)[:200]}"
            self.status.uploads_enabled = False
            LOGGER.error("Restore failed; uploads are switched off for this process: %s", self.status.restore_error)

    # ------------------------------------------------------------------ snapshots
    def snapshot_now(self, force: bool = False) -> bool:
        """Upload a snapshot when something changed (or ``force``). Returns True when one was written."""
        if self.backend is None or not self.status.uploads_enabled:
            return False
        with self._lock:
            current = signature(self.layout)
            if not force and current == self._last_signature:
                return False
            name = PREFIX + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + SUFFIX
            try:
                with tempfile.TemporaryDirectory(prefix="ats_upload_") as scratch:
                    archive = Path(scratch) / name
                    make_snapshot(self.layout, archive)
                    self.backend.put(name, archive)
                self._prune()
            except Exception as exc:  # noqa: BLE001 - the next round tries again; the app must keep working
                self.status.last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
                LOGGER.warning("Snapshot failed: %s", self.status.last_error)
                return False
            self._last_signature = current
            self.status.last_snapshot_at, self.status.last_snapshot_name, self.status.last_error = time.time(), name, ""
            return True

    def _prune(self) -> None:
        assert self.backend is not None
        names = self.backend.names()
        self.status.snapshots = names[-KEEP:]
        for old in names[:-KEEP]:
            try:
                self.backend.delete(old)
            except Exception:  # noqa: BLE001 - an old snapshot that cannot be deleted is only wasted space
                LOGGER.warning("Could not delete the old snapshot %s", old)

    def start(self) -> None:
        """Restore if needed and begin the background snapshots (once per process)."""
        if self._thread is not None:
            return
        self.restore_if_fresh()
        if self.backend is None:
            return
        self._thread = threading.Thread(target=self._loop, name="ats-durable", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        last_upload = 0.0
        while True:
            time.sleep(POLL_INTERVAL)
            if time.time() - last_upload >= MIN_INTERVAL and self.snapshot_now():
                last_upload = time.time()


# ----------------------------------------------------------------------------------------
# process-wide instance
# ----------------------------------------------------------------------------------------
_INSTANCE: Durable | None = None
_INSTANCE_LOCK = threading.Lock()


def is_ephemeral_host(root: Path) -> bool:
    """Streamlit Community Cloud runs the app from ``/mount/src`` as ``adminuser``; its disk is reset on every restart."""
    return root.as_posix().startswith("/mount/src") or os.environ.get("HOME", "") == "/home/adminuser"


def get_durable() -> Durable:
    """The process-wide service, created from the settings on first use. Call ``.start()`` before opening any database."""
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            from ats.config import ROOT_DIR, get_settings, lookup_secret

            settings = get_settings()
            layout = Layout(settings.data_dir, settings.db_path, settings.users_db_path)
            try:
                backend = backend_from_settings(lookup_secret)
            except Exception as exc:  # noqa: BLE001 - a bad bucket setting must not stop the app from starting
                LOGGER.error("Durable storage is misconfigured: %s", exc)
                backend = None
            _INSTANCE = Durable(layout, backend, ephemeral_host=is_ephemeral_host(ROOT_DIR))
            if backend is None and lookup_secret("BACKUP_S3_BUCKET"):
                _INSTANCE.status.last_error = "The bucket settings could not be used (is boto3 installed?)."
        return _INSTANCE


__all__ = ["Backend", "Durable", "FolderBackend", "Layout", "S3Backend", "Status", "backend_from_settings", "get_durable", "make_snapshot", "restore_snapshot", "signature"]
