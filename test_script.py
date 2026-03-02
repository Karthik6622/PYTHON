import os
import time
import unittest

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class TestValidLoginTC001(unittest.TestCase):
    """TC_001 - Verify user can log in with valid credentials."""

    def setUp(self):
        chrome_options = webdriver.ChromeOptions()
        # Useful defaults for CI; safe locally too.
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1280,800")

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.maximize_window()
        self.wait = WebDriverWait(self.driver, 15)

        # Best-effort configuration via environment variables.
        # Update these as needed for your AUT.
        self.base_url = os.getenv("LOGIN_URL", "https://example.com/login")
        self.username = os.getenv("LOGIN_USERNAME", "valid_username")
        self.password = os.getenv("LOGIN_PASSWORD", "valid_password")

    def _find_first_present(self, locators):
        """Return the first WebElement found using the provided locator list."""
        last_exc = None
        for by, value in locators:
            try:
                element = self.wait.until(EC.presence_of_element_located((by, value)))
                return element
            except TimeoutException as exc:
                last_exc = exc
        raise NoSuchElementException(f"None of the locators matched: {locators}") from last_exc

    def test_valid_login(self):
        driver = self.driver

        # Step: Browser is open on the login page.
        driver.get(self.base_url)

        # Step: Enter a valid username.
        username_input = self._find_first_present(
            [
                (By.ID, "username"),
                (By.NAME, "username"),
                (By.ID, "email"),
                (By.NAME, "email"),
                (By.CSS_SELECTOR, "input[type='text']"),
            ]
        )
        username_input.clear()
        username_input.send_keys(self.username)

        # Step: Enter the correct password.
        password_input = self._find_first_present(
            [
                (By.ID, "password"),
                (By.NAME, "password"),
                (By.CSS_SELECTOR, "input[type='password']"),
            ]
        )
        password_input.clear()
        password_input.send_keys(self.password)

        # Step: Click the Login button.
        login_button = self._find_first_present(
            [
                (By.ID, "login"),
                (By.NAME, "login"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[contains(translate(normalize-space(.), 'LOGIN', 'login'), 'login')]") ,
                (By.XPATH, "//input[@type='submit']"),
            ]
        )
        try:
            login_button.click()
        except Exception:
            # Fallback: some pages require submit on a form.
            password_input.submit()

        # Expected Result: User is successfully logged in and dashboard/homepage is displayed.
        # Best-effort assertions without AUT-specific selectors.
        # 1) URL changes away from /login (common pattern)
        try:
            self.wait.until(lambda d: d.current_url != self.base_url)
        except TimeoutException:
            # Not all apps change URL; continue with other checks.
            pass

        # 2) Look for common dashboard markers.
        dashboard_markers = [
            (By.ID, "dashboard"),
            (By.CSS_SELECTOR, "[data-test='dashboard']"),
            (By.XPATH, "//*[contains(translate(normalize-space(.), 'DASHBOARDHOME', 'dashboardhome'), 'dashboard')]") ,
            (By.XPATH, "//*[contains(translate(normalize-space(.), 'DASHBOARDHOME', 'dashboardhome'), 'home')]") ,
            (By.CSS_SELECTOR, "nav"),
        ]

        marker_found = False
        for by, value in dashboard_markers:
            try:
                self.wait.until(EC.presence_of_element_located((by, value)))
                marker_found = True
                break
            except TimeoutException:
                continue

        # 3) Ensure no obvious login error is displayed.
        error_locators = [
            (By.CSS_SELECTOR, ".error"),
            (By.CSS_SELECTOR, ".alert.alert-danger"),
            (By.CSS_SELECTOR, "[role='alert']"),
            (By.XPATH, "//*[contains(translate(normalize-space(.), 'INVALIDERROR', 'invaliderror'), 'invalid')]"),
            (By.XPATH, "//*[contains(translate(normalize-space(.), 'INVALIDERROR', 'invaliderror'), 'error')]"),
        ]

        error_visible = False
        for by, value in error_locators:
            try:
                el = WebDriverWait(driver, 2).until(EC.presence_of_element_located((by, value)))
                if el and el.is_displayed() and el.text.strip():
                    error_visible = True
                    break
            except TimeoutException:
                continue

        self.assertFalse(error_visible, "Login error message appears to be displayed.")

        # Final assertion: either a dashboard marker is found OR URL no longer looks like login.
        url_lower = driver.current_url.lower()
        not_login_url = ("login" not in url_lower) or (driver.current_url != self.base_url)
        self.assertTrue(
            marker_found or not_login_url,
            f"Dashboard/homepage not detected. current_url={driver.current_url}",
        )

        # Small pause for stability when running interactively.
        time.sleep(1)

    def tearDown(self):
        try:
            self.driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main(verbosity=2)