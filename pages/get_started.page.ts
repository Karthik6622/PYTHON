import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class GetStartedPage extends BasePage {
  readonly path = "/~/+/";

  /** Welcome back */
  get welcome_back_heading(): Locator {
    return this.locator("get_started.welcome_back_heading");
  }

  /** Email */
  get email_textbox(): Locator {
    return this.locator("get_started.email_textbox");
  }

  /** Password */
  get password_textbox(): Locator {
    return this.locator("get_started.password_textbox");
  }

  /** Log in */
  get log_in_button(): Locator {
    return this.locator("get_started.log_in_button");
  }

  /** Continue with Google */
  get continue_with_google_button(): Locator {
    return this.locator("get_started.continue_with_google_button");
  }

  /** Continue with GitHub */
  get continue_with_github_link(): Locator {
    return this.locator("get_started.continue_with_github_link");
  }

  /** Show password */
  get show_password_button(): Locator {
    return this.locator("get_started.show_password_button");
  }

  /** Forgot password? */
  get forgot_password_button(): Locator {
    return this.locator("get_started.forgot_password_button");
  }

  /** Create account */
  get create_account_button(): Locator {
    return this.locator("get_started.create_account_button");
  }

  /** navigates back to welcome screen */
  get back_to_welcome_button(): Locator {
    return this.locator("get_started.back_to_welcome_button");
  }

  /** shows alternative login options */
  get or_continue_with_div(): Locator {
    return this.locator("get_started.or_continue_with_div");
  }

  /** prompts new user onboarding */
  get new_here_div(): Locator {
    return this.locator("get_started.new_here_div");
  }
}
