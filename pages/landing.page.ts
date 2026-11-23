import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class LandingPage extends BasePage {
  readonly path = "/~/+/";

  /** Here for whatever is on your mind. */
  get here_for_whatever_is_on_your_mind_heading(): Locator {
    return this.locator("landing.here_for_whatever_is_on_your_mind_heading");
  }

  /** Get started */
  get get_started_button(): Locator {
    return this.locator("landing.get_started_button");
  }

  /** Create account */
  get create_account_button(): Locator {
    return this.locator("landing.create_account_button");
  }

  /** Your conversations, your space */
  get your_conversations_your_space_heading(): Locator {
    return this.locator("landing.your_conversations_your_space_heading");
  }

  /** Always ready to talk */
  get always_ready_to_talk_heading(): Locator {
    return this.locator("landing.always_ready_to_talk_heading");
  }

  /** Made to feel personal */
  get made_to_feel_personal_heading(): Locator {
    return this.locator("landing.made_to_feel_personal_heading");
  }
}
