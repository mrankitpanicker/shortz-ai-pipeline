"""
gui/views/history_view.py — Job history display.

Reads history.json (written by the pipeline after each generation)
and displays it as a sorted table.
"""

import json
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt


class _Theme:
    BG_SURFACE     = "rgba(15, 20, 40, 200)"
    BG_LOG         = "rgba(3, 7, 20, 240)"
    TEXT_PRIMARY    = "#E6F0FF"
    TEXT_SECONDARY  = "#8899BB"
    TEXT_WHITE      = "#FFFFFF"
    ACCENT          = "#00BFFF"
    FONT_FAMILY     = "Segoe UI"
    FONT_MONO       = "Consolas"

HISTORY_FILE = Path(__file__).resolve().parent.parent.parent / "history.json"


def _label(text, size=9, bold=False, color=_Theme.TEXT_PRIMARY):
    lbl = QLabel(text)
    weight = QFont.Weight.DemiBold if bold else QFont.Weight.Normal
    lbl.setFont(QFont(_Theme.FONT_FAMILY, size, weight))
    lbl.setStyleSheet(f"color: {color}; background: transparent;")
    return lbl


class HistoryView(QWidget):
    """Displays past generation history from history.json."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.addWidget(_label("GENERATION HISTORY", 13, bold=True, color=_Theme.ACCENT))
        header_row.addStretch()

        refresh_btn = QPushButton("⟳ Refresh")
        refresh_btn.setFont(QFont(_Theme.FONT_FAMILY, 9))
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {_Theme.TEXT_PRIMARY};
                border: 1px solid rgba(255,255,255,40); border-radius: 10px; padding: 5px 12px;
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,15); border-color: {_Theme.ACCENT};
            }}
        """)
        refresh_btn.clicked.connect(self._load_history)
        header_row.addWidget(refresh_btn)
        root.addLayout(header_row)

        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["#", "Date", "Preview"])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setFont(QFont(_Theme.FONT_MONO, 9))
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {_Theme.BG_LOG}; color: {_Theme.TEXT_PRIMARY};
                border: 1px solid rgba(255,255,255,20); border-radius: 10px;
                gridline-color: rgba(255,255,255,15);
            }}
            QHeaderView::section {{
                background-color: rgba(10,15,40,220); color: {_Theme.ACCENT};
                border: none; padding: 6px; font-weight: bold;
            }}
            QTableWidget::item {{ padding: 4px 8px; }}
            QTableWidget::item:selected {{ background-color: rgba(0,191,255,40); }}
        """)
        root.addWidget(self._table)

        self._status = _label("", 8, color=_Theme.TEXT_SECONDARY)
        root.addWidget(self._status)

        # Auto-load on construction
        self._load_history()

    def _load_history(self):
        """Read history.json and populate the table."""
        if not HISTORY_FILE.exists():
            self._status.setText("No history file found")
            self._table.setRowCount(0)
            return

        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            self._status.setText(f"Error loading history: {e}")
            return

        # Sort by entry number descending
        entries = sorted(data.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0, reverse=True)
        self._table.setRowCount(len(entries))

        for row, (num, info) in enumerate(entries):
            date = info.get("date", "—")
            preview = info.get("text_preview", "—")
            self._table.setItem(row, 0, QTableWidgetItem(str(num)))
            self._table.setItem(row, 1, QTableWidgetItem(date))
            self._table.setItem(row, 2, QTableWidgetItem(preview))

        self._status.setText(f"{len(entries)} entries loaded")
