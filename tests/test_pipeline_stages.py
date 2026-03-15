"""
tests/test_pipeline_stages.py — Validate pipeline stage modules import correctly.
"""


def test_text_stage_import():
    from worker.pipeline.stages import text_stage
    assert hasattr(text_stage, "run")


def test_tts_stage_import():
    from worker.pipeline.stages import tts_stage
    assert hasattr(tts_stage, "run")


def test_align_stage_import():
    from worker.pipeline.stages import align_stage
    assert hasattr(align_stage, "run")


def test_subtitle_stage_import():
    from worker.pipeline.stages import subtitle_stage
    assert hasattr(subtitle_stage, "run")


def test_render_stage_import():
    from worker.pipeline.stages import render_stage
    assert hasattr(render_stage, "run")


def test_pipeline_runner_import():
    from worker.pipeline import pipeline_runner
    assert hasattr(pipeline_runner, "run_pipeline")
