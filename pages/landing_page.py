from __future__ import annotations

from pages.base_page import BasePage
from utils.element import Element


class LandingPage(BasePage):
    """Page object for ~ +"""

    path = '/~/+/'

    @property
    def get_started_button(self) -> Element:
        """Get started"""
        return self.element('landing.get_started_button')

    @property
    def create_account_button(self) -> Element:
        """Create account"""
        return self.element('landing.create_account_button')

    @property
    def continue_with_google_button(self) -> Element:
        """Continue with Google"""
        return self.element('landing.continue_with_google_button')

    @property
    def continue_with_github_link(self) -> Element:
        """Continue with GitHub"""
        return self.element('landing.continue_with_github_link')

    @property
    def withyou_div(self) -> Element:
        """WithYou"""
        return self.element('landing.withyou_div')

    @property
    def withyou_div_2(self) -> Element:
        """WithYou"""
        return self.element('landing.withyou_div_2')

    @property
    def withyou_div_3(self) -> Element:
        """WithYou"""
        return self.element('landing.withyou_div_3')

    @property
    def withyou_div_4(self) -> Element:
        """WithYou"""
        return self.element('landing.withyou_div_4')
