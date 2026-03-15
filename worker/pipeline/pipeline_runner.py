"""
worker/pipeline/pipeline_runner.py — Orchestrates the 5-stage pipeline.

Runs stages sequentially, updating Redis job metadata after each stage.
Uses ResourceManager for model lifecycle and StageTelemetry for observability.

Stages:
    1. text      — read script
    2. tts       — synthesize speech (GPU, cached model)
    3. alignment — word-level timestamps (GPU, load/unload)
    4. subtitles — build ASS file (CPU)
    5. render    — FFmpeg composite (CPU)
"""

import logging
import time
from worker.pipeline.stages import text_stage, tts_stage, align_stage, subtitle_stage, render_stage
from core.telemetry import JobTelemetry
import Shortz

log = logging.getLogger("shortz.pipeline")

STAGES = [
    ("text",      text_stage.run),
    ("voice",     tts_stage.run),
    ("alignment", align_stage.run),
    ("subtitles", subtitle_stage.run),
    ("render",    render_stage.run),
]


def run_pipeline(job_id: str, resource_manager, status_callback=None, voice_path: str = ""):
    """Execute the full video generation pipeline for one job.

    Args:
        job_id: Redis job identifier.
        resource_manager: worker.resource_manager.ResourceManager instance.
        status_callback: Optional callable(job_id, status, stage, progress)
                         for updating Redis metadata between stages.
        voice_path: Optional path to a custom voice sample for TTS cloning.

    Returns:
        dict with pipeline context including output paths.

    Raises:
        Exception: Any stage failure propagates to caller.
    """
    telemetry = JobTelemetry(job_id)
    telemetry.start()

    # Pipeline context — shared across all stages
    ctx = {
        "resource_manager": resource_manager,
        "voice_path": voice_path,
        "_stage_times": {},
    }

    progress_map = {
        "text": 5,
        "voice": 40,
        "alignment": 65,
        "subtitles": 80,
        "render": 95,
    }

    for stage_name, stage_fn in STAGES:
        # Update Redis with current stage
        if status_callback:
            progress = progress_map.get(stage_name, 0)
            status_callback(job_id, "running", stage=stage_name, progress=progress)

        log.info("▶ Stage: %s  job=%s", stage_name, job_id[:8])
        ctx = stage_fn(job_id, ctx)

        # Record timing for telemetry
        if stage_name in ctx.get("_stage_times", {}):
            telemetry.record_stage(stage_name, ctx["_stage_times"][stage_name])

    # Save to history
    line_num = ctx.get("line_num")
    text = ctx.get("text", "")
    if line_num is not None:
        history = Shortz.load_history()
        history[str(line_num)] = {
            "date": ctx.get("human_date", ""),
            "text_preview": text[:50] + "..." if len(text) > 50 else text,
        }
        Shortz.save_history(history)

    total = telemetry.finish()
    log.info("Pipeline complete  job=%s  total=%.1fs", job_id[:8], total)

    return ctx
