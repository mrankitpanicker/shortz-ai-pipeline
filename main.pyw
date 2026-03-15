# main.pyw — Thin GUI launcher for Shortz
#
# Production entry point launched by shortz_supervisor.py.
# All pipeline logic lives in the Worker. The GUI is only a dashboard.

import sys
import os
import logging
import traceback

# Suppress noisy warnings
logging.getLogger().setLevel(logging.ERROR)
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "true"

# 1. SETUP PATH
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# 2. INSTALL GLOBAL ERROR HANDLER
try:
    from core.error_logger import install_global_handler, log_exception
    install_global_handler()
except ImportError:
    # Fallback if core module is missing
    def log_exception(exc, context=""):
        traceback.print_exception(type(exc), exc, exc.__traceback__)


# ====================================================================
# ENTRY POINT
# ====================================================================

def launch_gui():
    """Start the GUI with full crash protection."""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QCoreApplication
    from gui import MainWindow

    if not QCoreApplication.instance():
        app = QApplication(sys.argv)
    else:
        app = QCoreApplication.instance()

    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    # DPI awareness (Windows)
    try:
        if sys.platform == "win32":
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    try:
        launch_gui()
    except Exception as e:
        log_exception(e, context="gui.launch")
        # Show error dialog as fallback
        try:
            import tkinter as tk
            tk.Tk().withdraw()
            import tkinter.messagebox
            tkinter.messagebox.showerror(
                "Shortz — Launch Error",
                f"GUI failed to start:\n\n{e}\n\nCheck logs/errors/error.log"
            )
        except Exception:
            pass
        sys.exit(1)