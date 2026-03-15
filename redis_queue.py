"""
redis_queue.py — Shared Redis job-queue utilities for Shortz.

Reads configuration from core.config so Redis host/port is
set in one place (environment variables or .env).
"""

import time
import uuid
import logging
import redis

from core.config import (
    REDIS_HOST, REDIS_PORT, REDIS_DB,
    QUEUE_NAME, PROCESSING_QUEUE,
)

log = logging.getLogger("shortz.redis")

# Statuses that mean a job is genuinely active
ACTIVE_STATUSES = frozenset({"queued", "running", "processing"})


# -------------------------------------------------
# CONNECTION POOLS
# -------------------------------------------------

_api_pool = redis.ConnectionPool(
    host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
    max_connections=10,
    socket_connect_timeout=3, socket_timeout=5,
    decode_responses=False,
    retry_on_error=[redis.ConnectionError, redis.TimeoutError],
    health_check_interval=30,
)

_worker_pool = redis.ConnectionPool(
    host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
    max_connections=4,
    socket_connect_timeout=5, socket_timeout=None,   # blocking pop
    decode_responses=False,
    retry_on_error=[redis.ConnectionError],
    health_check_interval=30,
)


def get_redis() -> redis.Redis:
    """Short-timeout client for API / health checks."""
    return redis.Redis(connection_pool=_api_pool)


def get_redis_worker() -> redis.Redis:
    """No-timeout client for blocking BLMOVE/BRPOPLPUSH."""
    return redis.Redis(connection_pool=_worker_pool)


# -------------------------------------------------
# SINGLE JOB ENQUEUE
# -------------------------------------------------

def enqueue_job(
    r: redis.Redis,
    job_id: str,
    voice_path: str = "",
) -> None:
    """Atomically create job metadata + push to queue.

    Metadata is always created BEFORE the queue push so that
    /status never hits a missing-metadata window.
    """
    try:
        with r.pipeline() as pipe:
            pipe.hset(f"job:{job_id}", mapping={
                "status":     "queued",
                "progress":   "0",
                "stage":      "waiting",
                "voice_path": voice_path,
                "created":    str(int(time.time())),
            })
            pipe.rpush(QUEUE_NAME, job_id)
            pipe.execute()
        log.info("[INFO] Job queued: %s", job_id)
    except redis.RedisError as e:
        log.error("[ERROR] Failed to enqueue job %s: %s", job_id, e)
        raise


# -------------------------------------------------
# BATCH ENQUEUE
# -------------------------------------------------

def enqueue_batch(
    r: redis.Redis,
    count: int,
    voice_path: str = "",
) -> list[str]:
    """Atomically enqueue N jobs in a single Redis pipeline.

    Returns a list of the newly created job IDs.
    """
    if count < 1:
        return []
    job_ids = [str(uuid.uuid4()) for _ in range(count)]
    ts = str(int(time.time()))
    try:
        with r.pipeline() as pipe:
            for jid in job_ids:
                pipe.hset(f"job:{jid}", mapping={
                    "status":     "queued",
                    "progress":   "0",
                    "stage":      "waiting",
                    "voice_path": voice_path,
                    "created":    ts,
                })
                pipe.rpush(QUEUE_NAME, jid)
            pipe.execute()
        log.info("[INFO] Batch of %d jobs queued: %s…", count, job_ids[0][:8])
        return job_ids
    except redis.RedisError as e:
        log.error("[ERROR] enqueue_batch failed: %s", e)
        raise


# -------------------------------------------------
# DEQUEUE
# -------------------------------------------------

def dequeue_job(r: redis.Redis, timeout: int = 0) -> str | None:
    """Atomically pop from job queue → processing queue.

    Tries BLMOVE (Redis 6.2+) then falls back to BRPOPLPUSH.
    """
    try:
        try:
            result = r.blmove(QUEUE_NAME, PROCESSING_QUEUE, timeout, "RIGHT", "LEFT")
        except (redis.ResponseError, AttributeError):
            result = r.brpoplpush(QUEUE_NAME, PROCESSING_QUEUE, timeout)

        if result:
            jid = result.decode() if isinstance(result, bytes) else result
            log.info("[INFO] Worker started processing job: %s", jid)
            return jid
        return None
    except redis.RedisError as e:
        log.error("[ERROR] dequeue_job failed: %s", e)
        return None


# -------------------------------------------------
# JOB STATUS
# -------------------------------------------------

def set_job_status(r: redis.Redis, job_id: str, status: str, **extra) -> None:
    mapping = {"status": status, "updated": str(int(time.time()))}
    mapping.update({k: str(v) for k, v in extra.items()})
    try:
        r.hset(f"job:{job_id}", mapping=mapping)
        log.info("[INFO] Job %s → %s", job_id[:8], status)
    except redis.RedisError as e:
        log.error("[ERROR] set_job_status failed for %s: %s", job_id, e)
        raise


def get_job_status(r: redis.Redis, job_id: str) -> dict | None:
    try:
        data = r.hgetall(f"job:{job_id}")
        return {k.decode(): v.decode() for k, v in data.items()} if data else None
    except redis.RedisError as e:
        log.error("[ERROR] get_job_status failed for %s: %s", job_id, e)
        return None


# -------------------------------------------------
# LIFECYCLE
# -------------------------------------------------

def complete_job(r: redis.Redis, job_id: str) -> None:
    """Remove from processing queue; keep metadata for final poll."""
    try:
        r.lrem(PROCESSING_QUEUE, 0, job_id)
        log.info("[INFO] Removed %s from processing queue", job_id[:8])
    except redis.RedisError as e:
        log.error("[ERROR] complete_job failed for %s: %s", job_id, e)


def cleanup_job(r: redis.Redis, job_id: str) -> None:
    """Remove ALL Redis traces for a job."""
    try:
        with r.pipeline() as pipe:
            pipe.delete(f"job:{job_id}")
            pipe.lrem(PROCESSING_QUEUE, 0, job_id)
            pipe.lrem(QUEUE_NAME, 0, job_id)
            pipe.execute()
        log.info("[INFO] Cleaned up job %s", job_id[:8])
    except redis.RedisError as e:
        log.error("[ERROR] cleanup_job failed for %s: %s", job_id, e)


# -------------------------------------------------
# ACTIVE JOB DISCOVERY
# -------------------------------------------------

def is_job_in_queue(r: redis.Redis, job_id: str) -> bool:
    try:
        return r.lpos(QUEUE_NAME, job_id.encode()) is not None
    except redis.RedisError:
        return False


def find_active_job(r: redis.Redis) -> dict | None:
    """Return the first active job (processing queue → pending queue).

    Only returns jobs with status in ACTIVE_STATUSES.
    Completed / failed jobs are skipped (stale entries).
    """
    try:
        for raw_id in r.lrange(PROCESSING_QUEUE, 0, -1):
            jid = raw_id.decode()
            data = get_job_status(r, jid)
            if data and data.get("status") in ACTIVE_STATUSES:
                data["job_id"] = jid
                return data
            elif not data:
                return {"job_id": jid, "status": "queued", "progress": "0", "stage": "waiting"}

        for raw_id in r.lrange(QUEUE_NAME, 0, -1):
            jid = raw_id.decode()
            data = get_job_status(r, jid)
            if data and data.get("status") in ACTIVE_STATUSES:
                data["job_id"] = jid
                return data
            elif not data:
                return {"job_id": jid, "status": "queued", "progress": "0", "stage": "waiting"}

        return None
    except redis.RedisError as e:
        log.error("[ERROR] find_active_job failed: %s", e)
        return None


def find_all_active_jobs(r: redis.Redis) -> list[dict]:
    """Return ALL active jobs across processing + pending queues.

    Used by /active_job for batch-mode monitoring.
    """
    seen: set[str] = set()
    jobs: list[dict] = []

    try:
        for queue in (PROCESSING_QUEUE, QUEUE_NAME):
            for raw_id in r.lrange(queue, 0, -1):
                jid = raw_id.decode()
                if jid in seen:
                    continue
                seen.add(jid)
                data = get_job_status(r, jid)
                if data and data.get("status") in ACTIVE_STATUSES:
                    data["job_id"] = jid
                    jobs.append(data)
                elif not data:
                    jobs.append({
                        "job_id": jid, "status": "queued",
                        "progress": "0", "stage": "waiting",
                    })
    except redis.RedisError as e:
        log.error("[ERROR] find_all_active_jobs failed: %s", e)

    return jobs