"""Centralized logging configuration for Odysseus.

Two modes:
  Normal (default): INFO to console + rotating file.
  Debug (ODYSSEUS_DEBUG=1): DEBUG to console + file, with subsystem filtering.
"""

import logging
import logging.handlers
import os
import sys

from src.constants import LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT

LOG_FORMAT = os.getenv("ODYSSEUS_LOG_FORMAT", "text")
DEBUG_MODE = os.getenv("ODYSSEUS_DEBUG", "0") not in ("0", "", "false", "no")
DEBUG_SUBSYSTEMS = [
    s.strip()
    for s in os.getenv("ODYSSEUS_DEBUG_SUBSYSTEMS", "").split(",")
    if s.strip()
]

_TEXT_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_JSON_FMT = (
    '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s",'
    '"message":"%(message)s"}'
)


def _build_formatter():
    fmt = _JSON_FMT if LOG_FORMAT == "json" else _TEXT_FMT
    return logging.Formatter(fmt)


def _console_handler():
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(_build_formatter())
    return h


def _file_handler():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    h = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT,
    )
    h.setFormatter(_build_formatter())
    return h


def setup_logging():
    root = logging.getLogger()
    root.handlers.clear()

    if DEBUG_MODE:
        root.setLevel(logging.DEBUG)
        ch = _console_handler()
        ch.setLevel(logging.DEBUG)
        fh = _file_handler()
        fh.setLevel(logging.DEBUG)
        root.addHandler(ch)
        root.addHandler(fh)

        if DEBUG_SUBSYSTEMS:
            for name in DEBUG_SUBSYSTEMS:
                logging.getLogger(name).setLevel(logging.DEBUG)
            for name in list(root.manager.loggerDict):
                if not any(name.startswith(s) for s in DEBUG_SUBSYSTEMS):
                    existing = logging.getLogger(name)
                    if not existing.handlers:
                        existing.setLevel(logging.INFO)
        else:
            for name in list(root.manager.loggerDict):
                existing = logging.getLogger(name)
                if not existing.handlers:
                    existing.setLevel(logging.DEBUG)
    else:
        root.setLevel(logging.INFO)
        root.addHandler(_console_handler())
        root.addHandler(_file_handler())

    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
