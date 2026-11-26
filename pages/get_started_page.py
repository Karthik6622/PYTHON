from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class GetStartedPage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def password_textbox(self) -> Locator:
        """Password"""
        return self.locator('get_started.password_textbox')

    @property
    def log_in_button(self) -> Locator:
        """Log in"""
        return self.locator('get_started.log_in_button')

    @property
    def welcome_back_heading(self) -> Locator:
        """Welcome back"""
        return self.locator('get_started.welcome_back_heading')

    @property
    def show_password_button(self) -> Locator:
        """Show password"""
        return self.locator('get_started.show_password_button')

    @property
    def forgot_password_button(self) -> Locator:
        """Forgot password?"""
        return self.locator('get_started.forgot_password_button')

    @property
    def back_to_welcome_button(self) -> Locator:
        """returns user to welcome screen"""
        return self.locator('get_started.back_to_welcome_button')

    @property
    def continue_with_google_button(self) -> Locator:
        """Continue with Google"""
        return self.locator('get_started.continue_with_google_button')

    @property
    def continue_with_github_link(self) -> Locator:
        """Continue with GitHub"""
        return self.locator('get_started.continue_with_github_link')

    @property
    def create_account_button(self) -> Locator:
        """Create account"""
        return self.locator('get_started.create_account_button')

    @property
    def email_textbox(self) -> Locator:
        """Email"""
        return self.locator('get_started.email_textbox')
