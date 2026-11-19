from __future__ import annotations

from pages.base_page import BasePage
from utils.element import Element


class CreateAccountPage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def display_name_div(self) -> Element:
        """Display name"""
        return self.element('create_account.display_name_div')

    @property
    def display_name_textbox(self) -> Element:
        """Display name"""
        return self.element('create_account.display_name_textbox')

    @property
    def email_div(self) -> Element:
        """Email"""
        return self.element('create_account.email_div')

    @property
    def email_textbox(self) -> Element:
        """Email"""
        return self.element('create_account.email_textbox')

    @property
    def password_div(self) -> Element:
        """Password"""
        return self.element('create_account.password_div')

    @property
    def password_textbox(self) -> Element:
        """Password"""
        return self.element('create_account.password_textbox')

    @property
    def show_password_button(self) -> Element:
        """Show password"""
        return self.element('create_account.show_password_button')

    @property
    def confirm_password_div(self) -> Element:
        """Confirm password"""
        return self.element('create_account.confirm_password_div')

    @property
    def confirm_password_textbox(self) -> Element:
        """Confirm password"""
        return self.element('create_account.confirm_password_textbox')

    @property
    def show_password_button_2(self) -> Element:
        """Show password"""
        return self.element('create_account.show_password_button_2')

    @property
    def i_have_read_the_privacy_notice_and_under_checkbox(self) -> Element:
        """I have read the privacy notice and understand this is an AI"""
        return self.element('create_account.i_have_read_the_privacy_notice_and_under_checkbox')

    @property
    def create_account_button(self) -> Element:
        """Create account"""
        return self.element('create_account.create_account_button')

    @property
    def continue_with_google_button(self) -> Element:
        """Continue with Google"""
        return self.element('create_account.continue_with_google_button')

    @property
    def continue_with_github_link(self) -> Element:
        """Continue with GitHub"""
        return self.element('create_account.continue_with_github_link')

    @property
    def back_to_welcome_button(self) -> Element:
        """Back to welcome"""
        return self.element('create_account.back_to_welcome_button')

    @property
    def log_in_button(self) -> Element:
        """Log in"""
        return self.element('create_account.log_in_button')
