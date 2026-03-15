# Architecture

## System Overview

Shortz is a distributed AI video generation system with four components communicating via Redis:

```
┌──────────────────────────────────────────────────────────────────┐
│                        SUPERVISOR                                │
│  Launches Redis → Worker → API → GUI                             │
│  Monitors processes · Restart backoff · Health gates             │
└──────────────────────────────────────────────────────────────────┘
         │              │             │              │
    ┌────▼────┐   ┌─────▼─────┐  ┌───▼───┐   ┌─────▼─────┐
    │  Redis  │   │  Worker   │  │  API  │   │   GUI     │
    │  Queue  │◄──│  (GPU)    │  │(Fast  │   │  (PyQt6)  │
    │         │──►│           │  │ API)  │   │           │
    └─────────┘   └───────────┘  └───────┘   └───────────┘
```

## Pipeline Flow

Each job executes these stages sequentially:

```
1. TEXT        Read script from input/input.txt
2. VOICE       XTTS v2 synthesizes speech → .wav
3. ALIGNMENT   Whisper word-level timestamps
4. SUBTITLES   Build karaoke ASS file
5. RENDER      FFmpeg composites video → .mp4
```

### VRAM Management

The pipeline is designed for 4 GB VRAM GPUs:

| Stage | Model | VRAM | Strategy |
|-------|-------|------|----------|
| Voice | XTTS v2 | ~2 GB | Loaded at worker start, shared across jobs |
| Alignment | Whisper Small | ~1 GB | Loaded per-job, released after alignment |
| Render | FFmpeg | 0 | CPU-only subprocess |

## Redis Data Structures

### Queues

| Key | Type | Purpose |
|-----|------|---------|
| `shortz_jobs` | LIST | Pending job queue (FIFO) |
| `shortz_processing` | LIST | Currently processing (reliability) |

### Job Metadata

Each job has a Redis hash:

```
job:{job_id} → {
    status:     "queued" | "running" | "complete" | "failed"
    progress:   "0" .. "100"
    stage:      "waiting" | "text" | "voice" | "alignment" | "subtitles" | "render" | "done"
    voice_path: "/path/to/voice.wav"
    created:    unix_timestamp
    updated:    unix_timestamp
}
```

### Queue Operations

- **Enqueue:** atomic pipeline: `HSET` metadata + `RPUSH` to queue
- **Dequeue:** `BLMOVE` (Redis 6.2+) or `BRPOPLPUSH` (fallback)
- **Complete:** `LREM` from processing queue

## Threading Model

### GUI (PyQt6)

The GUI runs on the Qt event loop. All network I/O happens in QThread workers:

| Thread | Purpose | Signal |
|--------|---------|--------|
| `StatusPollerThread` | Polls `/status/{id}` | `result_ready(dict)` |
| `HealthCheckThread` | Polls `/health` | `health_updated(dict)` |
| `JobSubmitterThread` | POST `/generate` | `jobs_created(list)` |
| `ActiveJobDetectorThread` | GET `/active_job` | `job_found(str)` |

Shared state is protected by `QMutex`. All signal→slot connections use `QueuedConnection` to ensure thread safety.

### API (FastAPI)

FastAPI runs on uvicorn's async event loop. Blocking Redis calls are offloaded via `asyncio.to_thread()`.

The Redis client is **lazy-initialised** on first request — not at module import — to survive slow Redis startup without crashing.

### Worker

The worker runs a synchronous blocking loop:
1. `BLMOVE` blocks until a job arrives
2. Process the pipeline
3. `LREM` from processing queue
4. Loop

Connection health is verified before each blocking pop via `PING`.

## Startup Sequence

```
Supervisor
  │
  ├── 1. Verify WSL
  ├── 2. Start Redis (with PONG retry)
  ├── 3. Start Worker (wait for XTTS voice model)
  ├── 4. Start API
  ├── 5. wait_for_api() — polls /health up to 30s
  ├── 6. Start GUI
  │      └── QTimer.singleShot(500ms) → ActiveJobDetectorThread
  │          ├── job found → attach poller
  │          └── no job → POST /generate
  └── 7. Monitor loop (5s interval, exponential restart backoff)
```

## Error Handling

| Layer | Strategy |
|-------|----------|
| API | Global exception handler → 500 JSON, never crashes |
| Worker | Per-job try/except, Redis reconnect with backoff |
| GUI | Per-thread error signals, exponential poll backoff |
| Supervisor | Restart backoff (2s→4s→8s…60s max), max 10 attempts |
