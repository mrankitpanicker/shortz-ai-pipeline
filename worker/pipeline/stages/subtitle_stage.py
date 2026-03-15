"""
worker/pipeline/stages/subtitle_stage.py — ASS karaoke subtitle generation.

Builds a word-level karaoke ASS subtitle file from the aligned timestamps.
"""

import logging
from core.telemetry import StageTelemetry
import Shortz

log = logging.getLogger("shortz.stage.subtitles")


def run(job_id: str, ctx: dict) -> dict:
    """Build karaoke ASS subtitle file.

    Requires ctx keys: 'ref_words', 'timestamps', 'fname'
    Populates: 'ass_file'
    """
    fname = ctx["fname"]
    ref_words = ctx["ref_words"]
    timestamps = ctx["timestamps"]

    ass_file = Shortz.FOLDERS["subtitles"] / f"{fname}.ass"
    ctx["ass_file"] = ass_file

    with StageTelemetry("subtitles", job_id) as t:
        log.info("Building karaoke ASS subtitles (%d words)", len(ref_words))
        Shortz.build_karaoke_ass(ref_words, timestamps, ass_file)
        log.info("ASS file written: %s", ass_file.name)

    ctx["_stage_times"]["subtitles"] = t.elapsed
    return ctx
