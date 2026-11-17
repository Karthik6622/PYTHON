from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class MyProfilePage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def el_1_conversation_s_saved_to_this_app_s_lo_div(self) -> Locator:
        """1 conversation(s) saved to this app’s local data folder."""
        return self.locator('my_profile.1_conversation_s_saved_to_this_app_s_lo_div')
