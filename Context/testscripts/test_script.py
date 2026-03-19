import os
import unittest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


class TestLoginValidCredentials(unittest.TestCase):
    """TC_001: Verify user can log in with valid credentials."""

    def setUp(self):
        chrome_options = webdriver.ChromeOptions()
        if os.getenv("HEADLESS", "").lower() in {"1", "true", "yes"}:
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--window-size=1920,1080")

        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.maximize_window()
        self.wait = WebDriverWait(self.driver, 15)

        # Test data should be supplied via environment variables for security.
        self.base_url = os.getenv("LOGIN_URL", "http://localhost:8000/login")
        self.username = os.getenv("VALID_USERNAME", "testuser")
        self.password = os.getenv("VALID_PASSWORD", "password")

    def _find_first_present(self, locators):
        """Return the first WebElement found from a list of (By, value) locators."""
        last_exc = None
        for by, value in locators:
            try:
                return self.wait.until(EC.presence_of_element_located((by, value)))
            except TimeoutException as exc:
                last_exc = exc
        if last_exc:
            raise last_exc
        raise NoSuchElementException("No locator matched.")

    def test_login_with_valid_credentials(self):
        driver = self.driver
        driver.get(self.base_url)

        # Best-effort locators for common login forms.
        username_field = self._find_first_present([
            (By.ID, "username"),
            (By.NAME, "username"),
            (By.ID, "email"),
            (By.NAME, "email"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.CSS_SELECTOR, "input[type='text']"),
            (By.XPATH, "//input[contains(@placeholder,'User') or contains(@aria-label,'User')]")
        ])

        password_field = self._find_first_present([
            (By.ID, "password"),
            (By.NAME, "password"),
            (By.CSS_SELECTOR, "input[type='password']"),
            (By.XPATH, "//input[@type='password']")
        ])

        username_field.clear()
        username_field.send_keys(self.username)

        password_field.clear()
        password_field.send_keys(self.password)

        login_button = self._find_first_present([
            (By.ID, "login"),
            (By.NAME, "login"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[normalize-space()='Login' or normalize-space()='Sign in' or contains(.,'Login') or contains(.,'Sign in')]")
        ])

        login_button.click()

        # Expected: user dashboard/homepage is displayed.
        # We assert by checking URL change and/or presence of a common dashboard element.
        try:
            self.wait.until(lambda d: d.current_url.rstrip("/") != self.base_url.rstrip("/"))
        except TimeoutException:
            # If URL doesn't change, continue to check for dashboard markers.
            pass

        dashboard_marker = None
        marker_locators = [
            (By.ID, "dashboard"),
            (By.CSS_SELECTOR, "[data-test='dashboard']"),
            (By.XPATH, "//*[contains(translate(., 'DASHBOARDHOME', 'dashboardhome'), 'dashboard') or contains(translate(., 'DASHBOARDHOME', 'dashboardhome'), 'home')]")
        ]

        for by, value in marker_locators:
            try:
                dashboard_marker = self.wait.until(EC.presence_of_element_located((by, value)))
                break
            except TimeoutException:
                continue

        # Also check for absence of a common login error message.
        error_present = False
        error_locators = [
            (By.CSS_SELECTOR, ".error"),
            (By.CSS_SELECTOR, ".alert.alert-danger"),
            (By.XPATH, "//*[contains(translate(., 'INVALIDERROR', 'invaliderror'), 'invalid') or contains(translate(., 'INVALIDERROR', 'invaliderror'), 'error')]")
        ]
        for by, value in error_locators:
            try:
                el = driver.find_element(by, value)
                if el.is_displayed():
                    error_present = True
                    break
            except NoSuchElementException:
                continue

        self.assertFalse(error_present, "Login error message displayed; login may have failed.")

        # Final assertion: either a dashboard marker appears OR URL suggests dashboard/home.
        url_lower = driver.current_url.lower()
        url_indicates_success = any(k in url_lower for k in ["dashboard", "home", "account", "profile"])
        self.assertTrue(
            dashboard_marker is not None or url_indicates_success,
            f"Expected dashboard/homepage after login. Current URL: {driver.current_url}"
        )

    def tearDown(self):
        if getattr(self, "driver", None):
            self.driver.quit()


if __name__ == "__main__":
    unittest.main(verbosity=2)