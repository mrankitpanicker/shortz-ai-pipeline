# System Architecture

## Overview

Shortz is a local AI inference pipeline that generates short-form videos. It runs on a single machine with an NVIDIA GPU and uses a job-queue architecture to decouple the GUI from the compute-heavy pipeline.

## Components

### Core Pipeline (`Shortz.py`)

Main function: `main_generate()`

```
Text input
  ↓
XTTS v2 voice synthesis (GPU — VRAM intensive)
  ↓
Whisper word-level alignment (GPU — separate model)
  ↓
ASS karaoke subtitle generation (CPU)
  ↓
FFmpeg 1080×1920 video rendering (CPU/GPU)
  ↓
MP4 output
```

> **GPU memory constraint**: XTTS and Whisper cannot be loaded simultaneously on a 4GB VRAM GPU. The pipeline handles this by loading one model at a time within `main_generate()`.

### Queue System

```
FastAPI :8000
  │  POST /generate → enqueue_job() → RPUSH shortz_jobs
  │  GET /status/{id} → get_job_status() → HGETALL job:{id}
  │
Redis :6379
  │  Queue: shortz_jobs (list)
  │  Status: job:{id} (hash) → {status, created, updated, error}
  │
Worker
  │  BLPOP shortz_jobs → Shortz.main_generate()
  │  Updates job:{id} → running → complete/failed
```

### GUI Architecture

**Production path** (`services/gui_main.py`):
```
gui.MainWindow (UI)
  ← gui_bridge.BridgedController
    ← APIPollingWorker (QThread)
      ← api_client.ShortzAPIClient
        ← HTTP POST /generate
        ← HTTP GET /status/{id} (polling every 2s)
```

The GUI submits jobs via the API and polls for progress. It never touches `Shortz.py` directly.

**Legacy path** (`main.pyw`) — bypasses the queue:
```
gui.MainWindow (UI)
  ← MainController
    ← EngineWorker (QThread)
      ← Shortz.main_generate()  ← DIRECT CALL (dangerous on 4GB GPU)
```

### Supervisor (`system/shortz_supervisor_v2.py`)

Launches all components in sequence:
1. Verify WSL
2. Start Redis (via WSL)
3. Start Worker (`worker.py`) — waits for XTTS load
4. Start API (`api_server.py`) via Uvicorn
5. Start GUI (`services/gui_main.py`) — API-bridged
6. Auto-trigger `POST /generate`
7. Start Monitoring API (port 8070)
8. Monitor loop — auto-restart crashed processes

### Monitoring Layer

```
monitoring_api.py :8070
  ├── GET /queue     ← queue_monitor.py → Redis
  ├── GET /metrics   ← metrics_collector.py → Prometheus format
  ├── GET /gpu       ← gpu_monitor.py → nvidia-smi
  ├── GET /health    ← Redis + API + GPU checks
  ├── GET /dashboard ← dashboard/index.html
  └── GET /api/jobs  ← queue_monitor.list_jobs()
         │
    Prometheus :9090 (scrapes /metrics every 15s)
         │
    Grafana :3000 (visualizes dashboards)
```

## Data Flow Diagram

```
┌─────────┐     HTTP      ┌──────────┐    RPUSH    ┌─────────┐
│   GUI   │──────────────→│  FastAPI  │───────────→│  Redis   │
│  (PyQt) │  POST/generate│  :8000   │  shortz_jobs│  :6379  │
└─────────┘               └──────────┘             └────┬────┘
     ↑                                                   │ BLPOP
     │ poll GET /status                                  ↓
     │                                           ┌──────────┐
     └───────────────────────────────────────────│  Worker   │
                                                  │ Shortz.py│
                                                  └────┬─────┘
                                                       ↓
                                                 output/video/
```

## Port Map

| Port | Service | Protocol |
|------|---------|----------|
| 6379 | Redis | TCP |
| 8000 | FastAPI (generate/status) | HTTP |
| 8070 | Monitoring API + Dashboard | HTTP |
| 9090 | Prometheus | HTTP |
| 3000 | Grafana | HTTP |
