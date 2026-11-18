import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class SettingsPage extends BasePage {
  readonly path = "/~/+/";

  /** Settings */
  get settings_radio(): Locator {
    return this.locator("settings.settings_radio");
  }

  /** Reply tone */
  get reply_tone_combobox(): Locator {
    return this.locator("settings.reply_tone_combobox");
  }

  /** Reply length */
  get reply_length_combobox(): Locator {
    return this.locator("settings.reply_length_combobox");
  }

  /** Chat mode */
  get chat_mode_combobox(): Locator {
    return this.locator("settings.chat_mode_combobox");
  }

  /** Romantic mode partner */
  get romantic_mode_partner_combobox(): Locator {
    return this.locator("settings.romantic_mode_partner_combobox");
  }

  /** Help for Your city (optional) */
  get help_for_your_city_optional_button(): Locator {
    return this.locator("settings.help_for_your_city_optional_button");
  }

  /** Save preferences */
  get save_preferences_button(): Locator {
    return this.locator("settings.save_preferences_button");
  }

  /** Delete my account */
  get delete_my_account_button(): Locator {
    return this.locator("settings.delete_my_account_button");
  }

  /** I understand this permanently deletes my account and convers */
  get i_understand_this_permanently_deletes_my_checkbox(): Locator {
    return this.locator("settings.i_understand_this_permanently_deletes_my_checkbox");
  }

  /** I understand this permanently deletes my account and convers */
  get i_understand_this_permanently_deletes_my_div(): Locator {
    return this.locator("settings.i_understand_this_permanently_deletes_my_div");
  }

  /** Deleting your account permanently removes its local account */
  get deleting_your_account_permanently_remove_div(): Locator {
    return this.locator("settings.deleting_your_account_permanently_remove_div");
  }

  /** Chat */
  get chat_radio(): Locator {
    return this.locator("settings.chat_radio");
  }

  /** keyboard_double_arrow_left */
  get keyboard_double_arrow_left_span(): Locator {
    return this.locator("settings.keyboard_double_arrow_left_span");
  }

  /** Collapse sidebar */
  get collapse_sidebar_button(): Locator {
    return this.locator("settings.collapse_sidebar_button");
  }
}
