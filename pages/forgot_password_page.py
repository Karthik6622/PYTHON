from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class ForgotPasswordPage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def email_textbox(self) -> Locator:
        """Email"""
        return self.locator('forgot_password.email_textbox')

    @property
    def continue_button(self) -> Locator:
        """Continue"""
        return self.locator('forgot_password.continue_button')

    @property
    def back_to_log_in_button(self) -> Locator:
        """Back to log in"""
        return self.locator('forgot_password.back_to_log_in_button')

    @property
    def email_label(self) -> Locator:
        """Email"""
        return self.locator('forgot_password.email_label')

    @property
    def signed_up_with_google_or_github_you_can_div(self) -> Locator:
        """Signed up with Google or GitHub? You can keep using those bu"""
        return self.locator('forgot_password.signed_up_with_google_or_github_you_can_div')
