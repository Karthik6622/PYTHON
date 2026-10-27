"""KindSpace Personal Assistant Streamlit entry point."""

from __future__ import annotations

import logging
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.storage import initialize_storage
from src.ui import render_app


APP_DIR = Path(__file__).resolve().parent
load_dotenv(APP_DIR / ".env", override=False)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    st.set_page_config(page_title="KindSpace Personal Assistant", page_icon="🌿", layout="centered")
    try:
        initialize_storage()
    except Exception:
        logging.getLogger("kindspace.app").exception("Could not initialize local storage")
        st.error("KindSpace could not prepare its local data folder. Check folder permissions and try again.")
        st.stop()
    render_app()


if __name__ == "__main__":
    main()
