import pytest
from MobileApps.libs.flows.android.smart.flow_container import FLOW_NAMES
import time

pytest.app_info = "HPX"

class Test_Suite_02_Add_Shortcut:
    @pytest.fixture(scope="class", autouse=True)
    def class_setup(cls, request, android_hpx_flow_setup , load_printers_session):
        cls = cls.__class__
        cls.driver, cls.fc = android_hpx_flow_setup
        cls.p = load_printers_session
        # Define flows
        cls.device_mfe = cls.fc.hpx_fd["devicesMFE"]
        cls.hpx_printer_details = cls.fc.fd[FLOW_NAMES.HPX_PRINTERS_DETAILS]
        cls.printers = cls.fc.fd[FLOW_NAMES.PRINTERS]
        cls.hpx_shortcuts = cls.fc.fd[FLOW_NAMES.HPX_SHORTCUTS]
        # Enable HPX Flag
        cls.fc.hpx = True
    
    def test_01_verify_the_behavior_when_user_disables_the_print_destination_toggle_bar_in_add_shortcut_screen(self):
        """
        Description: C4380
        Steps:
            1.Install and Launch the HPX app.
            2.Click on the printer icon on the root view screen.
            3.Then click on the shortcuts tile on the device details page.
            4.Click on the Add new shortcuts in shortcuts screen.
            5.Then click on the Create your own shortcut arrow button.
            6.Disable the 'Print' destination toggle bar in 'Add Shortcut' screen
            7.Verify the screen.
        Expected Result:
            User should be able to Disable the 'Print' destination toggle bar in 'Add shortcut' screen.
            After disabling the 'Print' destination toggle bar, 'continue' button should be disabled.
        """
        self.fc.reset_app()
        self.fc.flow_load_home_screen(skip_value_prop=False)
        self.hpx_printer_details.click_add_device_btn()
        self.printers.search_printer_by_ip(self.p.ipAddress)
        self.hpx_printer_details.click_printer_device_card()
        self.hpx_printer_details.click_shortcuts_tile(raise_e=False)
        self.hpx_shortcuts.verify_shortcuts_screen_title()
        self.hpx_shortcuts.click_add_new_shortcut_btn()
        self.hpx_shortcuts.verify_add_new_shortcut_screen_title()
        self.hpx_shortcuts.click_create_your_own_shortcut()
        self.hpx_shortcuts.verify_add_new_shortcut_title()
        self.hpx_shortcuts.click_edit_shortcut_print_toggle_btn()
        assert self.hpx_shortcuts.is_continue_btn_enabled() == 'false', "Continue button should be disabled after toggling print option off"
    
    def test_02_verify_the_behavior_when_user_enables_the_email_destination_toggle_bar_in_add_shortcut_screen(self):
        """
        Description: C4381
        Steps:
            1.Install and Launch the HPX app.
            2.Click on the printer icon on the root view screen.
            3.Then click on the shortcuts tile on the device details page.
            4.Click on the Add new shortcuts in shortcuts screen.
            5.Then click on the Create your own shortcut arrow button.
            6.Enable the 'Email' destination toggle bar in 'Add Shortcut' screen
            7.Verify the screen.
        Expected Result:
            User should be able to Enable the 'Email' destination toggle bar in 'Add shortcut' screen.
            After enabling the 'Email' destination toggle bar, 'continue' button should be enabled.
        """
        self.fc.reset_app()
        self.fc.flow_load_home_screen(skip_value_prop=False)
        self.hpx_printer_details.click_add_device_btn()
        self.printers.search_printer_by_ip(self.p.ipAddress)
        self.hpx_printer_details.click_printer_device_card()
        self.hpx_printer_details.click_shortcuts_tile(raise_e=False)
        self.hpx_shortcuts.verify_shortcuts_screen_title()
        self.hpx_shortcuts.click_add_new_shortcut_btn()
        self.hpx_shortcuts.verify_add_new_shortcut_screen_title()
        self.hpx_shortcuts.click_create_your_own_shortcut()
        self.hpx_shortcuts.verify_add_new_shortcut_title()
        self.hpx_shortcuts.click_edit_shortcut_email_toggle_btn()
        assert self.hpx_shortcuts.is_continue_btn_enabled(), "Continue button should be enabled after toggling email option"

    def test_03_verify_the_behavior_when_user_disables_the_email_destination_toggle_bar_in_add_shortcut_screen(self):
        """
        Description: C4382
        Steps:
            1.Install and Launch the HPX app.
            2.Click on the printer icon on the root view screen.
            3.Then click on the shortcuts tile on the device details page.
            4.Click on the Add new shortcuts in shortcuts screen.
            5.Then click on the Create your own shortcut arrow button.
            6.Disable the 'Email' destination toggle bar in 'Add Shortcut' screen
            7.Verify the screen.
        Expected Result:
            User should be able to Disable the 'Email' destination toggle bar in 'Add shortcut' screen.
            After disabling the 'Email' destination toggle bar, 'continue' button should be disabled.
        """
        self.fc.reset_app()
        self.fc.flow_load_home_screen(skip_value_prop=False)
        self.hpx_printer_details.click_add_device_btn()
        self.printers.search_printer_by_ip(self.p.ipAddress)
        self.hpx_printer_details.click_printer_device_card()
        self.hpx_printer_details.click_shortcuts_tile(raise_e=False)
        self.hpx_shortcuts.verify_shortcuts_screen_title()
        self.hpx_shortcuts.click_add_new_shortcut_btn()
        self.hpx_shortcuts.verify_add_new_shortcut_screen_title()
        self.hpx_shortcuts.click_create_your_own_shortcut()
        self.hpx_shortcuts.verify_add_new_shortcut_title()
        self.hpx_shortcuts.click_edit_shortcut_email_toggle_btn()
        self.hpx_shortcuts.click_edit_shortcut_email_toggle_btn()
        assert self.hpx_shortcuts.is_continue_btn_enabled() == 'false', "Continue button should be disabled after toggling email option off"
    
    def test_04_verify_the_behavior_when_user_enables_the_save_destination_toggle_bar_in_add_shortcut_screen(self):
        """
        Description: C4383
        Steps:
            1.Install and Launch the HPX app.
            2.Click on the printer icon on the root view screen.
            3.Then click on the shortcuts tile on the device details page.
            4.Click on the Add new shortcuts in shortcuts screen.
            5.Then click on the Create your own shortcut arrow button.
            6.Enable the 'Save' destination toggle bar in 'Add Shortcut' screen
            7.Verify the screen.
        Expected Result:
            User should be able to Enable the 'Save' destination toggle bar in 'Add shortcut' screen.
        """
        self.fc.reset_app()
        self.fc.flow_load_home_screen(skip_value_prop=False)
        self.hpx_printer_details.click_add_device_btn()
        self.printers.search_printer_by_ip(self.p.ipAddress)
        self.hpx_printer_details.click_printer_device_card()
        self.hpx_printer_details.click_shortcuts_tile(raise_e=False)
        self.hpx_shortcuts.verify_shortcuts_screen_title()
        self.hpx_shortcuts.click_add_new_shortcut_btn()
        self.hpx_shortcuts.verify_add_new_shortcut_screen_title()
        self.hpx_shortcuts.click_create_your_own_shortcut()
        self.hpx_shortcuts.verify_add_new_shortcut_title()
        self.hpx_shortcuts.click_edit_shortcut_save_toggle_btn()
        assert self.hpx_shortcuts.is_continue_btn_enabled(), "Continue button should be enabled after toggling save option"

    def test_05_verify_the_behavior_when_user_disables_the_save_destination_toggle_bar_in_add_shortcut_screen(self):
        """
        Description: C4384
        Steps:
            1.Install and Launch the HPX app.
            2.Click on the printer icon on the root view screen.
            3.Then click on the shortcuts tile on the device details page.
            4.Click on the Add new shortcuts in shortcuts screen.
            5.Then click on the Create your own shortcut arrow button.
            6.Disable the 'Save' destination toggle bar in 'Add Shortcut' screen
            7.Verify the screen.
        Expected Result:
            User should be able to Disable the 'Save' destination toggle bar in 'Add shortcut' screen.
            After disabling the 'Save' destination toggle bar, 'continue' button should be disabled.
        """
        self.fc.reset_app()
        self.fc.flow_load_home_screen(skip_value_prop=False)
        self.hpx_printer_details.click_add_device_btn()
        self.printers.search_printer_by_ip(self.p.ipAddress)
        self.hpx_printer_details.click_printer_device_card()
        self.hpx_printer_details.click_shortcuts_tile(raise_e=False)
        self.hpx_shortcuts.verify_shortcuts_screen_title()
        self.hpx_shortcuts.click_add_new_shortcut_btn()
        self.hpx_shortcuts.verify_add_new_shortcut_screen_title()
        self.hpx_shortcuts.click_create_your_own_shortcut()
        self.hpx_shortcuts.verify_add_new_shortcut_title()
        self.hpx_shortcuts.click_edit_shortcut_save_toggle_btn()
        self.hpx_shortcuts.click_edit_shortcut_save_toggle_btn()
        assert self.hpx_shortcuts.is_continue_btn_enabled() == 'false', "Continue button should be disabled after toggling save option off"

    def test_06_verify_the_screen_when_the_user_enables_only_the_print_destination_in_the_add_shortcut_screen(self):
        """
        Description: C4385
        Steps:
            1.Install and Launch the HPX app.
            2.Click on the printer icon on the root view screen.
            3.Then click on the shortcuts tile on the device details page.
            4.Click on the Add new shortcuts in shortcuts screen.
            5.Then click on the Create your own shortcut arrow button.
            6.Enable only the 'Print' destination toggle bar in 'Add Shortcut' screen.
            7.Then click on the Continue button.
            8.Verify the screen.
        Expected Result:
            User should be navigated to the 'Add print' screen.
        """
        self.fc.reset_app()
        self.fc.flow_load_home_screen(skip_value_prop=False)
        self.hpx_printer_details.click_add_device_btn()
        self.printers.search_printer_by_ip(self.p.ipAddress)
        self.hpx_printer_details.click_printer_device_card()
        self.hpx_printer_details.click_shortcuts_tile(raise_e=False)
        self.hpx_shortcuts.verify_shortcuts_screen_title()
        self.hpx_shortcuts.click_add_new_shortcut_btn()
        self.hpx_shortcuts.verify_add_new_shortcut_screen_title()
        self.hpx_shortcuts.click_create_your_own_shortcut()
        self.hpx_shortcuts.verify_add_new_shortcut_title()
        self.hpx_shortcuts.click_edit_shortcut_print_toggle_btn()
        assert self.hpx_shortcuts.is_continue_btn_enabled(), "Continue button should be enabled after toggling print option"
        self.hpx_shortcuts.click_edit_shortcut_continue_btn()
        assert self.hpx_shortcuts.verify_shortcuts_add_print_screen_title()

    def test_07_verify_the_screen_when_user_clicks_on_back_button_in_add_print_screen(self):
        """
        Description: C4386
        Steps:
            1.Install and Launch the HPX app.
            2.Click on the printer icon on the root view screen.
            3.Then click on the shortcuts tile on the device details page.
            4.Click on the Add new shortcuts in shortcuts screen.
            5.Then click on the Create your own shortcut arrow button.
            6.Navigate 'Add print' screen.
            7.Click on the back button.
            7.Verify the screen.
        Expected Result:
            User should be redirected to the 'Add Shortcut' screen without any error.
        """
        self.fc.reset_app()
        self.fc.flow_load_home_screen(skip_value_prop=False)
        self.hpx_printer_details.click_add_device_btn()
        self.printers.search_printer_by_ip(self.p.ipAddress)
        self.hpx_printer_details.click_printer_device_card()
        self.hpx_printer_details.click_shortcuts_tile(raise_e=False)
        self.hpx_shortcuts.verify_shortcuts_screen_title()
        self.hpx_shortcuts.click_add_new_shortcut_btn()
        self.hpx_shortcuts.verify_add_new_shortcut_screen_title()
        self.hpx_shortcuts.click_create_your_own_shortcut()
        self.hpx_shortcuts.verify_add_new_shortcut_title()
        self.hpx_shortcuts.click_edit_shortcut_print_toggle_btn()
        assert self.hpx_shortcuts.is_continue_btn_enabled(), "Continue button should be enabled after toggling print option"
        self.hpx_shortcuts.click_edit_shortcut_continue_btn()
        self.hpx_shortcuts.verify_shortcuts_add_print_screen_title()
        self.driver.back()
        assert self.hpx_shortcuts.verify_add_new_shortcut_title()
    
    def test_08_verify_the_behavior_when_the_user_selects_any_value_in_the_copies_dropdown_on_the_add_print_screen(self):
        """
        Description: C4387
        Steps:
            1.Install and Launch the HPX app.
            2.Navigate to printer details screen.
            3.Navigate to 'Add Shortcuts' screen.
            4.Enable only the 'Print' destination toggle bar.
            5.Click on the 'Copies' dropdown.
            6.Select any other value.
            7.verify the screen.
        Expected Result:
            User should be able to select any desired value in 'Copies' dropdown.
            The selected value should be displayed in 'Copies' dropdown.
        """
        self.fc.reset_app()
        self.fc.flow_load_home_screen(skip_value_prop=False)
        self.hpx_printer_details.click_add_device_btn()
        self.printers.search_printer_by_ip(self.p.ipAddress)
        self.hpx_printer_details.click_printer_device_card()
        self.hpx_printer_details.click_shortcuts_tile(raise_e=False)
        self.hpx_shortcuts.verify_shortcuts_screen_title()
        self.hpx_shortcuts.click_add_new_shortcut_btn()
        self.hpx_shortcuts.verify_add_new_shortcut_screen_title()
        self.hpx_shortcuts.click_create_your_own_shortcut()
        self.hpx_shortcuts.verify_add_new_shortcut_title()
        self.hpx_shortcuts.click_edit_shortcut_print_toggle_btn()
        assert self.hpx_shortcuts.is_continue_btn_enabled(), "Continue button should be enabled after toggling print option"
        self.hpx_shortcuts.click_edit_shortcut_continue_btn()
        self.hpx_shortcuts.click_edit_print_copies_dropdown_btn()
        self.hpx_shortcuts.select_copies_number("two")
        self.hpx_shortcuts.click_edit_print_copies_dropdown_btn()
        assert self.hpx_shortcuts.verify_select_copies_number("two"), "Selected copies number should be two"
        self.hpx_shortcuts.select_copies_number("two")
        
    
    def test_09_verify_the_behavior_when_the_user_selects_any_option_in_the_color_dropdown_on_the_add_print_screen(self):
        """
        Description: C4388
        Steps:
            1.Install and Launch the HPX app.
            2.Navigate to printer details screen.
            3.Navigate to 'Add Shortcuts' screen.
            4.Enable only the 'Print' destination toggle bar.
            5.Click on the 'Color' dropdown.
            6.Select any other option.
            7.verify the screen.
        Expected Result:
            User should be able to select any desired option in 'Color' dropdown.
            The selected option should be displayed in 'Color' dropdown.
        """
        self.fc.reset_app()
        self.fc.flow_load_home_screen(skip_value_prop=False)
        self.hpx_printer_details.click_add_device_btn()
        self.printers.search_printer_by_ip(self.p.ipAddress)
        self.hpx_printer_details.click_printer_device_card()
        self.hpx_printer_details.click_shortcuts_tile(raise_e=False)
        self.hpx_shortcuts.verify_shortcuts_screen_title()
        self.hpx_shortcuts.click_add_new_shortcut_btn()
        self.hpx_shortcuts.verify_add_new_shortcut_screen_title()
        self.hpx_shortcuts.click_create_your_own_shortcut()
        self.hpx_shortcuts.verify_add_new_shortcut_title()
        self.hpx_shortcuts.click_edit_shortcut_print_toggle_btn()
        assert self.hpx_shortcuts.is_continue_btn_enabled(), "Continue button should be enabled after toggling print option"
        self.hpx_shortcuts.click_edit_shortcut_continue_btn()
        self.hpx_shortcuts.verify_shortcuts_add_print_screen_title()
        self.hpx_shortcuts.click_select_color_dropdown_btn()
        self.hpx_shortcuts.select_color_option("grayscale")
        self.hpx_shortcuts.click_select_color_dropdown_btn()
        self.hpx_shortcuts.verify_select_color_option("grayscale")
        self.hpx_shortcuts.select_color_option("color")

    def test_10_verify_the_behavior_when_the_user_selects_any_option_in_the_two_sided_dropdown_on_the_add_print_screen(self):
        """
        Description: C4389
        Steps:
            1.Install and Launch the HPX app.
            2.Navigate to printer details screen.
            3.Navigate to 'Add Shortcuts' screen.
            4.Enable only the 'Print' destination toggle bar.
            5.Click on the 'Two-sided' dropdown.
            6.Select any other option.
            7.verify the screen.
        Expected Result:
            User should be able to select any desired option in 'Two-sided' dropdown.
            The selected option should be displayed in 'Two-sided' dropdown.
        """
        self.fc.reset_app()
        self.fc.flow_load_home_screen(skip_value_prop=False)
        self.hpx_printer_details.click_add_device_btn()
        self.printers.search_printer_by_ip(self.p.ipAddress)
        self.hpx_printer_details.click_printer_device_card()
        self.hpx_printer_details.click_shortcuts_tile(raise_e=False)
        self.hpx_shortcuts.verify_shortcuts_screen_title()
        self.hpx_shortcuts.click_add_new_shortcut_btn()
        self.hpx_shortcuts.verify_add_new_shortcut_screen_title()
        self.hpx_shortcuts.click_create_your_own_shortcut()
        self.hpx_shortcuts.verify_add_new_shortcut_title()
        self.hpx_shortcuts.click_edit_shortcut_print_toggle_btn()
        assert self.hpx_shortcuts.is_continue_btn_enabled(), "Continue button should be enabled after toggling print option"
        self.hpx_shortcuts.click_edit_shortcut_continue_btn()
        self.hpx_shortcuts.verify_shortcuts_add_print_screen_title()
        self.hpx_shortcuts.click_two_sided_dropdown_btn()
        self.hpx_shortcuts.select_two_sided_option("short_edge")
        self.hpx_shortcuts.click_two_sided_dropdown_btn()
        self.hpx_shortcuts.verify_select_two_sided_option("short_edge")
        self.hpx_shortcuts.select_two_sided_option("off")
    
    def test_11_verify_the_behavior_when_user_clicks_on_add_to_shortcut_button_in_add_print_screen(self):
        """
        Description: C4390
        Steps:
            1.Install and Launch the HPX app.
            2.Navigate to printer details screen.
            3.Navigate to 'Add Shortcuts' screen.
            4.Enable only the 'Print' destination toggle bar.
            5.Select the print settings.
            6.Click on the Add to Shortcut button.
            7.verify the behavior.
        Expected Result:
            User should be redirected to 'Add shortcut' screen with the saved details from 'Add print' screen.
        """
        self.fc.reset_app()
        self.fc.flow_load_home_screen(skip_value_prop=False)
        self.hpx_printer_details.click_add_device_btn()
        self.printers.search_printer_by_ip(self.p.ipAddress)
        self.hpx_printer_details.click_printer_device_card()
        self.hpx_printer_details.click_shortcuts_tile(raise_e=False)
        self.hpx_shortcuts.verify_shortcuts_screen_title()
        self.hpx_shortcuts.click_add_new_shortcut_btn()
        self.hpx_shortcuts.verify_add_new_shortcut_screen_title()
        self.hpx_shortcuts.click_create_your_own_shortcut()
        self.hpx_shortcuts.verify_add_new_shortcut_title()
        self.hpx_shortcuts.click_edit_shortcut_continue_btn()
        assert self.hpx_shortcuts.verify_shortcut_settings_screen_title()
