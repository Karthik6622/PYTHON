"""Where the studio's data lives and whether it survives a restart: shown on the Projects and Status pages."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from ats.persistence import get_durable

SETUP_HELP = """\
Add one of these to the app's secrets (Streamlit Cloud: *Settings > Secrets*) or to `.env`:

```toml
# An S3-compatible bucket (AWS S3, Cloudflare R2, Backblaze B2, Supabase Storage, MinIO)
BACKUP_S3_BUCKET = "my-studio-backup"
BACKUP_S3_ACCESS_KEY_ID = "..."
BACKUP_S3_SECRET_ACCESS_KEY = "..."
BACKUP_S3_ENDPOINT = ""   # leave empty for AWS; the provider's S3 endpoint URL for the others
BACKUP_S3_REGION = ""

# or a folder that is kept across restarts (a mounted volume, a synced drive)
BACKUP_DIR = "/path/to/folder"
```

Also set `ATS_SECRET_KEY` to any long random text, so saved connection secrets stay readable after a restore.
"""


def _ago(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S") if timestamp else "not yet"


def alert() -> None:
    """Problems that put data at risk, shown on every page (nothing is shown when all is well)."""
    status = get_durable().status
    if status.restore_error:
        st.error(
            f"The saved data could not be restored ({status.restore_error}). Backups are paused so that nothing good is overwritten. "
            "Check the storage settings and restart the app."
        )


def panel(compact: bool = False) -> None:
    """The backup state. ``compact`` shows only what needs attention (Projects page); the Status page shows everything."""
    status = get_durable().status
    if not status.configured:
        if status.ephemeral_host:
            st.warning(
                "**Your data is not backed up.** This host resets its disk whenever the app restarts or is redeployed, and then accounts, "
                "projects and generated tests are gone. Turn on durable storage to keep them."
            )
            with st.expander("How to turn on durable storage"):
                st.markdown(SETUP_HELP)
        elif not compact:
            st.caption("Data is stored in the data folder of this machine. To also keep a copy elsewhere, set `BACKUP_DIR` or the `BACKUP_S3_*` settings.")
        if status.last_error and not compact:
            st.error(status.last_error)
        return
    if compact and not status.last_error:
        return
    st.markdown("### Data backup")
    a, b, c = st.columns(3)
    a.metric("Backup", "on")
    b.metric("Last snapshot", _ago(status.last_snapshot_at))
    c.metric("Snapshots kept", len(status.snapshots) or "-")
    st.caption(f"Stored in {status.backend}. A snapshot is written about a minute after something changes.")
    if status.restored_from:
        st.success(f"This start restored the saved data from {status.restored_from}.")
    if status.last_error:
        st.error(f"The last backup failed: {status.last_error}")
    if st.button("Back up now", key="durable_backup_now") and not get_durable().snapshot_now(force=True):
        st.error(get_durable().status.last_error or "Nothing was backed up (backups are paused).")
