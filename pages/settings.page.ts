import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class SettingsPage extends BasePage {
  readonly path = "/~/+/";

  /** Settings */
  get settings_radio(): Locator {
    return this.locator("settings.settings_radio");
  }

  /** Settings */
  get settings_heading(): Locator {
    return this.locator("settings.settings_heading");
  }

  /** Privacy and account data */
  get privacy_and_account_data_heading(): Locator {
    return this.locator("settings.privacy_and_account_data_heading");
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

  /** Help for Romantic mode partner */
  get help_for_romantic_mode_partner_button(): Locator {
    return this.locator("settings.help_for_romantic_mode_partner_button");
  }

  /** Romantic mode partner */
  get romantic_mode_partner_combobox(): Locator {
    return this.locator("settings.romantic_mode_partner_combobox");
  }

  /** Help for Your city (optional) */
  get help_for_your_city_optional_button(): Locator {
    return this.locator("settings.help_for_your_city_optional_button");
  }

  /** Your city (optional) */
  get your_city_optional_textbox(): Locator {
    return this.locator("settings.your_city_optional_textbox");
  }

  /** Save preferences */
  get save_preferences_button(): Locator {
    return this.locator("settings.save_preferences_button");
  }

  /** Type your email address to confirm deletion */
  get type_your_email_address_to_confirm_delet_textbox(): Locator {
    return this.locator("settings.type_your_email_address_to_confirm_delet_textbox");
  }

  /** I understand this permanently deletes my account and convers */
  get i_understand_this_permanently_deletes_my_checkbox(): Locator {
    return this.locator("settings.i_understand_this_permanently_deletes_my_checkbox");
  }

  /** Delete my account */
  get delete_my_account_button(): Locator {
    return this.locator("settings.delete_my_account_button");
  }

  /** My Profile */
  get my_profile_radio(): Locator {
    return this.locator("settings.my_profile_radio");
  }

  /** explains the permanent deletion consequence */
  get deleting_your_account_permanently_remove_div(): Locator {
    return this.locator("settings.deleting_your_account_permanently_remove_div");
  }
}
