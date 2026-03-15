"""
gui/main_window.py — MainWindow entry point for modular imports.

Re-exports MainWindow from the root-level gui.py to satisfy the
``gui/main_window.py`` import path in the repository architecture.

The root gui.py contains the full threading model, widget construction,
and state management required for production stability.

Usage:
    from gui.main_window import MainWindow
"""

import importlib
import sys

# Import root gui.py (module name "gui" would conflict with this package)
_spec = importlib.util.spec_from_file_location(
    "gui_root",
    str(__import__("pathlib").Path(__file__).resolve().parent.parent / "gui.py"),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["gui_root"] = _mod
_spec.loader.exec_module(_mod)

MainWindow = _mod.MainWindow  # noqa: F811
