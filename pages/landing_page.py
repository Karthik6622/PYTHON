from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class LandingPage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def here_for_whatever_is_on_your_mind_heading(self) -> Locator:
        """Here for whatever is on your mind."""
        return self.locator('landing.here_for_whatever_is_on_your_mind_heading')

    @property
    def your_conversations_your_space_heading(self) -> Locator:
        """Your conversations, your space"""
        return self.locator('landing.your_conversations_your_space_heading')

    @property
    def always_ready_to_talk_heading(self) -> Locator:
        """Always ready to talk"""
        return self.locator('landing.always_ready_to_talk_heading')

    @property
    def made_to_feel_personal_heading(self) -> Locator:
        """Made to feel personal"""
        return self.locator('landing.made_to_feel_personal_heading')

    @property
    def withyou_div(self) -> Locator:
        """displays the WithYou branding on landing page"""
        return self.locator('landing.withyou_div')

    @property
    def get_started_button(self) -> Locator:
        """Get started"""
        return self.locator('landing.get_started_button')

    @property
    def continue_with_google_button(self) -> Locator:
        """Continue with Google"""
        return self.locator('landing.continue_with_google_button')

    @property
    def continue_with_github_link(self) -> Locator:
        """Continue with GitHub"""
        return self.locator('landing.continue_with_github_link')

    @property
    def create_account_button(self) -> Locator:
        """Create account"""
        return self.locator('landing.create_account_button')

    @property
    def or_continue_with_div(self) -> Locator:
        """shows alternative login continue options"""
        return self.locator('landing.or_continue_with_div')
