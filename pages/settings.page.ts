import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class SettingsPage extends BasePage {
  readonly path = "/~/+/";

  /** Settings */
  get settings_radio(): Locator {
    return this.locator("settings.settings_radio");
  }

  /** Settings */
  get settings_div(): Locator {
    return this.locator("settings.settings_div");
  }

  /** Reply tone */
  get reply_tone_combobox(): Locator {
    return this.locator("settings.reply_tone_combobox");
  }

  /** Reply length */
  get reply_length_combobox(): Locator {
    return this.locator("settings.reply_length_combobox");
  }

  /** Topics you often ask about */
  get topics_you_often_ask_about_combobox(): Locator {
    return this.locator("settings.topics_you_often_ask_about_combobox");
  }

  /** Chat mode */
  get chat_mode_combobox(): Locator {
    return this.locator("settings.chat_mode_combobox");
  }

  /** Romantic mode partner */
  get romantic_mode_partner_combobox(): Locator {
    return this.locator("settings.romantic_mode_partner_combobox");
  }

  /** Your city (optional) */
  get your_city_optional_textbox(): Locator {
    return this.locator("settings.your_city_optional_textbox");
  }

  /** Save preferences */
  get save_preferences_button(): Locator {
    return this.locator("settings.save_preferences_button");
  }

  /** Delete my account */
  get delete_my_account_button(): Locator {
    return this.locator("settings.delete_my_account_button");
  }

  /** Chat */
  get chat_radio(): Locator {
    return this.locator("settings.chat_radio");
  }
}
