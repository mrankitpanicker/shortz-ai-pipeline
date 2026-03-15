"""
worker/pipeline/stages/tts_stage.py — XTTS v2 speech synthesis.

Uses the cached TTS model from ResourceManager to synthesize
speech from the cleaned script text.
"""

import logging
from pathlib import Path
from datetime import datetime
from core.telemetry import StageTelemetry
import Shortz

log = logging.getLogger("shortz.stage.tts")


def run(job_id: str, ctx: dict) -> dict:
    """Synthesise speech via XTTS. Populates ctx with audio paths and durations.

    Requires ctx keys: 'text', 'resource_manager'
    Populates: 'out_wav', 'chunks', 'durations', 'out_txt', 'fname'
    """
    mgr = ctx["resource_manager"]
    tts_model = mgr.get_tts()
    if tts_model is None:
        raise RuntimeError("TTS model not loaded")

    text = ctx["text"]
    voice_path = ctx.get("voice_path", "") or str(Shortz.XTTS_SPEAKER)

    now = datetime.now()
    fname = now.strftime("%d%m%Y")
    ctx["fname"] = fname
    ctx["human_date"] = now.strftime("%d/%m/%Y")

    out_wav = Shortz.FOLDERS["output_hindi"] / f"{fname}.wav"
    out_txt = Shortz.FOLDERS["output_hindi"] / f"{fname}.txt"
    ctx["out_wav"] = out_wav
    ctx["out_txt"] = out_txt

    out_txt.write_text(text, encoding="utf-8")

    # Temporarily override the speaker path if custom voice was selected
    original_speaker = Shortz.XTTS_SPEAKER
    if voice_path and Path(voice_path).exists():
        Shortz.XTTS_SPEAKER = str(voice_path)

    with StageTelemetry("tts", job_id) as t:
        log.info("Synthesising speech (%d chars) → %s", len(text), out_wav.name)
        chunks, durations = Shortz.tts_generate_and_measure(text, out_wav)
        ctx["chunks"] = chunks
        ctx["durations"] = durations
        log.info("TTS complete: %d chunks, total %.1fs audio",
                 len(chunks), sum(durations))

    # Restore original speaker
    Shortz.XTTS_SPEAKER = original_speaker

    ctx["_stage_times"]["tts"] = t.elapsed
    return ctx
