"""
gui/views/settings_view.py — User-editable configuration panel.

Reads current values from core.config and allows the user
to override them for the current session.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGridLayout,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt


class _Theme:
    BG_INPUT        = "#0D1225"
    TEXT_PRIMARY     = "#E6F0FF"
    TEXT_SECONDARY   = "#8899BB"
    TEXT_WHITE       = "#FFFFFF"
    ACCENT           = "#00BFFF"
    SUCCESS          = "#00E676"
    FONT_FAMILY      = "Segoe UI"
    FONT_MONO        = "Consolas"


# Default config values — read from core.config at import time
try:
    from core.config import (
        REDIS_HOST, REDIS_PORT, API_PORT,
        DEFAULT_VOICE, OUTPUT_DIR, LOG_DIR,
    )
except ImportError:
    REDIS_HOST = "127.0.0.1"
    REDIS_PORT = 6379
    API_PORT = 8000
    DEFAULT_VOICE = ""
    OUTPUT_DIR = ""
    LOG_DIR = ""


FIELDS = [
    ("Redis Host",    "REDIS_HOST",    str(REDIS_HOST)),
    ("Redis Port",    "REDIS_PORT",    str(REDIS_PORT)),
    ("API Port",      "API_PORT",      str(API_PORT)),
    ("Default Voice", "VOICE_SAMPLE",  str(DEFAULT_VOICE)),
    ("Output Dir",    "OUTPUT_DIR",    str(OUTPUT_DIR)),
    ("Log Dir",       "LOG_DIR",       str(LOG_DIR)),
]


def _label(text, size=9, bold=False, color=_Theme.TEXT_PRIMARY, mono=False):
    lbl = QLabel(text)
    family = _Theme.FONT_MONO if mono else _Theme.FONT_FAMILY
    weight = QFont.Weight.DemiBold if bold else QFont.Weight.Normal
    lbl.setFont(QFont(family, size, weight))
    lbl.setStyleSheet(f"color: {color}; background: transparent;")
    return lbl


class SettingsView(QWidget):
    """Configuration panel showing editable fields + env var names."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        root.addWidget(_label("SYSTEM SETTINGS", 13, bold=True, color=_Theme.ACCENT))
        root.addWidget(_label(
            "These values are set via environment variables. "
            "Edit here for the current session only.",
            9, color=_Theme.TEXT_SECONDARY
        ))

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setContentsMargins(0, 8, 0, 0)

        self._inputs: dict[str, QLineEdit] = {}

        input_style = f"""
            QLineEdit {{
                background-color: {_Theme.BG_INPUT}; color: {_Theme.TEXT_WHITE};
                border: 1px solid rgba(255,255,255,40); border-radius: 8px;
                padding: 6px 10px; font-family: {_Theme.FONT_MONO}; font-size: 9pt;
            }}
            QLineEdit:focus {{
                border-color: {_Theme.ACCENT};
            }}
        """

        for row, (label, env_key, default) in enumerate(FIELDS):
            grid.addWidget(_label(label, 9, bold=True), row, 0)
            inp = QLineEdit(default)
            inp.setFont(QFont(_Theme.FONT_MONO, 9))
            inp.setStyleSheet(input_style)
            inp.setMinimumWidth(280)
            grid.addWidget(inp, row, 1)
            env_lbl = _label(env_key, 8, mono=True, color=_Theme.TEXT_SECONDARY)
            grid.addWidget(env_lbl, row, 2)
            self._inputs[env_key] = inp

        root.addLayout(grid)

        # Save button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._status = _label("", 9, color=_Theme.SUCCESS)
        btn_row.addWidget(self._status)

        save_btn = QPushButton("💾  Save Settings")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setFont(QFont(_Theme.FONT_FAMILY, 10))
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(0,191,255,180); color: #001016;
                border-radius: 12px; padding: 8px 20px; font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(50,210,255,220);
            }}
        """)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

        root.addStretch()

    def _save(self):
        """Apply settings to os.environ for the current process."""
        import os
        for env_key, inp in self._inputs.items():
            val = inp.text().strip()
            if val:
                os.environ[env_key] = val
        self._status.setText("Settings saved to environment ✓")

