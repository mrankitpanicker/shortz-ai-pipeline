"""
worker/pipeline/stages/render_stage.py — FFmpeg video rendering.

Composites audio + ASS subtitles into a final MP4 video.
CPU-only — does not use GPU memory.
"""

import logging
from core.telemetry import StageTelemetry
import Shortz

log = logging.getLogger("shortz.stage.render")


def run(job_id: str, ctx: dict) -> dict:
    """Render final video via FFmpeg.

    Requires ctx keys: 'out_wav', 'ass_file', 'fname'
    Populates: 'final_video'
    """
    fname = ctx["fname"]
    out_wav = ctx["out_wav"]
    ass_file = ctx["ass_file"]
    final_video = Shortz.FOLDERS["video"] / f"{fname}.mp4"
    ctx["final_video"] = final_video

    with StageTelemetry("render", job_id) as t:
        log.info("Rendering video: %s + %s → %s", out_wav.name, ass_file.name, final_video.name)
        Shortz.create_final_video(out_wav, ass_file, final_video)
        log.info("Video rendered: %s", final_video.name)

    ctx["_stage_times"]["render"] = t.elapsed
    return ctx
