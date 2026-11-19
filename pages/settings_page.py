from __future__ import annotations

from pages.base_page import BasePage
from utils.element import Element


class SettingsPage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def chat_mode_combobox(self) -> Element:
        """Chat mode"""
        return self.element('settings.chat_mode_combobox')

    @property
    def chat_radio(self) -> Element:
        """Chat"""
        return self.element('settings.chat_radio')

    @property
    def settings_radio(self) -> Element:
        """Settings"""
        return self.element('settings.settings_radio')

    @property
    def your_city_optional_textbox(self) -> Element:
        """Your city (optional)"""
        return self.element('settings.your_city_optional_textbox')

    @property
    def reply_tone_combobox(self) -> Element:
        """Reply tone"""
        return self.element('settings.reply_tone_combobox')

    @property
    def save_preferences_button(self) -> Element:
        """Save preferences"""
        return self.element('settings.save_preferences_button')

    @property
    def reply_length_combobox(self) -> Element:
        """Reply length"""
        return self.element('settings.reply_length_combobox')

    @property
    def topics_you_often_ask_about_combobox(self) -> Element:
        """Topics you often ask about"""
        return self.element('settings.topics_you_often_ask_about_combobox')

    @property
    def romantic_mode_partner_combobox(self) -> Element:
        """Romantic mode partner"""
        return self.element('settings.romantic_mode_partner_combobox')

    @property
    def my_profile_radio(self) -> Element:
        """My Profile"""
        return self.element('settings.my_profile_radio')

    @property
    def delete_my_account_button(self) -> Element:
        """Delete my account"""
        return self.element('settings.delete_my_account_button')

    @property
    def deleting_your_account_permanently_remove_div(self) -> Element:
        """account deletion warning"""
        return self.element('settings.deleting_your_account_permanently_remove_div')

    @property
    def i_understand_this_permanently_deletes_my_checkbox(self) -> Element:
        """I understand this permanently deletes my account and convers"""
        return self.element('settings.i_understand_this_permanently_deletes_my_checkbox')

    @property
    def type_your_email_address_to_confirm_delet_textbox(self) -> Element:
        """Type your email address to confirm deletion"""
        return self.element('settings.type_your_email_address_to_confirm_delet_textbox')

    @property
    def help_for_chat_mode_button(self) -> Element:
        """Help for Chat mode"""
        return self.element('settings.help_for_chat_mode_button')

    @property
    def help_for_romantic_mode_partner_button(self) -> Element:
        """Help for Romantic mode partner"""
        return self.element('settings.help_for_romantic_mode_partner_button')

    @property
    def help_for_your_city_optional_button(self) -> Element:
        """Help for Your city (optional)"""
        return self.element('settings.help_for_your_city_optional_button')

    @property
    def log_out_button(self) -> Element:
        """Log out"""
        return self.element('settings.log_out_button')
