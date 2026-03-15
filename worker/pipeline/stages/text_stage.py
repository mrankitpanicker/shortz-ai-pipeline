"""
worker/pipeline/stages/text_stage.py — Read and prepare script text.

Reads the next line from input/input.txt, cleans it for TTS,
and returns the text + line number.
"""

import logging
from core.telemetry import StageTelemetry
import Shortz

log = logging.getLogger("shortz.stage.text")


def run(job_id: str, ctx: dict) -> dict:
    """Read the next script line. Populates ctx with 'text' and 'line_num'.

    Args:
        job_id: Redis job ID.
        ctx: Shared pipeline context dict.

    Returns:
        Updated ctx with 'text' (cleaned string) and 'line_num' (int).

    Raises:
        RuntimeError: If no input text is available.
    """
    with StageTelemetry("text", job_id) as t:
        text, num = Shortz.get_next_line_and_number()

        if not text or text == "मित्र… आज का संदेश उपलब्ध नहीं है।":
            raise RuntimeError(f"No input text available (line={num})")

        ctx["text"] = text
        ctx["line_num"] = num
        log.info("Script line #%s read (%d chars)", num, len(text))

    ctx["_stage_times"]["text"] = t.elapsed
    return ctx
