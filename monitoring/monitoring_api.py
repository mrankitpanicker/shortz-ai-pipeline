"""
monitoring_api.py — Monitoring & Observability API for the Shortz platform.

A SEPARATE FastAPI app running on port 8070 so the existing api_server.py
on port 8000 remains completely untouched.

Endpoints:
    GET /queue      — queue stats
    GET /metrics    — Prometheus-compatible text metrics
    GET /gpu        — GPU stats
    GET /health     — system health
    GET /dashboard  — web dashboard (HTML)
    GET /api/jobs   — job list JSON for the dashboard
"""

import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from monitoring.gpu_monitor import get_gpu_stats
from monitoring.queue_monitor import get_queue_stats, list_jobs, _get_redis
from monitoring.metrics_collector import render_prometheus
from monitoring.logging_config import get_logger

import redis as redis_lib

# -------------------------------------------------
# APP
# -------------------------------------------------

app = FastAPI(
    title="Shortz Monitoring API",
    description="Monitoring and observability endpoints for the Shortz AI pipeline.",
    version="1.0.0",
)

logger = get_logger("api")

DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"

_startup_time = time.time()

# -------------------------------------------------
# ENDPOINTS
# -------------------------------------------------


@app.get("/queue", tags=["Queue"])
def queue_stats():
    """
    Return current queue statistics.

    - **queue_length** – jobs waiting in the queue.
    - **workers_active** – jobs currently being processed.
    - **jobs_processing** – alias for workers_active.
    """
    try:
        stats = get_queue_stats()
        logger.info("queue_stats requested")
        return stats
    except Exception as exc:
        logger.error(f"queue_stats error: {exc}")
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/metrics", tags=["Metrics"])
def metrics():
    """
    Return all metrics in Prometheus text exposition format.

    Content-Type: text/plain; version=0.0.4
    """
    try:
        body = render_prometheus()
        logger.info("metrics requested")
        return PlainTextResponse(
            body,
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )
    except Exception as exc:
        logger.error(f"metrics error: {exc}")
        return PlainTextResponse(f"# error: {exc}\n", status_code=500)


@app.get("/gpu", tags=["GPU"])
def gpu():
    """
    Return GPU stats: memory used/free, utilization %, temperature.
    """
    try:
        stats = get_gpu_stats()
        logger.info("gpu_stats requested")
        return stats
    except Exception as exc:
        logger.error(f"gpu_stats error: {exc}")
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/health", tags=["Health"])
def health():
    """
    System health check.

    Returns status of: redis, api, worker, gpu.
    """
    result: dict = {
        "api_status": "healthy",
        "uptime_seconds": round(time.time() - _startup_time, 1),
    }

    # Redis
    try:
        r = _get_redis()
        r.ping()
        result["redis_status"] = "healthy"
    except Exception as exc:
        result["redis_status"] = f"unhealthy: {exc}"

    # Worker — check if any job is running (proxy for worker alive)
    try:
        stats = get_queue_stats()
        result["worker_status"] = (
            "active" if stats["workers_active"] > 0 else "idle"
        )
    except Exception:
        result["worker_status"] = "unknown"

    # GPU
    try:
        gpu_info = get_gpu_stats()
        result["gpu_status"] = "available" if gpu_info["available"] else "unavailable"
    except Exception:
        result["gpu_status"] = "unavailable"

    return result


@app.get("/api/jobs", tags=["Jobs"])
def api_jobs(limit: int = 50):
    """
    Return a JSON list of recent jobs for the dashboard.
    """
    try:
        jobs = list_jobs(limit=limit)
        logger.info(f"api_jobs requested (limit={limit})")
        return {"jobs": jobs, "count": len(jobs)}
    except Exception as exc:
        logger.error(f"api_jobs error: {exc}")
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard"])
def dashboard():
    """
    Serve the monitoring dashboard HTML page.
    """
    index_path = DASHBOARD_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            "<h1>Dashboard not found</h1><p>Place index.html in monitoring/dashboard/</p>",
            status_code=404,
        )
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


# -------------------------------------------------
# ENTRYPOINT
# -------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("  Shortz Monitoring API — http://localhost:8070")
    print("  Dashboard            — http://localhost:8070/dashboard")
    print("  Health               — http://localhost:8070/health")
    print("  Prometheus Metrics   — http://localhost:8070/metrics")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8070)
