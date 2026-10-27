"""Responsive Streamlit views for KindSpace."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import streamlit as st

from . import storage
from .assistant import stream_reply
from .auth import (
    AccountLockedError,
    AccountValidationError,
    authenticate_social_user,
    authenticate_user,
    create_account,
    password_reset_token_is_valid,
    public_account,
    request_password_reset,
    reset_password,
)
from .mailer import email_service_problem
from .model_client import ModelConfigurationError
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
from .styles import APP_CSS, WELCOME_HERO_HTML


LOGGER = logging.getLogger("kindspace.ui")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def apply_styles() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)


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
    st.markdown('<div class="ks-brand">KindSpace</div>', unsafe_allow_html=True)
    st.write("")
    st.markdown(WELCOME_HERO_HTML, unsafe_allow_html=True)
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
        email = st.text_input("Email", max_chars=254, autocomplete="email")
        password = st.text_input("Password", type="password", autocomplete="new-password", help="At least 10 characters with upper/lowercase, a number, and a special character.")
        confirm_password = st.text_input("Confirm password", type="password", autocomplete="new-password")
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
    if st.button("Back to welcome", key="create_back"):
        st.session_state.view = "Welcome"
        st.rerun()


def render_login() -> None:
    _show_social_error()
    st.title("Welcome back")
    if st.session_state.pop("password_reset_done", False):
        st.success("Your password was updated. Log in with your new password.")
    _social_buttons("login")
    st.divider()
    with st.form("login_form", clear_on_submit=True):
        email = st.text_input("Email", autocomplete="email")
        password = st.text_input("Password", type="password", autocomplete="current-password")
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
    if st.button("Forgot password?", key="login_forgot"):
        st.session_state.view = "Forgot Password"
        st.rerun()
    if st.button("Back to welcome", key="login_back"):
        st.session_state.view = "Welcome"
        st.rerun()


def render_forgot_password() -> None:
    st.title("Reset your password")
    st.caption("Enter the email address on your account and we'll send you a reset link.")
    problem = email_service_problem()
    if problem:
        st.error(problem)
    with st.form("forgot_password_form", clear_on_submit=False):
        email = st.text_input("Email", max_chars=254, autocomplete="email")
        submitted = st.form_submit_button("Send reset link", type="primary", use_container_width=True, disabled=problem is not None)
    if submitted:
        try:
            request_password_reset(email)
            st.success("If an account exists for that email, a reset link is on its way. It expires in 30 minutes.")
        except AccountValidationError as exc:
            st.error(str(exc))
        except Exception:
            LOGGER.exception("Password reset request failed")
            st.error("We couldn't process that request right now. Please try again.")
    st.caption("Signed up with Google or GitHub? You can keep using those buttons on the log in page.")
    if st.button("Back to log in", key="forgot_back"):
        st.session_state.view = "Login"
        st.rerun()


def render_reset_password() -> None:
    token = str(st.session_state.get("reset_token", ""))
    st.title("Choose a new password")
    if not password_reset_token_is_valid(token):
        st.error("This reset link is invalid or has expired. Request a new one.")
        if st.button("Request a new link", type="primary", key="reset_request_new"):
            st.session_state.pop("reset_token", None)
            st.session_state.view = "Forgot Password"
            st.rerun()
        return
    with st.form("reset_password_form", clear_on_submit=False):
        password = st.text_input("New password", type="password", autocomplete="new-password", help="At least 10 characters with upper/lowercase, a number, and a special character.")
        confirm_password = st.text_input("Confirm new password", type="password", autocomplete="new-password")
        submitted = st.form_submit_button("Update password", type="primary", use_container_width=True)
    if submitted:
        try:
            reset_password(token, password, confirm_password)
            st.session_state.pop("reset_token", None)
            st.session_state.view = "Login"
            st.session_state.password_reset_done = True
            st.rerun()
        except AccountValidationError as exc:
            st.error(str(exc))
        except Exception:
            LOGGER.exception("Password reset failed")
            st.error("We couldn't update the password right now. Please try again.")


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
    st.text_input("Email", value=str(user.get("email", "")), disabled=True)
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


def _handle_reset_link() -> None:
    """Move a reset token from the URL into the session so it isn't left in the address bar."""
    token = st.query_params.get("reset_token")
    if token is None:
        return
    st.query_params.clear()
    if not st.session_state.get("authenticated"):
        st.session_state.reset_token = str(token)[:200]
        st.session_state.view = "Reset Password"


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
    _handle_reset_link()
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
        elif view == "Reset Password":
            render_reset_password()
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
