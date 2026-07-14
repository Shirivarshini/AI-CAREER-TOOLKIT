"""
Application-wide logging configuration.

Why this file exists
---------------------
Enterprise services need consistent, structured logs (timestamps, module
name, log level) across every module — resume parsing, GitHub calls,
DB access, etc. Configuring logging in one place avoids inconsistent
`print()` statements and ad-hoc logger setups scattered through the code.

How it works
------------
`configure_logging()` sets up the root logger's format and level once,
at application startup (called from `app/main.py`). Every module then
does `logger = logging.getLogger(__name__)` to get a properly configured,
named logger.

Where future code should go
----------------------------
If we later ship structured JSON logs (e.g. for CloudWatch Logs Insights),
swap the `Formatter` here for a JSON formatter — no other module needs
to change since they only ever call `logging.getLogger(__name__)`.
"""

import logging
import sys

from app.config.settings import get_settings


def configure_logging() -> None:
    """Configure the root logger once at application startup."""
    settings = get_settings()

    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if configure_logging() is ever called twice
    # (e.g. under a reloader process).
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Quiet down noisy third-party loggers unless we're in debug mode.
    if not settings.APP_DEBUG:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
