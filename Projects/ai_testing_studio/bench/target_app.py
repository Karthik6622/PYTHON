"""Benchmark target: a small Streamlit app shaped like the real "PersonalPartner" app (landing page, in-memory sign-in,
sidebar radio navigation between signed-in views). Several views deliberately have a PRIMARY button, so they all share
data-testid="stBaseButton-primary".

Run: streamlit run bench/target_app.py --server.port 8611 --server.headless true
"""

from __future__ import annotations

import os
import random
import time

import streamlit as st

USER = "[REDACTED_EMAIL_ADDRESS_1]"
PASSWORD = "Secret123"
# BENCH_HARD=1: the application changed after discovery, like a real app between releases: every rerun is slower (Streamlit
# Cloud latency), the Chat and Profile views show an extra primary button ("New chat") above the real one, and the profile
# button was renamed.
HARD = os.environ.get("BENCH_HARD") == "1"

st.set_page_config(page_title="PersonalPartner", layout="centered")
if HARD:
    time.sleep(random.uniform(0.4, 1.2))

state = st.session_state
state.setdefault("signed_in", False)
state.setdefault("screen", "landing")  # landing | login


def landing() -> None:
    st.title("WithYou")
    st.write("A personal AI companion")
    if state.screen == "login":
        login_form()
        return
    left, right = st.columns(2)
    if left.button("Get started", type="primary"):
        state.screen = "login"
        st.rerun()
    if right.button("Create account", type="secondary"):
        st.info("Account creation is coming soon")


def login_form() -> None:
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Log in", type="primary"):
        if email.strip() == USER and password == PASSWORD:
            state.signed_in = True
            state.screen = "landing"
            st.rerun()
        else:
            st.error("Invalid email or password")


def chat() -> None:
    st.header("Chat")
    if HARD:
        st.button("New chat", type="primary")
    message = st.text_input("Message")
    if st.button("Send", type="primary"):
        st.markdown(f"You: {message}")
        st.success("Message sent")


def profile() -> None:
    st.header("Profile")
    if HARD:
        st.button("New chat", type="primary", key="profile_new_chat")
    st.text_input("Display name")
    st.text_input("City")
    if st.button("Save your profile" if HARD else "Save profile", type="primary"):
        st.success("Profile saved")


def settings() -> None:
    st.header("Settings")
    st.checkbox("Email notifications")
    st.selectbox("Theme", ["Light", "Dark"])
    if st.button("Save settings", type="primary"):
        st.success("Settings saved")


if not state.signed_in:
    landing()
else:
    choice = st.sidebar.radio("Navigate", ["Chat", "Profile", "Settings"])
    if st.sidebar.button("Sign out"):
        state.signed_in = False
        state.screen = "landing"
        st.rerun()
    {"Chat": chat, "Profile": profile, "Settings": settings}[choice]()
