import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class MyProfilePage extends BasePage {
  readonly path = "/~/+/";

  /** My Profile */
  get my_profile_radio(): Locator {
    return this.locator("my_profile.my_profile_radio");
  }

  /** Display name */
  get display_name_textbox(): Locator {
    return this.locator("my_profile.display_name_textbox");
  }

  /** Email */
  get email_textbox(): Locator {
    return this.locator("my_profile.email_textbox");
  }

  /** 1 conversation(s) saved to this app’s local data folder. */
  get el_1_conversation_s_saved_to_this_app_s_lo_div(): Locator {
    return this.locator("my_profile.1_conversation_s_saved_to_this_app_s_lo_div");
  }

  /** The app stores account and conversation data locally on the */
  get the_app_stores_account_and_conversation_div(): Locator {
    return this.locator("my_profile.the_app_stores_account_and_conversation_div");
  }

  /** Export selected conversation as Markdown */
  get export_selected_conversation_as_markdown_button(): Locator {
    return this.locator("my_profile.export_selected_conversation_as_markdown_button");
  }

  /** Skip to main content */
  get skip_to_main_content_link(): Locator {
    return this.locator("my_profile.skip_to_main_content_link");
  }
}
