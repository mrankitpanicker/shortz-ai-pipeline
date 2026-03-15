"""
core/config.py — Centralised configuration for all Shortz services.

All environment variables are read here.  Components import from this
module instead of duplicating os.getenv() calls.

Environment variables (with defaults):

    REDIS_HOST          127.0.0.1
    REDIS_PORT          6379
    REDIS_DB            0
    API_HOST            0.0.0.0
    API_PORT            8000
    GPU_ID              0
    OUTPUT_DIR          ./output
    LOG_DIR             ./logs
    VOICE_SAMPLE        ./voices/uvi.wav
    MAX_BATCH_SIZE      10
    WORKER_ID           gpu-worker-1
"""

import os
from pathlib import Path

# -------------------------------------------------
# PROJECT ROOT (works for both flat and package layouts)
# -------------------------------------------------

_HERE = Path(__file__).resolve().parent          # core/
PROJECT_ROOT = _HERE.parent                       # shortz/


# -------------------------------------------------
# REDIS
# -------------------------------------------------

REDIS_HOST: str = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB:   int = int(os.getenv("REDIS_DB",   "0"))

QUEUE_NAME       = "shortz_jobs"
PROCESSING_QUEUE = "shortz_processing"


# -------------------------------------------------
# API
# -------------------------------------------------

API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))
API_BASE_URL: str = os.getenv(
    "API_BASE_URL",
    f"http://127.0.0.1:{API_PORT}",
)


# -------------------------------------------------
# WORKER
# -------------------------------------------------

GPU_ID:     int = int(os.getenv("GPU_ID",     "0"))
WORKER_ID: str = os.getenv("WORKER_ID", "gpu-worker-1")


# -------------------------------------------------
# PATHS
# -------------------------------------------------

OUTPUT_DIR  = Path(os.getenv("OUTPUT_DIR",  str(PROJECT_ROOT / "output")))
LOG_DIR     = Path(os.getenv("LOG_DIR",     str(PROJECT_ROOT / "logs")))
VOICE_DIR   = Path(os.getenv("VOICE_DIR",   str(PROJECT_ROOT / "voices")))
INPUT_DIR   = Path(os.getenv("INPUT_DIR",   str(PROJECT_ROOT / "input")))
BIN_DIR     = Path(os.getenv("BIN_DIR",     str(PROJECT_ROOT / "bin")))

DEFAULT_VOICE: str = os.getenv(
    "VOICE_SAMPLE",
    str(VOICE_DIR / "uvi.wav"),
)


# -------------------------------------------------
# JOB LIMITS
# -------------------------------------------------

MAX_BATCH_SIZE: int = int(os.getenv("MAX_BATCH_SIZE", "10"))


# -------------------------------------------------
# ENSURE KEY DIRECTORIES EXIST
# -------------------------------------------------

for _d in (OUTPUT_DIR, LOG_DIR, VOICE_DIR, INPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)
