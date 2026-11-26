from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class CreateAccountPage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def create_your_account_heading(self) -> Locator:
        """Create your account"""
        return self.locator('create_account.create_your_account_heading')

    @property
    def display_name_textbox(self) -> Locator:
        """Display name"""
        return self.locator('create_account.display_name_textbox')

    @property
    def email_textbox(self) -> Locator:
        """Email"""
        return self.locator('create_account.email_textbox')

    @property
    def help_for_password_button(self) -> Locator:
        """Help for Password"""
        return self.locator('create_account.help_for_password_button')

    @property
    def password_textbox(self) -> Locator:
        """Password"""
        return self.locator('create_account.password_textbox')

    @property
    def show_password_button(self) -> Locator:
        """toggles password visibility"""
        return self.locator('create_account.show_password_button')

    @property
    def confirm_password_textbox(self) -> Locator:
        """Confirm password"""
        return self.locator('create_account.confirm_password_textbox')

    @property
    def show_password_button_2(self) -> Locator:
        """secondary toggle for password visibility"""
        return self.locator('create_account.show_password_button_2')

    @property
    def i_have_read_the_privacy_notice_and_under_checkbox(self) -> Locator:
        """I have read the privacy notice and understand this is an AI"""
        return self.locator('create_account.i_have_read_the_privacy_notice_and_under_checkbox')

    @property
    def i_have_read_the_privacy_notice_and_under_div(self) -> Locator:
        """privacy notice acceptance"""
        return self.locator('create_account.i_have_read_the_privacy_notice_and_under_div')

    @property
    def log_in_button(self) -> Locator:
        """Log in"""
        return self.locator('create_account.log_in_button')

    @property
    def back_to_welcome_button(self) -> Locator:
        """returns to welcome screen from signup"""
        return self.locator('create_account.back_to_welcome_button')

    @property
    def or_continue_with_div(self) -> Locator:
        """presents continue options during signup"""
        return self.locator('create_account.or_continue_with_div')

    @property
    def continue_with_google_button(self) -> Locator:
        """Continue with Google"""
        return self.locator('create_account.continue_with_google_button')

    @property
    def continue_with_github_link(self) -> Locator:
        """Continue with GitHub"""
        return self.locator('create_account.continue_with_github_link')

    @property
    def already_have_an_account_div(self) -> Locator:
        """prompts existing users to log in"""
        return self.locator('create_account.already_have_an_account_div')

    @property
    def create_account_button(self) -> Locator:
        """Create account"""
        return self.locator('create_account.create_account_button')
