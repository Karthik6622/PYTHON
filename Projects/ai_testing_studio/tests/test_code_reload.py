"""After a code update (Streamlit reloads the changed modules inside the running server) the shared services are rebuilt from the
new code, so old-class objects never reach new code; running jobs and in-memory GitHub tokens are carried over."""

from __future__ import annotations

import sys
import types

from ats.ui import session


def test_services_are_rebuilt_after_a_code_reload_and_keep_jobs_and_tokens(monkeypatch):
    first = session.get_services()
    assert session.get_services() is first  # unchanged code: the same services
    first.tokens.set("p1", "ghp_token_kept_in_memory")

    monkeypatch.setitem(sys.modules, "ats.models", types.ModuleType("ats.models"))  # what a reload does: a new module object
    second = session.get_services()

    assert second is not first and second.repo is not first.repo and second.testcases is not first.testcases
    assert second.jobs is first.jobs  # the job manager (and its running jobs) survives
    assert second.tokens.get("p1") == "ghp_token_kept_in_memory"
    assert session.get_services() is second
