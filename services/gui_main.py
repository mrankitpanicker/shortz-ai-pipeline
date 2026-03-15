"""
gui_main.py — Production entry point for the Shortz GUI.

This replaces main.pyw as the entry point for the GUI.
It imports gui.py's MainWindow but wires it to the BridgedController
(API-based) instead of main.pyw's EngineWorker (direct pipeline call).

Architecture:
    gui_main.py
       └── gui.MainWindow         (UI — unchanged)
       └── gui_bridge.BridgedController  (API-driven controller)
              └── api_client.ShortzAPIClient
                     └── POST /generate → Redis → Worker → Shortz pipeline

Usage:
    python services/gui_main.py
    python services/gui_main.py --auto    # auto-start job
"""

import sys
import os
import logging

# Suppress noisy warnings early
logging.getLogger().setLevel(logging.ERROR)
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "true"

# Ensure project root is on the path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication


def main():
    # DPI awareness on Windows
    try:
        if sys.platform == "win32":
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    # Import the GUI window class
    try:
        from gui import MainWindow
    except ImportError:
        print("ERROR: gui.py not found. Ensure it exists in the project root.")
        sys.exit(1)

    # Create Qt app
    if not QCoreApplication.instance():
        app = QApplication(sys.argv)
    else:
        app = QCoreApplication.instance()

    # Create window
    try:
        window = MainWindow()
    except TypeError:
        window = MainWindow(None, None)

    # Wire to the BRIDGED controller (API-based, not direct Shortz call)
    from services.gui_bridge import BridgedController
    controller = BridgedController(app, window)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
