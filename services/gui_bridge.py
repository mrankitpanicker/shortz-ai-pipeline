"""
gui_bridge.py — API-based GUI controller for the Shortz platform.

Replaces the direct Shortz.main_generate() call in main.pyw with an
API-driven approach:

    1. Submit job via POST /generate
    2. Poll GET /status/{job_id} every 2 seconds
    3. Relay status to the GUI via Qt signals

This ensures the pipeline flows through:
    GUI → FastAPI → Redis → Worker → Shortz pipeline

Instead of:
    GUI → Shortz.main_generate() (BAD — bypasses everything)

Usage:
    from services.gui_bridge import BridgedController
    controller = BridgedController(app, window)
"""

import sys
import os
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, QTimer, QTime, pyqtSignal
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget, QMessageBox

from services.api_client import ShortzAPIClient


# ====================================================================
# API POLLING WORKER (replaces EngineWorker from main.pyw)
# ====================================================================

class APIPollingWorker(QThread):
    """
    Submit a job via the API and poll for completion.

    Emits the same signals as main.pyw's EngineWorker so the GUI
    wiring stays compatible:
        log_update(str)
        status_update(float, str)
        process_finished(float, str)
    """

    log_update = pyqtSignal(str)
    status_update = pyqtSignal(float, str)
    process_finished = pyqtSignal(float, str)

    POLL_INTERVAL_SEC = 2.0

    # Map Redis job status → approximate progress percentage
    STATUS_PROGRESS = {
        "queued":   5.0,
        "running":  50.0,
        "complete": 100.0,
        "failed":   0.0,
    }

    def __init__(self, api_client: ShortzAPIClient, parent=None):
        super().__init__(parent)
        self.api = api_client
        self._stop_requested = False

    def run(self):
        try:
            # 1. Submit the job
            self.log_update.emit("Submitting job to API...")
            result = self.api.submit_job()
            job_id = result.get("job_id")
            if not job_id:
                self.log_update.emit(f"API error: {result}")
                self.process_finished.emit(0.0, "Error: No job_id returned")
                return

            self.log_update.emit(f"Job queued: {job_id[:8]}…")
            self.status_update.emit(5.0, "Queued")

            # 2. Poll until complete/failed
            last_status = "queued"
            poll_count = 0
            while not self._stop_requested:
                time.sleep(self.POLL_INTERVAL_SEC)
                poll_count += 1

                try:
                    data = self.api.get_status(job_id)
                except ConnectionError as e:
                    self.log_update.emit(f"API connection lost: {e}")
                    # Keep trying
                    continue

                status = data.get("status", "unknown")

                if status != last_status:
                    self.log_update.emit(f"Status: {status}")
                    last_status = status

                # Map status to progress
                progress = self.STATUS_PROGRESS.get(status, 25.0)

                # For "running" status, slowly increase progress to simulate activity
                if status == "running":
                    # Ramp from 10→90 over ~5 minutes (150 polls at 2s)
                    ramp = min(80.0, 10.0 + (poll_count * 0.5))
                    progress = ramp

                self.status_update.emit(progress, status.capitalize())

                if status == "complete":
                    self.log_update.emit(f"Job {job_id[:8]}… completed successfully")
                    self.process_finished.emit(100.0, "Generation Complete")
                    return

                if status == "failed":
                    error_msg = data.get("error", "Unknown error")
                    self.log_update.emit(f"Job failed: {error_msg}")
                    self.process_finished.emit(0.0, f"Error: {error_msg}")
                    return

            # Stop was requested
            self.log_update.emit("Job polling stopped by user")
            self.process_finished.emit(0.0, "Stopped")

        except Exception as e:
            self.log_update.emit(f"FATAL ERROR: {e}")
            self.process_finished.emit(0.0, f"Error: {e}")

    def stop_process(self):
        """Signal the polling loop to stop."""
        self._stop_requested = True


# ====================================================================
# BRIDGED CONTROLLER (replaces MainController from main.pyw)
# ====================================================================

class BridgedController(QObject):
    """
    Drop-in replacement for main.pyw's MainController.

    Wires the GUI buttons to the API-based polling worker instead of
    the direct Shortz.main_generate() approach.
    """

    def __init__(self, app: QApplication, window: QWidget, api_url: str = "http://127.0.0.1:8000"):
        super().__init__()
        self.app = app
        self.window = window
        self.is_running = False
        self.worker_thread = None
        self.api = ShortzAPIClient(base_url=api_url)

        CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
        self.CURRENT_DIR = str(Path(CURRENT_DIR).parent)

        # Stop any leftover timers from gui.py's MainWindow
        if hasattr(window, 'simulation_timer'):
            window.simulation_timer.stop()
        window.is_running = False

        # Find buttons
        buttons = window.findChildren(QPushButton)
        self.start_btn = next((b for b in buttons if "START" in b.text()), None)
        self.open_btn = next((b for b in buttons if "OUTPUT FOLDER" in b.text()), None)

        # Initial status
        self._direct_log("System ready. Waiting for API server...")
        self._direct_update_status("Initializing", "Wait...", False, True)

        # Check API readiness
        self.api_check_timer = QTimer(self)
        self.api_check_timer.timeout.connect(self._check_api_ready)
        self.api_check_timer.start(2000)

        # Wire buttons
        if self.start_btn:
            try:
                self.start_btn.clicked.disconnect()
            except Exception:
                pass
            self.start_btn.clicked.connect(self.handle_start_automation)

        if self.open_btn:
            try:
                self.open_btn.clicked.disconnect()
            except Exception:
                pass
            self.open_btn.clicked.connect(self.handle_open_output)

    # ------------------------------------------------------------------
    # API READINESS
    # ------------------------------------------------------------------

    def _check_api_ready(self):
        """Poll until the API server is reachable, then enable the Start button."""
        if self.api.health_check():
            self.api_check_timer.stop()
            self._direct_update_status("Engine Ready", "START AUTOMATION  ▶", True, False)
            self._direct_update_progress(0.0)
            self._direct_log("✅ API server connected. Ready for job.")

            # Auto-trigger if --auto flag was passed
            if "--auto" in sys.argv:
                QTimer.singleShot(1000, self.handle_start_automation)
        else:
            self._direct_log("⏳ Waiting for API server...")

    # ------------------------------------------------------------------
    # START / STOP
    # ------------------------------------------------------------------

    def handle_start_automation(self):
        if self.is_running:
            # Stop
            if self.worker_thread and self.worker_thread.isRunning():
                self.worker_thread.stop_process()
            self.is_running = False
            self._direct_update_status("Stopped", "START AUTOMATION  ▶", True, False)
            self._direct_log("Session stopped by user.")
        else:
            # Start
            self.is_running = True
            self.start_btn.setText("PROCESSING...")
            self.start_btn.setEnabled(False)
            if self.open_btn:
                self.open_btn.setDisabled(True)
            self._direct_update_progress(0.0)
            self._direct_log("Submitting job via API...")

            self.worker_thread = APIPollingWorker(self.api, parent=self)
            self.worker_thread.log_update.connect(self._direct_log)
            self.worker_thread.status_update.connect(self._update_gui_status)
            self.worker_thread.process_finished.connect(self._handle_process_finished)
            self.worker_thread.start()

    # ------------------------------------------------------------------
    # GUI UPDATES (same interface as main.pyw's MainController)
    # ------------------------------------------------------------------

    def _direct_log(self, message: str):
        if not hasattr(self.window, 'log_box'):
            return
        current_text = self.window.log_box.text()
        timestamp = QTime.currentTime().toString('hh:mm:ss')
        lines = (current_text + f"\n[{timestamp}] {message}").split('\n')
        if len(lines) > 30:
            lines = lines[-30:]
        self.window.log_box.setText('\n'.join(lines))

    def _direct_update_status(self, metric_status: str, button_text: str, button_enabled: bool, chip_visible: bool):
        if not hasattr(self.window, 'metrics_body'):
            return
        metrics_html = (
            f"Process ID: PRO TIER \n\n"
            f"Engine: Text To Voice \n\n"
            f"Renderer: Video Generator \n\n"
            f"Status: {metric_status}"
        )
        self.window.metrics_body.setText(metrics_html)
        if self.start_btn:
            self.start_btn.setText(button_text)
            self.start_btn.setEnabled(button_enabled)
        if self.open_btn:
            self.open_btn.setEnabled(button_enabled or 'COMPLETE' in metric_status.upper())

    def _direct_update_progress(self, progress: float):
        if not hasattr(self.window, 'percent_label'):
            return
        self.window.percent_label.setText(f"{int(progress)}%")
        self.window.waveform_widget.setProgress(progress)

    def _update_gui_status(self, percentage: float, message: str):
        self._direct_update_progress(percentage)
        if percentage >= 100.0:
            return
        self._direct_update_status(message, "STOP AUTOMATION ⏹", True, True)

    def _handle_process_finished(self, final_progress: float, final_status: str):
        self.is_running = False
        self._direct_update_progress(final_progress)

        if "Error" in final_status or final_progress < 100.0:
            self._direct_update_status("Error", "RETRY START ▶", True, False)
            self._direct_log(f"💥 {final_status}")
        else:
            self._direct_update_status("Generation Complete", "RESTART AUTOMATION ↺", True, False)
            self._direct_log("🎉 Process finished successfully.")
            QApplication.beep()
            self._write_done_file()

    def _write_done_file(self):
        """Write completion marker for external orchestration."""
        try:
            done_dir = Path("C:/automation/done")
            done_dir.mkdir(parents=True, exist_ok=True)
            (done_dir / "shortz.done").write_text("done")
        except Exception as e:
            self._direct_log(f"Warning: Could not write done file: {e}")

    def handle_open_output(self):
        import subprocess as sp
        output_dir = os.path.join(self.CURRENT_DIR, "output", "video")
        os.makedirs(output_dir, exist_ok=True)
        self._direct_log(f"Opening folder: {output_dir}")
        sp.Popen(["explorer", output_dir])
