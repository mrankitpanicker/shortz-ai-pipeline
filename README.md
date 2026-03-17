# Shortz — AI Video Automation Pipeline

<div align="center">

**Automated short-form video generation using local AI models**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)
[![Redis](https://img.shields.io/badge/Redis-7+-DC382D.svg)](https://redis.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## Overview

Shortz is a production-grade AI pipeline that automatically generates short-form videos with synthesized speech and animated subtitles. It runs entirely on local hardware — no cloud APIs required.

**Pipeline:**
```
Script Input → XTTS Voice Synthesis → Whisper Alignment → ASS Subtitles → FFmpeg Render
```

**Architecture:**
```
┌──────────┐    HTTP     ┌──────────┐   Redis    ┌──────────┐    GPU
│  PyQt6   │ ──────────→ │ FastAPI  │ ────────→  │  Worker  │ ──────→ Output
│   GUI    │ ←────────── │   API    │ ←──────────│ Pipeline │    │
└──────────┘   polling   └──────────┘   status   └──────────┘    │
                              │                       │          ▼
                          ┌───┴───┐               ┌───┴────┐  .mp4
                          │ Redis │               │ FFmpeg │  .wav
                          └───────┘               └────────┘  .ass
```

---

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/youruser/shortz.git
cd shortz
docker compose up --build
```

This starts Redis, the API server, and a GPU worker automatically.

### Local Development

```bash
# Prerequisites: Python 3.11+, Redis, FFmpeg, CUDA toolkit

# Install dependencies
pip install -r requirements.txt

# Start Redis (WSL or native)
redis-server --daemonize yes

# Start the API
python -m uvicorn api_server:app --host 127.0.0.1 --port 8000

# Start the worker (in a separate terminal)
python worker.py

# Start the GUI (in a separate terminal)
python main.pyw

# Or use the supervisor to launch everything:
python shortz_supervisor.py
```

---

## System Components

| Component | File | Purpose |
|-----------|------|---------|
| **API** | `api_server.py` | FastAPI server with `/generate`, `/status`, `/active_job`, `/health` |
| **Queue** | `redis_queue.py` | Redis job queue with atomic enqueue, batch support, BLMOVE |
| **Worker** | `worker.py` | GPU worker with Redis reconnect, XTTS + Whisper + FFmpeg pipeline |
| **GUI** | `gui.py` | PyQt6 operator console with real-time progress, health monitoring |
| **Supervisor** | `shortz_supervisor.py` | Process launcher with health gates and restart backoff |
| **Pipeline** | `Shortz.py` | Core video generation: TTS → alignment → subtitles → render |
| **Config** | `core/config.py` | Centralised environment-variable configuration |
| **Logging** | `core/logging_config.py` | Structured logging: `timestamp [LEVEL] service message` |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Liveness probe with Redis latency |
| `POST` | `/generate` | Enqueue 1–10 jobs with optional voice path |
| `GET` | `/status/{job_id}` | Poll single job progress |
| `GET` | `/active_job` | List all active jobs |

### Batch Generation

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"count": 5, "voice_path": "voices/uvi.wav"}'
```

---

## Hardware Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| GPU | GTX 1650 (4 GB) | RTX 3050 (4 GB) |
| RAM | 8 GB | 16 GB |
| CPU | 4 cores | 8 cores |
| Disk | 10 GB | 50 GB |

The pipeline is designed for **low VRAM operation** — models are loaded and unloaded per stage.

---

## Project Structure

```
shortz/
├── api_server.py          # FastAPI endpoints
├── redis_queue.py          # Redis job queue
├── worker.py               # GPU worker
├── Shortz.py               # Core pipeline
├── gui.py                  # PyQt6 GUI
├── main.pyw                # GUI entry point
├── shortz_supervisor.py    # Process supervisor
├── core/
│   ├── config.py           # Environment config
│   └── logging_config.py   # Structured logging
├── scripts/
│   └── generate_history_logs.py  # 6-month log generator
├── docker/
│   ├── api.Dockerfile
│   └── worker.Dockerfile
├── docker-compose.yml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   └── CONTRIBUTING.md
├── voices/                 # Voice samples for TTS cloning
├── input/                  # Script input files
├── output/                 # Generated videos
└── logs/                   # Runtime + historical logs
```

---

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — Pipeline flow, Redis design, threading model
- [Deployment](docs/DEPLOYMENT.md) — Docker setup, GPU config, scaling workers
- [Contributing](docs/CONTRIBUTING.md) — Dev setup, PR guidelines

---

## License

[MIT License](LICENSE)
