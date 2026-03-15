"""
worker.py — Job worker for the Shortz pipeline.

Continuously listens to the Redis queue and calls
Shortz.main_generate() directly (no subprocesses).

Reliability features:
  • Verifies Redis connection before each blocking queue pop.
    If Redis is down, waits 3s and retries — never crashes the loop.
  • Uses get_redis_worker() (no socket timeout) for blocking BLMOVE.
  • Calls complete_job() to clean up processing queue on finish or failure.
"""

import time
import traceback
import logging
from redis_queue import get_redis_worker, dequeue_job, set_job_status, complete_job
import Shortz

log = logging.getLogger("shortz.worker")


# -------------------------------------------------
# REDIS RECONNECT HELPER
# -------------------------------------------------

def _get_healthy_redis(max_wait: int = 60):
    """Return a Redis client that successfully pings, retrying with backoff.

    Blocks until Redis is reachable or max_wait seconds elapse.
    Returns the Redis client, or None on timeout.
    """
    attempt = 0
    backoff = 3
    deadline = time.time() + max_wait

    while time.time() < deadline:
        attempt += 1
        try:
            r = get_redis_worker()
            r.ping()
            if attempt > 1:
                log.info("[INFO] Redis reconnected (attempt %d)", attempt)
            return r
        except Exception as e:
            log.warning("[WARN] Redis not ready (attempt %d): %s — retrying in %ds", attempt, e, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)

    log.error("[ERROR] Redis unreachable after %ds — giving up this cycle", max_wait)
    return None


# -------------------------------------------------
# WORKER LOOP
# -------------------------------------------------

def worker_loop():
    """Block on the Redis queue and process jobs one at a time.

    Startup:
      Waits for Redis to become healthy before entering the queue loop.
    Mid-run recovery:
      If dequeue_job returns None (Redis error), re-validates the connection
      before blocking again.
    """
    log.info("[INFO] Worker started — waiting for Redis …")
    print("Worker started — waiting for Redis …")

    # Initial connection with generous timeout (XTTS may delay startup)
    r = _get_healthy_redis(max_wait=120)
    if r is None:
        log.error("[ERROR] Cannot connect to Redis — worker exiting")
        return

    log.info("[INFO] Worker connected to Redis — waiting for jobs")
    print("Worker connected — waiting for jobs …")

    while True:
        # Verify connection before the blocking pop
        try:
            r.ping()
        except Exception:
            log.warning("[WARN] Redis connection lost — reconnecting …")
            r = _get_healthy_redis(max_wait=60)
            if r is None:
                log.error("[ERROR] Redis reconnect failed — retrying in 10s")
                time.sleep(10)
                continue

        job_id = dequeue_job(r)  # blocking BLMOVE/BRPOPLPUSH

        if job_id is None:
            # dequeue returned None usually means a Redis error during the pop
            log.warning("[WARN] dequeue_job returned None — will re-validate connection")
            time.sleep(1)
            continue

        log.info("[INFO] Worker started processing job: %s", job_id)
        print(f"[{job_id}] picked up — running pipeline")
        set_job_status(r, job_id, "running", stage="text", progress=0)

        try:
            Shortz.main_generate()
            set_job_status(r, job_id, "complete", progress=100, stage="done")
            complete_job(r, job_id)
            log.info("[INFO] Job complete: %s", job_id)
            print(f"[{job_id}] complete")

        except Exception as e:
            tb = traceback.format_exc()
            log.error("[ERROR] Worker failure on job %s: %s", job_id, e)
            set_job_status(r, job_id, "failed", error=str(e))
            complete_job(r, job_id)
            print(f"[{job_id}] FAILED — {e}\n{tb}")


# -------------------------------------------------
# ENTRYPOINT
# -------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    worker_loop()
