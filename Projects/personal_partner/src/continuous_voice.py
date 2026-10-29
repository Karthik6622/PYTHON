"""Continuous voice chat: a browser microphone component that listens hands-free.

The component ends each sentence after 3 seconds of silence, sends it to the server as WAV, and plays replies
sent back from the server. It stays quiet while a reply is being made and while that reply plays.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).with_name("continuous_voice_component")
_component = components.declare_component("withyou_continuous_voice", path=str(_COMPONENT_DIR))


def continuous_mic(*, reply_id: int, reply_audio: str, key: str) -> dict[str, Any] | None:
    """Render the mic component. Returns {"id", "audio"} (base64 WAV) when a sentence finished, else None.

    A new reply_id with reply_audio plays that reply once. An empty reply_audio just releases the mic to listen again.
    """
    value = _component(reply_id=reply_id, reply_audio=reply_audio, key=key, default=None)
    return value if isinstance(value, dict) else None
