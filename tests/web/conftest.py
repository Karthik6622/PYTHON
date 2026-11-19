import os
import re

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.service import Service as EdgeService

from utils.app import App

DEFAULT_BASE_URL = 'https://personalpartner.streamlit.app/'
DEFAULT_BROWSER = 'chrome'


def build_driver(browser: str):
    headless = os.environ.get("HEADLESS", "1") != "0"
    insecure = os.environ.get("IGNORE_HTTPS_ERRORS") == "1"
    if browser == "firefox":
        options = webdriver.FirefoxOptions()
        if headless:
            options.add_argument("-headless")
        options.accept_insecure_certs = insecure
        return webdriver.Firefox(options=options)
    options = webdriver.EdgeOptions() if browser == "edge" else webdriver.ChromeOptions()
    for argument in ("--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900"):
        options.add_argument(argument)
    if headless:
        options.add_argument("--headless=new")
    options.accept_insecure_certs = insecure
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    binary = os.environ.get("CHROME_BIN")
    if binary and browser != "edge":
        options.binary_location = binary
    driver_path = os.environ.get("CHROMEDRIVER")
    if browser == "edge":
        return webdriver.Edge(options=options, service=EdgeService(driver_path) if driver_path else None)
    return webdriver.Chrome(options=options, service=ChromeService(driver_path) if driver_path else None)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    setattr(item, "rep_" + call.when, outcome.get_result())


@pytest.fixture
def app(request):
    browser = (os.environ.get("BROWSER") or DEFAULT_BROWSER).lower()
    driver = build_driver(browser)
    marker = request.node.get_closest_marker("tc")
    test_case_id = marker.args[0] if marker else re.sub(r"\W+", "_", request.node.name)
    session = App(driver, os.environ.get("BASE_URL") or DEFAULT_BASE_URL, test_case_id)
    yield session
    report = getattr(request.node, "rep_call", None)
    try:
        session.finish(failed=bool(report and report.failed))
    finally:
        driver.quit()
