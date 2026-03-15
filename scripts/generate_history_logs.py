"""
scripts/generate_history_logs.py — Realistic 6-month operation log generator.

Simulates the Shortz system running daily for 6 months, producing log files
that look like real production output for portfolio / demo purposes.

Output structure:
    logs/history/YYYY-MM/DD.log

Usage:
    python scripts/generate_history_logs.py
    python scripts/generate_history_logs.py --months 3
    python scripts/generate_history_logs.py --verify      # dry-run, prints sample
"""

import argparse
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# ─── Project root so we can resolve log dir without importing full stack ────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_HISTORY_DIR = PROJECT_ROOT / "logs" / "history"

# ─── Pipeline stage sequence ────────────────────────────────────────────────
STAGES = [
    ("text",      "📜 Reading Script…",                        (0.5, 2.0)),
    ("voice",     "🎶 Synthesizing Speech Segments",           (18.0, 45.0)),
    ("alignment", "⏱️ Synchronizing Word Timeline…",          (4.0, 12.0)),
    ("subtitles", "📝 Crafting Dynamic Highlights…",           (1.0, 3.0)),
    ("render",    "🎥 Rendering Final Sequence…",              (8.0, 22.0)),
]

WORKER_IDS = ["gpu-worker-1", "gpu-worker-2"]
VOICE_SAMPLES = ["uvi.wav", "female_01.wav", "male_deep.wav"]


# ─── Helpers ────────────────────────────────────────────────────────────────

def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _rand_start(day: datetime) -> datetime:
    """Return a random hour:minute within 06:00–22:00 on the given day."""
    hour = random.randint(6, 21)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return day.replace(hour=hour, minute=minute, second=second, microsecond=0)


def _generate_job_log(job_id: str, t: datetime, voice: str, worker: str) -> tuple[list[str], datetime]:
    """Generate log lines for a single job. Returns (lines, end_time)."""
    lines = []

    def line(dt, level, msg):
        lines.append(f"{_ts(dt)}  [{level:<5}]  {worker}  {msg}")

    line(t, "INFO", f"Job queued: {job_id[:8]}…")
    t += timedelta(seconds=random.uniform(0.5, 2.5))
    line(t, "INFO", f"Worker started processing job: {job_id[:8]}…")
    t += timedelta(seconds=random.uniform(0.2, 1.0))
    line(t, "INFO", f"Voice sample: {voice}")

    for stage_key, stage_label, (lo, hi) in STAGES:
        duration = random.uniform(lo, hi)
        line(t, "INFO", f"Stage → {stage_key}")
        t += timedelta(seconds=0.1)

        # Emit progress updates for voice / render stages
        if stage_key in ("voice", "render"):
            steps = random.randint(3, 6)
            for i in range(1, steps + 1):
                pct = int(i * 100 / steps)
                mid = t + timedelta(seconds=duration * i / steps)
                lines.append(f"  {stage_label}: {pct}%")

        line(t + timedelta(seconds=duration), "INFO", f"{stage_label}  [done]")
        t += timedelta(seconds=duration + random.uniform(0.1, 0.5))

    line(t, "INFO", f"Job complete: {job_id[:8]}…  ✅")
    t += timedelta(seconds=random.uniform(0.3, 1.0))

    # 5% chance of a warning (transient GPU stall etc.)
    if random.random() < 0.05:
        lines.append(f"{_ts(t)}  [WARN ]  {worker}  GPU stall detected — retried automatically")

    return lines, t


def _generate_day(day: datetime) -> list[str]:
    """Generate all log lines for a calendar day."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f"  Shortz System Log — {day.strftime('%A, %d %B %Y')}")
    lines.append("=" * 72)
    lines.append("")

    # Supervisor startup
    t = day.replace(hour=random.randint(5, 7), minute=random.randint(0, 59), second=random.randint(0, 59))
    lines.append(f"{_ts(t)}  [INFO ]  supervisor  Starting Redis via WSL…")
    t += timedelta(seconds=random.uniform(1, 3))
    lines.append(f"{_ts(t)}  [OK   ]  supervisor  Redis running")
    t += timedelta(seconds=random.uniform(0.5, 2))
    lines.append(f"{_ts(t)}  [INFO ]  supervisor  API server started on http://127.0.0.1:8000")
    t += timedelta(seconds=random.uniform(0.5, 1.5))
    lines.append(f"{_ts(t)}  [INFO ]  supervisor  Worker started (gpu-worker-1)")
    t += timedelta(seconds=random.uniform(20, 90))
    lines.append(f"{_ts(t)}  [OK   ]  worker      🎙️ Voice Model Online.")
    lines.append("")

    # How many jobs today?
    job_count = 2 if random.random() < 0.12 else 1
    # Small chance of skipped day (weekend, maintenance)
    if random.random() < 0.04:
        lines.append(f"{_ts(t)}  [INFO ]  supervisor  No jobs scheduled today — idle")
        return lines

    for job_idx in range(job_count):
        if job_idx > 0:
            # Gap between jobs — at least 30 min
            t += timedelta(minutes=random.randint(30, 180))
        else:
            t = _rand_start(day)

        job_id = str(uuid.uuid4())
        voice = random.choice(VOICE_SAMPLES)
        worker = random.choice(WORKER_IDS)
        job_lines, t = _generate_job_log(job_id, t, voice, worker)
        lines.extend(job_lines)
        lines.append("")

    # Supervisor shutdown (evening)
    shutdown_hour = random.randint(20, 23)
    t_shutdown = day.replace(hour=shutdown_hour, minute=random.randint(0, 59))
    if t_shutdown > t:
        lines.append(f"{_ts(t_shutdown)}  [INFO ]  supervisor  System idle — all jobs complete")
        lines.append(f"{_ts(t_shutdown + timedelta(seconds=2))}  [INFO ]  supervisor  Watchdog sleeping…")

    return lines


# ─── Main ───────────────────────────────────────────────────────────────────

def generate(months: int = 6, verify: bool = False) -> None:
    end_date   = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=months * 30)

    if verify:
        # Dry-run: print a single sample day
        sample_day = end_date - timedelta(days=7)
        lines = _generate_day(sample_day)
        print("\n".join(lines[:60]))
        print(f"\n[verify] Would generate {(end_date - start_date).days} days of logs → logs/history/")
        return

    total_days = 0
    current = start_date

    while current < end_date:
        yyyy_mm = current.strftime("%Y-%m")
        dd      = current.strftime("%d")
        out_dir = LOG_HISTORY_DIR / yyyy_mm
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{dd}.log"

        lines = _generate_day(current)
        out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        total_days += 1
        current += timedelta(days=1)

    print(f"[generate_history_logs] Generated {total_days} daily log files in {LOG_HISTORY_DIR}")


def main():
    parser = argparse.ArgumentParser(description="Generate Shortz historical log files.")
    parser.add_argument("--months", type=int, default=6,
                        help="Number of months to simulate (default: 6)")
    parser.add_argument("--verify", action="store_true",
                        help="Dry-run: print a sample day without writing files")
    args = parser.parse_args()

    if args.months < 1 or args.months > 24:
        print("--months must be between 1 and 24", file=sys.stderr)
        sys.exit(1)

    generate(months=args.months, verify=args.verify)


if __name__ == "__main__":
    main()
