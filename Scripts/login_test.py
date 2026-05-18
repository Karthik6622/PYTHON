# login_test.py

import pytest

# --- Fixtures ---

@pytest.fixture
def launch_login_page():
    """
    Fixture to simulate launching the login page.
    Returns a mock page object with basic login functionality.
    """
    class LoginPage:
        def __init__(self):
            self.username = ""
            self.password = ""
            self.login_button_enabled = False
            self.error_message = ""
            self.redirected_to_dashboard = False
            self.session_active = False

        def display(self):
            # Simulate displaying the login page
            return True

        def enter_username(self, username):
            # Simulate entering username and validation
            self.username = username
            self._validate_fields()

        def enter_password(self, password):
            # Simulate entering password (masked)
            self.password = password
            self._validate_fields()

        def _validate_fields(self):
            # Enable the login button only if both fields are non-empty
            self.login_button_enabled = bool(self.username) and bool(self.password)

        def is_login_button_enabled(self):
            return self.login_button_enabled

        def click_login(self):
            # Simulate login logic
            if self.username == "valid_user" and self.password == "valid_password":
                self.redirected_to_dashboard = True
                self.session_active = True
                self.error_message = ""
            else:
                self.redirected_to_dashboard = False
                self.session_active = False
                self.error_message = "Invalid username or password."

        def is_redirected_to_dashboard(self):
            return self.redirected_to_dashboard

        def get_error_message(self):
            return self.error_message

        def is_session_active(self):
            return self.session_active

    return LoginPage()

# --- Testcase 1 ---

def test_verify_successful_login_using_valid_username_and_password(launch_login_page):
    """
    TC_LOGIN_001: Verify successful login using valid username and password.
    """
    login_page = launch_login_page

    # Step 1: Launch the application login page
    assert login_page.display(), "Login page should be displayed successfully"

    # Step 2: Enter valid username or email in the username field
    login_page.enter_username("valid_user")
    assert login_page.username == "valid_user", "Username should be accepted"
    assert login_page.is_login_button_enabled() is False, "Login button should not be enabled until password is entered"

    # Step 3: Enter valid password in the password field
    login_page.enter_password("valid_password")
    assert login_page.password == "valid_password", "Password should be accepted and masked"
    assert login_page.is_login_button_enabled() is True, "Login button should be enabled after valid input"

    # Step 4: Ensure Login button is enabled
    assert login_page.is_login_button_enabled(), "Login button must be enabled"

    # Step 5: Click on the Login button
    login_page.click_login()
    assert login_page.is_redirected_to_dashboard(), "User should be redirected to dashboard"
    assert login_page.is_session_active(), "User session should be active"
    assert login_page.get_error_message() == "", "No error message should be displayed"

# --- Testcase 2 ---

def test_verify_login_failure_with_invalid_password(launch_login_page):
    """
    TC_LOGIN_002: Verify login failure with invalid password.
    """
    login_page = launch_login_page

    # Step 1: Launch the application login page
    assert login_page.display(), "Login page should be displayed successfully"

    # Step 2: Enter valid username or email in the username field
    login_page.enter_username("valid_user")
    assert login_page.username == "valid_user", "Username should be accepted"
    assert login_page.is_login_button_enabled() is False, "Login button should not be enabled until password is entered"

    # Step 3: Enter invalid password in the password field
    login_page.enter_password("invalid_password")
    assert login_page.password == "invalid_password", "Password should be accepted and masked"
    assert login_page.is_login_button_enabled() is True, "Login button should be enabled after valid input"

    # Step 4: Ensure Login button is enabled
    assert login_page.is_login_button_enabled(), "Login button must be enabled"

    # Step 5: Click on the Login button
    login_page.click_login()
    assert not login_page.is_redirected_to_dashboard(), "User should remain on login page"
    assert not login_page.is_session_active(), "No user session should be created"
    assert login_page.get_error_message() == "Invalid username or password.", "Generic error message should be displayed"
