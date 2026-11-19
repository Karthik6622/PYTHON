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

  /** Forgot password? */
  get forgot_password_button(): Locator {
    return this.locator("get_started.forgot_password_button");
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

  /** Log in */
  get log_in_div(): Locator {
    return this.locator("get_started.log_in_div");
  }

  /** Back to welcome */
  get back_to_welcome_button(): Locator {
    return this.locator("get_started.back_to_welcome_button");
  }

  /** Create account */
  get create_account_button(): Locator {
    return this.locator("get_started.create_account_button");
  }

  /** get_started.stwidgetlabel_label */
  get stwidgetlabel_label(): Locator {
    return this.locator("get_started.stwidgetlabel_label");
  }

  /** get_started.stwidgetlabel_label_2 */
  get stwidgetlabel_label_2(): Locator {
    return this.locator("get_started.stwidgetlabel_label_2");
  }
}
