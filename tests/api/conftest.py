import re

import pytest

from utils.api import ApiSession


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    setattr(item, "rep_" + call.when, outcome.get_result())


@pytest.fixture
def api(request):
    marker = request.node.get_closest_marker("tc")
    test_case_id = marker.args[0] if marker else re.sub(r"\W+", "_", request.node.name)
    session = ApiSession(test_case_id)
    yield session
    report = getattr(request.node, "rep_call", None)
    session.finish(failed=bool(report and report.failed))
    session.close()
