from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class CreateAccountPage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def display_name_textbox(self) -> Locator:
        """Display name"""
        return self.locator('create_account.display_name_textbox')

    @property
    def email_textbox(self) -> Locator:
        """Email"""
        return self.locator('create_account.email_textbox')

    @property
    def password_textbox(self) -> Locator:
        """Password"""
        return self.locator('create_account.password_textbox')

    @property
    def confirm_password_textbox(self) -> Locator:
        """Confirm password"""
        return self.locator('create_account.confirm_password_textbox')

    @property
    def i_have_read_the_privacy_notice_and_under_checkbox(self) -> Locator:
        """I have read the privacy notice and understand this is an AI"""
        return self.locator('create_account.i_have_read_the_privacy_notice_and_under_checkbox')

    @property
    def create_account_button(self) -> Locator:
        """Create account"""
        return self.locator('create_account.create_account_button')

    @property
    def show_password_button(self) -> Locator:
        """Show password"""
        return self.locator('create_account.show_password_button')

    @property
    def show_password_button_2(self) -> Locator:
        """Show password"""
        return self.locator('create_account.show_password_button_2')

    @property
    def continue_with_google_button(self) -> Locator:
        """Continue with Google"""
        return self.locator('create_account.continue_with_google_button')

    @property
    def continue_with_github_link(self) -> Locator:
        """Continue with GitHub"""
        return self.locator('create_account.continue_with_github_link')

    @property
    def help_for_password_button(self) -> Locator:
        """Help for Password"""
        return self.locator('create_account.help_for_password_button')

    @property
    def back_to_welcome_button(self) -> Locator:
        """Back to welcome"""
        return self.locator('create_account.back_to_welcome_button')
