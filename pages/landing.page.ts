import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class LandingPage extends BasePage {
  readonly path = "/~/+/";

  /** Get started */
  get get_started_button(): Locator {
    return this.locator("landing.get_started_button");
  }

  /** Create account */
  get create_account_button(): Locator {
    return this.locator("landing.create_account_button");
  }

  /** Continue with Google */
  get continue_with_google_button(): Locator {
    return this.locator("landing.continue_with_google_button");
  }

  /** Continue with GitHub */
  get continue_with_github_link(): Locator {
    return this.locator("landing.continue_with_github_link");
  }

  /** landing.stheader_header */
  get stheader_header(): Locator {
    return this.locator("landing.stheader_header");
  }

  /** Skip to main content */
  get skip_to_main_content_link(): Locator {
    return this.locator("landing.skip_to_main_content_link");
  }

  /** st.iframe */
  get st_iframe_iframe(): Locator {
    return this.locator("landing.st_iframe_iframe");
  }
}
