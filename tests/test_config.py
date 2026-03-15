"""
tests/test_config.py — Validate core configuration module.
"""

import os


def test_config_defaults():
    """core.config provides sensible defaults without env vars."""
    from core.config import REDIS_HOST, REDIS_PORT, API_PORT, MAX_BATCH_SIZE
    assert REDIS_HOST == os.environ.get("REDIS_HOST", "127.0.0.1")
    assert isinstance(REDIS_PORT, int)
    assert isinstance(API_PORT, int)
    assert 1 <= MAX_BATCH_SIZE <= 100


def test_config_paths():
    """core.config path values are non-empty strings."""
    from core.config import OUTPUT_DIR, LOG_DIR
    assert isinstance(OUTPUT_DIR, str) and len(OUTPUT_DIR) > 0
    assert isinstance(LOG_DIR, str) and len(LOG_DIR) > 0
