from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class HomePage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def chat_bubblenew_conversation_button(self) -> Locator:
        """opens new conversation dialog"""
        return self.locator('home.chat_bubblenew_conversation_button')

    @property
    def chat_mode_radiogroup(self) -> Locator:
        """chat mode radio selection"""
        return self.locator('home.chat_mode_radiogroup')

    @property
    def recent_chats_div(self) -> Locator:
        """recent chats section header in sidebar"""
        return self.locator('home.recent_chats_div')

    @property
    def keyboard_arrow_right_manage_current_chat_button(self) -> Locator:
        """keyboard_arrow_right Manage current chat"""
        return self.locator('home.keyboard_arrow_right_manage_current_chat_button')

    @property
    def conversation_title_textbox(self) -> Locator:
        """Conversation title"""
        return self.locator('home.conversation_title_textbox')

    @property
    def normal_div(self) -> Locator:
        """chat mode normal option"""
        return self.locator('home.normal_div')

    @property
    def romantic_div(self) -> Locator:
        """chat mode romantic option"""
        return self.locator('home.romantic_div')

    @property
    def friend_div(self) -> Locator:
        """chat mode friend option"""
        return self.locator('home.friend_div')

    @property
    def english_teacher_div(self) -> Locator:
        """chat mode english teacher option"""
        return self.locator('home.english_teacher_div')

    @property
    def chat_bubble_new_conversation_button(self) -> Locator:
        """chat_bubble New conversation"""
        return self.locator('home.chat_bubble_new_conversation_button')

    @property
    def normal_radio(self) -> Locator:
        """Normal"""
        return self.locator('home.normal_radio')

    @property
    def type_a_message_attach_a_file_or_tap_th_textbox(self) -> Locator:
        """Type a message, attach a file, or tap the mic…"""
        return self.locator('home.type_a_message_attach_a_file_or_tap_th_textbox')

    @property
    def send_message_button(self) -> Locator:
        """Send message"""
        return self.locator('home.send_message_button')

    @property
    def chat_message_from_assistant_group(self) -> Locator:
        """Chat message from assistant"""
        return self.locator('home.chat_message_from_assistant_group')

    @property
    def save_title_button(self) -> Locator:
        """Save title"""
        return self.locator('home.save_title_button')

    @property
    def delete_this_chat_button(self) -> Locator:
        """Delete this chat"""
        return self.locator('home.delete_this_chat_button')

    @property
    def recent_chats_div_2(self) -> Locator:
        """recent chats section content wrapper"""
        return self.locator('home.recent_chats_div_2')

    @property
    def romantic_radio(self) -> Locator:
        """Romantic"""
        return self.locator('home.romantic_radio')

    @property
    def friend_radio(self) -> Locator:
        """Friend"""
        return self.locator('home.friend_radio')

    @property
    def english_teacher_radio(self) -> Locator:
        """English Teacher"""
        return self.locator('home.english_teacher_radio')

    @property
    def my_profile_radio(self) -> Locator:
        """My Profile"""
        return self.locator('home.my_profile_radio')

    @property
    def settings_radio(self) -> Locator:
        """Settings"""
        return self.locator('home.settings_radio')

    @property
    def settings_div(self) -> Locator:
        """settings section in main"""
        return self.locator('home.settings_div')

    @property
    def account_radiogroup(self) -> Locator:
        """account selection radiogroup"""
        return self.locator('home.account_radiogroup')

    @property
    def chat_radio(self) -> Locator:
        """Chat"""
        return self.locator('home.chat_radio')

    @property
    def hey_kk_i_m_withyou_your_ai_companion_div(self) -> Locator:
        """AI companion greeting banner"""
        return self.locator('home.hey_kk_i_m_withyou_your_ai_companion_div')

    @property
    def collapse_sidebar_button(self) -> Locator:
        """Collapse sidebar"""
        return self.locator('home.collapse_sidebar_button')

    @property
    def keyboard_double_arrow_left_span(self) -> Locator:
        """navigates backward in sidebar"""
        return self.locator('home.keyboard_double_arrow_left_span')

    @property
    def keyboard_arrow_right_span(self) -> Locator:
        """navigates forward in sidebar"""
        return self.locator('home.keyboard_arrow_right_span')

    @property
    def conversation_title_label(self) -> Locator:
        """labels conversation title input"""
        return self.locator('home.conversation_title_label')
