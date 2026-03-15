"""
api_server.py — FastAPI front-end for the Shortz job queue.

Endpoints:
    GET   /health           → liveness probe with Redis latency
    POST  /generate         → enqueue 1–10 video-generation jobs
    GET   /status/{job_id}  → poll single job status
    GET   /active_job       → list all currently active jobs

Design:
    • Redis client is lazy-initialised (_get_r()) to survive slow Redis startup.
    • All blocking Redis calls are offloaded via asyncio.to_thread.
    • Global exception handler ensures the API never exits on app errors.
"""

import uuid
import time
import asyncio
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.config import MAX_BATCH_SIZE, QUEUE_NAME, PROCESSING_QUEUE
from core.logging_config import setup_logging
from redis_queue import (
    get_redis, enqueue_job, enqueue_batch, get_job_status,
    find_active_job, find_all_active_jobs, is_job_in_queue,
)

# -------------------------------------------------
# LOGGING
# -------------------------------------------------

log = setup_logging("api")

# -------------------------------------------------
# APP
# -------------------------------------------------

app = FastAPI(
    title="Shortz Video Generation API",
    description="Redis-backed job queue for AI video generation.",
    version="1.0.0",
)

_redis_client = None


def _get_r():
    """Lazy-initialised Redis client — avoids crash if Redis isn't ready at import."""
    global _redis_client
    if _redis_client is None:
        _redis_client = get_redis()
    return _redis_client


# -------------------------------------------------
# REQUEST MODELS
# -------------------------------------------------

class GenerateRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=MAX_BATCH_SIZE, description="Number of jobs (1–10)")
    voice_path: Optional[str] = Field(default="", description="Path to voice sample .wav/.mp3")


# -------------------------------------------------
# MIDDLEWARE
# -------------------------------------------------

@app.middleware("http")
async def log_requests(request, call_next):
    response = await call_next(request)
    log.debug("%s %s → %s", request.method, request.url.path, response.status_code)
    return response


# -------------------------------------------------
# ENDPOINTS
# -------------------------------------------------

@app.get("/health", tags=["Infrastructure"])
async def health():
    """Liveness probe with Redis latency and queue metrics."""
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

        # Queue depth metrics
        def _queue_metrics():
            return (
                r.llen(QUEUE_NAME),
                r.llen(PROCESSING_QUEUE),
            )
        queue_size, processing_count = await asyncio.to_thread(_queue_metrics)

    except Exception as e:
        log.warning("[WARN] Redis health-check failed: %s", e)

    return {
        "status": "ok" if redis_ok else "degraded",
        "redis": redis_ok,
        "redis_latency_ms": redis_latency_ms,
        "queue_size": queue_size,
        "processing_count": processing_count,
    }


@app.get("/active_job", tags=["Jobs"])
async def active_job():
    """Return all currently active jobs (queued / running).

    Returns ``{"jobs": [...], "count": N}`` where N >= 0.
    The GUI uses this to detect existing jobs and resume monitoring.
    """
    r = _get_r()
    try:
        jobs = await asyncio.to_thread(find_all_active_jobs, r)
    except Exception as e:
        log.error("[ERROR] active_job lookup failed: %s", e)
        raise HTTPException(status_code=503, detail="Redis unavailable")

    return {"jobs": jobs, "count": len(jobs)}


@app.post("/generate", tags=["Jobs"])
async def generate(body: GenerateRequest = GenerateRequest()):
    """Enqueue 1–10 video-generation jobs.

    Prevents duplicate submission: if active jobs already exist,
    returns them without creating new ones.
    """
    r = _get_r()

    # Dedup guard for count == 1
    if body.count == 1:
        try:
            existing = await asyncio.to_thread(find_active_job, r)
        except Exception:
            existing = None

        if existing is not None:
            jid = existing.get("job_id", "")
            log.info("[INFO] Active job %s already exists — returning existing", jid[:8])
            return {
                "jobs": [existing],
                "count": 1,
                "reused": True,
            }

    # Batch enqueue
    voice = body.voice_path or ""
    try:
        if body.count == 1:
            jid = str(uuid.uuid4())
            await asyncio.to_thread(enqueue_job, r, jid, voice)
            jobs = [{"job_id": jid, "status": "queued", "voice_path": voice}]
        else:
            jids = await asyncio.to_thread(enqueue_batch, r, body.count, voice)
            jobs = [{"job_id": jid, "status": "queued", "voice_path": voice} for jid in jids]
    except Exception as e:
        log.error("[ERROR] Failed to enqueue jobs: %s", e)
        raise HTTPException(status_code=503, detail="Redis unavailable")

    log.info("[INFO] Queued %d job(s)", body.count)
    return {"jobs": jobs, "count": body.count}


@app.get("/status/{job_id}", tags=["Jobs"])
async def status(job_id: str):
    """Return status for a single job.

    Returns a queued placeholder instead of 404 when the job is in
    a queue but worker hasn't written metadata yet.
    """
    r = _get_r()

    try:
        data = await asyncio.to_thread(get_job_status, r, job_id)
    except Exception as e:
        log.error("[ERROR] Redis error for %s: %s", job_id, e)
        raise HTTPException(status_code=503, detail="Redis unavailable")

    if data is not None:
        return data

    # Metadata missing — check queues before returning 404
    try:
        in_queue = await asyncio.to_thread(is_job_in_queue, r, job_id)
        if in_queue:
            log.warning("[WARN] Job %s in queue but metadata missing — returning queued", job_id[:8])
            return {"status": "queued", "progress": "0", "stage": "waiting"}

        def _in_proc():
            return r.lpos(PROCESSING_QUEUE, job_id.encode()) is not None

        if await asyncio.to_thread(_in_proc):
            log.warning("[WARN] Job %s in processing but metadata missing — returning queued", job_id[:8])
            return {"status": "queued", "progress": "0", "stage": "waiting"}
    except Exception as e:
        log.error("[ERROR] Queue check failed for %s: %s", job_id, e)

    raise HTTPException(status_code=404, detail="Job not found")


# -------------------------------------------------
# GLOBAL EXCEPTION HANDLER — API never exits on errors
# -------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    log.exception("[ERROR] Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# -------------------------------------------------
# ENTRYPOINT
# -------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    from core.config import API_HOST, API_PORT
    uvicorn.run(app, host=API_HOST, port=API_PORT)
