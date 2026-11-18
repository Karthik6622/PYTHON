import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class SettingsPage extends BasePage {
  readonly path = "/~/+/";

  /** Chat mode */
  get chat_mode_combobox(): Locator {
    return this.locator("settings.chat_mode_combobox");
  }

  /** Chat mode */
  get chat_mode_div(): Locator {
    return this.locator("settings.chat_mode_div");
  }

  /** Chat */
  get chat_radio(): Locator {
    return this.locator("settings.chat_radio");
  }

  /** settings.stmarkdowncontainer_div */
  get stmarkdowncontainer_div(): Locator {
    return this.locator("settings.stmarkdowncontainer_div");
  }

  /** Log out */
  get log_out_button(): Locator {
    return this.locator("settings.log_out_button");
  }

  /** settings.stelementcontainer_div_4 */
  get stelementcontainer_div_4(): Locator {
    return this.locator("settings.stelementcontainer_div_4");
  }
}
