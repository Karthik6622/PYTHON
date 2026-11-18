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

  /** Show password */
  get show_password_button(): Locator {
    return this.locator("get_started.show_password_button");
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

  /** Forgot password? */
  get forgot_password_button(): Locator {
    return this.locator("get_started.forgot_password_button");
  }

  /** get_started.stheader_header */
  get stheader_header(): Locator {
    return this.locator("get_started.stheader_header");
  }

  /** Skip to main content */
  get skip_to_main_content_link(): Locator {
    return this.locator("get_started.skip_to_main_content_link");
  }

  /** get_started.stappiframeresizeranchor_div */
  get stappiframeresizeranchor_div(): Locator {
    return this.locator("get_started.stappiframeresizeranchor_div");
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
