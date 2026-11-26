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
    def i_have_read_the_privacy_notice_and_under_div(self) -> Locator:
        """privacy notice acknowledgment in create account flow"""
        return self.locator('create_account.i_have_read_the_privacy_notice_and_under_div')

    @property
    def or_continue_with_div(self) -> Locator:
        """shows alternative login continue options in create account"""
        return self.locator('create_account.or_continue_with_div')

    @property
    def already_have_an_account_div(self) -> Locator:
        """prompts returning users to log in"""
        return self.locator('create_account.already_have_an_account_div')

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
        """toggles password visibility in create account form"""
        return self.locator('create_account.show_password_button')

    @property
    def confirm_password_textbox(self) -> Locator:
        """Confirm password"""
        return self.locator('create_account.confirm_password_textbox')

    @property
    def show_password_button_2(self) -> Locator:
        """toggles password visibility (variant 2) in create account form"""
        return self.locator('create_account.show_password_button_2')

    @property
    def i_have_read_the_privacy_notice_and_under_checkbox(self) -> Locator:
        """I have read the privacy notice and understand this is an AI"""
        return self.locator('create_account.i_have_read_the_privacy_notice_and_under_checkbox')

    @property
    def log_in_button(self) -> Locator:
        """Log in"""
        return self.locator('create_account.log_in_button')

    @property
    def back_to_welcome_button(self) -> Locator:
        """returns user to welcome screen from create account"""
        return self.locator('create_account.back_to_welcome_button')

    @property
    def create_account_button(self) -> Locator:
        """Create account"""
        return self.locator('create_account.create_account_button')
