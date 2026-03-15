"""
gui/views/dashboard_view.py — Dashboard view widget.

Contains the automation control card, job progress display,
pipeline stepper, and system log viewer.

This view is the primary operator interface and is shown
as page 0 of the QStackedWidget in MainWindow.

Note: The dashboard is currently built inline in gui.py::_build_ui()
for maximum integration with the threading model and state management.
This module provides a reference for the architectural target when
the full extraction is performed.
"""

# The DashboardView is currently composed inline in gui.py MainWindow._build_ui().
# The widgets it uses (control card, progress, stepper, log viewer) are tightly
# coupled to MainWindow's QThread workers and QMutex state.
#
# A full extraction would require:
#   1. Moving all dashboard widgets into this class
#   2. Passing signal references for thread communication
#   3. Forwarding MainWindow state updates to this view
#
# For now, the dashboard remains part of MainWindow to preserve
# production stability. The sidebar already routes to it via
# QStackedWidget index 0.

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtGui import QFont


class _Theme:
    TEXT_PRIMARY = "#E6F0FF"
    TEXT_SECONDARY = "#8899BB"
    ACCENT = "#00BFFF"
    FONT_FAMILY = "Segoe UI"


class DashboardView(QWidget):
    """Placeholder for future full extraction of dashboard from MainWindow.

    Currently the dashboard is built inline in gui.py::_build_ui() because
    its widgets are tightly coupled to the threading model. This class
    serves as the architectural target.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)

        info = QLabel("Dashboard is active on the main page")
        info.setFont(QFont(_Theme.FONT_FAMILY, 11))
        info.setStyleSheet(f"color: {_Theme.TEXT_SECONDARY}; background: transparent;")
        layout.addWidget(info)
        layout.addStretch()
