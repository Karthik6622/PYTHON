from __future__ import annotations

from pages.base_page import BasePage
from utils.element import Element


class HomePage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def type_a_message_attach_a_file_or_tap_th_textbox(self) -> Element:
        """Type a message, attach a file, or tap the mic…"""
        return self.element('home.type_a_message_attach_a_file_or_tap_th_textbox')

    @property
    def recent_chats_div(self) -> Element:
        """open recent chats sidebar"""
        return self.element('home.recent_chats_div')

    @property
    def new_chat_button(self) -> Element:
        """New chat"""
        return self.element('home.new_chat_button')

    @property
    def manage_current_chat_button(self) -> Element:
        """manage active conversation"""
        return self.element('home.manage_current_chat_button')

    @property
    def chat_radio(self) -> Element:
        """Chat"""
        return self.element('home.chat_radio')

    @property
    def my_profile_radio(self) -> Element:
        """My Profile"""
        return self.element('home.my_profile_radio')

    @property
    def settings_radio(self) -> Element:
        """Settings"""
        return self.element('home.settings_radio')

    @property
    def log_out_button(self) -> Element:
        """Log out"""
        return self.element('home.log_out_button')

    @property
    def hello_button(self) -> Element:
        """trigger greeting action"""
        return self.element('home.hello_button')

    @property
    def send_message_button(self) -> Element:
        """Send message"""
        return self.element('home.send_message_button')

    @property
    def start_recording_button(self) -> Element:
        """Start recording"""
        return self.element('home.start_recording_button')

    @property
    def upload_files_button(self) -> Element:
        """Upload files"""
        return self.element('home.upload_files_button')

    @property
    def hey_kk_what_s_on_your_mind_today_div(self) -> Element:
        """prompt user for input"""
        return self.element('home.hey_kk_what_s_on_your_mind_today_div')

    @property
    def new_conversation_button(self) -> Element:
        """New conversation"""
        return self.element('home.new_conversation_button')

    @property
    def conversation_title_textbox(self) -> Element:
        """Conversation title"""
        return self.element('home.conversation_title_textbox')

    @property
    def chat_message_from_assistant_group(self) -> Element:
        """display assistant response"""
        return self.element('home.chat_message_from_assistant_group')

    @property
    def hello_button_2(self) -> Element:
        """trigger greeting action"""
        return self.element('home.hello_button_2')

    @property
    def conversation_title_div(self) -> Element:
        """display conversation title"""
        return self.element('home.conversation_title_div')

    @property
    def save_title_button(self) -> Element:
        """Save title"""
        return self.element('home.save_title_button')

    @property
    def chat_message_from_user_group(self) -> Element:
        """display user message"""
        return self.element('home.chat_message_from_user_group')
