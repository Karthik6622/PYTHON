import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class GetStartedPage extends BasePage {
  readonly path = "/~/+/";

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

  /** Show password */
  get show_password_button(): Locator {
    return this.locator("get_started.show_password_button");
  }

  /** Forgot password? */
  get forgot_password_button(): Locator {
    return this.locator("get_started.forgot_password_button");
  }

  /** Back to welcome */
  get back_to_welcome_button(): Locator {
    return this.locator("get_started.back_to_welcome_button");
  }

  /** Continue with Google */
  get continue_with_google_button(): Locator {
    return this.locator("get_started.continue_with_google_button");
  }

  /** Continue with GitHub */
  get continue_with_github_link(): Locator {
    return this.locator("get_started.continue_with_github_link");
  }

  /** Create account */
  get create_account_button(): Locator {
    return this.locator("get_started.create_account_button");
  }

  /** Skip to main content */
  get skip_to_main_content_link(): Locator {
    return this.locator("get_started.skip_to_main_content_link");
  }
}
