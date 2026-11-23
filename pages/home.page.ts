import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class HomePage extends BasePage {
  readonly path = "/~/+/";

  /** Good afternoon, karthik */
  get good_afternoon_karthik_heading(): Locator {
    return this.locator("home.good_afternoon_karthik_heading");
  }

  /** displays the AI companion greeting */
  get withyou_div(): Locator {
    return this.locator("home.withyou_div");
  }

  /** Chat message from assistant */
  get chat_message_from_assistant_group(): Locator {
    return this.locator("home.chat_message_from_assistant_group");
  }

  /** shows the welcome message to user */
  get hey_karthik_i_m_withyou_your_ai_compan_div(): Locator {
    return this.locator("home.hey_karthik_i_m_withyou_your_ai_compan_div");
  }

  /** indicates chat mode state */
  get chat_mode_div(): Locator {
    return this.locator("home.chat_mode_div");
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

  /** Type a message, attach a file, or tap the mic… */
  get type_a_message_attach_a_file_or_tap_th_textbox(): Locator {
    return this.locator("home.type_a_message_attach_a_file_or_tap_th_textbox");
  }

  /** Send message */
  get send_message_button(): Locator {
    return this.locator("home.send_message_button");
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

  /** Log out */
  get log_out_button(): Locator {
    return this.locator("home.log_out_button");
  }

  /** New chat */
  get new_chat_button(): Locator {
    return this.locator("home.new_chat_button");
  }

  /** New conversation */
  get new_conversation_button(): Locator {
    return this.locator("home.new_conversation_button");
  }

  /** opens manage current chat dialog */
  get manage_current_chat_button(): Locator {
    return this.locator("home.manage_current_chat_button");
  }

  /** Delete this chat */
  get delete_this_chat_button(): Locator {
    return this.locator("home.delete_this_chat_button");
  }

  /** Save title */
  get save_title_button(): Locator {
    return this.locator("home.save_title_button");
  }

  /** shows recent chats section */
  get recent_chats_div(): Locator {
    return this.locator("home.recent_chats_div");
  }

  /** 🔊 Speak replies */
  get speak_replies_switch(): Locator {
    return this.locator("home.speak_replies_switch");
  }

  /** Upload files */
  get upload_files_button(): Locator {
    return this.locator("home.upload_files_button");
  }

  /** Start recording */
  get start_recording_button(): Locator {
    return this.locator("home.start_recording_button");
  }

  /** Conversation title */
  get conversation_title_textbox(): Locator {
    return this.locator("home.conversation_title_textbox");
  }
}
