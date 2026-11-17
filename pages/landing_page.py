from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class LandingPage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def get_started_button(self) -> Locator:
        """Get started"""
        return self.locator('landing.get_started_button')

    @property
    def create_account_button(self) -> Locator:
        """Create account"""
        return self.locator('landing.create_account_button')

    @property
    def continue_with_google_button(self) -> Locator:
        """Continue with Google"""
        return self.locator('landing.continue_with_google_button')

    @property
    def continue_with_github_link(self) -> Locator:
        """Continue with GitHub"""
        return self.locator('landing.continue_with_github_link')

    @property
    def withyoua_personal_ai_companionpowered_by_div(self) -> Locator:
        """WithYouA personal AI companionPowered by RK"""
        return self.locator('landing.withyoua_personal_ai_companionpowered_by_div')
