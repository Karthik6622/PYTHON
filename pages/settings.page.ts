import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class SettingsPage extends BasePage {
  readonly path = "/~/+/";

  /** Settings */
  get settings_radio(): Locator {
    return this.locator("settings.settings_radio");
  }

  /** settings.stmarkdowncontainer_div_4 */
  get stmarkdowncontainer_div_4(): Locator {
    return this.locator("settings.stmarkdowncontainer_div_4");
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
  get delete_my_account_div(): Locator {
    return this.locator("settings.delete_my_account_div");
  }

  /** Delete my account */
  get delete_my_account_button(): Locator {
    return this.locator("settings.delete_my_account_button");
  }

  /** Deleting your account permanently removes its local account */
  get deleting_your_account_permanently_remove_div(): Locator {
    return this.locator("settings.deleting_your_account_permanently_remove_div");
  }

  /** I understand this permanently deletes my account and convers */
  get i_understand_this_permanently_deletes_my_checkbox(): Locator {
    return this.locator("settings.i_understand_this_permanently_deletes_my_checkbox");
  }

  /** settings.stmarkdown_div */
  get stmarkdown_div(): Locator {
    return this.locator("settings.stmarkdown_div");
  }

  /** Help for Chat mode */
  get help_for_chat_mode_button(): Locator {
    return this.locator("settings.help_for_chat_mode_button");
  }

  /** Log out */
  get log_out_button(): Locator {
    return this.locator("settings.log_out_button");
  }

  /** My Profile */
  get my_profile_radio(): Locator {
    return this.locator("settings.my_profile_radio");
  }
}
