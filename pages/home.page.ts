import type { Locator } from '@playwright/test';
import { BasePage } from './base.page';

export class HomePage extends BasePage {
  readonly path = "/~/+/";

  /** Good morning, kk */
  get good_morning_kk_heading(): Locator {
    return this.locator("home.good_morning_kk_heading");
  }

  /** navigates to or identifies the WithYou section in the sidebar */
  get withyou_div(): Locator {
    return this.locator("home.withyou_div");
  }

  /** identifies the Recent Chats section in the sidebar */
  get recent_chats_div(): Locator {
    return this.locator("home.recent_chats_div");
  }

  /** Hello */
  get hello_button(): Locator {
    return this.locator("home.hello_button");
  }

  /** identifies the CHAT MODE indicator */
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

  /** Upload files */
  get upload_files_button(): Locator {
    return this.locator("home.upload_files_button");
  }

  /** Start recording */
  get start_recording_button(): Locator {
    return this.locator("home.start_recording_button");
  }

  /** Send message */
  get send_message_button(): Locator {
    return this.locator("home.send_message_button");
  }

  /** New chat */
  get new_chat_button(): Locator {
    return this.locator("home.new_chat_button");
  }

  /** New conversation */
  get new_conversation_button(): Locator {
    return this.locator("home.new_conversation_button");
  }

  /** opens the manage current chat dialog */
  get manage_current_chat_button(): Locator {
    return this.locator("home.manage_current_chat_button");
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

  /** Chat */
  get chat_radio(): Locator {
    return this.locator("home.chat_radio");
  }
}
