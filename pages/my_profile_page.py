from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class MyProfilePage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def display_name_textbox(self) -> Locator:
        """Display name"""
        return self.locator('my_profile.display_name_textbox')

    @property
    def email_textbox(self) -> Locator:
        """Email"""
        return self.locator('my_profile.email_textbox')

    @property
    def export_selected_conversation_as_markdown_button(self) -> Locator:
        """Export selected conversation as Markdown"""
        return self.locator('my_profile.export_selected_conversation_as_markdown_button')

    @property
    def your_account_details_stay_separate_from_div(self) -> Locator:
        """privacy notice about data separation"""
        return self.locator('my_profile.your_account_details_stay_separate_from_div')

    @property
    def el_5_conversation_s_saved_to_this_app_s_lo_div(self) -> Locator:
        """5 conversation(s) saved to this app’s local data folder."""
        return self.locator('my_profile.5_conversation_s_saved_to_this_app_s_lo_div')

    @property
    def the_app_stores_account_and_conversation_div(self) -> Locator:
        """The app stores account and conversation data locally on the"""
        return self.locator('my_profile.the_app_stores_account_and_conversation_div')

    @property
    def my_profile_heading(self) -> Locator:
        """My Profile"""
        return self.locator('my_profile.my_profile_heading')

    @property
    def settings_radio(self) -> Locator:
        """Settings"""
        return self.locator('my_profile.settings_radio')
