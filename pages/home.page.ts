import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class HomePage extends BasePage {
  readonly path = "/~/+/";

  /** New chat */
  get new_chat_button(): Locator {
    return this.locator("home.new_chat_button");
  }

  /** displays recent chats section */
  get recent_chats_div(): Locator {
    return this.locator("home.recent_chats_div");
  }

  /** opens manage current chat dialog */
  get manage_current_chat_button(): Locator {
    return this.locator("home.manage_current_chat_button");
  }

  /** New conversation */
  get new_conversation_button(): Locator {
    return this.locator("home.new_conversation_button");
  }

  /** ai companion greeting banner */
  get hey_kk_i_m_withyou_your_ai_companion_div(): Locator {
    return this.locator("home.hey_kk_i_m_withyou_your_ai_companion_div");
  }

  /** chat mode selection section */
  get chat_mode_div(): Locator {
    return this.locator("home.chat_mode_div");
  }

  /** account navigation item in sidebar */
  get account_div(): Locator {
    return this.locator("home.account_div");
  }

  /** Log out */
  get log_out_button(): Locator {
    return this.locator("home.log_out_button");
  }

  /** Romantic */
  get romantic_radio(): Locator {
    return this.locator("home.romantic_radio");
  }

  /** Type a message, attach a file, or tap the mic… */
  get type_a_message_attach_a_file_or_tap_th_textbox(): Locator {
    return this.locator("home.type_a_message_attach_a_file_or_tap_th_textbox");
  }

  /** Conversation title */
  get conversation_title_textbox(): Locator {
    return this.locator("home.conversation_title_textbox");
  }

  /** Save title */
  get save_title_button(): Locator {
    return this.locator("home.save_title_button");
  }

  /** Settings */
  get settings_radio(): Locator {
    return this.locator("home.settings_radio");
  }

  /** Chat */
  get chat_radio(): Locator {
    return this.locator("home.chat_radio");
  }

  /** My Profile */
  get my_profile_radio(): Locator {
    return this.locator("home.my_profile_radio");
  }

  /** navigates back to previous chat */
  get keyboard_double_arrow_left_span(): Locator {
    return this.locator("home.keyboard_double_arrow_left_span");
  }

  /** Collapse sidebar */
  get collapse_sidebar_button(): Locator {
    return this.locator("home.collapse_sidebar_button");
  }

  /** Normal */
  get normal_radio(): Locator {
    return this.locator("home.normal_radio");
  }

  /** Friend */
  get friend_radio(): Locator {
    return this.locator("home.friend_radio");
  }

  /** English Teacher */
  get english_teacher_radio(): Locator {
    return this.locator("home.english_teacher_radio");
  }

  /** Send message */
  get send_message_button(): Locator {
    return this.locator("home.send_message_button");
  }

  /** Delete this chat */
  get delete_this_chat_button(): Locator {
    return this.locator("home.delete_this_chat_button");
  }

  /** Skip to main content */
  get skip_to_main_content_link(): Locator {
    return this.locator("home.skip_to_main_content_link");
  }
}
