from __future__ import annotations

from pages.base_page import BasePage
from utils.element import Element


class GetStartedPage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def email_div(self) -> Element:
        """Email"""
        return self.element('get_started.email_div')

    @property
    def email_textbox(self) -> Element:
        """Email"""
        return self.element('get_started.email_textbox')

    @property
    def password_div(self) -> Element:
        """Password"""
        return self.element('get_started.password_div')

    @property
    def password_textbox(self) -> Element:
        """Password"""
        return self.element('get_started.password_textbox')

    @property
    def show_password_button(self) -> Element:
        """Show password"""
        return self.element('get_started.show_password_button')

    @property
    def log_in_button(self) -> Element:
        """Log in"""
        return self.element('get_started.log_in_button')

    @property
    def forgot_password_button(self) -> Element:
        """Forgot password?"""
        return self.element('get_started.forgot_password_button')

    @property
    def create_account_button(self) -> Element:
        """Create account"""
        return self.element('get_started.create_account_button')

    @property
    def back_to_welcome_button(self) -> Element:
        """Back to welcome"""
        return self.element('get_started.back_to_welcome_button')

    @property
    def continue_with_google_button(self) -> Element:
        """Continue with Google"""
        return self.element('get_started.continue_with_google_button')

    @property
    def continue_with_github_link(self) -> Element:
        """Continue with GitHub"""
        return self.element('get_started.continue_with_github_link')
