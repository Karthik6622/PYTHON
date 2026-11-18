import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class HomePage extends BasePage {
  readonly path = "/~/+/";

  /** AI companion greeting main content */
  get hey_kk_i_m_withyou_your_ai_companion_div(): Locator {
    return this.locator("home.hey_kk_i_m_withyou_your_ai_companion_div");
  }

  /** New chat */
  get new_chat_button(): Locator {
    return this.locator("home.new_chat_button");
  }

  /** New conversation */
  get new_conversation_button(): Locator {
    return this.locator("home.new_conversation_button");
  }

  /** open manage current chat menu */
  get manage_current_chat_button(): Locator {
    return this.locator("home.manage_current_chat_button");
  }

  /** recent chats section header in sidebar */
  get recent_chats_div(): Locator {
    return this.locator("home.recent_chats_div");
  }

  /** My Profile */
  get my_profile_radio(): Locator {
    return this.locator("home.my_profile_radio");
  }

  /** Settings */
  get settings_radio(): Locator {
    return this.locator("home.settings_radio");
  }

  /** page header element */
  get stheader_header(): Locator {
    return this.locator("home.stheader_header");
  }

  /** Chat */
  get chat_radio(): Locator {
    return this.locator("home.chat_radio");
  }

  /** Conversation title */
  get conversation_title_textbox(): Locator {
    return this.locator("home.conversation_title_textbox");
  }

  /** Save title */
  get save_title_button(): Locator {
    return this.locator("home.save_title_button");
  }

  /** Delete this chat */
  get delete_this_chat_button(): Locator {
    return this.locator("home.delete_this_chat_button");
  }

  /** account selection radio group */
  get account_radiogroup(): Locator {
    return this.locator("home.account_radiogroup");
  }

  /** display conversation title */
  get conversation_title_div(): Locator {
    return this.locator("home.conversation_title_div");
  }

  /** Type a message, attach a file, or tap the mic… */
  get type_a_message_attach_a_file_or_tap_th_textbox(): Locator {
    return this.locator("home.type_a_message_attach_a_file_or_tap_th_textbox");
  }

  /** Send message */
  get send_message_button(): Locator {
    return this.locator("home.send_message_button");
  }

  /** Log out */
  get log_out_button(): Locator {
    return this.locator("home.log_out_button");
  }

  /** Collapse sidebar */
  get collapse_sidebar_button(): Locator {
    return this.locator("home.collapse_sidebar_button");
  }
}
