"""
metrics_collector.py — Prometheus metrics aggregator for the Shortz platform.

Collects worker metrics, GPU metrics, and queue metrics, then exposes
them in Prometheus text exposition format (text/plain; version=0.0.4).

Usage:
    from monitoring.metrics_collector import collect_all_metrics, render_prometheus

    metrics = collect_all_metrics()
    text    = render_prometheus()       # ready for HTTP response
"""

import time
from typing import Any

from monitoring.gpu_monitor import get_gpu_metrics_flat
from monitoring.queue_monitor import get_queue_metrics_flat

# -------------------------------------------------
# WORKER METRICS (in-memory counters)
# -------------------------------------------------

_worker_state: dict[str, Any] = {
    "start_time": time.time(),
    "jobs_processed": 0,
    "jobs_failed": 0,
    "total_job_time": 0.0,   # sum of all job durations in seconds
}


def record_job(duration: float, failed: bool = False) -> None:
    """Call after each job completes to update worker counters."""
    _worker_state["jobs_processed"] += 1
    _worker_state["total_job_time"] += duration
    if failed:
        _worker_state["jobs_failed"] += 1


def get_worker_metrics() -> dict[str, float]:
    """Return worker-level metrics."""
    processed = _worker_state["jobs_processed"]
    avg = (
        _worker_state["total_job_time"] / processed
        if processed > 0
        else 0.0
    )
    uptime = time.time() - _worker_state["start_time"]
    return {
        "shortz_worker_jobs_processed": float(processed),
        "shortz_worker_jobs_failed": float(_worker_state["jobs_failed"]),
        "shortz_worker_avg_job_time_seconds": round(avg, 3),
        "shortz_worker_uptime_seconds": round(uptime, 1),
    }


# -------------------------------------------------
# AGGREGATE
# -------------------------------------------------

def collect_all_metrics() -> dict[str, float]:
    """Merge worker, GPU, and queue metrics into a single dict."""
    metrics: dict[str, float] = {}
    metrics.update(get_worker_metrics())

    try:
        metrics.update(get_gpu_metrics_flat())
    except Exception:
        metrics["shortz_gpu_available"] = 0

    try:
        metrics.update(get_queue_metrics_flat())
    except Exception:
        metrics["shortz_queue_length"] = -1

    return metrics


# -------------------------------------------------
# PROMETHEUS TEXT FORMAT
# -------------------------------------------------

_HELP_MAP: dict[str, str] = {
    "shortz_worker_jobs_processed":        "Total number of jobs processed by the worker.",
    "shortz_worker_jobs_failed":           "Total number of jobs that failed.",
    "shortz_worker_avg_job_time_seconds":  "Average job processing time in seconds.",
    "shortz_worker_uptime_seconds":        "Worker uptime in seconds.",
    "shortz_gpu_available":                "Whether an NVIDIA GPU is available (1/0).",
    "shortz_queue_length":                 "Number of jobs waiting in the Redis queue.",
    "shortz_workers_active":               "Number of workers currently processing jobs.",
    "shortz_jobs_processing":              "Number of jobs currently being processed.",
    "shortz_jobs_total":                   "Total number of jobs tracked in Redis.",
    "shortz_jobs_queued":                  "Jobs in queued state.",
    "shortz_jobs_running":                 "Jobs in running state.",
    "shortz_jobs_complete":                "Jobs in complete state.",
    "shortz_jobs_failed":                  "Jobs in failed state.",
}

_TYPE_MAP: dict[str, str] = {
    "shortz_worker_jobs_processed":       "counter",
    "shortz_worker_jobs_failed":          "counter",
    "shortz_worker_avg_job_time_seconds": "gauge",
    "shortz_worker_uptime_seconds":       "gauge",
    "shortz_gpu_available":               "gauge",
    "shortz_queue_length":                "gauge",
    "shortz_workers_active":              "gauge",
    "shortz_jobs_processing":             "gauge",
    "shortz_jobs_total":                  "gauge",
    "shortz_jobs_queued":                 "gauge",
    "shortz_jobs_running":                "gauge",
    "shortz_jobs_complete":               "gauge",
    "shortz_jobs_failed":                 "gauge",
}


def render_prometheus() -> str:
    """
    Return all metrics in Prometheus text exposition format.

    Example output:
        # HELP shortz_queue_length Number of jobs waiting in the Redis queue.
        # TYPE shortz_queue_length gauge
        shortz_queue_length 3
    """
    metrics = collect_all_metrics()
    lines: list[str] = []
    seen: set[str] = set()

    for key, value in sorted(metrics.items()):
        # Strip GPU-index suffix to find the base metric name for HELP/TYPE
        base = key
        for digit_suffix in "0123456789":
            # e.g. shortz_gpu0_memory_used_mb → keep as-is for value line
            pass

        if base not in seen:
            help_text = _HELP_MAP.get(base, "")
            type_text = _TYPE_MAP.get(base, "gauge")
            if help_text:
                lines.append(f"# HELP {key} {help_text}")
            lines.append(f"# TYPE {key} {type_text}")
            seen.add(base)

        lines.append(f"{key} {value}")

    lines.append("")  # trailing newline
    return "\n".join(lines)
