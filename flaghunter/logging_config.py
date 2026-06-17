"""Centralized logging configuration for FlagHunter."""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path


DEFAULT_LOG_DIR = Path("logs/app")
DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(
    level: int | str | None = None,
    log_dir: Path | str | None = None,
    console: bool = True,
    file: bool = True,
) -> None:
    """Configure FlagHunter logging with rotating file + console handlers.

    Args:
        level: Log level (default: INFO, or DEBUG if FLAGHUNTER_DEBUG=true)
        log_dir: Directory for log files (default: logs/app)
        console: Whether to add a console handler
        file: Whether to add a rotating file handler
    """
    if level is None:
        level = logging.DEBUG if os.getenv("FLAGHUNTER_DEBUG", "").lower() in ("1", "true", "yes") else logging.INFO
    else:
        level = logging.getLevelName(level) if isinstance(level, str) else level

    log_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(DEFAULT_FORMAT)
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers if called multiple times
    if root.handlers:
        for h in root.handlers[:]:
            root.removeHandler(h)

    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        root.addHandler(console_handler)

    if file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "flaghunter.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root.addHandler(file_handler)

        # Separate error log
        error_handler = logging.handlers.RotatingFileHandler(
            log_dir / "error.log",
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8",
        )
        error_handler.setFormatter(formatter)
        error_handler.setLevel(logging.ERROR)
        root.addHandler(error_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)
