"""
gui/views/pipeline_view.py — Pipeline stage monitor.

Shows the 5-stage pipeline with real-time stage timing,
and a mini-history of recent jobs with their exec durations.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
)
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush
from PyQt6.QtCore import Qt, QPointF, QRectF


class _Theme:
    """Local reference to avoid circular import with main gui.py."""
    BG_SURFACE    = "rgba(15, 20, 40, 200)"
    BG_LOG        = "rgba(3, 7, 20, 240)"
    TEXT_PRIMARY   = "#E6F0FF"
    TEXT_SECONDARY = "#8899BB"
    TEXT_WHITE     = "#FFFFFF"
    ACCENT         = "#00BFFF"
    SUCCESS        = "#00E676"
    WARNING        = "#FFB74D"
    ERROR          = "#FF5252"
    INACTIVE       = "#404860"
    FONT_FAMILY    = "Segoe UI"
    FONT_MONO      = "Consolas"


STAGES = [
    ("Text Processing",    "Read script, prepare text"),
    ("Voice Generation",   "XTTS v2 neural TTS synthesis"),
    ("Word Alignment",     "Whisper word-level timestamps"),
    ("Subtitle Rendering", "ASS karaoke subtitle builder"),
    ("Video Rendering",    "FFmpeg compositing + encode"),
]

STAGE_METRICS = {
    "Text Processing":    {"avg": "1.2s",  "vram": "—"},
    "Voice Generation":   {"avg": "22s",   "vram": "~2 GB"},
    "Word Alignment":     {"avg": "8s",    "vram": "~1 GB"},
    "Subtitle Rendering": {"avg": "1.5s",  "vram": "—"},
    "Video Rendering":    {"avg": "14s",   "vram": "—"},
}


def _label(text, size=9, bold=False, color=_Theme.TEXT_PRIMARY, mono=False):
    lbl = QLabel(text)
    family = _Theme.FONT_MONO if mono else _Theme.FONT_FAMILY
    weight = QFont.Weight.DemiBold if bold else QFont.Weight.Normal
    lbl.setFont(QFont(family, size, weight))
    lbl.setStyleSheet(f"color: {color}; background: transparent;")
    return lbl


class PipelineView(QWidget):
    """Pipeline stage reference card with typical timings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        root.addWidget(_label("PIPELINE STAGES", 13, bold=True, color=_Theme.ACCENT))
        root.addWidget(_label(
            "Each job processes through 5 sequential stages. "
            "Models are loaded/unloaded to fit within 4 GB VRAM.",
            9, color=_Theme.TEXT_SECONDARY
        ))

        # Stage table
        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setContentsMargins(0, 8, 0, 0)

        headers = ["#", "Stage", "Description", "Avg Time", "VRAM"]
        for col, h in enumerate(headers):
            lbl = _label(h, 8, bold=True, color=_Theme.TEXT_SECONDARY)
            grid.addWidget(lbl, 0, col)

        for i, (name, desc) in enumerate(STAGES):
            metrics = STAGE_METRICS.get(name, {})
            row = i + 1
            grid.addWidget(_label(str(row), 9, mono=True, color=_Theme.ACCENT), row, 0)
            grid.addWidget(_label(name, 9, bold=True), row, 1)
            grid.addWidget(_label(desc, 8, color=_Theme.TEXT_SECONDARY), row, 2)
            grid.addWidget(_label(metrics.get("avg", "—"), 9, mono=True, color=_Theme.SUCCESS), row, 3)
            grid.addWidget(_label(metrics.get("vram", "—"), 9, mono=True, color=_Theme.WARNING), row, 4)

        root.addLayout(grid)

        # Flow diagram
        root.addSpacing(12)
        root.addWidget(_label("EXECUTION FLOW", 11, bold=True, color=_Theme.ACCENT))
        flow = _label(
            "Script → XTTS (GPU) → Whisper (GPU) → ASS Builder (CPU) → FFmpeg (CPU) → .mp4",
            10, mono=True, color=_Theme.TEXT_WHITE
        )
        flow.setStyleSheet(
            f"color: {_Theme.TEXT_WHITE}; background: {_Theme.BG_LOG}; "
            f"border: 1px solid rgba(255,255,255,20); border-radius: 10px; padding: 12px;"
        )
        root.addWidget(flow)

        root.addSpacing(8)
        root.addWidget(_label("VRAM MANAGEMENT", 11, bold=True, color=_Theme.ACCENT))
        root.addWidget(_label(
            "XTTS loads once at worker startup and remains cached.\n"
            "Whisper loads on first alignment job and reuses across subsequent jobs.\n"
            "After alignment, gc.collect() + torch.cuda.empty_cache() release unused VRAM.",
            9, color=_Theme.TEXT_SECONDARY
        ))

        root.addStretch()
