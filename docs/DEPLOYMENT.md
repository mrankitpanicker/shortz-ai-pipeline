# Deployment Guide

## Local Development

### Prerequisites

- Python 3.11+
- Redis 6.2+ (via WSL, Docker, or native)
- FFmpeg + FFprobe (in `bin/` or system PATH)
- CUDA toolkit (for GPU inference; CPU fallback available)

### Setup

```bash
# Clone the repository
git clone https://github.com/youruser/shortz.git
cd shortz

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt
```

### Running Services

**Option 1: Supervisor (recommended for development)**

```bash
python shortz_supervisor.py
```

This starts Redis, Worker, API, and GUI in the correct order with health gates.

**Option 2: Manual**

```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Worker
python worker.py

# Terminal 3: API
python -m uvicorn api_server:app --host 127.0.0.1 --port 8000

# Terminal 4: GUI
python main.pyw
```

---

## Docker Deployment

### Quick Start

```bash
docker compose up --build
```

This starts three services:
- **redis** — Redis 7 Alpine with healthcheck
- **api** — FastAPI server on port 8000
- **worker** — GPU worker with CUDA

### Scaling Workers

Run multiple workers across GPUs:

```bash
docker compose up --build --scale worker=3
```

Each worker claims a job from the Redis queue independently.

### GPU Configuration

Workers use NVIDIA Container Toolkit for GPU access. Set `GPU_ID` per worker:

```yaml
# docker-compose.override.yml
services:
  worker:
    environment:
      - GPU_ID=0
```

For multi-GPU machines, scale workers and assign GPUs:

```bash
GPU_ID=0 docker compose run worker &
GPU_ID=1 docker compose run worker &
```

### Volumes

| Mount | Purpose |
|-------|---------|
| `./output` | Generated video files |
| `./input` | Script input files |
| `./voices` | Voice samples for TTS cloning |
| `./logs` | Runtime and historical logs |

### CPU Fallback

If no GPU is available, remove the `deploy.resources` section from `docker-compose.yml`:

```yaml
services:
  worker:
    # Remove this block:
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]
```

The worker will automatically fall back to CPU inference.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `127.0.0.1` | Redis server hostname |
| `REDIS_PORT` | `6379` | Redis server port |
| `REDIS_DB` | `0` | Redis database number |
| `API_HOST` | `0.0.0.0` | API bind address |
| `API_PORT` | `8000` | API listen port |
| `GPU_ID` | `0` | CUDA device index |
| `WORKER_ID` | `gpu-worker-1` | Worker identifier for logs |
| `OUTPUT_DIR` | `./output` | Video output directory |
| `LOG_DIR` | `./logs` | Log file directory |
| `VOICE_SAMPLE` | `./voices/uvi.wav` | Default voice for TTS |
| `MAX_BATCH_SIZE` | `10` | Maximum jobs per batch request |

---

## Monitoring

### Health Check

```bash
curl http://localhost:8000/health
```

Returns:
```json
{
  "status": "ok",
  "redis": true,
  "redis_latency_ms": 1.2
}
```

### Active Jobs

```bash
curl http://localhost:8000/active_job
```

### Logs

Runtime logs are written to `logs/runtime/`:
```
logs/runtime/api.log
logs/runtime/worker.log
```

Generate historical logs for demo:
```bash
python scripts/generate_history_logs.py --months 6
```
