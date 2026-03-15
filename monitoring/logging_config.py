"""
logging_config.py — Structured logging setup for the Shortz platform.

Creates rotating JSON-formatted log files:
    logs/system.log   — general system events
    logs/worker.log   — worker lifecycle & job processing
    logs/api.log      — API request/response logs
    logs/jobs.log     — per-job structured entries

Usage:
    from monitoring.logging_config import get_logger, log_job_event
    logger = get_logger("worker")
    log_job_event("abc-123", "started")
"""

import json
import logging
import logging.handlers
import os
import time
from pathlib import Path
from datetime import datetime, timezone

# -------------------------------------------------
# PATHS
# -------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILES = {
    "system": LOGS_DIR / "system.log",
    "worker": LOGS_DIR / "worker.log",
    "api":    LOGS_DIR / "api.log",
    "jobs":   LOGS_DIR / "jobs.log",
}

# -------------------------------------------------
# JSON FORMATTER
# -------------------------------------------------

class JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        # Merge any extra structured fields
        for key in ("job_id", "status", "duration", "error", "extra"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val
        return json.dumps(entry, default=str)


# -------------------------------------------------
# LOGGER FACTORY
# -------------------------------------------------

_loggers: dict[str, logging.Logger] = {}

def get_logger(name: str = "system") -> logging.Logger:
    """
    Return (or create) a named logger that writes to the matching log file.
    Valid names: system, worker, api, jobs.
    """
    if name in _loggers:
        return _loggers[name]

    log_file = LOG_FILES.get(name, LOG_FILES["system"])
    logger = logging.getLogger(f"shortz.{name}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Rotating file handler — 5 MB per file, keep 5 backups
    fh = logging.handlers.RotatingFileHandler(
        str(log_file),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(JSONFormatter())
    logger.addHandler(fh)

    # Also log to stderr for convenience
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(JSONFormatter())
    logger.addHandler(sh)

    _loggers[name] = logger
    return logger


# -------------------------------------------------
# JOB EVENT HELPER
# -------------------------------------------------

def log_job_event(
    job_id: str,
    status: str,
    *,
    start_time: float | None = None,
    end_time: float | None = None,
    error: str | None = None,
    extra: dict | None = None,
) -> None:
    """
    Write a structured job event to logs/jobs.log.

    Parameters
    ----------
    job_id : str
        Unique job identifier.
    status : str
        One of: queued, running, complete, failed.
    start_time / end_time : float, optional
        Unix timestamps; duration is computed automatically when both given.
    error : str, optional
        Error message for failed jobs.
    extra : dict, optional
        Arbitrary extra metadata.
    """
    logger = get_logger("jobs")
    duration = None
    if start_time is not None and end_time is not None:
        duration = round(end_time - start_time, 3)

    logger.info(
        "job_event",
        extra={
            "job_id": job_id,
            "status": status,
            "duration": duration,
            "error": error,
            "extra": extra,
        },
    )
