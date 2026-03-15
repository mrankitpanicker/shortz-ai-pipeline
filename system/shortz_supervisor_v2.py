"""
shortz_supervisor_v2.py — Production supervisor for the Shortz AI stack.

Key difference from shortz_supervisor.py:
    Launches services/gui_main.py instead of main.pyw, ensuring
    the GUI uses the API→Redis→Worker pipeline (not direct Shortz calls).

Lifecycle:
    1. Verify WSL
    2. Ensure Redis is running (auto-start + PONG retry)
    3. Start Worker (gpu-worker-1) with XTTS readiness detection
    4. Start FastAPI API server
    5. Start GUI (via services/gui_main.py — API-bridged controller)
    6. Auto-trigger generation via API
    7. Start Monitoring API (port 8070)
    8. Monitor all processes — auto-restart on crash
"""

import subprocess
import sys
import os
import time
import logging
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

# -------------------------------------------------
# CONFIG
# -------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent.parent
PYTHON      = sys.executable
LOG_DIR     = PROJECT_DIR / "logs"

WORKER_ID   = "gpu-worker-1"
QUEUE_NAME  = "shortz_jobs"
GPU_COUNT   = 1

REDIS_RETRY_INTERVAL = 2
REDIS_MAX_RETRIES    = 15
MONITOR_INTERVAL     = 5
XTTS_DETECT_TIMEOUT  = 300
API_URL              = "http://127.0.0.1:8000"
MONITORING_URL       = "http://127.0.0.1:8070"

# -------------------------------------------------
# LOGGING
# -------------------------------------------------

LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILES = {
    "system": LOG_DIR / "system.log",
    "worker": LOG_DIR / "worker.log",
    "api":    LOG_DIR / "api.log",
    "gui":    LOG_DIR / "gui.log",
    "monitor": LOG_DIR / "monitor.log",
}


def setup_logger(name: str, filepath: Path) -> logging.Logger:
    logger = logging.getLogger(f"supervisor.{name}")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(message)s", "%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(filepath, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    if name == "system":
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    return logger


syslog = setup_logger("system", LOG_FILES["system"])


# -------------------------------------------------
# HELPERS
# -------------------------------------------------

def run_silent(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, capture_output=True, text=True, cwd=str(PROJECT_DIR),
    )


def is_process_running(script_name: str) -> bool:
    """Check if a Python script is already running via wmic."""
    try:
        r = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'",
             "get", "CommandLine", "/FORMAT:LIST"],
            capture_output=True, text=True,
        )
        return script_name in r.stdout
    except Exception:
        return False


def spawn(args: list[str], label: str, logfile: Path) -> subprocess.Popen:
    """Spawn a child process with stdout piped to a log file."""
    fh = open(logfile, "a", encoding="utf-8")
    proc = subprocess.Popen(
        args, cwd=str(PROJECT_DIR),
        stdout=fh, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    syslog.info("[START] %s  (PID %d)", label, proc.pid)
    return proc


# -------------------------------------------------
# STEP 1 — WSL
# -------------------------------------------------

def verify_wsl() -> None:
    r = run_silent(["wsl", "echo", "OK"])
    if r.stdout.strip() != "OK":
        syslog.error("[FAIL]  WSL is not available")
        sys.exit(1)
    syslog.info("[OK]    WSL available")


# -------------------------------------------------
# STEP 2 — REDIS
# -------------------------------------------------

def ensure_redis() -> None:
    r = run_silent(["wsl", "redis-cli", "ping"])
    if r.stdout.strip() == "PONG":
        syslog.info("[OK]    Redis already running")
        return

    syslog.info("[....]  Starting Redis via WSL")
    run_silent(["wsl", "redis-server", "--daemonize", "yes"])

    for attempt in range(1, REDIS_MAX_RETRIES + 1):
        time.sleep(REDIS_RETRY_INTERVAL)
        r = run_silent(["wsl", "redis-cli", "ping"])
        if r.stdout.strip() == "PONG":
            syslog.info("[OK]    Redis running  (attempt %d)", attempt)
            return
        syslog.info("[....]  Redis health-check %d/%d", attempt, REDIS_MAX_RETRIES)

    syslog.error("[FAIL]  Redis did not respond after %d attempts", REDIS_MAX_RETRIES)
    sys.exit(1)


# -------------------------------------------------
# STEP 3 — WORKER
# -------------------------------------------------

def start_worker() -> subprocess.Popen | None:
    if is_process_running("worker.py"):
        syslog.info("[WARN]  Worker already running — skipping")
        return None

    proc = spawn(
        [PYTHON, "worker.py"],
        f"Worker {WORKER_ID}  [queue={QUEUE_NAME}  gpu={GPU_COUNT}]",
        LOG_FILES["worker"],
    )
    detect_xtts(proc)
    return proc


def detect_xtts(proc: subprocess.Popen) -> None:
    """Watch worker log for 'Voice Model Online' to confirm XTTS loaded."""
    syslog.info("[....]  Waiting for XTTS voice engine …")
    start = time.time()

    while time.time() - start < XTTS_DETECT_TIMEOUT:
        if proc.poll() is not None:
            syslog.warning("[WARN]  Worker exited before XTTS loaded")
            return
        try:
            content = LOG_FILES["worker"].read_text(encoding="utf-8", errors="ignore")
            if "Voice Model Online" in content:
                syslog.info("[READY] XTTS voice engine loaded")
                return
        except Exception:
            pass
        time.sleep(2)

    syslog.warning("[WARN]  XTTS detection timed out after %ds", XTTS_DETECT_TIMEOUT)


# -------------------------------------------------
# STEP 4 — API SERVER
# -------------------------------------------------

def start_api() -> subprocess.Popen:
    return spawn(
        [PYTHON, "-m", "uvicorn", "api_server:app",
         "--host", "127.0.0.1", "--port", "8000"],
        "API server  [http://127.0.0.1:8000]",
        LOG_FILES["api"],
    )


# -------------------------------------------------
# STEP 5 — GUI (API-bridged)
# -------------------------------------------------

def start_gui() -> subprocess.Popen:
    """
    Launch services/gui_main.py (NOT main.pyw).
    This ensures the GUI goes through the API instead of calling
    Shortz.main_generate() directly.
    """
    return spawn(
        [PYTHON, str(PROJECT_DIR / "services" / "gui_main.py"), "--auto"],
        "GUI (API-bridged)",
        LOG_FILES["gui"],
    )


# -------------------------------------------------
# STEP 6 — AUTO-TRIGGER
# -------------------------------------------------

def auto_trigger() -> None:
    """Send POST /generate to kick off the pipeline."""
    syslog.info("[....]  Auto-triggering generation via API")
    for attempt in range(1, 6):
        try:
            req = urllib.request.Request(
                f"{API_URL}/generate", data=b"", method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read().decode()
                syslog.info("[OK]    Auto-trigger sent  (response: %s)", body.strip())
                return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(2)

    syslog.warning("[WARN]  Auto-trigger failed — GUI will poll and can trigger manually")


# -------------------------------------------------
# STEP 7 — MONITORING API
# -------------------------------------------------

def start_monitoring() -> subprocess.Popen:
    """Start the monitoring API on port 8070."""
    return spawn(
        [PYTHON, "-m", "monitoring.monitoring_api"],
        f"Monitoring API  [{MONITORING_URL}]",
        LOG_FILES["monitor"],
    )


# -------------------------------------------------
# PROCESS MONITOR
# -------------------------------------------------

def monitor_loop(
    worker: subprocess.Popen | None,
    api: subprocess.Popen,
    gui: subprocess.Popen,
    monitor: subprocess.Popen | None,
) -> None:
    syslog.info("")
    syslog.info("Supervisor active — monitoring every %ds", MONITOR_INTERVAL)
    syslog.info("")

    while True:
        time.sleep(MONITOR_INTERVAL)

        # GUI closed → full shutdown
        if gui.poll() is not None:
            syslog.info("[EXIT]  GUI closed — shutting down")
            break

        # Worker crash → restart
        if worker is not None and worker.poll() is not None:
            code = worker.returncode
            syslog.warning("[CRASH] Worker exited (code %d) — restarting", code)
            worker = spawn(
                [PYTHON, "worker.py"],
                f"Worker {WORKER_ID} (restarted)",
                LOG_FILES["worker"],
            )

        # API crash → restart
        if api.poll() is not None:
            syslog.warning("[CRASH] API server exited — restarting")
            api = spawn(
                [PYTHON, "-m", "uvicorn", "api_server:app",
                 "--host", "127.0.0.1", "--port", "8000"],
                "API server (restarted)",
                LOG_FILES["api"],
            )

        # Monitor crash → restart
        if monitor is not None and monitor.poll() is not None:
            syslog.warning("[CRASH] Monitoring API exited — restarting")
            monitor = start_monitoring()

    # Clean shutdown
    for label, proc in [("Worker", worker), ("API", api), ("GUI", gui), ("Monitor", monitor)]:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            syslog.info("[STOP]  %s terminated", label)

    syslog.info("[OK]    All components stopped")


# -------------------------------------------------
# MAIN
# -------------------------------------------------

def main():
    print()
    print("=" * 60)
    print("   SHORTZ  —  System Supervisor v2 (API-bridged)")
    print("=" * 60)
    print()
    print(f"   Worker:     {WORKER_ID}")
    print(f"   Queue:      {QUEUE_NAME}")
    print(f"   GPU:        {GPU_COUNT}")
    print(f"   API:        {API_URL}")
    print(f"   Monitor:    {MONITORING_URL}")
    print(f"   Dashboard:  {MONITORING_URL}/dashboard")
    print()
    print("-" * 60)
    print()

    syslog.info("Supervisor v2 starting  [%s]", datetime.now().isoformat())

    # 1. WSL
    verify_wsl()

    # 2. Redis
    ensure_redis()

    # 3. Worker (+ XTTS detection)
    worker = start_worker()

    # 4. API
    api = start_api()
    time.sleep(2)

    # 5. GUI (API-bridged — NOT main.pyw)
    gui = start_gui()
    time.sleep(1)

    # 6. Auto-trigger
    auto_trigger()

    # 7. Monitoring
    monitor = None
    try:
        monitor = start_monitoring()
    except Exception as e:
        syslog.warning("[WARN]  Monitoring failed to start: %s", e)

    print()
    print("-" * 60)
    print("   All components launched.")
    print(f"   Dashboard: {MONITORING_URL}/dashboard")
    print("-" * 60)
    print()

    # 8. Monitor loop
    try:
        monitor_loop(worker, api, gui, monitor)
    except KeyboardInterrupt:
        syslog.info("[EXIT]  Ctrl+C — shutting down")
        for proc in [worker, api, gui, monitor]:
            if proc is not None and proc.poll() is None:
                proc.terminate()
        syslog.info("[OK]    All components stopped")


if __name__ == "__main__":
    main()
