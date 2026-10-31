"""Structured, secret-masked logging to ``logs/studio.log`` (rotating) and the console."""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone

from ats.config import ROOT_DIR
from ats.security import mask

_CONFIGURED = False


class MaskingJsonFormatter(logging.Formatter):
    """One JSON object per line; the message and any exception text are masked before they are written."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": mask(record.getMessage()),
        }
        extra = getattr(record, "ctx", None)
        if isinstance(extra, dict):
            payload["ctx"] = {key: mask(str(value)) for key, value in extra.items()}
        if record.exc_info:
            payload["exception"] = mask(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logger = logging.getLogger("ats")
    logger.setLevel(level)
    logger.propagate = False
    formatter = MaskingJsonFormatter()
    try:
        log_dir = ROOT_DIR / "logs"
        log_dir.mkdir(exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "studio.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        pass
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"ats.{name}")
