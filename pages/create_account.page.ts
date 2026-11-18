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

  /** Help for Password */
  get help_for_password_button(): Locator {
    return this.locator("create_account.help_for_password_button");
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

  /** I have read the privacy notice and understand this is an AI */
  get i_have_read_the_privacy_notice_and_under_checkbox(): Locator {
    return this.locator("create_account.i_have_read_the_privacy_notice_and_under_checkbox");
  }

  /** Create account */
  get create_account_button(): Locator {
    return this.locator("create_account.create_account_button");
  }

  /** Continue with Google */
  get continue_with_google_button(): Locator {
    return this.locator("create_account.continue_with_google_button");
  }

  /** Continue with GitHub */
  get continue_with_github_link(): Locator {
    return this.locator("create_account.continue_with_github_link");
  }

  /** Log in */
  get log_in_button(): Locator {
    return this.locator("create_account.log_in_button");
  }

  /** Back to welcome */
  get back_to_welcome_button(): Locator {
    return this.locator("create_account.back_to_welcome_button");
  }

  /** Create account */
  get create_account_div(): Locator {
    return this.locator("create_account.create_account_div");
  }

  /** create_account.stwidgetlabel_label */
  get stwidgetlabel_label(): Locator {
    return this.locator("create_account.stwidgetlabel_label");
  }

  /** create_account.stwidgetlabel_label_2 */
  get stwidgetlabel_label_2(): Locator {
    return this.locator("create_account.stwidgetlabel_label_2");
  }

  /** create_account.stwidgetlabel_label_3 */
  get stwidgetlabel_label_3(): Locator {
    return this.locator("create_account.stwidgetlabel_label_3");
  }

  /** Confirm password */
  get confirm_password_div(): Locator {
    return this.locator("create_account.confirm_password_div");
  }
}
