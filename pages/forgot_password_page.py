from __future__ import annotations

from pages.base_page import BasePage
from utils.element import Element


class ForgotPasswordPage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def enter_the_email_address_on_your_account_div(self) -> Element:
        """Enter the email address on your account."""
        return self.element('forgot_password.enter_the_email_address_on_your_account_div')

    @property
    def email_textbox(self) -> Element:
        """Email"""
        return self.element('forgot_password.email_textbox')

    @property
    def continue_button(self) -> Element:
        """Continue"""
        return self.element('forgot_password.continue_button')

    @property
    def back_to_log_in_button(self) -> Element:
        """Back to log in"""
        return self.element('forgot_password.back_to_log_in_button')

    @property
    def signed_up_with_google_or_github_you_can_div(self) -> Element:
        """Signed up with Google or GitHub? You can keep using those bu"""
        return self.element('forgot_password.signed_up_with_google_or_github_you_can_div')

    @property
    def email_div(self) -> Element:
        """Email"""
        return self.element('forgot_password.email_div')
