"""
api/services/job_service.py — Job lifecycle operations.

Encapsulates all Redis job interactions: enqueue, status lookup,
active job discovery. Used by API route handlers.
"""

import uuid
import asyncio
import logging
from typing import Optional

from redis_queue import (
    get_redis, enqueue_job, enqueue_batch, get_job_status,
    find_active_job, find_all_active_jobs, is_job_in_queue,
)
from core.config import QUEUE_NAME, PROCESSING_QUEUE

log = logging.getLogger("shortz.api.job_service")

_redis_client = None


def _get_r():
    """Lazy-initialised Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = get_redis()
    return _redis_client


async def get_health_metrics() -> dict:
    """Return Redis health and queue depth metrics."""
    import time
    r = _get_r()
    redis_ok = False
    redis_latency_ms = -1
    queue_size = 0
    processing_count = 0

    try:
        t0 = time.perf_counter()
        pong = await asyncio.to_thread(r.ping)
        redis_latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        redis_ok = bool(pong)

        def _metrics():
            return r.llen(QUEUE_NAME), r.llen(PROCESSING_QUEUE)
        queue_size, processing_count = await asyncio.to_thread(_metrics)
    except Exception as e:
        log.warning("Redis health-check failed: %s", e)

    return {
        "status": "ok" if redis_ok else "degraded",
        "redis": redis_ok,
        "redis_latency_ms": redis_latency_ms,
        "queue_size": queue_size,
        "processing_count": processing_count,
    }


async def list_active_jobs() -> list:
    """Return all active jobs across queues."""
    r = _get_r()
    return await asyncio.to_thread(find_all_active_jobs, r)


async def submit_jobs(count: int, voice_path: str = "") -> tuple[list[dict], bool]:
    """Enqueue jobs. Returns (job_list, reused_flag).

    If count == 1 and an active job exists, returns it instead of creating a new one.
    """
    r = _get_r()

    # Dedup guard for single jobs
    if count == 1:
        try:
            existing = await asyncio.to_thread(find_active_job, r)
        except Exception:
            existing = None
        if existing is not None:
            return [existing], True

    # Batch enqueue
    voice = voice_path or ""
    if count == 1:
        jid = str(uuid.uuid4())
        await asyncio.to_thread(enqueue_job, r, jid, voice)
        return [{"job_id": jid, "status": "queued", "voice_path": voice}], False
    else:
        jids = await asyncio.to_thread(enqueue_batch, r, count, voice)
        jobs = [{"job_id": jid, "status": "queued", "voice_path": voice} for jid in jids]
        return jobs, False


async def get_status(job_id: str) -> Optional[dict]:
    """Get job status from Redis. Returns None if not found anywhere."""
    r = _get_r()

    data = await asyncio.to_thread(get_job_status, r, job_id)
    if data is not None:
        return data

    # Check queues before declaring not-found
    in_queue = await asyncio.to_thread(is_job_in_queue, r, job_id)
    if in_queue:
        return {"status": "queued", "progress": "0", "stage": "waiting"}

    def _in_proc():
        return r.lpos(PROCESSING_QUEUE, job_id.encode()) is not None

    if await asyncio.to_thread(_in_proc):
        return {"status": "queued", "progress": "0", "stage": "waiting"}

    return None
