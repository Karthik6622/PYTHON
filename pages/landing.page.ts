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

  /** WithYouA personal AI companionPowered by RK */
  get withyoua_personal_ai_companionpowered_by_div(): Locator {
    return this.locator("landing.withyoua_personal_ai_companionpowered_by_div");
  }
}
