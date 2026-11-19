import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class HomePage extends BasePage {
  readonly path = "/~/+/";

  /** New chat */
  get new_chat_button(): Locator {
    return this.locator("home.new_chat_button");
  }

  /** Chat */
  get chat_radio(): Locator {
    return this.locator("home.chat_radio");
  }

  /** My Profile */
  get my_profile_radio(): Locator {
    return this.locator("home.my_profile_radio");
  }

  /** Settings */
  get settings_radio(): Locator {
    return this.locator("home.settings_radio");
  }

  /** Hey kk prompt main div */
  get hey_kk_what_s_on_your_mind_today_div(): Locator {
    return this.locator("home.hey_kk_what_s_on_your_mind_today_div");
  }

  /** displays WithYou welcome message in sidebar */
  get withyou_div(): Locator {
    return this.locator("home.withyou_div");
  }

  /** opens new conversation dialog */
  get new_conversation_button(): Locator {
    return this.locator("home.new_conversation_button");
  }

  /** opens new conversation dialog (role-based) */
  get new_conversation_button_2(): Locator {
    return this.locator("home.new_conversation_button_2");
  }

  /** RECENT CHATS section header in sidebar */
  get recent_chats_div(): Locator {
    return this.locator("home.recent_chats_div");
  }

  /** opens manage current chat menu */
  get manage_current_chat_button(): Locator {
    return this.locator("home.manage_current_chat_button");
  }

  /** Type a message, attach a file, or tap the mic… */
  get type_a_message_attach_a_file_or_tap_th_textbox(): Locator {
    return this.locator("home.type_a_message_attach_a_file_or_tap_th_textbox");
  }

  /** Send message */
  get send_message_button(): Locator {
    return this.locator("home.send_message_button");
  }

  /** Chat message from assistant */
  get chat_message_from_assistant_group(): Locator {
    return this.locator("home.chat_message_from_assistant_group");
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

  /** chat selection div */
  get chat_div(): Locator {
    return this.locator("home.chat_div");
  }

  /** My Profile navigation item */
  get my_profile_div(): Locator {
    return this.locator("home.my_profile_div");
  }

  /** Settings navigation item */
  get settings_div(): Locator {
    return this.locator("home.settings_div");
  }

  /** Log out navigation item */
  get log_out_div(): Locator {
    return this.locator("home.log_out_div");
  }

  /** Collapse sidebar */
  get collapse_sidebar_button(): Locator {
    return this.locator("home.collapse_sidebar_button");
  }
}
