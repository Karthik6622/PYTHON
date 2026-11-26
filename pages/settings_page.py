from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class SettingsPage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def settings_heading(self) -> Locator:
        """Settings"""
        return self.locator('settings.settings_heading')

    @property
    def privacy_and_account_data_heading(self) -> Locator:
        """Privacy and account data"""
        return self.locator('settings.privacy_and_account_data_heading')

    @property
    def reply_tone_combobox(self) -> Locator:
        """Reply tone"""
        return self.locator('settings.reply_tone_combobox')

    @property
    def reply_length_combobox(self) -> Locator:
        """Reply length"""
        return self.locator('settings.reply_length_combobox')

    @property
    def topics_you_often_ask_about_combobox(self) -> Locator:
        """Topics you often ask about"""
        return self.locator('settings.topics_you_often_ask_about_combobox')

    @property
    def chat_mode_combobox(self) -> Locator:
        """Chat mode"""
        return self.locator('settings.chat_mode_combobox')

    @property
    def romantic_mode_partner_combobox(self) -> Locator:
        """Romantic mode partner"""
        return self.locator('settings.romantic_mode_partner_combobox')

    @property
    def your_city_optional_textbox(self) -> Locator:
        """Your city (optional)"""
        return self.locator('settings.your_city_optional_textbox')

    @property
    def save_preferences_button(self) -> Locator:
        """Save preferences"""
        return self.locator('settings.save_preferences_button')

    @property
    def delete_my_account_button(self) -> Locator:
        """Delete my account"""
        return self.locator('settings.delete_my_account_button')

    @property
    def type_your_email_address_to_confirm_delet_textbox(self) -> Locator:
        """Type your email address to confirm deletion"""
        return self.locator('settings.type_your_email_address_to_confirm_delet_textbox')

    @property
    def i_understand_this_permanently_deletes_my_checkbox(self) -> Locator:
        """I understand this permanently deletes my account and convers"""
        return self.locator('settings.i_understand_this_permanently_deletes_my_checkbox')

    @property
    def my_profile_radio(self) -> Locator:
        """My Profile"""
        return self.locator('settings.my_profile_radio')

    @property
    def deleting_your_account_permanently_remove_div(self) -> Locator:
        """explains permanent account deletion consequences"""
        return self.locator('settings.deleting_your_account_permanently_remove_div')
