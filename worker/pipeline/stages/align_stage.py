"""
worker/pipeline/stages/align_stage.py — Whisper word-level alignment.

Loads Whisper via ResourceManager, aligns speech to words,
and unloads the model afterwards to free VRAM.
"""

import gc
import logging
from core.telemetry import StageTelemetry
import Shortz

log = logging.getLogger("shortz.stage.align")


def run(job_id: str, ctx: dict) -> dict:
    """Align speech to word-level timestamps using Whisper.

    Requires ctx keys: 'text', 'out_wav', 'chunks', 'durations', 'resource_manager'
    Populates: 'timestamps', 'ref_words'
    """
    mgr = ctx["resource_manager"]
    text = ctx["text"]
    out_wav = ctx["out_wav"]

    with StageTelemetry("alignment", job_id) as t:
        whisper_model = mgr.load_whisper("small")
        if whisper_model is None:
            raise RuntimeError("Failed to load Whisper model")

        log.info("Aligning audio → word timestamps")
        result = whisper_model.transcribe(str(out_wav), word_timestamps=True, language="hi")

        raw_ts = []
        for seg in result["segments"]:
            if "words" in seg:
                for w in seg["words"]:
                    raw_ts.append((float(w["start"]), float(w["end"])))

        ref_words = text.split()
        ref_count = len(ref_words)

        if not raw_ts:
            log.warning("Whisper returned no timestamps — using fallback")
            fallback_ts = Shortz.derive_word_timestamps_from_chunks(
                ctx["chunks"], ctx["durations"], text
            )
            timestamps = [(s, e, w) for (s, e), w in zip(fallback_ts, ref_words)]
        else:
            if len(raw_ts) >= ref_count:
                aligned_ts = raw_ts[:ref_count]
            else:
                log.warning("Whisper returned %d timestamps for %d words — interpolating",
                            len(raw_ts), ref_count)
                last_end = raw_ts[-1][1] if raw_ts else 0.25
                interval = last_end / ref_count
                aligned_ts = [(i * interval, (i + 1) * interval) for i in range(ref_count)]
            timestamps = [(s, e, w) for (s, e), w in zip(aligned_ts, ref_words)]

        ctx["timestamps"] = timestamps
        ctx["ref_words"] = ref_words
        log.info("Alignment complete: %d words aligned", len(timestamps))

    # Free alignment VRAM — critical for 4GB GPUs
    del result
    gc.collect()
    mgr.unload_whisper()

    ctx["_stage_times"]["alignment"] = t.elapsed
    return ctx
