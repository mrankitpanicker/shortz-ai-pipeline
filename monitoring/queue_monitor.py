"""
queue_monitor.py — Redis queue monitoring for the Shortz platform.

Reads the Redis queue and job hashes to compute:
    queue_length   — jobs waiting in the queue
    workers_active — number of jobs currently in "running" state
    jobs_processing — same as workers_active (alias)

Also provides a full job listing for the dashboard.

Usage:
    from monitoring.queue_monitor import get_queue_stats, list_jobs
"""

import time
from typing import Any

import redis

# -------------------------------------------------
# REDIS CONFIG  (mirrors redis_queue.py)
# -------------------------------------------------

REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
QUEUE_NAME = "shortz_jobs"


def _get_redis() -> redis.Redis:
    """Return a Redis client."""
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
    )


# -------------------------------------------------
# QUEUE STATS
# -------------------------------------------------

def get_queue_stats(r: redis.Redis | None = None) -> dict[str, Any]:
    """
    Return current queue statistics.

    {
        "queue_length": int,
        "workers_active": int,
        "jobs_processing": int,
        "total_jobs": int,
        "jobs_by_status": { "queued": n, "running": n, "complete": n, "failed": n }
    }
    """
    if r is None:
        r = _get_redis()

    queue_length = r.llen(QUEUE_NAME)

    # Scan all job:* keys and bucket by status
    counts: dict[str, int] = {
        "queued": 0,
        "running": 0,
        "complete": 0,
        "failed": 0,
    }
    total = 0
    for key in r.scan_iter(match="job:*", count=200):
        status = r.hget(key, "status") or "unknown"
        counts[status] = counts.get(status, 0) + 1
        total += 1

    return {
        "queue_length": queue_length,
        "workers_active": counts.get("running", 0),
        "jobs_processing": counts.get("running", 0),
        "total_jobs": total,
        "jobs_by_status": counts,
    }


# -------------------------------------------------
# JOB LISTING
# -------------------------------------------------

def list_jobs(
    r: redis.Redis | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Return the most recent jobs with their full status hashes.

    Each entry: { job_id, status, created, updated, error?, ... }
    """
    if r is None:
        r = _get_redis()

    jobs: list[dict[str, Any]] = []
    for key in r.scan_iter(match="job:*", count=200):
        data = r.hgetall(key)
        if not data:
            continue
        job_id = key.split(":", 1)[1] if ":" in key else key
        entry: dict[str, Any] = {"job_id": job_id}
        entry.update(data)
        jobs.append(entry)

    # Sort by 'created' descending (most recent first)
    jobs.sort(key=lambda j: j.get("created", "0"), reverse=True)
    return jobs[:limit]


# -------------------------------------------------
# Prometheus-friendly flat dict
# -------------------------------------------------

def get_queue_metrics_flat(r: redis.Redis | None = None) -> dict[str, float]:
    """Return flat key-value metrics for Prometheus exposition."""
    stats = get_queue_stats(r)
    return {
        "shortz_queue_length": float(stats["queue_length"]),
        "shortz_workers_active": float(stats["workers_active"]),
        "shortz_jobs_processing": float(stats["jobs_processing"]),
        "shortz_jobs_total": float(stats["total_jobs"]),
        "shortz_jobs_queued": float(stats["jobs_by_status"].get("queued", 0)),
        "shortz_jobs_running": float(stats["jobs_by_status"].get("running", 0)),
        "shortz_jobs_complete": float(stats["jobs_by_status"].get("complete", 0)),
        "shortz_jobs_failed": float(stats["jobs_by_status"].get("failed", 0)),
    }
