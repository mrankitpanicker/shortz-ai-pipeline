"""
tests/test_telemetry.py — Validate telemetry module.
"""

import time


def test_stage_telemetry_timing():
    """StageTelemetry records elapsed time correctly."""
    from core.telemetry import StageTelemetry

    with StageTelemetry("test_stage", job_id="abc123") as t:
        time.sleep(0.05)

    assert t.elapsed >= 0.04
    assert t.elapsed < 1.0


def test_job_telemetry_records_stages():
    """JobTelemetry accumulates per-stage timings."""
    from core.telemetry import JobTelemetry

    jt = JobTelemetry("abc123")
    jt.start()
    jt.record_stage("text", 0.5)
    jt.record_stage("tts", 15.0)
    total = jt.finish()

    assert "text" in jt.stages
    assert "tts" in jt.stages
    assert jt.stages["text"] == 0.5
    assert total >= 0
