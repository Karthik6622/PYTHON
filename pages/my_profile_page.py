from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class MyProfilePage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def my_profile_heading(self) -> Locator:
        """My Profile"""
        return self.locator('my_profile.my_profile_heading')
