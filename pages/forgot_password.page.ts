import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class ForgotPasswordPage extends BasePage {
  readonly path = "/~/+/";

  /** Email */
  get email_textbox(): Locator {
    return this.locator("forgot_password.email_textbox");
  }

  /** Continue */
  get continue_button(): Locator {
    return this.locator("forgot_password.continue_button");
  }

  /** Back to log in */
  get back_to_log_in_button(): Locator {
    return this.locator("forgot_password.back_to_log_in_button");
  }

  /** Skip to main content */
  get skip_to_main_content_link(): Locator {
    return this.locator("forgot_password.skip_to_main_content_link");
  }
}
