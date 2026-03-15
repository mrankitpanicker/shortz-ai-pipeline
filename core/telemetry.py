"""
core/telemetry.py — Stage-level execution telemetry.

Provides a lightweight context manager to time pipeline stages
and emit structured log lines.

Usage:
    with StageTelemetry("tts", job_id="abc123") as t:
        do_work()
    # Logs: 2026-03-15 05:45:23 [INFO] tts Stage complete  job=abc123  elapsed=18.4s
"""

import time
import logging

log = logging.getLogger("shortz.telemetry")


class StageTelemetry:
    """Context manager that times a pipeline stage and logs the result."""

    def __init__(self, stage_name: str, job_id: str = ""):
        self.stage_name = stage_name
        self.job_id = job_id
        self.start_time = 0.0
        self.elapsed = 0.0

    def __enter__(self):
        self.start_time = time.perf_counter()
        log.info("[%s] Stage started  job=%s", self.stage_name, self.job_id[:8])
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed = time.perf_counter() - self.start_time
        if exc_type is not None:
            log.error(
                "[%s] Stage FAILED  job=%s  elapsed=%.1fs  error=%s",
                self.stage_name, self.job_id[:8], self.elapsed, exc_val,
            )
        else:
            log.info(
                "[%s] Stage complete  job=%s  elapsed=%.1fs",
                self.stage_name, self.job_id[:8], self.elapsed,
            )
        return False  # Don't suppress exceptions


class JobTelemetry:
    """Tracks total job execution time and per-stage breakdown."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.start_time = 0.0
        self.stages: dict[str, float] = {}

    def start(self):
        self.start_time = time.perf_counter()
        log.info("[worker] Job started  job=%s", self.job_id[:8])

    def record_stage(self, name: str, elapsed: float):
        self.stages[name] = elapsed

    def finish(self):
        total = time.perf_counter() - self.start_time
        breakdown = "  ".join(f"{k}={v:.1f}s" for k, v in self.stages.items())
        log.info(
            "[worker] Job complete  job=%s  total=%.1fs  %s",
            self.job_id[:8], total, breakdown,
        )
        return total
