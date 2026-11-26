from __future__ import annotations

from pages.landing_page import LandingPage
from pages.get_started_page import GetStartedPage
from pages.create_account_page import CreateAccountPage
from pages.home_page import HomePage
from pages.settings_page import SettingsPage
from pages.my_profile_page import MyProfilePage


class Pages:
    def __init__(self, app) -> None:
        self.landing = LandingPage(app)
        self.get_started = GetStartedPage(app)
        self.create_account = CreateAccountPage(app)
        self.home = HomePage(app)
        self.settings = SettingsPage(app)
        self.my_profile = MyProfilePage(app)
