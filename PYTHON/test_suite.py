import pytest
from MobileApps.libs.flows.windows.hpx_rebranding.flow_container import FlowContainer


pytest.app_info = "DESKTOP"
pytest.set_info = "HPX"

@pytest.mark.usefixtures("class_setup_fixture_ota_regression")
class Test_Suite_04_Settings_privacy(object):
    @pytest.fixture(scope="class", autouse=True)
    def class_setup(cls, request, windows_test_setup):
        cls = cls.__class__
        cls.driver = windows_test_setup
        cls.fc = FlowContainer(cls.driver)
        cls.profile = cls.fc.fd["profile"]
        cls.devicesMFE = cls.fc.fd["devicesMFE"]
        cls.hpx_settings = cls.fc.fd["hpx_settings"]
        cls.fc.kill_myhp_process()
        cls.fc.kill_chrome_process()
        yield
        cls.fc.close_myHP()
    
    @pytest.mark.regressionDryRunPass
    @pytest.mark.regressionDryRunPassSet2
    def test_01_verify_click_the_HP_Privacy_Statement_link_C53303841(self):
        self.fc.launch_myHP_and_skip_fuf()  
        if "Maximize HP" == self.profile.verify_myhp_maximize():
           self.profile.maximize_myhp()
        self.profile.verify_home_device_card()  
        self.profile.click_devicepage_avatar_btn()
        self.profile.click_profile_settings_btn()    
        self.hpx_settings.verify_privacy_statement_link()
        self.hpx_settings.click_privacy_statement_link()
        self.devicesMFE.verify_browser_webview_pane()
        self.hpx_settings.verify_privacy_in_external_browser()
        self.fc.kill_chrome_process()
        self.fc.close_myHP()

    @pytest.mark.regressionDryRunPass
    @pytest.mark.regressionDryRunPassSet1
    def test_02_verify_visibility_manage_privacy_settings_button_C53303843(self):
        self.fc.launch_myHP_and_skip_fuf()  
        if "Maximize HP" == self.profile.verify_myhp_maximize():
           self.profile.maximize_myhp()
        self.profile.verify_home_device_card()   
        self.profile.click_devicepage_avatar_btn()
        self.profile.click_profile_settings_btn()    
        self.hpx_settings.verify_manage_privacy_title()
        self.fc.close_myHP()  

    @pytest.mark.regressionDryRunPass
    @pytest.mark.regressionDryRunPassSet1
    def test_03_verify__manage_privacy_settings_C53303844(self):
        self.fc.launch_myHP_and_skip_fuf()  
        if "Maximize HP" == self.profile.verify_myhp_maximize():
           self.profile.maximize_myhp()
        self.profile.verify_home_device_card()
        self.profile.click_devicepage_avatar_btn()
        self.profile.click_profile_settings_btn()    
        self.hpx_settings.verify_manage_privacy_title()
        self.hpx_settings.click_manage_privacy_btn()
        self.hpx_settings.verify_application_privacy_consents()
        self.fc.close_myHP()  
    
    @pytest.mark.regressionDryRunPass
    @pytest.mark.regressionDryRunPassSet2
    def test_04_verify_delete_your_account_link_C53303842(self):
        self.fc.kill_myhp_process()
        self.fc.kill_chrome_process()
        self.fc.launch_myHP_and_skip_fuf()
        if "Maximize HP" == self.profile.verify_myhp_maximize():
            self.profile.maximize_myhp()
        logged_in = self.profile.verify_top_profile_icon_signed_in()
        if not logged_in:
            self.profile.sign_in_to_hp("qamamobiprod.rcb@gmail.com", "Rcb@12345")
        self.profile.click_top_profile_icon_signed_in()  
        self.profile.verify_settings_side_panel()
        self.profile.click_profile_settings_btn()
        # After logging only the "Delete your account" link should be visible
        self.hpx_settings.verify_delete_your_account()            
        self.fc.close_myHP()
