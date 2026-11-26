from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class GetStartedPage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def welcome_back_heading(self) -> Locator:
        """Welcome back"""
        return self.locator('get_started.welcome_back_heading')

    @property
    def email_textbox(self) -> Locator:
        """Email"""
        return self.locator('get_started.email_textbox')

    @property
    def password_textbox(self) -> Locator:
        """Password"""
        return self.locator('get_started.password_textbox')

    @property
    def log_in_button(self) -> Locator:
        """Log in"""
        return self.locator('get_started.log_in_button')

    @property
    def forgot_password_button(self) -> Locator:
        """Forgot password?"""
        return self.locator('get_started.forgot_password_button')
