import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class CreateAccountPage extends BasePage {
  readonly path = "/~/+/";

  /** Display name */
  get display_name_textbox(): Locator {
    return this.locator("create_account.display_name_textbox");
  }

  /** Email */
  get email_textbox(): Locator {
    return this.locator("create_account.email_textbox");
  }

  /** Password */
  get password_textbox(): Locator {
    return this.locator("create_account.password_textbox");
  }

  /** Confirm password */
  get confirm_password_textbox(): Locator {
    return this.locator("create_account.confirm_password_textbox");
  }

  /** Create account */
  get create_account_button(): Locator {
    return this.locator("create_account.create_account_button");
  }

  /** Back to welcome */
  get back_to_welcome_button(): Locator {
    return this.locator("create_account.back_to_welcome_button");
  }

  /** Log in */
  get log_in_button(): Locator {
    return this.locator("create_account.log_in_button");
  }

  /** I have read the privacy notice and understand this is an AI */
  get i_have_read_the_privacy_notice_and_under_checkbox(): Locator {
    return this.locator("create_account.i_have_read_the_privacy_notice_and_under_checkbox");
  }

  /** Continue with Google */
  get continue_with_google_button(): Locator {
    return this.locator("create_account.continue_with_google_button");
  }

  /** Continue with GitHub */
  get continue_with_github_link(): Locator {
    return this.locator("create_account.continue_with_github_link");
  }

  /** Skip to main content */
  get skip_to_main_content_link(): Locator {
    return this.locator("create_account.skip_to_main_content_link");
  }
}
