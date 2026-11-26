from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class HomePage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def good_afternoon_karthik_heading(self) -> Locator:
        """Good afternoon, karthik"""
        return self.locator('home.good_afternoon_karthik_heading')

    @property
    def withyou_div(self) -> Locator:
        """displays the WithYou branding"""
        return self.locator('home.withyou_div')

    @property
    def recent_chats_div(self) -> Locator:
        """opens recent chats section"""
        return self.locator('home.recent_chats_div')

    @property
    def chat_mode_div(self) -> Locator:
        """indicates current chat mode status"""
        return self.locator('home.chat_mode_div')

    @property
    def hey_karthik_what_s_on_your_mind_today_div(self) -> Locator:
        """welcome message prompt for user input"""
        return self.locator('home.hey_karthik_what_s_on_your_mind_today_div')

    @property
    def help_for_chat_mode_button(self) -> Locator:
        """Help for Chat mode"""
        return self.locator('home.help_for_chat_mode_button')

    @property
    def normal_radio(self) -> Locator:
        """Normal"""
        return self.locator('home.normal_radio')

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
    def speak_replies_switch(self) -> Locator:
        """🔊 Speak replies"""
        return self.locator('home.speak_replies_switch')

    @property
    def type_a_message_attach_a_file_or_tap_th_textbox(self) -> Locator:
        """Type a message, attach a file, or tap the mic…"""
        return self.locator('home.type_a_message_attach_a_file_or_tap_th_textbox')

    @property
    def upload_files_button(self) -> Locator:
        """Upload files"""
        return self.locator('home.upload_files_button')

    @property
    def start_recording_button(self) -> Locator:
        """Start recording"""
        return self.locator('home.start_recording_button')

    @property
    def send_message_button(self) -> Locator:
        """Send message"""
        return self.locator('home.send_message_button')

    @property
    def chat_mode_radiogroup(self) -> Locator:
        """Chat mode"""
        return self.locator('home.chat_mode_radiogroup')

    @property
    def account_radiogroup(self) -> Locator:
        """Account"""
        return self.locator('home.account_radiogroup')

    @property
    def new_conversation_button(self) -> Locator:
        """opens new conversation dialog"""
        return self.locator('home.new_conversation_button')

    @property
    def new_conversation_button_2(self) -> Locator:
        """opens new conversation dialog (variant 2)"""
        return self.locator('home.new_conversation_button_2')

    @property
    def new_conversation_button_3(self) -> Locator:
        """opens new conversation dialog (variant 3)"""
        return self.locator('home.new_conversation_button_3')

    @property
    def new_conversation_button_4(self) -> Locator:
        """opens new conversation dialog (variant 4)"""
        return self.locator('home.new_conversation_button_4')

    @property
    def my_test_conversation_button(self) -> Locator:
        """My test conversation"""
        return self.locator('home.my_test_conversation_button')

    @property
    def manage_current_chat_button(self) -> Locator:
        """manages the active chat details"""
        return self.locator('home.manage_current_chat_button')

    @property
    def conversation_title_textbox(self) -> Locator:
        """Conversation title"""
        return self.locator('home.conversation_title_textbox')

    @property
    def save_title_button(self) -> Locator:
        """Save title"""
        return self.locator('home.save_title_button')

    @property
    def delete_this_chat_button(self) -> Locator:
        """Delete this chat"""
        return self.locator('home.delete_this_chat_button')

    @property
    def new_chat_button(self) -> Locator:
        """New chat"""
        return self.locator('home.new_chat_button')

    @property
    def log_out_button(self) -> Locator:
        """Log out"""
        return self.locator('home.log_out_button')

    @property
    def chat_radio(self) -> Locator:
        """Chat"""
        return self.locator('home.chat_radio')

    @property
    def my_profile_radio(self) -> Locator:
        """My Profile"""
        return self.locator('home.my_profile_radio')

    @property
    def settings_radio(self) -> Locator:
        """Settings"""
        return self.locator('home.settings_radio')
