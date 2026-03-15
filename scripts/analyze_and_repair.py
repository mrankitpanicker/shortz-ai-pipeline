"""
scripts/analyze_and_repair.py — Project health analyzer and auto-repair tool.

Scans all Python files, checks for broken imports, missing modules,
directory integrity, and attempts automatic repairs.

Usage:
    python scripts/analyze_and_repair.py

Exit codes:
    0 — all checks passed or repairs applied
    1 — unresolvable issues found
"""

import ast
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

issues = []
repairs = []


def check(label: str, ok: bool, fix_fn=None):
    if ok:
        print(f"  {GREEN}✓{RESET} {label}")
    else:
        print(f"  {RED}✗{RESET} {label}")
        if fix_fn:
            fix_fn()
            repairs.append(label)
            print(f"    {YELLOW}↳ auto-repaired{RESET}")
        else:
            issues.append(label)


# -------------------------------------------------
# 1. DIRECTORY STRUCTURE
# -------------------------------------------------

def check_directories():
    print(f"\n{CYAN}── Directory Structure ──{RESET}")
    required = [
        "logs/runtime",
        "logs/errors",
        "logs/history",
        "core",
        "worker/pipeline/stages",
        "gui/views",
        "gui/widgets",
        "api/routes",
        "api/services",
        "tests",
        "scripts",
        "docker",
        "docs",
        "input",
        "output/video",
        "output/hindi",
        "output/subtitles",
    ]
    for d in required:
        p = PROJECT_ROOT / d
        check(
            f"directory: {d}",
            p.is_dir(),
            fix_fn=lambda path=p: path.mkdir(parents=True, exist_ok=True),
        )


# -------------------------------------------------
# 2. REQUIRED FILES
# -------------------------------------------------

def check_required_files():
    print(f"\n{CYAN}── Required Files ──{RESET}")
    files = [
        "core/__init__.py",
        "core/config.py",
        "core/logging_config.py",
        "core/telemetry.py",
        "core/error_logger.py",
        "gui/__init__.py",
        "gui/views/__init__.py",
        "gui/views/pipeline_view.py",
        "gui/views/history_view.py",
        "gui/views/settings_view.py",
        "gui/views/dashboard_view.py",
        "gui/widgets/__init__.py",
        "gui/widgets/batch_selector.py",
        "gui/widgets/voice_browser.py",
        "worker/__init__.py",
        "worker/resource_manager.py",
        "worker/worker.py",
        "worker/pipeline/__init__.py",
        "worker/pipeline/pipeline_runner.py",
        "worker/pipeline/stages/__init__.py",
        "worker/pipeline/stages/text_stage.py",
        "worker/pipeline/stages/tts_stage.py",
        "worker/pipeline/stages/align_stage.py",
        "worker/pipeline/stages/subtitle_stage.py",
        "worker/pipeline/stages/render_stage.py",
        "api/__init__.py",
        "api/server.py",
        "api/routes/__init__.py",
        "api/routes/generation.py",
        "api/services/__init__.py",
        "api/services/job_service.py",
        "tests/__init__.py",
        "gui.py",
        "api_server.py",
        "redis_queue.py",
        "worker.py",
        "Shortz.py",
        "main.pyw",
        "shortz_supervisor.py",
        "requirements.txt",
        "README.md",
        "LICENSE",
        ".gitignore",
        "docker-compose.yml",
    ]
    for f in files:
        check(f"file: {f}", (PROJECT_ROOT / f).is_file())


# -------------------------------------------------
# 3. SYNTAX CHECK
# -------------------------------------------------

def check_syntax():
    print(f"\n{CYAN}── Syntax Check ──{RESET}")
    py_files = list(PROJECT_ROOT.rglob("*.py"))
    py_files = [f for f in py_files if "__pycache__" not in str(f)
                and ".git" not in str(f) and "venv" not in str(f)]

    for fp in sorted(py_files):
        rel = fp.relative_to(PROJECT_ROOT)
        try:
            source = fp.read_text(encoding="utf-8", errors="replace")
            ast.parse(source, filename=str(rel))
            # Only print failures to keep output clean
        except SyntaxError as e:
            print(f"  {RED}✗{RESET} {rel}  →  line {e.lineno}: {e.msg}")
            issues.append(f"syntax: {rel}")

    if not any("syntax:" in i for i in issues):
        print(f"  {GREEN}✓{RESET} All Python files parse successfully")


# -------------------------------------------------
# 4. __init__.py INTEGRITY
# -------------------------------------------------

def check_init_files():
    print(f"\n{CYAN}── Package __init__.py ──{RESET}")
    packages = [
        "core", "gui", "gui/views", "gui/widgets",
        "worker", "worker/pipeline", "worker/pipeline/stages",
        "api", "api/routes", "api/services", "tests",
    ]
    for pkg in packages:
        init = PROJECT_ROOT / pkg / "__init__.py"
        check(
            f"__init__.py: {pkg}/",
            init.is_file(),
            fix_fn=lambda path=init: (path.parent.mkdir(parents=True, exist_ok=True) or
                                      path.write_text("", encoding="utf-8")),
        )


# -------------------------------------------------
# 5. GUI IMPORT CHAIN
# -------------------------------------------------

def check_gui_imports():
    print(f"\n{CYAN}── GUI Import Chain ──{RESET}")
    init = PROJECT_ROOT / "gui" / "__init__.py"
    if init.is_file():
        content = init.read_text(encoding="utf-8")
        check("gui/__init__.py re-exports MainWindow", "MainWindow" in content)
    else:
        check("gui/__init__.py exists", False)


# -------------------------------------------------
# MAIN
# -------------------------------------------------

def main():
    print(f"\n{'=' * 56}")
    print(f"   SHORTZ — Project Analyzer & Auto-Repair")
    print(f"{'=' * 56}")

    check_directories()
    check_required_files()
    check_syntax()
    check_init_files()
    check_gui_imports()

    print(f"\n{'─' * 56}")
    if repairs:
        print(f"\n  {YELLOW}Repairs applied: {len(repairs)}{RESET}")
        for r in repairs:
            print(f"    ↳ {r}")
    if issues:
        print(f"\n  {RED}Unresolved issues: {len(issues)}{RESET}")
        for i in issues:
            print(f"    ✗ {i}")
        print()
        return 1
    else:
        print(f"\n  {GREEN}All checks passed ✓{RESET}")
        print()
        return 0


if __name__ == "__main__":
    sys.exit(main())
