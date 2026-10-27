"""Responsive Streamlit views for KindSpace."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import streamlit as st

from . import storage
from .assistant import stream_reply
from .auth import AccountValidationError, authenticate_social_user, authenticate_user, create_account, public_account
from .model_client import ModelConfigurationError
from .social_auth import (
    SocialLoginError,
    complete_github_callback,
    github_authorization_url,
    github_is_configured,
    google_identity,
    google_is_configured,
)
from .validation import safe_conversation_title, validate_message


LOGGER = logging.getLogger("kindspace.ui")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
          color-scheme: light;
          --ks-ink: #173238; --ks-muted: #536a6d; --ks-line: #d5e1de;
          --ks-paper: #f5f8f6; --ks-panel: #ffffff; --ks-teal: #176b61;
          --ks-teal-dark: #10564e; --ks-soft: #e4f1ed; --ks-peach: #fff0e6;
        }
        html, body, [class*="css"] { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
        .stApp { background: var(--ks-paper); color: var(--ks-ink); }
        .block-container { width: 100%; max-width: 980px; padding: clamp(1rem, 4vw, 2.5rem) clamp(.85rem, 4vw, 2rem) 2.5rem; }
        h1, h2, h3 { color: var(--ks-ink); letter-spacing: -.025em; }
        p, label, [data-testid="stCaptionContainer"] { color: var(--ks-muted); }
        [data-testid="stSidebar"] { background: #edf4f1; border-right: 1px solid var(--ks-line); }
        [data-testid="stSidebar"] .block-container { padding: 1.25rem .9rem; }
        [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea,
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
        [data-testid="stMultiSelect"] div[data-baseweb="select"] > div {
          border-radius: 12px; border-color: #bdceca; background: #fff; color: var(--ks-ink);
        }
        [data-testid="stTextInput"] input:focus, [data-testid="stTextArea"] textarea:focus,
        [data-testid="stSelectbox"] div[data-baseweb="select"]:focus-within {
          border-color: var(--ks-teal); box-shadow: 0 0 0 2px rgba(23,107,97,.18);
        }
        .stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] button {
          min-height: 2.75rem; border-radius: 12px; border: 1px solid var(--ks-line);
          color: var(--ks-ink); background: #fff; font-weight: 600; transition: background-color .15s ease, border-color .15s ease;
        }
        .stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] {
          background: var(--ks-teal); border-color: var(--ks-teal); color: #fff;
        }
        [data-testid="stBaseButton-primary"], [data-testid="stFormSubmitButton"] [data-testid="stBaseButton-primary"] {
          background: #145d54 !important; border-color: #145d54 !important; color: #fff !important;
        }
        [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-link"] {
          background: #fff !important; border: 1px solid #78918b !important; color: #173238 !important;
        }
        [data-testid="stBaseButton-secondary"]:hover, [data-testid="stBaseButton-link"]:hover {
          background: #e4f1ed !important; border-color: #145d54 !important; color: #103f3a !important;
        }
        [data-testid="stBaseButton-primary"]:hover {
          background: #0c4d46 !important; border-color: #0c4d46 !important; color: #fff !important;
        }
        [data-testid="stBaseButton-primary"]:disabled, [data-testid="stBaseButton-secondary"]:disabled {
          background: #e2e8e6 !important; border-color: #c3ceca !important; color: #52615d !important; opacity: 1 !important;
        }
        .stButton > button[kind="primary"]:hover, [data-testid="stFormSubmitButton"] button[kind="primary"]:hover {
          background: var(--ks-teal-dark); border-color: var(--ks-teal-dark); color: #fff;
        }
        .stButton > button:focus-visible, .stDownloadButton > button:focus-visible,
        [data-testid="stFormSubmitButton"] button:focus-visible { outline: 3px solid #e09665; outline-offset: 2px; }
        [data-testid="stChatMessage"] { padding: .75rem 0; }
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { line-height: 1.65; }
        [data-testid="stChatInput"] textarea { border-radius: 16px; min-height: 3.2rem; }
        .ks-brand { color: var(--ks-teal-dark); font-weight: 800; font-size: 1.05rem; letter-spacing: -.02em; }
        .ks-hero { padding: clamp(1.2rem, 4vw, 2.6rem); border: 1px solid var(--ks-line); border-radius: 24px; background: linear-gradient(135deg, #fff 8%, #edf6f2 100%); }
        .ks-eyebrow { color: var(--ks-teal-dark); font-weight: 700; font-size: .78rem; letter-spacing: .1em; text-transform: uppercase; }
        .ks-note { padding: .85rem 1rem; border-radius: 12px; border: 1px solid #f0d6c6; background: var(--ks-peach); color: #593f31; }
        .ks-card { padding: 1rem; border: 1px solid var(--ks-line); border-radius: 16px; background: var(--ks-panel); }
        @media (max-width: 640px) {
          [data-testid="stSidebar"] { min-width: 0; }
          [data-testid="stSidebar"] .block-container { padding: .8rem .65rem; }
          .ks-hero { border-radius: 18px; }
          [data-testid="stHorizontalBlock"] { gap: .65rem; }
          [data-testid="stChatMessage"] { padding: .5rem 0; }
          .stButton > button, [data-testid="stFormSubmitButton"] button { min-height: 2.9rem; }
        }
        @media (prefers-reduced-motion: reduce) {
          *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; animation-duration: .01ms !important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _set_authenticated(user: dict[str, Any]) -> None:
    public = public_account(user)
    st.session_state.authenticated = True
    st.session_state.user_id = public["user_id"]
    st.session_state.username = public["username"]
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
        "authenticated", "user_id", "username", "display_name", "user_preferences",
        "active_conversation_id", "pending_message_id", "pending_conversation_id",
        "last_model_error", "authenticated_view", "view",
    ):
        st.session_state.pop(key, None)
    st.session_state.view = "Welcome"
    st.rerun()


def _notice_storage_issues() -> None:
    for notice in storage.consume_storage_notices():
        st.warning(notice)


def _social_buttons(prefix: str) -> None:
    st.caption("Or continue with")
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
    if not google_is_configured() or not github_is_configured():
        st.caption("To enable social sign-up, add the provider credentials from `.streamlit/secrets.toml.example` to your private secrets file.")


def _show_social_error() -> None:
    message = st.session_state.pop("social_login_error", None)
    if message:
        st.error(message)


def render_welcome() -> None:
    _show_social_error()
    st.markdown('<div class="ks-brand">KindSpace</div>', unsafe_allow_html=True)
    st.write("")
    st.markdown(
        """
        <section class="ks-hero">
          <div class="ks-eyebrow">A little space to think things through</div>
          <h1>Meet you where you are.</h1>
          <p>KindSpace is a private AI assistant for everyday questions, reflection, planning, and encouragement.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.write("")
    left, right = st.columns(2)
    with left:
        if st.button("Log in", type="primary", use_container_width=True):
            st.session_state.view = "Login"
            st.rerun()
    with right:
        if st.button("Create account", use_container_width=True):
            st.session_state.view = "Create Account"
            st.rerun()
    st.markdown(
        '<div class="ks-note">KindSpace is an AI assistant, not a human, therapist, doctor, or emergency service. Your account and conversations are stored locally on this server.</div>',
        unsafe_allow_html=True,
    )


def render_create_account() -> None:
    _show_social_error()
    st.title("Create your account")
    st.caption("A private space for your conversations.")
    _social_buttons("signup")
    st.divider()
    with st.form("create_account_form", clear_on_submit=False):
        display_name = st.text_input("Display name", max_chars=80, autocomplete="name")
        username = st.text_input("Username", max_chars=30, autocomplete="username", help="3–30 characters: letters, numbers, periods, underscores.")
        email = st.text_input("Email", max_chars=254, autocomplete="email")
        password = st.text_input("Password", type="password", autocomplete="new-password", help="At least 10 characters with upper/lowercase, a number, and a special character.")
        confirm_password = st.text_input("Confirm password", type="password", autocomplete="new-password")
        accepted = st.checkbox("I have read the privacy notice and understand this is an AI assistant.")
        submitted = st.form_submit_button("Create account", type="primary", use_container_width=True)
    if submitted:
        try:
            user = create_account(display_name, username, email, password, confirm_password, accepted)
            _set_authenticated(user)
            st.success("Your account is ready.")
            st.rerun()
        except (AccountValidationError, ValueError) as exc:
            st.error(str(exc))
        except Exception:
            LOGGER.exception("Account creation failed")
            st.error("We couldn't create the account right now. Please try again.")
    if st.button("Back to welcome", key="create_back"):
        st.session_state.view = "Welcome"
        st.rerun()


def render_login() -> None:
    _show_social_error()
    st.title("Welcome back")
    _social_buttons("login")
    st.divider()
    with st.form("login_form", clear_on_submit=True):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Log in", type="primary", use_container_width=True)
    if submitted:
        try:
            user = authenticate_user(username, password)
        except Exception:
            LOGGER.exception("Login lookup failed")
            user = None
        if user:
            _set_authenticated(user)
            st.rerun()
        st.error("Invalid username or password")
    if st.button("Back to welcome", key="login_back"):
        st.session_state.view = "Welcome"
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
        greeting = f"Hi {st.session_state.display_name}, I’m KindSpace, an AI assistant. I’m here to help you think things through, plan, or explore a question. What’s on your mind?"
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
    greeting = f"Hi {st.session_state.display_name}, what would you like to talk through today?"
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
        st.markdown('<div class="ks-brand">KindSpace</div>', unsafe_allow_html=True)
        if st.button("＋  New chat", type="primary", use_container_width=True):
            _create_chat(user_id)
        st.caption("YOUR CONVERSATIONS")
        for item in conversations:
            conversation_id = str(item.get("conversation_id", ""))
            title = safe_conversation_title(str(item.get("title", "Conversation")))
            if st.button(title, key=f"conversation_{conversation_id}", use_container_width=True, help=title):
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


def _show_conversation(conversation: dict[str, Any]) -> None:
    for message in conversation.get("messages", []):
        role = str(message.get("role", "assistant"))
        if role not in {"user", "assistant"}:
            continue
        with st.chat_message(role, avatar="🙂" if role == "user" else "🌿"):
            st.markdown(str(message.get("content", "")))


def _send_message(user_id: str, conversation: dict[str, Any], content: str, message_id: str | None = None) -> None:
    error = validate_message(content)
    if error:
        st.error(error)
        return
    conversation_id = str(conversation["conversation_id"])
    if message_id is None:
        message_id = uuid.uuid4().hex
        storage.append_message(
            user_id,
            conversation_id,
            {"message_id": message_id, "role": "user", "content": content.strip(), "created_at": _now()},
        )
        if len(conversation.get("messages", [])) <= 1:
            storage.rename_conversation(user_id, conversation_id, safe_conversation_title(content))
    st.session_state.pending_message_id = message_id
    st.session_state.pending_conversation_id = conversation_id
    st.session_state.pop("last_model_error", None)

    latest = next(
        (item for item in storage.load_conversations(user_id) if item.get("conversation_id") == conversation_id),
        None,
    )
    if not latest:
        st.error("This conversation is no longer available. Start a new chat.")
        return
    try:
        with st.chat_message("assistant", avatar="🌿"):
            with st.status("KindSpace is thinking…", expanded=False) as status:
                response = st.write_stream(stream_reply(latest, st.session_state.get("user_preferences", {})))
                if not isinstance(response, str) or not response.strip():
                    raise RuntimeError("The assistant returned an empty response.")
                status.update(label="Reply ready", state="complete", expanded=False)
        storage.append_message(
            user_id,
            conversation_id,
            {"message_id": uuid.uuid4().hex, "role": "assistant", "content": response.strip(), "created_at": _now()},
        )
        st.session_state.pop("pending_message_id", None)
        st.session_state.pop("pending_conversation_id", None)
        st.rerun()
    except Exception as exc:
        LOGGER.exception("Model reply failed")
        if isinstance(exc, ModelConfigurationError):
            message = str(exc)
        else:
            message = "The assistant couldn't reply just now. Check your model settings or try again."
        st.session_state.last_model_error = message
        st.rerun()


def render_chat(user_id: str) -> None:
    conversations = _ensure_conversation(user_id)
    _conversation_sidebar(user_id, conversations)
    active_id = st.session_state.get("active_conversation_id")
    conversation = next((item for item in conversations if item.get("conversation_id") == active_id), None)
    if conversation is None:
        st.info("Choose a chat or start a new one.")
        return
    st.title("Your space")
    st.caption("A private conversation with an AI assistant.")
    _show_conversation(conversation)
    pending_id = st.session_state.get("pending_message_id")
    pending_conversation = st.session_state.get("pending_conversation_id")
    if pending_id and pending_conversation == active_id:
        if st.session_state.get("last_model_error"):
            st.error(st.session_state.last_model_error)
        if st.button("Retry response", type="primary"):
            pending = next((item for item in conversation.get("messages", []) if item.get("message_id") == pending_id), None)
            if pending:
                _send_message(user_id, conversation, str(pending.get("content", "")), message_id=pending_id)
            else:
                st.error("The message to retry could not be found.")
        return

    prompt = st.chat_input("Write what’s on your mind…", max_chars=8_000)
    if prompt:
        _send_message(user_id, conversation, prompt)


def render_profile(user_id: str) -> None:
    conversations = storage.load_conversations(user_id)
    user = storage.get_user_by_id(user_id) or {}
    st.title("My Profile")
    st.markdown('<div class="ks-card">Your account details stay separate from your chat content.</div>', unsafe_allow_html=True)
    st.write("")
    st.text_input("Display name", value=str(user.get("display_name", "")), disabled=True)
    st.text_input("Username", value=str(user.get("username", "")), disabled=True)
    st.caption(f"{len(conversations)} conversation(s) saved to this app’s local data folder.")
    st.markdown('<div class="ks-note">The app stores account and conversation data locally on the server where it runs. Use it only on a device or deployment you trust.</div>', unsafe_allow_html=True)
    if conversations:
        active = next((item for item in conversations if item.get("conversation_id") == st.session_state.get("active_conversation_id")), conversations[0])
        st.download_button(
            "Export selected conversation as Markdown",
            storage.export_conversation_as_markdown(active),
            file_name="kindspace-conversation.md",
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
        topics = st.multiselect("Topics you often ask about", ["Planning", "Learning", "Work", "Wellbeing", "Writing", "Everyday questions"], default=[value for value in preferences.get("topics", []) if value in {"Planning", "Learning", "Work", "Wellbeing", "Writing", "Everyday questions"}])
        saved = st.form_submit_button("Save preferences", type="primary")
    if saved:
        clean = {"tone": tone, "response_length": response_length, "topics": topics}
        if storage.update_user_preferences(user_id, clean):
            st.session_state.user_preferences = clean
            st.success("Preferences saved.")
    st.divider()
    st.subheader("Privacy and account data")
    st.caption("Deleting your account permanently removes its local account record and saved conversations.")
    with st.form("delete_account_form"):
        confirm_username = st.text_input("Type your username to confirm deletion")
        confirm_delete = st.checkbox("I understand this permanently deletes my account and conversations.")
        delete = st.form_submit_button("Delete my account", type="secondary")
    if delete:
        if confirm_username.strip().lower() != st.session_state.username.lower() or not confirm_delete:
            st.error("Enter your username and select the confirmation box.")
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
