"""
worker/worker.py — Modular job worker using the pipeline architecture.

Listens to the Redis queue and processes jobs through the 5-stage pipeline.

Architecture:
    ResourceManager   → loads/caches TTS model, manages Whisper lifecycle
    PipelineRunner     → orchestrates stages with telemetry
    worker_loop        → Redis BLMOVE consumption loop with reconnect

The original worker.py at project root is preserved for backward compatibility.
This module uses the new modular pipeline.
"""

import time
import traceback
import logging
import sys

from redis_queue import get_redis_worker, dequeue_job, set_job_status, complete_job
from worker.resource_manager import ResourceManager
from worker.pipeline.pipeline_runner import run_pipeline

log = logging.getLogger("shortz.worker")


def _get_healthy_redis(max_wait: int = 120):
    """Return a Redis client that successfully pings, retrying with backoff."""
    attempt = 0
    backoff = 3
    deadline = time.time() + max_wait

    while time.time() < deadline:
        attempt += 1
        try:
            r = get_redis_worker()
            r.ping()
            if attempt > 1:
                log.info("Redis reconnected (attempt %d)", attempt)
            return r
        except Exception as e:
            log.warning("Redis not ready (attempt %d): %s — retrying in %ds", attempt, e, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)

    log.error("Redis unreachable after %ds", max_wait)
    return None


def worker_loop():
    """Block on the Redis queue and process jobs through the modular pipeline.

    Lifecycle:
        1. Wait for Redis
        2. Load TTS model (cached for all jobs)
        3. Enter queue loop
        4. For each job: run_pipeline() with status callbacks
    """
    log.info("Worker starting — initializing ResourceManager")

    # Initialize GPU resource manager
    mgr = ResourceManager()
    if not mgr.load_tts():
        log.error("TTS model failed to load — worker cannot start")
        return

    log.info("TTS loaded — waiting for Redis")
    r = _get_healthy_redis(max_wait=120)
    if r is None:
        log.error("Cannot connect to Redis — worker exiting")
        mgr.shutdown()
        return

    log.info("Worker ready — entering job loop")

    def _status_cb(job_id, status, stage="", progress=0):
        """Update Redis job metadata between pipeline stages."""
        try:
            set_job_status(r, job_id, status, stage=stage, progress=progress)
        except Exception as e:
            log.warning("Failed to update job status: %s", e)

    while True:
        # Verify Redis connection
        try:
            r.ping()
        except Exception:
            log.warning("Redis connection lost — reconnecting")
            r = _get_healthy_redis(max_wait=60)
            if r is None:
                log.error("Redis reconnect failed — retrying in 10s")
                time.sleep(10)
                continue

        job_id = dequeue_job(r)
        if job_id is None:
            time.sleep(1)
            continue

        log.info("Job picked up: %s", job_id[:8])
        set_job_status(r, job_id, "running", stage="text", progress=0)

        try:
            ctx = run_pipeline(
                job_id=job_id,
                resource_manager=mgr,
                status_callback=_status_cb,
                voice_path="",  # GUI sends voice_path via job metadata
            )
            set_job_status(r, job_id, "complete", progress=100, stage="done")
            complete_job(r, job_id)
            log.info("Job complete: %s", job_id[:8])

        except Exception as e:
            tb = traceback.format_exc()
            log.error("Job FAILED %s: %s\n%s", job_id[:8], e, tb)
            set_job_status(r, job_id, "failed", error=str(e))
            complete_job(r, job_id)

    # Unreachable in normal operation; cleanup on SIGINT is handled by the OS
    mgr.shutdown()


if __name__ == "__main__":
    from core.logging_config import setup_logging
    setup_logging("worker")
    worker_loop()
