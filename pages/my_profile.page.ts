import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class MyProfilePage extends BasePage {
  readonly path = "/~/+/";

  /** My Profile */
  get my_profile_heading(): Locator {
    return this.locator("my_profile.my_profile_heading");
  }

  /** Display name */
  get display_name_textbox(): Locator {
    return this.locator("my_profile.display_name_textbox");
  }

  /** Email */
  get email_textbox(): Locator {
    return this.locator("my_profile.email_textbox");
  }

  /** 3 conversation(s) saved to this app’s local data folder. */
  get el_3_conversation_s_saved_to_this_app_s_lo_div(): Locator {
    return this.locator("my_profile.3_conversation_s_saved_to_this_app_s_lo_div");
  }

  /** The app stores account and conversation data locally on the */
  get the_app_stores_account_and_conversation_div(): Locator {
    return this.locator("my_profile.the_app_stores_account_and_conversation_div");
  }

  /** Chat */
  get chat_radio(): Locator {
    return this.locator("my_profile.chat_radio");
  }

  /** My Profile */
  get my_profile_radio(): Locator {
    return this.locator("my_profile.my_profile_radio");
  }

  /** Export selected conversation as Markdown */
  get export_selected_conversation_as_markdown_button(): Locator {
    return this.locator("my_profile.export_selected_conversation_as_markdown_button");
  }

  /** Settings */
  get settings_radio(): Locator {
    return this.locator("my_profile.settings_radio");
  }
}
