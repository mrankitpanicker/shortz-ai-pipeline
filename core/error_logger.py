"""
core/error_logger.py — Centralized error logging for the Shortz stack.

Provides:
    • install_global_handler()  — sys.excepthook + threading.excepthook
    • log_exception(exc)        — manual exception logging
    • safe_execute(fn)          — decorator for crash-safe function calls

All uncaught exceptions are written to:
    logs/errors/error.log

Format:
    2026-03-15 07:02:11 [ERROR] module.name
    Traceback (most recent call last):
      ...
"""

import sys
import logging
import traceback
import threading
from pathlib import Path

# Ensure error log directory exists
ERROR_LOG_DIR = Path(__file__).resolve().parent.parent / "logs" / "errors"
ERROR_LOG_DIR.mkdir(parents=True, exist_ok=True)
ERROR_LOG_FILE = ERROR_LOG_DIR / "error.log"

# Configure dedicated error logger
_error_logger = logging.getLogger("shortz.errors")
_error_logger.setLevel(logging.ERROR)
_error_logger.propagate = False

# File handler — append mode, always available
_fh = logging.FileHandler(ERROR_LOG_FILE, encoding="utf-8")
_fh.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s\n%(message)s\n",
    datefmt="%Y-%m-%d %H:%M:%S",
))
_error_logger.addHandler(_fh)

# Console handler — so errors are also visible in terminal
_sh = logging.StreamHandler(sys.stderr)
_sh.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
_error_logger.addHandler(_sh)


def log_exception(exc: BaseException, context: str = ""):
    """Log an exception with full traceback to error.log.

    Args:
        exc: The exception to log.
        context: Optional context string (e.g. 'gui.startup', 'worker.pipeline').
    """
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    prefix = f"[{context}] " if context else ""
    _error_logger.error("%s%s\n%s", prefix, exc, tb)


def _global_excepthook(exc_type, exc_value, exc_tb):
    """sys.excepthook replacement — captures all uncaught exceptions."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    _error_logger.error("Uncaught exception\n%s", tb)


def _thread_excepthook(args):
    """threading.excepthook replacement — captures thread exceptions."""
    if issubclass(args.exc_type, SystemExit):
        return
    tb = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    thread_name = args.thread.name if args.thread else "unknown"
    _error_logger.error("Uncaught exception in thread '%s'\n%s", thread_name, tb)


def install_global_handler():
    """Install global exception hooks for main thread and all sub-threads.

    Call this once at application startup (supervisor or GUI entry point).
    """
    sys.excepthook = _global_excepthook
    threading.excepthook = _thread_excepthook
    _error_logger.info("Global exception handlers installed → %s", ERROR_LOG_FILE)


def safe_execute(fn, context: str = ""):
    """Execute a callable with crash logging. Returns None on failure.

    Usage:
        safe_execute(lambda: start_gui(), context="gui.launch")
    """
    try:
        return fn()
    except Exception as exc:
        log_exception(exc, context=context)
        return None
