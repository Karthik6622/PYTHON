import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class MyProfilePage extends BasePage {
  readonly path = "/~/+/";

  /** My Profile */
  get my_profile_div(): Locator {
    return this.locator("my_profile.my_profile_div");
  }

  /** Display name */
  get display_name_textbox(): Locator {
    return this.locator("my_profile.display_name_textbox");
  }

  /** Email */
  get email_textbox(): Locator {
    return this.locator("my_profile.email_textbox");
  }

  /** 2 conversation(s) saved to this app’s local data folder. */
  get el_2_conversation_s_saved_to_this_app_s_lo_div(): Locator {
    return this.locator("my_profile.2_conversation_s_saved_to_this_app_s_lo_div");
  }

  /** The app stores account and conversation data locally on the */
  get the_app_stores_account_and_conversation_div(): Locator {
    return this.locator("my_profile.the_app_stores_account_and_conversation_div");
  }

  /** Your account details stay separate from your chat content. */
  get your_account_details_stay_separate_from_div(): Locator {
    return this.locator("my_profile.your_account_details_stay_separate_from_div");
  }

  /** Export selected conversation as Markdown */
  get export_selected_conversation_as_markdown_button(): Locator {
    return this.locator("my_profile.export_selected_conversation_as_markdown_button");
  }

  /** My Profile */
  get my_profile_radio(): Locator {
    return this.locator("my_profile.my_profile_radio");
  }

  /** RECENT CHATS section header in my_profile sidebar */
  get recent_chats_div(): Locator {
    return this.locator("my_profile.recent_chats_div");
  }

  /** my_profile.stmarkdown_div_4 */
  get stmarkdown_div_4(): Locator {
    return this.locator("my_profile.stmarkdown_div_4");
  }

  /** Display name */
  get display_name_div(): Locator {
    return this.locator("my_profile.display_name_div");
  }

  /** Email */
  get email_div(): Locator {
    return this.locator("my_profile.email_div");
  }
}
