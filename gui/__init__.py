"""
gui/ package — Re-exports MainWindow from root gui.py.

The gui/ directory shadows the root-level gui.py module.
This __init__.py ensures ``from gui import MainWindow`` still works
by loading gui.py via importlib and re-exporting its public symbols.
"""

import importlib.util
import sys
from pathlib import Path

# Load root gui.py as "gui_root" to avoid circular reference
_gui_path = Path(__file__).resolve().parent.parent / "gui.py"
_spec = importlib.util.spec_from_file_location("gui_root", str(_gui_path))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["gui_root"] = _mod
_spec.loader.exec_module(_mod)

# Re-export MainWindow so ``from gui import MainWindow`` works
MainWindow = _mod.MainWindow
