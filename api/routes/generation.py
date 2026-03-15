"""
api/routes/generation.py — Job generation and status routes.

FastAPI router providing:
    POST /generate       → batch job submission
    GET  /status/{id}    → single job status
    GET  /active_job     → all active jobs
    GET  /health         → liveness probe + queue metrics
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.config import MAX_BATCH_SIZE
from api.services.job_service import (
    get_health_metrics, list_active_jobs, submit_jobs, get_status,
)

log = logging.getLogger("shortz.api.routes")

router = APIRouter()


class GenerateRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=MAX_BATCH_SIZE, description="Number of jobs (1–10)")
    voice_path: Optional[str] = Field(default="", description="Path to voice sample .wav/.mp3")


@router.get("/health", tags=["Infrastructure"])
async def health():
    """Liveness probe with Redis latency and queue metrics."""
    return await get_health_metrics()


@router.get("/active_job", tags=["Jobs"])
async def active_job():
    """Return all currently active jobs (queued + running)."""
    try:
        jobs = await list_active_jobs()
    except Exception as e:
        log.error("active_job lookup failed: %s", e)
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"jobs": jobs, "count": len(jobs)}


@router.post("/generate", tags=["Jobs"])
async def generate(body: GenerateRequest = GenerateRequest()):
    """Enqueue 1–10 video-generation jobs.

    Prevents duplicate submission: if active jobs already exist,
    returns them without creating new ones.
    """
    try:
        jobs, reused = await submit_jobs(body.count, body.voice_path or "")
    except Exception as e:
        log.error("Failed to enqueue jobs: %s", e)
        raise HTTPException(status_code=503, detail="Redis unavailable")

    result = {"jobs": jobs, "count": len(jobs)}
    if reused:
        result["reused"] = True
    log.info("Queued %d job(s)%s", len(jobs), " (reused)" if reused else "")
    return result


@router.get("/status/{job_id}", tags=["Jobs"])
async def status(job_id: str):
    """Return status for a single job."""
    try:
        data = await get_status(job_id)
    except Exception as e:
        log.error("Redis error for %s: %s", job_id, e)
        raise HTTPException(status_code=503, detail="Redis unavailable")

    if data is not None:
        return data
    raise HTTPException(status_code=404, detail="Job not found")
