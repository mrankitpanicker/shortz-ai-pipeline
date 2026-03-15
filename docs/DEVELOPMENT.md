# Development Guide

## Project Conventions

### Protected Files

These files contain the working pipeline logic and must **not** be modified:

| File | Purpose |
|------|---------|
| `Shortz.py` | Core AI pipeline (`main_generate()`) |
| `worker.py` | Redis queue worker loop |
| `api_server.py` | FastAPI endpoints |
| `redis_queue.py` | Redis queue utilities |
| `main.pyw` | Legacy GUI controller (kept for reference) |
| `gui.py` | PyQt6 GUI layout and widgets |

To add features, create new modules that wrap or extend these files.

### Adding New API Endpoints

Create a new FastAPI router in `services/` and mount it on the existing app, or add monitoring endpoints to `monitoring/monitoring_api.py`.

### Adding New Pipeline Steps

Wrap `Shortz.main_generate()` from a new module — do not edit `Shortz.py` directly.

### Adding New Monitoring Metrics

1. Add a collector function in `monitoring/metrics_collector.py`
2. Add HELP/TYPE metadata in the `_HELP_MAP` and `_TYPE_MAP` dicts
3. The `/metrics` endpoint will expose them automatically

---

## Code Organization

```
Shortz/
├── Core (DO NOT MODIFY)
│   ├── Shortz.py          — AI pipeline
│   ├── worker.py          — Queue consumer
│   ├── api_server.py      — HTTP API
│   └── redis_queue.py     — Queue helpers
│
├── services/              — New service layer
│   ├── api_client.py      — HTTP client for API
│   ├── gui_bridge.py      — API-based GUI controller
│   └── gui_main.py        — Production GUI entry point
│
├── system/                — Orchestration
│   └── shortz_supervisor_v2.py
│
├── monitoring/            — Observability
│   ├── monitoring_api.py
│   ├── gpu_monitor.py
│   ├── queue_monitor.py
│   ├── metrics_collector.py
│   ├── logging_config.py
│   └── dashboard/
│
└── docs/                  — Documentation
```

---

## GUI Development

### Architecture

The GUI has two modes:

| Mode | Entry Point | Controller | Pipeline Access |
|------|-------------|-----------|----------------|
| **Production** | `services/gui_main.py` | `BridgedController` | Via API → Redis → Worker |
| **Legacy** | `main.pyw` | `MainController` | Direct `Shortz.main_generate()` |

**Always use production mode.** The legacy mode loads XTTS inside the GUI process, which conflicts with the worker's GPU usage on 4GB VRAM GPUs.

### Signal Interface

Both controllers emit the same signals to the GUI:
- `log_update(str)` — text for the log panel
- `status_update(float, str)` — progress percentage + status text
- `process_finished(float, str)` — final progress + final status

---

## Testing

### Syntax Check

```powershell
python -m py_compile services/api_client.py
python -m py_compile services/gui_bridge.py
python -m py_compile services/gui_main.py
python -m py_compile system/shortz_supervisor_v2.py
```

### API Smoke Test

```bash
# Submit job
curl -X POST http://localhost:8000/generate
# → {"job_id": "...", "status": "queued"}

# Check status
curl http://localhost:8000/status/<job_id>
# → {"status": "running", ...}
```

### Health Check

```bash
curl http://localhost:8070/health
```

---

## Logging

Structured JSON logs are written to `logs/`:

| File | Source |
|------|--------|
| `system.log` | Supervisor events |
| `worker.log` | Worker + pipeline output |
| `api.log` | FastAPI/Uvicorn |
| `gui.log` | GUI output |
| `jobs.log` | Per-job events (from monitoring) |
