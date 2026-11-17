import os
import re
from pathlib import Path

import pytest

from utils.app import App

DEFAULT_BASE_URL = 'https://personalpartner.streamlit.app/'


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "ignore_https_errors": os.environ.get("IGNORE_HTTPS_ERRORS") == "1"}


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    setattr(item, "rep_" + call.when, outcome.get_result())


@pytest.fixture
def app(page, request):
    marker = request.node.get_closest_marker("tc")
    test_case_id = marker.args[0] if marker else re.sub(r"\W+", "_", request.node.name)
    session = App(page, os.environ.get("BASE_URL") or DEFAULT_BASE_URL, test_case_id)
    yield session
    report = getattr(request.node, "rep_call", None)
    session.finish(failed=bool(report and report.failed))
