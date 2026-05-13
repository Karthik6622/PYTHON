import pytest

# Assume login_page and dashboard_page are properly implemented fixtures or page objects

@pytest.fixture
def login_page():
    # Return a page object for login interactions
    # This should be implemented in the actual test framework
    pass

@pytest.fixture
def dashboard_page():
    # Return a page object for dashboard interactions
    # This should be implemented in the actual test framework
    pass

def test_verify_successful_login_using_valid_username_and_password(login_page, dashboard_page):
    """
    Validate successful login functionality using valid credentials.
    Preconditions:
    - Application is accessible
    - User account with valid credentials exists
    """
    username = "valid_user"
    password = "valid_password"

    # Step 1: Launch the application login page
    login_page.open()
    assert login_page.is_displayed(), "Login page should be displayed successfully"

    # Step 2: Enter valid username or email in the username field
    login_page.enter_username(username)
    assert login_page.is_username_accepted(), "Username or email should be accepted"

    # Step 3: Enter valid password in the password field
    login_page.enter_password(password)
    assert login_page.is_password_accepted_and_masked(), "Password should be accepted and masked"

    # Step 4: Ensure the Login button is enabled
    assert login_page.is_login_button_enabled(), "Login button should be enabled"

    # Step 5: Click on the Login button
    login_page.click_login()

    # Validation: User should be redirected to the dashboard
    assert dashboard_page.is_displayed(), "User should be redirected to the dashboard"
    # Post-condition: User session should remain active
    assert dashboard_page.is_session_active(), "User session should remain active"

def test_verify_login_failure_with_invalid_password(login_page):
    """
    Ensure login fails and appropriate error message is displayed when an invalid password is entered.
    Preconditions:
    - Application is accessible
    - User account with valid username exists
    """
    username = "valid_user"
    password = "invalid_password"

    # Step 1: Launch the application login page
    login_page.open()
    assert login_page.is_displayed(), "Login page should be displayed successfully"

    # Step 2: Enter valid username or email in the username field
    login_page.enter_username(username)
    assert login_page.is_username_accepted(), "Username or email should be accepted"

    # Step 3: Enter invalid password in the password field
    login_page.enter_password(password)
    assert login_page.is_password_accepted_and_masked(), "Password should be accepted and masked"

    # Step 4: Ensure the Login button is enabled
    assert login_page.is_login_button_enabled(), "Login button should be enabled"

    # Step 5: Click on the Login button
    login_page.click_login()

    # Validation: A generic error message should be displayed indicating invalid credentials. User should remain on the login page.
    assert login_page.is_error_message_displayed("Invalid credentials"), "A generic error message should be displayed indicating invalid credentials."
    assert login_page.is_displayed(), "User should remain on the login page"
    # Post-conditions
    assert not login_page.is_session_created(), "User session is not created"
