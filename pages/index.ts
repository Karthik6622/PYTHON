import { LandingPage } from './landing.page';
import { GetStartedPage } from './get_started.page';
import { HomePage } from './home.page';
import { MyProfilePage } from './my_profile.page';
import { CreateAccountPage } from './create_account.page';
import { ForgotPasswordPage } from './forgot_password.page';
import { SettingsPage } from './settings.page';

export class Pages {
  readonly landing: LandingPage;
  readonly get_started: GetStartedPage;
  readonly home: HomePage;
  readonly my_profile: MyProfilePage;
  readonly create_account: CreateAccountPage;
  readonly forgot_password: ForgotPasswordPage;
  readonly settings: SettingsPage;

  constructor(app: any) {
    this.landing = new LandingPage(app);
    this.get_started = new GetStartedPage(app);
    this.home = new HomePage(app);
    this.my_profile = new MyProfilePage(app);
    this.create_account = new CreateAccountPage(app);
    this.forgot_password = new ForgotPasswordPage(app);
    this.settings = new SettingsPage(app);
  }
}
