import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class MyProfilePage extends BasePage {
  readonly path = "/~/+/";

  /** My Profile */
  get my_profile_heading(): Locator {
    return this.locator("my_profile.my_profile_heading");
  }

  /** Settings */
  get settings_radio(): Locator {
    return this.locator("my_profile.settings_radio");
  }

  /** My Profile */
  get my_profile_radio(): Locator {
    return this.locator("my_profile.my_profile_radio");
  }

  /** shows conversation count saved locally */
  get el_1_conversation_s_saved_to_this_app_s_lo_div(): Locator {
    return this.locator("my_profile.1_conversation_s_saved_to_this_app_s_lo_div");
  }

  /** Export selected conversation as Markdown */
  get export_selected_conversation_as_markdown_button(): Locator {
    return this.locator("my_profile.export_selected_conversation_as_markdown_button");
  }
}
