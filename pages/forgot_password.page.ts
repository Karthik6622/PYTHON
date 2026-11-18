import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class ForgotPasswordPage extends BasePage {
  readonly path = "/~/+/";

  /** forgot_password.stheader_header */
  get stheader_header(): Locator {
    return this.locator("forgot_password.stheader_header");
  }

  /** Enter the email address on your account. */
  get enter_the_email_address_on_your_account_div(): Locator {
    return this.locator("forgot_password.enter_the_email_address_on_your_account_div");
  }

  /** Email */
  get email_textbox(): Locator {
    return this.locator("forgot_password.email_textbox");
  }

  /** Continue */
  get continue_button(): Locator {
    return this.locator("forgot_password.continue_button");
  }

  /** Signed up with Google or GitHub? You can keep using those bu */
  get signed_up_with_google_or_github_you_can_div(): Locator {
    return this.locator("forgot_password.signed_up_with_google_or_github_you_can_div");
  }

  /** Back to log in */
  get back_to_log_in_button(): Locator {
    return this.locator("forgot_password.back_to_log_in_button");
  }
}
