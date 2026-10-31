"""Discovery page: run website analysis, inspect pages and the locator repository, manage authentication sessions."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from ats.config import get_settings
from ats.services import Services
from ats.ui.session import require_project, safe, show_notices