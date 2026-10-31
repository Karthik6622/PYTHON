"""Shared test setup: isolated data directory, no real API key, local fixture website."""

from __future__ import annotations

import functools
import http.server
import os
import tempfile
import threading
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="ats_tests_")
os.environ["DATA_DIR"] = _TMP
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(_TMP) / "test.db").replace("\\", "/")
os.environ["ALLOW_PRIVATE_NETWORK"] = "true"
os.environ["EXECUTION_MODE"] = "local"
os.environ["MODEL_API_KEY"] = "test-key-not-real"
os.environ["NVIDIA_API_KEY"] = ""
os.environ["MODEL_MAX_RETRIES"] = "2"

SITE_DIR = Path(__file__).parent / "fixtures" / "site"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:  # noqa: D401
        return


@pytest.fixture(scope="session")
def site_url() -> str:
    handler = functools.partial(_QuietHandler, directory=str(SITE_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture()
def repo():
    from ats.config import get_settings
    from ats.db import Database
    from ats.repository import Repository

    db = Database(Path(tempfile.mkdtemp(prefix="ats_db_", dir=_TMP)) / "t.db")
    del get_settings
    return Repository(db)


@pytest.fixture(scope="session")
def browser_ready() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            browser.close()
        return True
    except Exception:  # noqa: BLE001
        return False
