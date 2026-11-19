from __future__ import annotations

from pages.base_page import BasePage
from utils.element import Element


class MyProfilePage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def display_name_textbox(self) -> Element:
        """Display name"""
        return self.element('my_profile.display_name_textbox')

    @property
    def settings_radio(self) -> Element:
        """Settings"""
        return self.element('my_profile.settings_radio')

    @property
    def display_name_div(self) -> Element:
        """show display name"""
        return self.element('my_profile.display_name_div')

    @property
    def chat_radio(self) -> Element:
        """Chat"""
        return self.element('my_profile.chat_radio')

    @property
    def email_div(self) -> Element:
        """show email"""
        return self.element('my_profile.email_div')

    @property
    def email_textbox(self) -> Element:
        """Email"""
        return self.element('my_profile.email_textbox')

    @property
    def el_3_conversation_s_saved_to_this_app_s_lo_div(self) -> Element:
        """show local conversation count"""
        return self.element('my_profile.3_conversation_s_saved_to_this_app_s_lo_div')

    @property
    def the_app_stores_account_and_conversation_div(self) -> Element:
        """disclose data storage policy"""
        return self.element('my_profile.the_app_stores_account_and_conversation_div')

    @property
    def your_account_details_stay_separate_from_div(self) -> Element:
        """privacy notice display"""
        return self.element('my_profile.your_account_details_stay_separate_from_div')

    @property
    def export_selected_conversation_as_markdown_button(self) -> Element:
        """Export selected conversation as Markdown"""
        return self.element('my_profile.export_selected_conversation_as_markdown_button')

    @property
    def my_profile_radio(self) -> Element:
        """My Profile"""
        return self.element('my_profile.my_profile_radio')

    @property
    def collapse_sidebar_button(self) -> Element:
        """Collapse sidebar"""
        return self.element('my_profile.collapse_sidebar_button')

    @property
    def log_out_button(self) -> Element:
        """Log out"""
        return self.element('my_profile.log_out_button')
