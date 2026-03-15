"""
gpu_monitor.py — GPU monitoring via nvidia-smi for the Shortz platform.

Exposes GPU memory, utilization, and temperature.
Gracefully returns "unavailable" when no NVIDIA GPU or driver is present.

Usage:
    from monitoring.gpu_monitor import get_gpu_stats
    stats = get_gpu_stats()
"""

import subprocess
import shutil
from typing import Any

# -------------------------------------------------
# GPU STATS
# -------------------------------------------------

def get_gpu_stats() -> dict[str, Any]:
    """
    Query nvidia-smi for GPU metrics.

    Returns a dict with:
        available : bool
        gpus : list[dict]   – one entry per GPU with:
            index, name,
            memory_used_mb, memory_total_mb, memory_free_mb, memory_util_pct,
            gpu_util_pct, temperature_c
    """
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi is None:
        return {"available": False, "error": "nvidia-smi not found", "gpus": []}

    query_fields = ",".join([
        "index",
        "name",
        "memory.used",
        "memory.total",
        "memory.free",
        "utilization.memory",
        "utilization.gpu",
        "temperature.gpu",
    ])

    try:
        result = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=" + query_fields,
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {
                "available": False,
                "error": result.stderr.strip() or "nvidia-smi failed",
                "gpus": [],
            }
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return {"available": False, "error": str(exc), "gpus": []}

    gpus: list[dict[str, Any]] = []
    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 8:
            continue
        gpus.append({
            "index":           int(parts[0]),
            "name":            parts[1],
            "memory_used_mb":  _safe_float(parts[2]),
            "memory_total_mb": _safe_float(parts[3]),
            "memory_free_mb":  _safe_float(parts[4]),
            "memory_util_pct": _safe_float(parts[5]),
            "gpu_util_pct":    _safe_float(parts[6]),
            "temperature_c":   _safe_float(parts[7]),
        })

    return {"available": True, "gpus": gpus}


def _safe_float(val: str) -> float:
    """Convert a string to float, returning 0.0 on failure."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


# -------------------------------------------------
# Prometheus-friendly flat dict
# -------------------------------------------------

def get_gpu_metrics_flat() -> dict[str, float]:
    """
    Return flat key-value metrics suitable for Prometheus exposition.
    Keys are prefixed with 'shortz_gpu_'.
    """
    stats = get_gpu_stats()
    metrics: dict[str, float] = {}
    if not stats["available"]:
        metrics["shortz_gpu_available"] = 0
        return metrics

    metrics["shortz_gpu_available"] = 1
    for gpu in stats["gpus"]:
        idx = gpu["index"]
        metrics[f"shortz_gpu{idx}_memory_used_mb"] = gpu["memory_used_mb"]
        metrics[f"shortz_gpu{idx}_memory_total_mb"] = gpu["memory_total_mb"]
        metrics[f"shortz_gpu{idx}_memory_free_mb"] = gpu["memory_free_mb"]
        metrics[f"shortz_gpu{idx}_memory_util_pct"] = gpu["memory_util_pct"]
        metrics[f"shortz_gpu{idx}_utilization_pct"] = gpu["gpu_util_pct"]
        metrics[f"shortz_gpu{idx}_temperature_c"] = gpu["temperature_c"]
    return metrics
