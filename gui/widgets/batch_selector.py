"""
gui/widgets/batch_selector.py — Batch count ComboBox widget.

Provides a styled ComboBox for selecting how many videos to generate
in a single batch (1, 3, 5, or 10).
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal


class BatchSelector(QWidget):
    """Batch count selector with styled ComboBox.

    Signals:
        count_changed(int): Emitted when the selected batch count changes.
    """
    count_changed = pyqtSignal(int)
    COUNTS = [1, 3, 5, 10]

    _STYLE = """
        QComboBox {{
            background-color: {bg}; color: {fg};
            border: 1px solid rgba(255,255,255,40); border-radius: 10px;
            padding: 6px 10px;
        }}
        QComboBox::drop-down {{ border: 0; width: 20px; }}
        QComboBox QAbstractItemView {{
            background: #0A1530; border: 1px solid {accent};
            selection-background-color: rgba(0,191,255,60); color: {fg};
        }}
    """

    def __init__(self, parent=None, bg="#0D1225", fg="#FFFFFF", accent="#00BFFF",
                 font_family="Segoe UI"):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        lbl = QLabel("Videos:")
        lbl.setFont(QFont(font_family, 9))
        lbl.setStyleSheet(f"color: #8899BB; background: transparent;")
        layout.addWidget(lbl)

        self._combo = QComboBox()
        self._combo.setFont(QFont(font_family, 10))
        for n in self.COUNTS:
            self._combo.addItem(f"{n} video{'s' if n > 1 else ''}")
        self._combo.setStyleSheet(self._STYLE.format(bg=bg, fg=fg, accent=accent))
        self._combo.currentIndexChanged.connect(self._on_change)
        layout.addWidget(self._combo, 1)

    def _on_change(self, index: int):
        count = self.COUNTS[index] if 0 <= index < len(self.COUNTS) else 1
        self.count_changed.emit(count)

    @property
    def count(self) -> int:
        idx = self._combo.currentIndex()
        return self.COUNTS[idx] if 0 <= idx < len(self.COUNTS) else 1
