import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class HomePage extends BasePage {
  readonly path = "/~/+/";

  /** displays AI companion greeting in main area */
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

  /** My Profile */
  get my_profile_radio(): Locator {
    return this.locator("home.my_profile_radio");
  }

  /** Settings */
  get settings_radio(): Locator {
    return this.locator("home.settings_radio");
  }

  /** Type a message, attach a file, or tap the mic… */
  get type_a_message_attach_a_file_or_tap_th_textbox(): Locator {
    return this.locator("home.type_a_message_attach_a_file_or_tap_th_textbox");
  }

  /** displays welcome branding text in sidebar */
  get withyou_div(): Locator {
    return this.locator("home.withyou_div");
  }

  /** displays recent chats section header in sidebar */
  get recent_chats_div(): Locator {
    return this.locator("home.recent_chats_div");
  }

  /** radio group for chat mode selection (Normal, Romantic, Friend, English Teacher) */
  get chat_mode_radiogroup(): Locator {
    return this.locator("home.chat_mode_radiogroup");
  }

  /** Normal */
  get normal_radio(): Locator {
    return this.locator("home.normal_radio");
  }

  /** Romantic */
  get romantic_radio(): Locator {
    return this.locator("home.romantic_radio");
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

  /** Chat message from assistant */
  get chat_message_from_assistant_group(): Locator {
    return this.locator("home.chat_message_from_assistant_group");
  }

  /** Log out */
  get log_out_button(): Locator {
    return this.locator("home.log_out_button");
  }

  /** radio group for account selection */
  get account_radiogroup(): Locator {
    return this.locator("home.account_radiogroup");
  }

  /** Skip to main content */
  get skip_to_main_content_link(): Locator {
    return this.locator("home.skip_to_main_content_link");
  }

  /** main content container layout div */
  get stelementcontainer_div_4(): Locator {
    return this.locator("home.stelementcontainer_div_4");
  }
}
