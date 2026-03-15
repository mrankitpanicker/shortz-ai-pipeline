"""
gui/widgets/voice_browser.py — Voice sample file browser widget.

Provides a Browse button + label showing the selected voice file path.
Supports .wav and .mp3 files for XTTS voice cloning.
"""

import os
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QFileDialog
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal


class VoiceBrowser(QWidget):
    """Voice sample browser with file dialog.

    Signals:
        voice_selected(str): Emitted when a voice file is selected.
    """
    voice_selected = pyqtSignal(str)

    def __init__(self, parent=None, font_family="Segoe UI",
                 fg="#E6F0FF", fg_dim="#8899BB", accent="#00BFFF",
                 mono="Consolas"):
        super().__init__(parent)
        self._path = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._label = QLabel("No voice selected")
        self._label.setFont(QFont(mono, 8))
        self._label.setStyleSheet(f"color: {fg_dim}; background: transparent;")
        self._label.setWordWrap(False)
        layout.addWidget(self._label, 1)

        btn = QPushButton("🎙 Browse")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(QFont(font_family, 9))
        btn.setFixedWidth(90)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {fg};
                border: 1px solid rgba(255,255,255,40); border-radius: 10px; padding: 5px;
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,15); border-color: {accent};
            }}
        """)
        btn.clicked.connect(self._browse)
        layout.addWidget(btn)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Voice Sample", "",
            "Audio Files (*.wav *.mp3);;All Files (*)",
        )
        if path:
            self._path = path
            name = os.path.basename(path)
            self._label.setText(name)
            self._label.setStyleSheet(
                f"color: #FFFFFF; font-family: Consolas; font-size: 8pt; background: transparent;"
            )
            self.voice_selected.emit(path)

    @property
    def selected_path(self) -> str:
        return self._path
