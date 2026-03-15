"""
shortz_supervisor.py — Production process supervisor for the Shortz AI stack.

Lifecycle:
  1. Verify WSL
  2. Ensure Redis is running (auto-start + PONG retry)
  3. Start Worker (+ XTTS readiness detection)
  4. Start FastAPI API server
  5. Wait for API health (up to 30s)
  6. Start GUI
  7. Monitor processes — auto-restart on crash with exponential backoff

Key design decisions:
  • The supervisor does NOT call /generate.
    The GUI handles auto-start via its own ActiveJobDetectorThread.
    Having both call /generate is the primary cause of duplicate jobs.
  • The API health check runs before the GUI starts, so the GUI's 500ms
    QTimer.singleShot auto-launch always finds a ready API.
  • Restart backoff prevents rapid loop restart cycles.

Logs: logs/system.log, worker.log, api.log, gui.log
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
from core.error_logger import install_global_handler, log_exception

# -------------------------------------------------
# CONFIG
# -------------------------------------------------

PROJECT_DIR = Path(r"D:\Projects\Shortz")
PYTHON      = r"d:\tts\venv\Scripts\python.exe"
LOG_DIR     = PROJECT_DIR / "logs"

WORKER_ID   = "gpu-worker-1"
QUEUE_NAME  = "shortz_jobs"
GPU_ID = 0

REDIS_RETRY_INTERVAL = 2     # seconds
REDIS_MAX_RETRIES    = 15
MONITOR_INTERVAL     = 5     # seconds
XTTS_DETECT_TIMEOUT  = 300   # seconds to wait for XTTS load
API_HEALTH_TIMEOUT   = 30    # seconds to wait for API readiness
API_URL              = "http://127.0.0.1:8000"

# Restart backoff: seconds between restart attempts (doubles each time, capped)
RESTART_BACKOFF_BASE = 2
RESTART_BACKOFF_MAX  = 60
RESTART_MAX_ATTEMPTS = 10    # after this many consecutive crashes, stop restarting

# -------------------------------------------------
# LOGGING SETUP
# -------------------------------------------------

LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILES = {
    "system": LOG_DIR / "system.log",
    "worker": LOG_DIR / "worker.log",
    "api":    LOG_DIR / "api.log",
    "gui":    LOG_DIR / "gui.log",
}


def setup_logger(name: str, filepath: Path) -> logging.Logger:
    logger = logging.getLogger(name)
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


syslog    = setup_logger("system", LOG_FILES["system"])
workerlog = setup_logger("worker", LOG_FILES["worker"])
apilog    = setup_logger("api",    LOG_FILES["api"])
guilog    = setup_logger("gui",    LOG_FILES["gui"])


# -------------------------------------------------
# HELPERS
# -------------------------------------------------

def run_silent(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_DIR),
    )


def is_worker_running() -> bool:
    try:
        r = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'",
             "get", "CommandLine", "/FORMAT:LIST"],
            capture_output=True, text=True,
        )
        return "worker.py" in r.stdout
    except Exception:
        return False


def spawn(args: list[str], label: str, logfile: Path) -> subprocess.Popen:
    fh = open(logfile, "a", encoding="utf-8")
    proc = subprocess.Popen(
        args,
        cwd=str(PROJECT_DIR),
        stdout=fh,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    syslog.info("[START] %s  (PID %d)", label, proc.pid)
    return proc


# -------------------------------------------------
# STEP 1 — VERIFY WSL
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
    if is_worker_running():
        syslog.info("[WARN]  Worker already running — skipping")
        return None

    proc = spawn(
        [PYTHON, "worker.py"],
        f"Worker {WORKER_ID}  [queue={QUEUE_NAME}  gpu={GPU_ID}]",
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
# STEP 5 — WAIT FOR API HEALTH
# -------------------------------------------------

def wait_for_api(timeout: int = API_HEALTH_TIMEOUT) -> bool:
    """Poll /health until the API responds OK, with a hard timeout.

    Returns True if API is ready, False if it timed out.
    This replaces the arbitrary time.sleep(2) that caused race conditions.
    """
    syslog.info("[....]  Waiting for API health (up to %ds) …", timeout)
    deadline = time.time() + timeout
    attempt = 0

    while time.time() < deadline:
        attempt += 1
        try:
            req = urllib.request.Request(f"{API_URL}/health")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.getcode() == 200:
                    syslog.info("[OK]    API health confirmed  (attempt %d)", attempt)
                    return True
        except Exception:
            pass
        time.sleep(1)

    syslog.error("[FAIL]  API not healthy after %ds", timeout)
    return False


# -------------------------------------------------
# STEP 6 — GUI
# -------------------------------------------------

def start_gui() -> subprocess.Popen:
    return spawn(
        [PYTHON, "main.pyw"],
        "GUI",
        LOG_FILES["gui"],
    )


# -------------------------------------------------
# PROCESS MONITOR (with restart backoff)
# -------------------------------------------------

def monitor_loop(
    worker: subprocess.Popen | None,
    api: subprocess.Popen,
    gui: subprocess.Popen,
) -> None:
    syslog.info("")
    syslog.info("Supervisor active — monitoring every %ds", MONITOR_INTERVAL)
    syslog.info("")

    api_crashes = 0
    worker_crashes = 0
    api_last_restart = 0.0
    worker_last_restart = 0.0

    while True:
        time.sleep(MONITOR_INTERVAL)

        # GUI closed → log + restart (don't shut down workers)
        if gui is not None and gui.poll() is not None:
            gui_code = gui.returncode
            if gui_code == 0:
                syslog.info("[EXIT]  GUI closed normally — shutting down")
                break
            else:
                syslog.warning("[CRASH] GUI exited unexpectedly (code %s) — restarting", gui_code)
                guilog.info("--- GUI CRASH (exit code %s) — restarting ---", gui_code)
                time.sleep(2)
                gui = spawn([PYTHON, "main.pyw"], "GUI (restart)", LOG_FILES["gui"])
                syslog.info("[RESTART] GUI restarted")
                continue

        # API crash → restart with backoff
        if api.poll() is not None:
            api_crashes += 1
            code = api.returncode

            if api_crashes > RESTART_MAX_ATTEMPTS:
                syslog.error(
                    "[FAIL]  API has crashed %d times — giving up. Check api.log.",
                    api_crashes,
                )
                break

            backoff = min(
                RESTART_BACKOFF_BASE * (2 ** (api_crashes - 1)),
                RESTART_BACKOFF_MAX,
            )
            since_last = time.time() - api_last_restart
            if since_last < backoff:
                wait = backoff - since_last
                syslog.warning(
                    "[CRASH] API exited (code %s, crash #%d) — backing off %.0fs",
                    code, api_crashes, wait,
                )
                time.sleep(wait)

            apilog.info("--- RESTART after crash #%d (exit code %s) ---", api_crashes, code)
            api = spawn(
                [PYTHON, "-m", "uvicorn", "api_server:app",
                 "--host", "127.0.0.1", "--port", "8000"],
                f"API server (restart #{api_crashes})",
                LOG_FILES["api"],
            )
            api_last_restart = time.time()
            syslog.info("[RESTART] API server restarted (attempt #%d)", api_crashes)

        # Worker crash → restart with backoff
        if worker is not None and worker.poll() is not None:
            worker_crashes += 1
            code = worker.returncode

            if worker_crashes > RESTART_MAX_ATTEMPTS:
                syslog.error(
                    "[FAIL]  Worker has crashed %d times — giving up.",
                    worker_crashes,
                )
                worker = None
            else:
                backoff = min(
                    RESTART_BACKOFF_BASE * (2 ** (worker_crashes - 1)),
                    RESTART_BACKOFF_MAX,
                )
                since_last = time.time() - worker_last_restart
                if since_last < backoff:
                    time.sleep(backoff - since_last)

                workerlog.info("--- RESTART after crash #%d (exit code %d) ---", worker_crashes, code)
                syslog.warning("[CRASH] Worker exited (code %d, crash #%d) — restarting", code, worker_crashes)
                worker = spawn(
                    [PYTHON, "worker.py"],
                    f"Worker {WORKER_ID} (restart #{worker_crashes})",
                    LOG_FILES["worker"],
                )
                worker_last_restart = time.time()
                detect_xtts(worker)
                syslog.info("[RESTART] Worker restarted (attempt #%d)", worker_crashes)

    # Clean shutdown
    for label, proc in [("Worker", worker), ("API", api), ("GUI", gui)]:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            syslog.info("[STOP]  %s terminated", label)

    syslog.info("[OK]    All components stopped")


# -------------------------------------------------
# MAIN
# -------------------------------------------------

def main():
    print()
    print("=" * 56)
    print("   SHORTZ  —  System Supervisor")
    print("=" * 56)
    print()
    print(f"   Worker:   {WORKER_ID}")
    print(f"   Queue:    {QUEUE_NAME}")
    print(f"   GPU:      {GPU_ID}")
    print(f"   API:      {API_URL}")
    print()
    print("-" * 56)
    print()

    syslog.info("Supervisor starting  [%s]", datetime.now().isoformat())

    # 1. WSL
    verify_wsl()

    # 2. Redis
    ensure_redis()

    # 3. Worker (+ XTTS detection)
    worker = start_worker()

    # 4. API
    api = start_api()

    # 5. Wait for API to be healthy before launching GUI
    #    This eliminates the startup race condition.
    if not wait_for_api():
        syslog.warning("[WARN]  API did not become healthy — GUI may fail to connect")

    # 6. GUI
    #    The GUI handles auto-start via its own ActiveJobDetectorThread.
    #    The supervisor does NOT call /generate — that would create duplicate jobs.
    gui = start_gui()

    print()
    print("-" * 56)
    print("   All components launched.")
    print("   GUI will automatically detect or submit a job.")
    print("-" * 56)
    print()

    # 7. Monitor
    try:
        monitor_loop(worker, api, gui)
    except KeyboardInterrupt:
        syslog.info("[EXIT]  Ctrl+C — shutting down")
        for proc in [worker, api, gui]:
            if proc is not None and proc.poll() is None:
                proc.terminate()
        syslog.info("[OK]    All components stopped")


if __name__ == "__main__":
    install_global_handler()
    main()
