"""
core/logging_config.py — Structured logging for all Shortz services.

Usage:
    from core.logging_config import setup_logging
    log = setup_logging("api")
    log.info("Server started on port 8000")

Output format:
    2026-03-15 06:01:23  [INFO]   api      Server started on port 8000
"""

import logging
import sys
from pathlib import Path
from datetime import datetime


# -------------------------------------------------
# CUSTOM FORMATTER
# -------------------------------------------------

class ShortzFormatter(logging.Formatter):
    """
    Formats log records as:
        timestamp  [LEVEL]   service   message
    """

    LEVEL_LABELS = {
        logging.DEBUG:    "[DEBUG]  ",
        logging.INFO:     "[INFO]   ",
        logging.WARNING:  "[WARN]   ",
        logging.ERROR:    "[ERROR]  ",
        logging.CRITICAL: "[CRIT]   ",
    }

    def __init__(self, service: str):
        super().__init__()
        self._service = service.ljust(8)

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        level = self.LEVEL_LABELS.get(record.levelno, "[INFO]   ")
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return f"{ts}  {level}  {self._service}  {msg}"


# -------------------------------------------------
# PUBLIC SETUP
# -------------------------------------------------

def setup_logging(
    service: str,
    log_dir: Path | None = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """Configure and return a logger for the named service.

    Args:
        service:  Short service name shown in every log line (e.g. "api", "worker").
        log_dir:  If provided, also writes to logs/runtime/<service>.log.
        level:    Minimum log level (default: INFO).

    Returns:
        A configured ``logging.Logger`` instance.
    """
    logger = logging.getLogger(f"shortz.{service}")

    # Avoid adding duplicate handlers in reload scenarios.
    if logger.handlers:
        return logger

    logger.setLevel(level)
    formatter = ShortzFormatter(service)

    # --- stdout handler (always) ---
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    sh.setLevel(level)
    logger.addHandler(sh)

    # --- file handler (optional) ---
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{service}.log"
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(formatter)
        fh.setLevel(level)
        logger.addHandler(fh)

    # Prevent propagation to root logger (avoids duplicate lines).
    logger.propagate = False

    return logger
