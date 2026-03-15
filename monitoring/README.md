# Shortz Monitoring & Observability

Real-time monitoring, metrics, and dashboards for the Shortz AI video generation platform.

---

## Architecture

```
┌──────────┐    ┌──────────────┐    ┌───────────────┐
│   GUI    │───▶│  FastAPI API  │───▶│  Redis Queue  │
│          │    │  :8000        │    │  :6379        │
└──────────┘    └──────────────┘    └──────┬────────┘
                                           │
                                    ┌──────▼────────┐
                                    │    Worker      │
                                    │ Shortz Pipeline│
                                    └──────┬────────┘
                                           │
                                    ┌──────▼────────┐
                                    │  Video Output  │
                                    └───────────────┘

                ── Monitoring Layer ──

┌──────────────────┐    ┌──────────────┐    ┌──────────┐
│ Monitoring API   │───▶│  Prometheus  │───▶│ Grafana  │
│ :8070            │    │  :9090       │    │ :3000    │
│  /queue          │    │              │    │          │
│  /metrics        │    └──────────────┘    └──────────┘
│  /gpu            │
│  /health         │
│  /dashboard      │
│  /api/jobs       │
└──────────────────┘
```

---

## Quick Start (Local)

### 1. Install dependencies

```bash
pip install fastapi uvicorn redis
```

### 2. Start Redis

```bash
redis-server
```

### 3. Start the monitoring API

```bash
python -m monitoring.monitoring_api
```

### 4. Open the dashboard

```
http://localhost:8070/dashboard
```

---

## Quick Start (Docker)

### Full stack with observability

```bash
docker compose -f docker-compose.yml -f docker/docker-compose.monitoring.yml up -d
```

This starts:
| Service | Port | Description |
|---|---|---|
| `redis` | 6379 | Job queue |
| `shortz-api` | 8000 | Video generation API |
| `shortz-worker` | — | Pipeline worker |
| `shortz-monitor` | 8070 | Monitoring API + Dashboard |
| `prometheus` | 9090 | Metrics store |
| `grafana` | 3000 | Dashboards (admin/shortz) |

---

## API Endpoints

All monitoring endpoints are served on **port 8070**.

### `GET /queue`
Queue statistics.
```json
{
  "queue_length": 2,
  "workers_active": 1,
  "jobs_processing": 1,
  "total_jobs": 15,
  "jobs_by_status": { "queued": 2, "running": 1, "complete": 10, "failed": 2 }
}
```

### `GET /metrics`
Prometheus text exposition format.
```
# HELP shortz_queue_length Number of jobs waiting in the Redis queue.
# TYPE shortz_queue_length gauge
shortz_queue_length 2
shortz_worker_jobs_processed 42
shortz_gpu0_utilization_pct 78.0
```

### `GET /gpu`
GPU stats via nvidia-smi.
```json
{
  "available": true,
  "gpus": [{
    "index": 0,
    "name": "NVIDIA GeForce RTX 4090",
    "memory_used_mb": 4200.0,
    "memory_total_mb": 24564.0,
    "gpu_util_pct": 78.0,
    "temperature_c": 62.0
  }]
}
```

### `GET /health`
System health check.
```json
{
  "redis_status": "healthy",
  "api_status": "healthy",
  "worker_status": "active",
  "gpu_status": "available",
  "uptime_seconds": 3621.5
}
```

### `GET /dashboard`
HTML monitoring dashboard (auto-refreshes every 5 seconds).

### `GET /api/jobs?limit=50`
Recent job list in JSON.

---

## Logging

Structured JSON logs are written to `logs/`:

| File | Contents |
|---|---|
| `system.log` | General system events |
| `worker.log` | Worker lifecycle, job processing |
| `api.log` | API request/response events |
| `jobs.log` | Per-job structured entries |

Each log entry includes: `timestamp`, `level`, `logger`, `message`, and optional `job_id`, `status`, `duration`, `error`.

---

## Grafana

Default credentials: **admin / shortz**

Pre-built dashboard panels:
- Queue Length, Workers Active, Jobs Completed, Jobs Failed (stat panels)
- Job Throughput over time (time series)
- Worker Uptime (time series)
- Average Job Time (gauge)
- GPU Memory Usage (time series)
- GPU Utilization & Temperature (time series)

---

## File Structure

```
monitoring/
├── __init__.py              # Package marker
├── logging_config.py        # Structured JSON logging
├── gpu_monitor.py           # nvidia-smi GPU metrics
├── queue_monitor.py         # Redis queue stats
├── metrics_collector.py     # Prometheus metrics aggregator
├── monitoring_api.py        # FastAPI monitoring server
├── dashboard/
│   └── index.html           # Web dashboard (Tailwind)
└── README.md                # This file

docker/
├── docker-compose.monitoring.yml
├── prometheus/
│   └── prometheus.yml
└── grafana/
    ├── provisioning/
    │   ├── datasources/datasource.yml
    │   └── dashboards/dashboard.yml
    └── dashboards/
        └── shortz_dashboard.json
```
