import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class CreateAccountPage extends BasePage {
  readonly path = "/~/+/";

  /** Create your account */
  get create_your_account_heading(): Locator {
    return this.locator("create_account.create_your_account_heading");
  }

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

  /** I have read the privacy notice and understand this is an AI */
  get i_have_read_the_privacy_notice_and_under_checkbox(): Locator {
    return this.locator("create_account.i_have_read_the_privacy_notice_and_under_checkbox");
  }

  /** Create account */
  get create_account_button(): Locator {
    return this.locator("create_account.create_account_button");
  }
}
