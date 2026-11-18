import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class CreateAccountPage extends BasePage {
  readonly path = "/~/+/";

  /** Password */
  get password_textbox(): Locator {
    return this.locator("create_account.password_textbox");
  }

  /** Show password */
  get show_password_button(): Locator {
    return this.locator("create_account.show_password_button");
  }

  /** Confirm password */
  get confirm_password_textbox(): Locator {
    return this.locator("create_account.confirm_password_textbox");
  }

  /** Show password */
  get show_password_button_2(): Locator {
    return this.locator("create_account.show_password_button_2");
  }

  /** Display name */
  get display_name_textbox(): Locator {
    return this.locator("create_account.display_name_textbox");
  }

  /** Email */
  get email_textbox(): Locator {
    return this.locator("create_account.email_textbox");
  }

  /** I have read the privacy notice and understand this is an AI */
  get i_have_read_the_privacy_notice_and_under_checkbox(): Locator {
    return this.locator("create_account.i_have_read_the_privacy_notice_and_under_checkbox");
  }

  /** Create account */
  get create_account_button(): Locator {
    return this.locator("create_account.create_account_button");
  }

  /** Create account */
  get create_account_div(): Locator {
    return this.locator("create_account.create_account_div");
  }

  /** Log in */
  get log_in_button(): Locator {
    return this.locator("create_account.log_in_button");
  }
}
