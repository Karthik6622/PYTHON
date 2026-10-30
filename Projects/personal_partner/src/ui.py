"""Responsive Streamlit views for WithYou."""

from __future__ import annotations

import html
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import streamlit as st

from . import storage
from .assistant import MODES, chat_mode, messages_for_mode, stream_reply
from .auth import (
    AccountLockedError,
    AccountValidationError,
    authenticate_social_user,
    authenticate_user,
    create_account,
    email_has_account,
    public_account,
    reset_password_for_email,
)
from .live_info import resolve_timezone
from .model_client import describe_model_error
from .social_auth import (
    SocialLoginError,
    complete_github_callback,
    github_authorization_url,
    github_is_configured,
    google_identity,
    google_is_configured,
    google_missing_settings,
)
from .validation import safe_conversation_title, validate_message
from .voice import VoiceError, synthesize_speech, transcribe_audio, voice_for
from .styles import APP_CSS, BRAND_HTML, auth_header_html
from .attachments import ACCEPTED_TYPES, DEFAULT_QUESTION, MAX_FILE_MB, MAX_FILES, process_uploads
from .futuristic import FUTURISTIC_CSS
from .image_gen import ImageGenerationError, generate_image, image_generation_configured, wants_image
from .welcome_design import (
    WELCOME_CSS,
    WELCOME_FONT_CSS,
    features_html,
    footer_html,
    hero_text_html,
    nav_brand_html,
    preview_html,
    trust_html,
)


LOGGER = logging.getLogger("kindspace.ui")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def apply_styles() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)
    st.markdown(FUTURISTIC_CSS, unsafe_allow_html=True)


def _set_authenticated(user: dict[str, Any]) -> None:
    public = public_account(user)
    st.session_state.authenticated = True
    st.session_state.user_id = public["user_id"]
    st.session_state.username = public["username"]
    st.session_state.email = public["email"]
    st.session_state.display_name = public["display_name"]
    st.session_state.user_preferences = public["preferences"]
    st.session_state.view = "Chat"
    st.session_state.pop("active_conversation_id", None)
    st.session_state.pop("pending_message_id", None)


def _logout() -> None:
    try:
        if bool(st.user.is_logged_in):
            st.logout()
    except Exception:
        pass
    for key in (
        "authenticated", "user_id", "username", "email", "display_name", "user_preferences",
        "active_conversation_id", "pending_message_id", "pending_conversation_id",
        "last_model_error", "authenticated_view", "view", "voice_reply", "voice_notice", "pending_speak",
    ):
        st.session_state.pop(key, None)
    st.session_state.view = "Welcome"
    st.rerun()


def _notice_storage_issues() -> None:
    for notice in storage.consume_storage_notices():
        st.warning(notice)


def _social_buttons(prefix: str, welcome: bool = False, stacked: bool = False) -> None:
    if welcome:
        # Public landing page: only offer providers that are actually configured and never show setup hints.
        if not (google_is_configured() or github_is_configured()):
            return
    st.markdown('<div class="ks-or">or continue with</div>', unsafe_allow_html=True)
    if stacked:
        google_col = github_col = st.container()
    else:
        google_col, github_col = st.columns(2)
    with google_col:
        if google_is_configured():
            if st.button("Continue with Google", key=f"{prefix}_google", use_container_width=True):
                st.login("google")
        else:
            st.button("Continue with Google", key=f"{prefix}_google", disabled=True, use_container_width=True)
    with github_col:
        url = github_authorization_url() if github_is_configured() else "#"
        st.link_button(
            "Continue with GitHub",
            url,
            key=f"{prefix}_github",
            disabled=not github_is_configured(),
            use_container_width=True,
        )
    if welcome:
        return
    missing = google_missing_settings()
    if missing:
        LOGGER.warning("Google sign-in is disabled; missing secrets: %s", ", ".join(missing))
        st.caption("Google sign-in is not set up yet. Missing secrets: " + ", ".join(f"`{name}`" for name in missing) + ".")
    if not github_is_configured():
        st.caption("GitHub sign-in is not set up yet. Add `[github]` client_id, client_secret, and redirect_uri to your secrets.")


def _show_social_error() -> None:
    message = st.session_state.pop("social_login_error", None)
    if message:
        st.error(message)


def render_welcome() -> None:
    _show_social_error()
    st.markdown(WELCOME_FONT_CSS + WELCOME_CSS, unsafe_allow_html=True)
    st.markdown(FUTURISTIC_CSS, unsafe_allow_html=True)
    with st.container(key="ks_welcome"):
        with st.container(key="ks_nav"):
            st.markdown(nav_brand_html(), unsafe_allow_html=True)
        with st.container(key="ks_hero"):
            left, right = st.columns([1.1, 0.9], vertical_alignment="center")
            with left:
                st.markdown(hero_text_html(str(st.session_state.get("display_name") or "")), unsafe_allow_html=True)
                with st.container(key="ks_cta"):
                    start_col, signup_col = st.columns(2)
                    with start_col:
                        if st.button("Get started", key="welcome_login", type="primary", use_container_width=True):
                            st.session_state.view = "Login"
                            st.rerun()
                    with signup_col:
                        if st.button("Create account", key="welcome_signup", use_container_width=True):
                            st.session_state.view = "Create Account"
                            st.rerun()
                    _social_buttons("welcome", welcome=True)
                st.markdown(trust_html(), unsafe_allow_html=True)
            with right:
                st.markdown(preview_html(), unsafe_allow_html=True)
        st.markdown(features_html(), unsafe_allow_html=True)
        st.markdown(footer_html(), unsafe_allow_html=True)


def _auth_links(prompt: str, label: str, key: str, view: str) -> None:
    st.markdown(f'<div class="ks-authprompt">{html.escape(prompt)}</div>', unsafe_allow_html=True)
    if st.button(label, key=key, type="tertiary"):
        st.session_state.pop("reset_email", None)
        st.session_state.view = view
        st.rerun()


def render_create_account() -> None:
    _show_social_error()
    with st.container(key="ks_authpage"):
        st.markdown(
            auth_header_html("Sign up", "Create your account", "A private space for your conversations. It only takes a minute."),
            unsafe_allow_html=True,
        )
        with st.form("create_account_form", clear_on_submit=False):
            display_name = st.text_input("Display name", max_chars=80, autocomplete="name", placeholder="What should we call you?")
            email = st.text_input("Email", max_chars=254, autocomplete="email", placeholder="you@example.com")
            password = st.text_input("Password", type="password", autocomplete="new-password", placeholder="Create a strong password", help="At least 10 characters with upper/lowercase, a number, and a special character.")
            confirm_password = st.text_input("Confirm password", type="password", autocomplete="new-password", placeholder="Type it once more")
            accepted = st.checkbox("I have read the privacy notice and understand this is an AI assistant.")
            submitted = st.form_submit_button("Create account", type="primary", use_container_width=True)
        if submitted:
            try:
                user = create_account(display_name, "", email, password, confirm_password, accepted)
                _set_authenticated(user)
                st.success("Your account is ready.")
                st.rerun()
            except (AccountValidationError, ValueError) as exc:
                st.error(str(exc))
            except Exception:
                LOGGER.exception("Account creation failed")
                st.error("We couldn't create the account right now. Please try again.")
        _social_buttons("signup", welcome=True)
        with st.container(key="ks_authlinks"):
            _auth_links("Already have an account?", "Log in", "create_to_login", "Login")
            if st.button("Back to welcome", key="create_back", type="tertiary"):
                st.session_state.view = "Welcome"
                st.rerun()


def render_login() -> None:
    _show_social_error()
    with st.container(key="ks_authpage"):
        st.markdown(
            auth_header_html("Login", "Welcome back", "Log in to pick up right where you left off."),
            unsafe_allow_html=True,
        )
        if st.session_state.pop("password_reset_done", False):
            st.success("Your password was updated. Log in with your new password.")
        with st.form("login_form", clear_on_submit=True):
            email = st.text_input("Email", autocomplete="email", placeholder="you@example.com")
            password = st.text_input("Password", type="password", autocomplete="current-password", placeholder="Your password")
            submitted = st.form_submit_button("Log in", type="primary", use_container_width=True)
        if submitted:
            locked = False
            try:
                user = authenticate_user(email, password)
            except AccountLockedError as exc:
                st.error(str(exc))
                user = None
                locked = True
            except Exception:
                LOGGER.exception("Login lookup failed")
                user = None
            if user:
                _set_authenticated(user)
                st.rerun()
            if not locked:
                st.error("Invalid email or password")
        _social_buttons("login", welcome=True)
        with st.container(key="ks_authlinks"):
            if st.button("Forgot password?", key="login_forgot", type="tertiary"):
                st.session_state.view = "Forgot Password"
                st.rerun()
            _auth_links("New here?", "Create account", "login_to_signup", "Create Account")
            if st.button("Back to welcome", key="login_back", type="tertiary"):
                st.session_state.view = "Welcome"
                st.rerun()


def render_forgot_password() -> None:
    with st.container(key="ks_authpage"):
        st.markdown(
            auth_header_html("Reset password", "Reset your password", "We'll get you back into your space."),
            unsafe_allow_html=True,
        )
        email = str(st.session_state.get("reset_email", ""))
        if not email:
            st.caption("Enter the email address on your account.")
            with st.form("forgot_password_form", clear_on_submit=False):
                typed = st.text_input("Email", max_chars=254, autocomplete="email", placeholder="you@example.com")
                submitted = st.form_submit_button("Continue", type="primary", use_container_width=True)
            if submitted:
                try:
                    if email_has_account(typed):
                        st.session_state.reset_email = typed.strip()
                        st.rerun()
                    st.error("No account exists with that email.")
                except AccountValidationError as exc:
                    st.error(str(exc))
                except Exception:
                    LOGGER.exception("Password reset lookup failed")
                    st.error("We couldn't process that request right now. Please try again.")
        else:
            st.caption(f"Choose a new password for {email}.")
            with st.form("reset_password_form", clear_on_submit=False):
                password = st.text_input("New password", type="password", autocomplete="new-password", placeholder="Create a strong password", help="At least 10 characters with upper/lowercase, a number, and a special character.")
                confirm_password = st.text_input("Confirm new password", type="password", autocomplete="new-password", placeholder="Type it once more")
                submitted = st.form_submit_button("Update password", type="primary", use_container_width=True)
            if submitted:
                try:
                    reset_password_for_email(email, password, confirm_password)
                    st.session_state.pop("reset_email", None)
                    st.session_state.view = "Login"
                    st.session_state.password_reset_done = True
                    st.rerun()
                except AccountValidationError as exc:
                    st.error(str(exc))
                except Exception:
                    LOGGER.exception("Password reset failed")
                    st.error("We couldn't update the password right now. Please try again.")
        st.caption("Signed up with Google or GitHub? You can keep using those buttons on the log in page.")
        with st.container(key="ks_authlinks"):
            if st.button("Back to log in", key="forgot_back", type="tertiary"):
                st.session_state.pop("reset_email", None)
                st.session_state.view = "Login"
                st.rerun()


def _ensure_conversation(user_id: str) -> list[dict[str, Any]]:
    conversations = storage.load_conversations(user_id)
    active_id = st.session_state.get("active_conversation_id")
    active = next((item for item in conversations if item.get("conversation_id") == active_id), None)
    if active is None and conversations:
        active = conversations[0]
        st.session_state.active_conversation_id = active.get("conversation_id")
    if active is None:
        active = storage.create_conversation(user_id)
        greeting = f"Hey {st.session_state.display_name}! I’m WithYou, your AI companion. Ask me anything, think out loud, or just chat. What’s on your mind?"
        storage.append_message(
            user_id,
            active["conversation_id"],
            {"message_id": uuid.uuid4().hex, "role": "assistant", "content": greeting, "created_at": _now()},
        )
        st.session_state.active_conversation_id = active["conversation_id"]
        conversations = storage.load_conversations(user_id)
    return conversations


def _create_chat(user_id: str) -> None:
    conversation = storage.create_conversation(user_id)
    greeting = f"Hey {st.session_state.display_name}! What’s on your mind today?"
    storage.append_message(
        user_id,
        conversation["conversation_id"],
        {"message_id": uuid.uuid4().hex, "role": "assistant", "content": greeting, "created_at": _now()},
    )
    st.session_state.active_conversation_id = conversation["conversation_id"]
    st.session_state.pop("pending_message_id", None)
    st.session_state.pop("last_model_error", None)
    st.rerun()


def _conversation_sidebar(user_id: str, conversations: list[dict[str, Any]]) -> None:
    with st.sidebar:
        st.markdown(BRAND_HTML, unsafe_allow_html=True)
        st.write("")
        if st.button("New chat", type="primary", icon=":material/add:", use_container_width=True):
            _create_chat(user_id)
        st.caption("RECENT CHATS")
        active_chat_id = st.session_state.get("active_conversation_id")
        with st.container(key="sidebar_chats"):
            for item in conversations:
                conversation_id = str(item.get("conversation_id", ""))
                title = safe_conversation_title(str(item.get("title", "Conversation")))
                is_active = conversation_id == active_chat_id
                key = f"ks_active_{conversation_id}" if is_active else f"conversation_{conversation_id}"
                icon = ":material/chat_bubble:" if is_active else ":material/chat_bubble_outline:"
                if st.button(title, key=key, icon=icon, use_container_width=True, help=title):
                    st.session_state.active_conversation_id = conversation_id
                    st.session_state.pop("pending_message_id", None)
                    st.session_state.pop("last_model_error", None)
                    st.rerun()
        st.divider()
        with st.expander("Manage current chat"):
            active_id = st.session_state.get("active_conversation_id")
            active = next((item for item in conversations if item.get("conversation_id") == active_id), None)
            if active:
                with st.form("rename_conversation_form"):
                    title = st.text_input("Conversation title", value=str(active.get("title", "")), max_chars=50)
                    if st.form_submit_button("Save title"):
                        if title.strip():
                            storage.rename_conversation(user_id, active_id, title)
                            st.rerun()
                        st.error("Enter a title first.")
                if st.button("Delete this chat", key="delete_current_chat"):
                    storage.delete_conversation(user_id, active_id)
                    st.session_state.pop("active_conversation_id", None)
                    st.session_state.pop("pending_message_id", None)
                    st.rerun()
        st.divider()
        view = st.radio("Account", ["Chat", "My Profile", "Settings"], key="authenticated_view", label_visibility="collapsed")
        if st.session_state.get("view") != view:
            st.session_state.view = view
            st.rerun()
        if st.button("Log out", use_container_width=True):
            _logout()


def _show_conversation(conversation: dict[str, Any], mode: str = "Normal") -> None:
    visible = messages_for_mode(conversation, mode)
    if mode == "Romantic" and not visible:
        st.caption("♥ This chat is just for the two of you. It stays here and never shows up in the other modes. Say hi!")
    for message in visible:
        role = str(message.get("role", "assistant"))
        if role not in {"user", "assistant"}:
            continue
        avatar = "🙂" if role == "user" else ("❤️" if mode == "Romantic" else "🌿")
        with st.chat_message(role, avatar=avatar):
            st.markdown(str(message.get("content", "")))
            attached = message.get("attachments")
            if isinstance(attached, list) and attached:
                names = ", ".join(
                    f"{'🖼️' if item.get('kind') == 'image' else '📄'} {item.get('name', 'file')}"
                    for item in attached if isinstance(item, dict)
                )
                st.caption(f"Attached: {names}")
            image_name = message.get("image")
            if role == "assistant" and isinstance(image_name, str):
                picture = storage.generated_image_bytes(str(st.session_state.get("user_id", "")), image_name)
                if picture:
                    st.image(picture)
                else:
                    st.caption("This picture is no longer available.")


def _reply_with_image(user_id: str, conversation_id: str, prompt: str, mode_tag: dict[str, str], avatar: str) -> None:
    """Create a picture (Cloudflare FLUX, AI Horde or Cosmos) and save it as the assistant's reply."""
    reply: dict[str, Any] = {"message_id": uuid.uuid4().hex, "role": "assistant", "created_at": _now(), **mode_tag}
    if not image_generation_configured():
        reply["content"] = (
            "I can't create pictures yet because no image service is set up. Add CLOUDFLARE_ACCOUNT_ID and "
            "CLOUDFLARE_API_TOKEN (or AI_HORDE_API_KEY), the same ones AI Book Studio uses, then ask again."
        )
    else:
        try:
            with st.chat_message("assistant", avatar=avatar):
                with st.spinner("Creating your image…"):
                    png = generate_image(prompt)
            reply["image"] = storage.save_generated_image(user_id, png)
            reply["content"] = "Here's the image I made for you."
        except ImageGenerationError as exc:
            st.session_state.last_model_error = str(exc)
            st.rerun()
        except Exception:
            LOGGER.exception("Image creation failed")
            st.session_state.last_model_error = "I couldn't create that image just now. Please try again."
            st.rerun()
    storage.append_message(user_id, conversation_id, reply)
    for key in ("pending_message_id", "pending_conversation_id", "pending_speak"):
        st.session_state.pop(key, None)
    st.rerun()


def _send_message(
    user_id: str, conversation: dict[str, Any], content: str, message_id: str | None = None, speak: bool = False,
    attachments: list[dict[str, str]] | None = None,
) -> None:
    error = validate_message(content)
    if error:
        st.error(error)
        return
    conversation_id = str(conversation["conversation_id"])
    mode = chat_mode(st.session_state.get("user_preferences", {}))
    mode_tag = {"mode": "Romantic"} if mode == "Romantic" else {}
    if message_id is None:
        message_id = uuid.uuid4().hex
        storage.append_message(
            user_id,
            conversation_id,
            {
                "message_id": message_id, "role": "user", "content": content.strip(), "created_at": _now(),
                **({"attachments": attachments} if attachments else {}), **mode_tag,
            },
        )
        if mode != "Romantic" and len(messages_for_mode(conversation, mode)) <= 1:
            storage.rename_conversation(user_id, conversation_id, safe_conversation_title(content))
    st.session_state.pending_message_id = message_id
    st.session_state.pending_conversation_id = conversation_id
    st.session_state.pending_speak = speak
    st.session_state.pop("last_model_error", None)

    latest = next(
        (item for item in storage.load_conversations(user_id) if item.get("conversation_id") == conversation_id),
        None,
    )
    if not latest:
        st.error("This conversation is no longer available. Start a new chat.")
        return
    if wants_image(content):
        _reply_with_image(user_id, conversation_id, content, mode_tag, "❤️" if mode == "Romantic" else "🌿")
    try:
        with st.chat_message("assistant", avatar="❤️" if mode == "Romantic" else "🌿"):
            with st.status("Typing…" if mode == "Romantic" else "WithYou is typing…", expanded=False) as status:
                response = st.write_stream(
                    stream_reply(latest, st.session_state.get("user_preferences", {}), _browser_timezone())
                )
                if not isinstance(response, str) or not response.strip():
                    raise RuntimeError("The assistant returned an empty response.")
                status.update(label="Reply ready", state="complete", expanded=False)
        storage.append_message(
            user_id,
            conversation_id,
            {"message_id": uuid.uuid4().hex, "role": "assistant", "content": response.strip(), "created_at": _now(), **mode_tag},
        )
        if speak:
            try:
                with st.spinner("Getting the voice ready…"):
                    audio = synthesize_speech(response, voice_for(st.session_state.get("user_preferences", {})))
                st.session_state.voice_reply = {"conversation_id": conversation_id, "audio": audio}
            except VoiceError as exc:
                st.session_state.voice_notice = str(exc)
            except Exception:
                LOGGER.exception("Spoken reply failed")
                st.session_state.voice_notice = "The reply is ready, but it could not be spoken. Please try again."
        st.session_state.pop("pending_message_id", None)
        st.session_state.pop("pending_conversation_id", None)
        st.session_state.pop("pending_speak", None)
        st.rerun()
    except Exception as exc:
        LOGGER.exception("Model reply failed")
        st.session_state.last_model_error = describe_model_error(exc)
        st.rerun()


def _browser_timezone() -> str | None:
    try:
        return str(st.context.timezone or "") or None
    except Exception:
        return None


def _greeting() -> str:
    tzinfo, _, _ = resolve_timezone(_browser_timezone())
    hour = datetime.now(tzinfo).hour
    if hour < 5:
        return "Still up"
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def _chat_header(conversation: dict[str, Any], mode: str) -> None:
    first_name = html.escape(str(st.session_state.get("display_name", "")).strip().split(" ")[0])
    title = html.escape(safe_conversation_title(str(conversation.get("title", "Conversation"))))
    hello = f"{_greeting()}, {first_name}" if first_name else _greeting()
    romantic = mode == "Romantic"
    chip = ""
    tagline = "Talk it out, ask away, or just say hi. WithYou is your AI companion."
    if romantic:
        chip = '<span class="ks-chip rose">♥ Romantic mode</span>'
        tagline = "Talk to me like you would to someone special."
    elif mode == "English correction":
        chip = '<span class="ks-chip">✏ English correction</span>'
        tagline = "Send a message: your English is corrected first, then your question is answered."
    flag = '<div class="ks-romantic-flag"></div>' if romantic else ""
    st.markdown(
        f'{flag}<div class="ks-chat-head"><div><div class="ks-eyebrow">{title}</div><h2>{hello}</h2>'
        f'<p>{tagline}</p></div>'
        f'{chip}</div>',
        unsafe_allow_html=True,
    )


def _mode_selector(user_id: str) -> str:
    preferences = dict(st.session_state.get("user_preferences", {}))
    current = chat_mode(preferences)
    chosen = st.radio(
        "Chat mode",
        MODES,
        index=MODES.index(current),
        key=f"chat_mode_{user_id}",
        horizontal=True,
        help="Normal: AI assistant. Romantic: a loving girlfriend or boyfriend. English correction: fixes your sentence first, then answers.",
    )
    if chosen != current:
        topics = [str(topic) for topic in preferences.get("topics", []) if isinstance(topic, str) and topic != "Romantic"]
        preferences["mode"] = chosen
        preferences["topics"] = topics
        if storage.update_user_preferences(user_id, preferences):
            st.session_state.user_preferences = preferences
            return chosen
        return current
    return current


def _voice_message(user_id: str, conversation: dict[str, Any], audio: Any, speak: bool) -> None:
    """Mic in the message bar: speech -> text (Nemotron omni / Whisper) -> normal chat reply -> spoken reply (Groq)."""
    try:
        with st.spinner("Listening…"):
            text = transcribe_audio(audio.getvalue())
    except VoiceError as exc:
        st.error(str(exc))
        return
    if not text:
        st.warning("I couldn't hear anything. Please try again, a little closer to the mic.")
        return
    with st.chat_message("user", avatar="🙂"):
        st.markdown(f"🎤 {text}")
    _send_message(user_id, conversation, text, speak=speak)


def _file_message(user_id: str, conversation: dict[str, Any], text: str, files: list[Any], speak: bool) -> None:
    """Uploads: documents are read locally and images by Nemotron 3 Nano Omni, then the main model answers."""
    with st.chat_message("user", avatar="🙂"):
        st.markdown(text or DEFAULT_QUESTION)
        st.caption("Attached: " + ", ".join(str(getattr(item, "name", "file")) for item in files[:MAX_FILES]))
    with st.spinner("Reading your file…"):
        attachments, problems = process_uploads(files, text)
    for problem in problems:
        st.warning(problem)
    if not attachments:
        return
    _send_message(user_id, conversation, text or DEFAULT_QUESTION, speak=speak, attachments=attachments)


def render_chat(user_id: str) -> None:
    conversations = _ensure_conversation(user_id)
    _conversation_sidebar(user_id, conversations)
    active_id = st.session_state.get("active_conversation_id")
    conversation = next((item for item in conversations if item.get("conversation_id") == active_id), None)
    if conversation is None:
        st.info("Choose a chat or start a new one.")
        return
    mode = _mode_selector(user_id)
    _chat_header(conversation, mode)
    _show_conversation(conversation, mode)
    notice = st.session_state.pop("voice_notice", None)
    if notice:
        st.warning(notice)
    speak = st.toggle("🔊 Speak replies", key="speak_voice_replies")
    voice_reply = st.session_state.pop("voice_reply", None)
    if voice_reply and voice_reply.get("conversation_id") == active_id:
        st.audio(voice_reply["audio"], format="audio/wav", autoplay=True)
    pending_id = st.session_state.get("pending_message_id")
    pending_conversation = st.session_state.get("pending_conversation_id")
    if pending_id and pending_conversation == active_id:
        if st.session_state.get("last_model_error"):
            st.error(st.session_state.last_model_error)
        if st.button("Retry response", type="primary"):
            pending = next((item for item in conversation.get("messages", []) if item.get("message_id") == pending_id), None)
            if pending:
                _send_message(
                    user_id, conversation, str(pending.get("content", "")), message_id=pending_id,
                    speak=bool(st.session_state.get("pending_speak", False)),
                )
            else:
                st.error("The message to retry could not be found.")
        return

    entry = st.chat_input(
        "Type a message, attach a file, or tap the mic…",
        max_chars=8_000,
        accept_file="multiple",
        file_type=ACCEPTED_TYPES,
        max_upload_size=MAX_FILE_MB,
        accept_audio=True,
        audio_sample_rate=16000,
    )
    if entry is None:
        return
    audio = getattr(entry, "audio", None)
    text = str(getattr(entry, "text", "") or "").strip()
    files = list(getattr(entry, "files", None) or [])
    if files:
        _file_message(user_id, conversation, text, files, speak)
    elif audio is not None and not text:
        _voice_message(user_id, conversation, audio, speak)
    elif text:
        _send_message(user_id, conversation, text, speak=speak)


def render_profile(user_id: str) -> None:
    conversations = storage.load_conversations(user_id)
    user = storage.get_user_by_id(user_id) or {}
    st.title("My Profile")
    st.markdown('<div class="ks-card">Your account details stay separate from your chat content.</div>', unsafe_allow_html=True)
    st.write("")
    st.text_input("Display name", value=str(user.get("display_name", "")), disabled=True)
    st.text_input("Email", value=str(user.get("email", "")), disabled=True)
    st.caption(f"{len(conversations)} conversation(s) saved to this app’s local data folder.")
    st.markdown('<div class="ks-note">The app stores account and conversation data locally on the server where it runs. Use it only on a device or deployment you trust.</div>', unsafe_allow_html=True)
    if conversations:
        active = next((item for item in conversations if item.get("conversation_id") == st.session_state.get("active_conversation_id")), conversations[0])
        st.download_button(
            "Export selected conversation as Markdown",
            storage.export_conversation_as_markdown({**active, "messages": messages_for_mode(active, "Normal")}),
            file_name="withyou-conversation.md",
            mime="text/markdown",
            use_container_width=True,
        )


def render_settings(user_id: str) -> None:
    st.title("Settings")
    preferences = dict(st.session_state.get("user_preferences", {}))
    with st.form("preferences_form"):
        tone_options = ["Warm", "Direct", "Encouraging", "Neutral"]
        length_options = ["Brief", "Balanced", "Detailed"]
        tone = st.selectbox("Reply tone", tone_options, index=tone_options.index(preferences.get("tone", "Warm")) if preferences.get("tone") in tone_options else 0)
        response_length = st.selectbox("Reply length", length_options, index=length_options.index(preferences.get("response_length", "Balanced")) if preferences.get("response_length") in length_options else 1)
        topic_options = ["Planning", "Learning", "Work", "Wellbeing", "Writing", "Everyday questions"]
        topics = st.multiselect("Topics you often ask about", topic_options, default=[value for value in preferences.get("topics", []) if value in topic_options])
        mode_value = chat_mode(preferences)
        mode = st.selectbox("Chat mode", MODES, index=MODES.index(mode_value), help="Romantic: replies like a loving girlfriend or boyfriend. English correction: your sentence is corrected first, then answered.")
        partner_options = ["Auto", "Girlfriend", "Boyfriend"]
        partner_value = preferences.get("partner", "Auto")
        partner = st.selectbox("Romantic mode partner", partner_options, index=partner_options.index(partner_value) if partner_value in partner_options else 0, help="Auto picks the opposite of what you say about yourself.")
        city = st.text_input("Your city (optional)", value=str(preferences.get("city", "")), max_chars=60, help="Used only to look up the weather when you ask about it.")
        saved = st.form_submit_button("Save preferences", type="primary")
    if saved:
        clean = {"tone": tone, "response_length": response_length, "topics": topics, "mode": mode, "partner": partner, "city": city.strip()}
        if storage.update_user_preferences(user_id, clean):
            st.session_state.user_preferences = clean
            st.session_state.pop(f"chat_mode_{user_id}", None)
            st.success("Preferences saved.")
    st.divider()
    st.subheader("Privacy and account data")
    st.caption("Deleting your account permanently removes its local account record and saved conversations.")
    with st.form("delete_account_form"):
        confirm_email = st.text_input("Type your email address to confirm deletion")
        confirm_delete = st.checkbox("I understand this permanently deletes my account and conversations.")
        delete = st.form_submit_button("Delete my account", type="secondary")
    if delete:
        if confirm_email.strip().lower() != str(st.session_state.get("email", "")).lower() or not confirm_delete:
            st.error("Enter your email address and select the confirmation box.")
        elif storage.delete_all_user_data(user_id):
            _logout()
        else:
            st.error("We couldn't delete the account. Please try again.")


def _handle_social_callbacks() -> None:
    if st.query_params.get("code") is not None or st.query_params.get("state") is not None:
        try:
            identity = complete_github_callback()
            if identity:
                user = authenticate_social_user(**identity)
                _set_authenticated(user)
        except (SocialLoginError, AccountValidationError, ValueError) as exc:
            st.session_state.social_login_error = str(exc)
        except Exception:
            LOGGER.exception("GitHub sign-in failed")
            st.session_state.social_login_error = "GitHub sign-in could not be completed. Please try again."
        finally:
            st.query_params.clear()
        st.rerun()

    if not st.session_state.get("authenticated"):
        try:
            identity = google_identity()
            if identity:
                user = authenticate_social_user(**identity)
                _set_authenticated(user)
                st.rerun()
        except (SocialLoginError, AccountValidationError, ValueError) as exc:
            st.session_state.social_login_error = str(exc)
            try:
                st.logout()
            except Exception:
                st.rerun()
        except Exception:
            LOGGER.exception("Google sign-in failed")
            st.session_state.social_login_error = "Google sign-in could not be completed. Please try again."
            try:
                st.logout()
            except Exception:
                st.rerun()


def render_app() -> None:
    apply_styles()
    _notice_storage_issues()
    _handle_social_callbacks()
    if not st.session_state.get("authenticated"):
        st.session_state.view = st.session_state.get("view", "Welcome")
        view = st.session_state.view
        if view == "Create Account":
            render_create_account()
        elif view == "Login":
            render_login()
        elif view == "Forgot Password":
            render_forgot_password()
        else:
            render_welcome()
        return

    user_id = str(st.session_state.get("user_id", ""))
    account = storage.get_user_by_id(user_id)
    if not account or not account.get("active"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.warning("Your session is no longer active. Please log in again.")
        render_welcome()
        return
    st.session_state.user_preferences = account.get("preferences", {})
    view = st.session_state.get("view", "Chat")
    if view == "My Profile":
        conversations = storage.load_conversations(user_id)
        _conversation_sidebar(user_id, conversations)
        render_profile(user_id)
    elif view == "Settings":
        conversations = storage.load_conversations(user_id)
        _conversation_sidebar(user_id, conversations)
        render_settings(user_id)
    else:
        render_chat(user_id)
