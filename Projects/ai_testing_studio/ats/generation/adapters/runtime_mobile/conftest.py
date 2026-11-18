import re

import pytest

from drivers.appium_driver import create_driver, load_capabilities, start_server
from drivers.mobile_session import MobileSession


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    setattr(item, "rep_" + call.when, outcome.get_result())


@pytest.fixture(scope="session")
def appium_driver():
    """One Appium session for the whole run: starts a local Appium server unless APPIUM_SERVER_URL is set, and stops it afterwards."""
    url, stop_server = start_server()
    driver = None
    try:
        driver = create_driver(url, load_capabilities())
        yield driver
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:  # the session may already be gone
                pass
        stop_server()


@pytest.fixture
def mobile(appium_driver, request):
    marker = request.node.get_closest_marker("tc")
    test_case_id = marker.args[0] if marker else re.sub(r"\W+", "_", request.node.name)
    session = MobileSession(appium_driver, test_case_id)
    session.start_test()
    yield session
    report = getattr(request.node, "rep_call", None)
    session.finish(failed=bool(report and report.failed), error=getattr(report, "longreprtext", "") if report and report.failed else "")
