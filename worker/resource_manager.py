"""
worker/resource_manager.py — GPU Resource Lifecycle Manager

Manages model loading/unloading for the Shortz pipeline.

Strategy for 4GB VRAM (RTX 3050):
  • TTS (XTTS v2):  Loaded once at worker startup, cached across all jobs (~2GB)
  • Whisper:         Loaded on first alignment, reused across jobs (~1GB)
                     Can be explicitly unloaded when VRAM pressure is high.

Usage:
    mgr = ResourceManager()
    mgr.load_tts()                # Once at startup
    tts = mgr.get_tts()           # Per-job
    whisper = mgr.load_whisper()   # Per alignment stage
    mgr.unload_whisper()           # After alignment
"""

import gc
import time
import logging
from pathlib import Path

log = logging.getLogger("shortz.resource_manager")

# Safe torch import
try:
    import torch
    _HAS_CUDA = torch.cuda.is_available()
except ImportError:
    torch = None
    _HAS_CUDA = False

# Safe TTS import
try:
    from TTS.api import TTS as _TTS_Class
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import XttsAudioConfig, XttsArgs
    from TTS.config.shared_configs import BaseDatasetConfig

    if torch is not None:
        torch.serialization.add_safe_globals([
            XttsConfig, XttsAudioConfig, XttsArgs, BaseDatasetConfig,
        ])
    _HAS_TTS = True
except ImportError:
    _TTS_Class = None
    _HAS_TTS = False

XTTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"


class ResourceManager:
    """Manages GPU model lifecycle for the Shortz worker pipeline.

    Thread safety: NOT thread-safe. Use one instance per worker process.
    """

    def __init__(self):
        self._tts_model = None
        self._whisper_model = None
        self._use_gpu = _HAS_CUDA
        log.info("ResourceManager init  gpu=%s  tts_available=%s", self._use_gpu, _HAS_TTS)

    # ----- TTS (XTTS v2) -----

    def load_tts(self) -> bool:
        """Load XTTS model. Returns True on success."""
        if self._tts_model is not None:
            log.debug("TTS already loaded — skipping")
            return True
        if not _HAS_TTS:
            log.error("TTS dependencies not installed")
            return False

        t0 = time.perf_counter()
        log.info("Loading XTTS v2 model  gpu=%s …", self._use_gpu)
        try:
            self._tts_model = _TTS_Class(XTTS_MODEL_NAME, progress_bar=False, gpu=self._use_gpu)
            elapsed = time.perf_counter() - t0
            log.info("XTTS loaded in %.1fs", elapsed)
            return True
        except Exception as e:
            log.error("XTTS load failed: %s", e)
            self._tts_model = None
            return False

    def get_tts(self):
        """Return the cached TTS model instance (or None)."""
        return self._tts_model

    # ----- Whisper -----

    def load_whisper(self, model_size: str = "small"):
        """Load Whisper model. Reuses if already loaded."""
        if self._whisper_model is not None:
            log.debug("Whisper already loaded — reusing")
            return self._whisper_model

        t0 = time.perf_counter()
        log.info("Loading Whisper '%s' …", model_size)
        try:
            import whisper
            self._whisper_model = whisper.load_model(model_size)
            elapsed = time.perf_counter() - t0
            log.info("Whisper loaded in %.1fs", elapsed)
            return self._whisper_model
        except Exception as e:
            log.error("Whisper load failed: %s", e)
            return None

    def unload_whisper(self):
        """Unload Whisper model and free GPU memory."""
        if self._whisper_model is None:
            return
        log.info("Unloading Whisper model")
        del self._whisper_model
        self._whisper_model = None
        gc.collect()
        if torch is not None and _HAS_CUDA:
            torch.cuda.empty_cache()
        log.info("Whisper unloaded — VRAM freed")

    # ----- Diagnostics -----

    @property
    def gpu_available(self) -> bool:
        return self._use_gpu

    def vram_info(self) -> dict:
        """Return current VRAM usage (MB) or empty dict if no GPU."""
        if torch is None or not _HAS_CUDA:
            return {}
        try:
            allocated = torch.cuda.memory_allocated(0) / 1024 / 1024
            reserved = torch.cuda.memory_reserved(0) / 1024 / 1024
            return {"allocated_mb": round(allocated, 1), "reserved_mb": round(reserved, 1)}
        except Exception:
            return {}

    def shutdown(self):
        """Release all models. Called on worker exit."""
        log.info("ResourceManager shutting down")
        self.unload_whisper()
        if self._tts_model is not None:
            del self._tts_model
            self._tts_model = None
        gc.collect()
        if torch is not None and _HAS_CUDA:
            torch.cuda.empty_cache()
"""
worker/resource_manager.py — GPU Resource Lifecycle Manager
"""
