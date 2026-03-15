"""
gui.py — Shortz Operator Console

Professional automation control interface with:
  • HeaderBar            — title + live service health with latency
  • SidebarNavigation    — page selection (Dashboard active)
  • PipelineStepper      — 5-stage QPainter visualization
  • AnimatedWaveProgress — neon waveform (60 FPS)
  • Job context panel    — stage, job ID, elapsed, ETA
  • ColorLogViewer       — color-coded log levels
  • Auto-launch          — API-based active job detection, safe startup

Thread architecture:
  • StatusPollerThread       — polls /status with session reuse + backoff
  • JobSubmitterThread       — POST /generate off main thread
  • ActiveJobDetectorThread  — calls GET /active_job (never scans Redis)
  • HealthCheckThread        — polls /health every 10s with latency

State safety:
  • QMutex guards job_id / is_running
  • QueuedConnection on all cross-thread signals
  • closeEvent ensures clean thread shutdown
"""

import os
import subprocess
import sys
import math
import time as _time
import random
import logging
import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox,
    QVBoxLayout, QHBoxLayout, QGridLayout, QGraphicsDropShadowEffect,
    QSizePolicy, QTextEdit, QFrame, QStackedWidget,
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QPainterPath, QLinearGradient, QPen,
    QBrush, QTextCursor,
)
from PyQt6.QtCore import (
    Qt, QRectF, QTimer, QTime, QPointF,
    QThread, pyqtSignal, QMutex, QMutexLocker,
)

log = logging.getLogger("shortz.gui")


# ====================================================================
# 1. DESIGN TOKENS
# ====================================================================

class Theme:
    BG_APP        = "#08091A"
    BG_SURFACE    = "rgba(15, 20, 40, 200)"
    BG_SIDEBAR    = "#0B0D1E"
    BG_HEADER     = "#0A0C1C"
    BG_INPUT      = "#0D1225"
    BG_LOG        = "rgba(3, 7, 20, 240)"

    TEXT_PRIMARY   = "#E6F0FF"
    TEXT_SECONDARY = "#8899BB"
    TEXT_WHITE     = "#FFFFFF"
    TEXT_DARK      = "#001016"

    ACCENT         = "#00BFFF"
    ACCENT_HOVER   = "#33CFFF"
    SUCCESS        = "#00E676"
    WARNING        = "#FFB74D"
    ERROR          = "#FF5252"
    INACTIVE       = "#404860"

    CARD_BORDER    = "rgba(255, 255, 255, 40)"
    CARD_RADIUS    = 20

    SHADOW_NEON    = "#00DFFF"
    SHADOW_WHITE   = "#FFFFFF"

    WAVE_COLORS = [
        QColor(0, 255, 255, 180),
        QColor(80, 210, 255, 180),
        QColor(0, 255, 170, 180),
        QColor(255, 255, 120, 180),
        QColor(255, 170, 50, 180),
        QColor(255, 90, 200, 180),
        QColor(180, 100, 255, 180),
    ]

    POLL_INTERVAL_MS    = 4000
    POLL_BACKOFF_MAX_MS = 30000
    API_BASE_URL        = "http://127.0.0.1:8000"

    FONT_FAMILY = "Segoe UI"
    FONT_MONO   = "Consolas"

    LOG_INFO    = "#8899BB"
    LOG_WARN    = "#FFB74D"
    LOG_ERROR   = "#FF5252"
    LOG_SUCCESS = "#00E676"


# ====================================================================
# 2. REUSABLE PRIMITIVES
# ====================================================================

def apply_neon_shadow(widget, color_hex, radius=12, x_offset=0, y_offset=0):
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(radius)
    shadow.setXOffset(x_offset)
    shadow.setYOffset(y_offset)
    shadow.setColor(QColor(color_hex))
    widget.setGraphicsEffect(shadow)


class GlassCard(QWidget):
    def __init__(self, parent=None, radius=Theme.CARD_RADIUS):
        super().__init__(parent)
        self._radius = radius
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setYOffset(12)
        shadow.setColor(QColor(0, 0, 0, 200))
        self.setGraphicsEffect(shadow)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0.0, QColor(255, 255, 255, 40))
        grad.setColorAt(0.5, QColor(255, 255, 255, 18))
        grad.setColorAt(1.0, QColor(255, 255, 255, 6))
        p.fillPath(path, grad)
        pen = QPen(QColor(255, 255, 255, 50))
        pen.setWidth(1)
        p.setPen(pen)
        p.drawPath(path)


def _make_label(text, size=9, bold=False, color=None, mono=False):
    lbl = QLabel(text)
    family = Theme.FONT_MONO if mono else Theme.FONT_FAMILY
    weight = QFont.Weight.DemiBold if bold else QFont.Weight.Normal
    lbl.setFont(QFont(family, size, weight))
    c = color or Theme.TEXT_SECONDARY
    lbl.setStyleSheet(f"color: {c}; background: transparent;")
    return lbl


# ====================================================================
# 3. SERVICE HEALTH INDICATOR
# ====================================================================

class ServiceIndicator(QWidget):
    def __init__(self, service_name: str, parent=None):
        super().__init__(parent)
        self._service = service_name
        self._color = QColor(Theme.INACTIVE)
        self._status_text = "…"
        self.setFixedHeight(28)
        self.setMinimumWidth(130)
        self.setStyleSheet("background: transparent;")

    def set_state(self, color_hex: str, status_text: str):
        self._color = QColor(color_hex)
        self._status_text = status_text
        self.update()

    def set_healthy(self, detail="online"):
        self.set_state(Theme.SUCCESS, detail)

    def set_degraded(self, detail="degraded"):
        self.set_state(Theme.WARNING, detail)

    def set_down(self, detail="OFFLINE"):
        self.set_state(Theme.ERROR, detail)

    def set_unknown(self, detail="…"):
        self.set_state(Theme.INACTIVE, detail)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        glow = QColor(self._color)
        glow.setAlpha(40)
        p.setBrush(QBrush(glow))
        p.setPen(Qt.PenStyle.NoPen)
        cy = self.height() // 2
        p.drawEllipse(QPointF(8, cy), 7, 7)
        p.setBrush(QBrush(self._color))
        p.drawEllipse(QPointF(8, cy), 4, 4)
        p.setPen(QPen(QColor(Theme.TEXT_PRIMARY)))
        p.setFont(QFont(Theme.FONT_FAMILY, 8, QFont.Weight.DemiBold))
        p.drawText(20, 0, 60, self.height(), Qt.AlignmentFlag.AlignVCenter, self._service)
        p.setPen(QPen(QColor(Theme.TEXT_SECONDARY)))
        p.setFont(QFont(Theme.FONT_MONO, 7))
        p.drawText(80, 0, self.width() - 84, self.height(),
                   Qt.AlignmentFlag.AlignVCenter, self._status_text)


# ====================================================================
# 4. HEADER BAR
# ====================================================================

class HeaderBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setStyleSheet(f"QWidget {{ background-color: {Theme.BG_HEADER}; }}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(8)

        title = QLabel("SHORTZ")
        title.setFont(QFont(Theme.FONT_FAMILY, 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Theme.ACCENT}; background: transparent;")
        apply_neon_shadow(title, Theme.SHADOW_NEON, radius=10)

        subtitle = QLabel("AI Pipeline Automation")
        subtitle.setFont(QFont(Theme.FONT_FAMILY, 9))
        subtitle.setStyleSheet(f"color: {Theme.TEXT_SECONDARY}; background: transparent;")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch()

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: rgba(255,255,255,20); background: transparent;")
        layout.addWidget(sep)

        self.svc_redis = ServiceIndicator("Redis")
        self.svc_api = ServiceIndicator("API")
        self.svc_worker = ServiceIndicator("Worker")
        for svc in (self.svc_redis, self.svc_api, self.svc_worker):
            layout.addWidget(svc)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("color: rgba(255,255,255,20); background: transparent;")
        layout.addWidget(sep2)

        self._clock = QLabel()
        self._clock.setFont(QFont(Theme.FONT_MONO, 9))
        self._clock.setStyleSheet(f"color: {Theme.TEXT_SECONDARY}; background: transparent;")
        layout.addWidget(self._clock)

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick)
        self._clock_timer.start(1000)
        self._tick()

    def _tick(self):
        self._clock.setText(QTime.currentTime().toString("hh:mm:ss"))


# ====================================================================
# 5. SIDEBAR
# ====================================================================

class SidebarNavigation(QWidget):
    page_changed = pyqtSignal(str)
    PAGES = [("📊", "Dashboard"), ("🔗", "Pipeline"), ("📜", "History"), ("⚙️", "Settings")]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(180)
        self.setStyleSheet(f"QWidget {{ background-color: {Theme.BG_SIDEBAR}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 20, 10, 20)
        layout.setSpacing(6)
        self._buttons = []
        for icon, label in self.PAGES:
            btn = QPushButton(f"  {icon}  {label}")
            btn.setCheckable(True)
            btn.setFont(QFont(Theme.FONT_FAMILY, 10))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(42)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent; color: {Theme.TEXT_SECONDARY};
                    border: none; border-radius: 10px; padding: 8px 14px; text-align: left;
                }}
                QPushButton:hover {{ background-color: rgba(0,191,255,15); color: {Theme.TEXT_PRIMARY}; }}
                QPushButton:checked {{
                    background-color: rgba(0,191,255,30); color: {Theme.ACCENT};
                    border-left: 3px solid {Theme.ACCENT};
                }}
            """)
            btn.clicked.connect(lambda _, n=label: self._on_click(n))
            layout.addWidget(btn)
            self._buttons.append(btn)
        layout.addStretch()
        self._buttons[0].setChecked(True)

    def _on_click(self, name):
        for b in self._buttons:
            b.setChecked(False)
        s = self.sender()
        if s:
            s.setChecked(True)
        self.page_changed.emit(name)


# ====================================================================
# 6. PIPELINE STEPPER
# ====================================================================

class PipelineStepper(QWidget):
    STAGES = ["Text", "Voice", "Alignment", "Subtitles", "Render"]
    STATE_COLORS = {
        "pending": QColor(Theme.INACTIVE), "active": QColor(Theme.ACCENT),
        "complete": QColor(Theme.SUCCESS), "failed": QColor(Theme.ERROR),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(72)
        self._states = ["pending"] * 5
        self.setStyleSheet("background: transparent;")

    def set_stage(self, index, state="active"):
        for i in range(5):
            if i < index:
                self._states[i] = "complete"
            elif i == index:
                self._states[i] = state
            else:
                self._states[i] = "pending"
        self.update()

    def set_all_complete(self):
        self._states = ["complete"] * 5
        self.update()

    def set_failed_at(self, index):
        self.set_stage(index, "failed")

    def reset(self):
        self._states = ["pending"] * 5
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = len(self.STAGES)
        w, h = self.width(), self.height()
        margin, nr, cy = 50, 11, 26
        positions = [margin + ((w - 2 * margin) * i) / (n - 1) for i in range(n)]

        for i in range(n - 1):
            lc = QColor(Theme.SUCCESS) if self._states[i] == "complete" else QColor(Theme.INACTIVE)
            p.setPen(QPen(lc, 2.5))
            p.drawLine(QPointF(positions[i] + nr, cy), QPointF(positions[i + 1] - nr, cy))

        for i, (stage, state) in enumerate(zip(self.STAGES, self._states)):
            cx = positions[i]
            color = self.STATE_COLORS.get(state, QColor(Theme.INACTIVE))
            if state == "active":
                glow = QColor(Theme.ACCENT)
                glow.setAlpha(45)
                p.setBrush(QBrush(glow))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(cx, cy), nr + 6, nr + 6)
            p.setBrush(QBrush(color))
            p.setPen(QPen(color.lighter(130), 1))
            p.drawEllipse(QPointF(cx, cy), nr, nr)
            if state == "complete":
                p.setPen(QPen(QColor(Theme.TEXT_DARK), 2))
                p.drawLine(QPointF(cx - 4, cy), QPointF(cx - 1, cy + 4))
                p.drawLine(QPointF(cx - 1, cy + 4), QPointF(cx + 5, cy - 4))
            if state == "failed":
                p.setPen(QPen(QColor(Theme.TEXT_WHITE), 2))
                p.drawLine(QPointF(cx - 4, cy - 4), QPointF(cx + 4, cy + 4))
                p.drawLine(QPointF(cx + 4, cy - 4), QPointF(cx - 4, cy + 4))
            tc = Theme.TEXT_PRIMARY if state != "pending" else Theme.TEXT_SECONDARY
            p.setPen(QPen(QColor(tc)))
            fw = QFont.Weight.DemiBold if state == "active" else QFont.Weight.Normal
            p.setFont(QFont(Theme.FONT_FAMILY, 8, fw))
            p.drawText(QRectF(cx - 42, cy + nr + 5, 84, 20),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, stage)


# ====================================================================
# 7. ANIMATED WAVEFORM
# ====================================================================

class AnimatedWaveProgress(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0.0
        self.wave_offset = 0.0
        self.colors = Theme.WAVE_COLORS
        self.cycle_variation = [random.uniform(0.7, 1.8) for _ in self.colors]
        self.phase_offsets = [random.uniform(0, 2 * math.pi) for _ in self.colors]
        self.speed_factors = [random.uniform(0.7, 1.4) for _ in self.colors]
        self.amplitude_factors = [random.uniform(0.7, 1.4) for _ in self.colors]
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick)
        self.anim_timer.start(16)

    def _tick(self):
        self.wave_offset -= 0.09
        if self.wave_offset > 6.28:
            self.wave_offset -= 6.28
        self.update()

    def setProgress(self, val):
        self.progress = max(0.0, min(100.0, val))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = max(1, self.width()), self.height()
        base = h * 0.5
        extra = h * 0.30 * (self.progress / 100.0)
        band = base + extra
        baseline = h - band * 0.6
        for i in range(len(self.colors) - 1, -1, -1):
            p.setBrush(self.colors[i])
            p.setPen(Qt.PenStyle.NoPen)
            path = QPainterPath()
            path.moveTo(0, h)
            cyc = self.cycle_variation[i]
            ph = self.phase_offsets[i]
            sp = self.speed_factors[i]
            amp = band * 0.5 * self.amplitude_factors[i]
            for x in range(w + 1):
                xn = x / float(w)
                wave = math.sin(xn * 2 * math.pi * cyc + self.wave_offset * sp + ph)
                yt = baseline - wave * amp * 0.5
                yt = max(h - band, min(baseline + amp * 0.2, yt))
                path.lineTo(x, yt)
            path.lineTo(w, h)
            path.lineTo(0, h)
            p.drawPath(path)


# ====================================================================
# 8. COLOR-CODED LOG VIEWER
# ====================================================================

class ColorLogViewer(QTextEdit):
    _MAX_LINES = 200
    _LEVEL_COLORS = {"✅": Theme.LOG_SUCCESS, "❌": Theme.LOG_ERROR, "⚠": Theme.LOG_WARN}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont(Theme.FONT_MONO, 9))
        self._line_count = 0

    def append_log(self, message):
        color = Theme.LOG_INFO
        for marker, c in self._LEVEL_COLORS.items():
            if marker in message:
                color = c
                break
        if "WARN" in message.upper() or "timed out" in message.lower():
            color = Theme.LOG_WARN
        elif "ERROR" in message.upper() or "failed" in message.lower():
            color = Theme.LOG_ERROR
        safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = f'<span style="color:{color}; font-family:{Theme.FONT_MONO}; font-size:9pt;">{safe}</span>'
        self.append(html)
        self._line_count += 1
        if self._line_count > self._MAX_LINES:
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor, 1)
            cursor.removeSelectedText()
            cursor.deleteChar()
            self._line_count -= 1


# ====================================================================
# 9. BACKGROUND THREADS
# ====================================================================

class StatusPollerThread(QThread):
    """Polls GET /status/{job_id} with session reuse + exponential backoff."""
    result_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, job_id, parent=None):
        super().__init__(parent)
        self.job_id = job_id
        self._running = True
        self._consecutive_errors = 0

    def run(self):
        session = requests.Session()
        url = f"{Theme.API_BASE_URL}/status/{self.job_id}"
        while self._running and self.job_id:
            try:
                resp = session.get(url, timeout=(3, 8))
                if resp.status_code == 404:
                    self.error_occurred.emit("Job not found on server")
                elif resp.status_code >= 500:
                    self._consecutive_errors += 1
                    self.error_occurred.emit(f"Server error: {resp.status_code}")
                else:
                    self._consecutive_errors = 0
                    self.result_ready.emit(resp.json())
            except requests.ConnectionError:
                self._consecutive_errors += 1
                self.error_occurred.emit("API not reachable")
            except requests.Timeout:
                self._consecutive_errors += 1
                self.error_occurred.emit("Status request timed out")
            except Exception as e:
                self._consecutive_errors += 1
                self.error_occurred.emit(f"Poll error: {e}")
            base_ms = Theme.POLL_INTERVAL_MS
            if self._consecutive_errors > 0:
                delay = min(base_ms * (2 ** self._consecutive_errors), Theme.POLL_BACKOFF_MAX_MS)
            else:
                delay = base_ms
            for _ in range(int(delay / 100)):
                if not self._running:
                    break
                self.msleep(100)
        session.close()

    def stop(self):
        self._running = False


class JobSubmitterThread(QThread):
    """POST /generate in a background thread.

    Supports batch submission (count 1-10) and custom voice path.
    Returns a list of job IDs on success.
    """
    jobs_created = pyqtSignal(list)    # list of job_id strings
    submission_failed = pyqtSignal(str)

    def __init__(self, count: int = 1, voice_path: str = "", parent=None):
        super().__init__(parent)
        self._count = max(1, min(count, 10))
        self._voice_path = voice_path

    def run(self):
        import json as _json
        payload = _json.dumps({"count": self._count, "voice_path": self._voice_path}).encode()
        try:
            resp = requests.post(
                f"{Theme.API_BASE_URL}/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                timeout=(5, 15),
            )
            if resp.status_code == 200:
                data = resp.json()
                jobs = data.get("jobs", [])
                ids = [j.get("job_id", "") for j in jobs if j.get("job_id")]
                if ids:
                    self.jobs_created.emit(ids)
                else:
                    self.submission_failed.emit("API returned no job IDs")
            else:
                self.submission_failed.emit(f"API returned status {resp.status_code}")
        except requests.ConnectionError:
            self.submission_failed.emit("API not reachable")
        except requests.Timeout:
            self.submission_failed.emit("Job submission timed out")
        except Exception as e:
            self.submission_failed.emit(f"Submission error: {e}")


class ActiveJobDetectorThread(QThread):
    """Calls GET /active_job to detect running jobs.

    NEVER scans Redis directly. The API is the single source of truth.
    Optionally waits for the API to become healthy first.
    Handles both the old single-job {status, job_id} and the
    new batch {jobs: [...], count: N} response shapes.
    """
    job_found = pyqtSignal(str)       # emits first active job_id
    no_job_found = pyqtSignal()
    detection_error = pyqtSignal(str)

    def __init__(self, wait_for_health=True, parent=None):
        super().__init__(parent)
        self._wait_for_health = wait_for_health

    def run(self):
        session = requests.Session()

        # Wait for API to be reachable (up to 15 seconds)
        if self._wait_for_health:
            for attempt in range(15):
                try:
                    resp = session.get(f"{Theme.API_BASE_URL}/health", timeout=2)
                    if resp.status_code == 200:
                        break
                except Exception:
                    pass
                self.msleep(1000)
            else:
                self.detection_error.emit("API not reachable after 15s")
                session.close()
                return

        try:
            resp = session.get(f"{Theme.API_BASE_URL}/active_job", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # New batch response: {"jobs": [...], "count": N}
                if "jobs" in data:
                    jobs = data.get("jobs", [])
                    if jobs:
                        self.job_found.emit(jobs[0].get("job_id", ""))
                    else:
                        self.no_job_found.emit()
                # Legacy single-job response: {"status": ..., "job_id": ...}
                elif data.get("status", "none") != "none" and data.get("job_id"):
                    self.job_found.emit(data["job_id"])
                else:
                    self.no_job_found.emit()
            else:
                self.detection_error.emit(f"API returned {resp.status_code}")
        except requests.ConnectionError:
            self.detection_error.emit("API not reachable")
        except requests.Timeout:
            self.detection_error.emit("Active job detection timed out")
        except Exception as e:
            self.detection_error.emit(f"Detection error: {e}")
        finally:
            session.close()


class HealthCheckThread(QThread):
    """Polls /health with exponential backoff on failure.

    Backoff schedule on consecutive failures:
      1st fail  → wait  5s
      2nd fail  → wait 10s
      3rd fail  → wait 20s
      4th+ fail → wait 30s (capped)
    Resets to normal 10s interval immediately on recovery.
    """
    health_updated = pyqtSignal(dict)

    _NORMAL_INTERVAL_S = 10
    _BACKOFF_BASE_S    = 5
    _BACKOFF_MAX_S     = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    def run(self):
        consecutive_failures = 0
        session = requests.Session()

        while self._running:
            api_ok = False
            try:
                t0 = _time.perf_counter()
                resp = session.get(f"{Theme.API_BASE_URL}/health", timeout=3)
                api_latency = round((_time.perf_counter() - t0) * 1000, 1)
                data = resp.json()
                data["api_latency_ms"] = api_latency
                self.health_updated.emit(data)
                consecutive_failures = 0
                api_ok = True
            except requests.Timeout:
                consecutive_failures += 1
                self.health_updated.emit({
                    "status": "unreachable", "redis": False,
                    "redis_latency_ms": -1, "api_latency_ms": -1,
                    "_timeout": True,
                })
            except requests.ConnectionError:
                consecutive_failures += 1
                # Session may be stale after a connection drop — recreate it.
                try:
                    session.close()
                except Exception:
                    pass
                session = requests.Session()
                self.health_updated.emit({
                    "status": "unreachable", "redis": False,
                    "redis_latency_ms": -1, "api_latency_ms": -1,
                })
            except Exception:
                consecutive_failures += 1
                self.health_updated.emit({
                    "status": "unreachable", "redis": False,
                    "redis_latency_ms": -1, "api_latency_ms": -1,
                })

            if api_ok:
                wait_s = self._NORMAL_INTERVAL_S
            else:
                wait_s = min(
                    self._BACKOFF_BASE_S * (2 ** (consecutive_failures - 1)),
                    self._BACKOFF_MAX_S,
                )

            # Sleep in 100ms slices so stop() is responsive.
            slices = int(wait_s * 10)
            for _ in range(slices):
                if not self._running:
                    break
                self.msleep(100)

        session.close()

    def stop(self):
        self._running = False


# ====================================================================
# 10. MAIN WINDOW
# ====================================================================

_STAGE_MAP = {
    "text": 0, "voice": 1, "alignment": 2,
    "subtitles": 3, "subtitle": 3, "render": 4, "video": 4,
    "waiting": -1, "done": -1,
}

_STAGE_NAMES = {
    0: "Text Processing", 1: "Voice Generation", 2: "Word Alignment",
    3: "Subtitle Generation", 4: "Video Rendering",
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SHORTZ — AI Pipeline Automation")
        self.setMinimumSize(900, 650)
        self.resize(1100, 750)

        # Thread-safe state
        self._state_mutex = QMutex()
        self.current_progress = 0.0
        self.is_running = False
        self.job_id = None
        self._job_start_time = None
        self._worker_alive = False
        self._current_stage_name = ""
        self._current_stage_idx = -1

        # Voice + batch selection state
        self._selected_voice_path: str = ""   # set by Browse button
        self._batch_count: int = 1             # set by batch ComboBox

        # Threads
        self._poller_thread = None
        self._submitter_thread = None
        self._detector_thread = None
        self._health_thread = None

        # Build UI
        self._build_ui()

        # Elapsed / ETA timer
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._update_elapsed)
        self._elapsed_timer.setInterval(1000)

        # Health monitor
        self._start_health_monitor()

        # Auto-launch: 500ms after event loop starts
        QTimer.singleShot(500, self._auto_launch)

    # ------------------------------------------------------------------
    # UI CONSTRUCTION
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("root")
        central.setStyleSheet(f"QWidget#root {{ background-color: {Theme.BG_APP}; }}")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = HeaderBar()
        root.addWidget(self.header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.sidebar = SidebarNavigation()
        body.addWidget(self.sidebar)

        content = QVBoxLayout()
        content.setContentsMargins(20, 16, 20, 12)
        content.setSpacing(14)

        # === Top row: Control + Progress ===
        top = QHBoxLayout()
        top.setSpacing(16)

        # --- Control Card ---
        ctrl = GlassCard()
        cl = QVBoxLayout(ctrl)
        cl.setContentsMargins(22, 18, 22, 18)
        cl.setSpacing(12)

        cl.addWidget(_make_label("AUTOMATION CONTROL", 11, bold=True, color=Theme.TEXT_PRIMARY))
        cl.addStretch()

        # Batch count selector
        batch_row = QHBoxLayout()
        batch_row.setSpacing(8)
        batch_lbl = _make_label("Videos:", 9, color=Theme.TEXT_SECONDARY)
        batch_row.addWidget(batch_lbl)
        self._batch_combo = QComboBox()
        self._batch_combo.setFont(QFont(Theme.FONT_FAMILY, 10))
        for n in (1, 3, 5, 10):
            self._batch_combo.addItem(f"{n} video{'s' if n > 1 else ''}")
        self._batch_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {Theme.BG_INPUT}; color: {Theme.TEXT_WHITE};
                border: 1px solid rgba(255,255,255,40); border-radius: 10px;
                padding: 6px 10px;
            }}
            QComboBox::drop-down {{ border: 0; width: 20px; }}
            QComboBox QAbstractItemView {{
                background: #0A1530; border: 1px solid {Theme.ACCENT};
                selection-background-color: rgba(0,191,255,60); color: {Theme.TEXT_WHITE};
            }}
        """)
        self._batch_combo.currentIndexChanged.connect(self._on_batch_changed)
        batch_row.addWidget(self._batch_combo, 1)
        cl.addLayout(batch_row)

        # Voice sample browser
        voice_row = QHBoxLayout()
        voice_row.setSpacing(8)
        self._voice_label = _make_label("No voice selected", 8, color=Theme.TEXT_SECONDARY, mono=True)
        self._voice_label.setWordWrap(False)
        voice_row.addWidget(self._voice_label, 1)
        browse_btn = QPushButton("🎙 Browse")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setFont(QFont(Theme.FONT_FAMILY, 9))
        browse_btn.setFixedWidth(90)
        browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Theme.TEXT_PRIMARY};
                border: 1px solid rgba(255,255,255,40); border-radius: 10px; padding: 5px;
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,15); border-color: {Theme.ACCENT};
            }}
        """)
        browse_btn.clicked.connect(self._browse_voice)
        voice_row.addWidget(browse_btn)
        cl.addLayout(voice_row)

        self.start_btn = QPushButton("START AUTOMATION ▶")
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setFont(QFont(Theme.FONT_FAMILY, 11, QFont.Weight.DemiBold))
        self.start_btn.clicked.connect(self.start_automation)
        self.start_btn.setMinimumHeight(44)
        self.start_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: qlineargradient(
                    x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(0,180,255,255), stop:1 rgba(0,255,255,255)
                );
                color: {Theme.TEXT_DARK}; border-radius: 16px;
                padding: 12px; letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background-color: qlineargradient(
                    x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(50,200,255,255), stop:1 rgba(50,255,255,255)
                );
            }}
            QPushButton:pressed {{ background-color: rgba(0,150,230,255); }}
            QPushButton:disabled {{
                background-color: rgba(80,80,80,150);
                color: rgba(180,180,180,150);
            }}
        """)
        cl.addWidget(self.start_btn)

        open_btn = QPushButton("📁  OUTPUT FOLDER")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setFont(QFont(Theme.FONT_FAMILY, 10))
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Theme.TEXT_PRIMARY};
                border: 1px solid rgba(255,255,255,40); border-radius: 14px;
                padding: 8px;
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,15); border-color: {Theme.ACCENT};
            }}
        """)
        open_btn.clicked.connect(self.open_output_folder)
        cl.addWidget(open_btn)
        cl.addStretch()

        # --- Progress Card ---
        prog = GlassCard()
        pl = QVBoxLayout(prog)
        pl.setContentsMargins(22, 18, 22, 18)
        pl.setSpacing(8)

        pl.addWidget(_make_label("JOB PROGRESS", 11, bold=True, color=Theme.TEXT_PRIMARY))

        prow = QHBoxLayout()
        self.percent_label = QLabel("0%")
        self.percent_label.setFont(QFont(Theme.FONT_FAMILY, 48, QFont.Weight.Bold))
        self.percent_label.setStyleSheet(f"color: {Theme.TEXT_WHITE}; background: transparent;")
        apply_neon_shadow(self.percent_label, Theme.SHADOW_NEON, radius=12)
        prow.addWidget(self.percent_label)
        prow.addStretch()
        pl.addLayout(prow)

        self.waveform_widget = AnimatedWaveProgress()
        self.waveform_widget.setFixedHeight(65)
        self.waveform_widget.setStyleSheet("""
            QWidget {
                border-radius: 14px;
                border: 1px solid rgba(255,255,255,30);
                background-color: rgba(6,10,30,120);
            }
        """)
        pl.addWidget(self.waveform_widget)

        # Job context panel
        ctx = QWidget()
        ctx.setStyleSheet(f"""
            QWidget {{
                background-color: rgba(10,15,30,180);
                border: 1px solid rgba(255,255,255,20);
                border-radius: 10px;
            }}
            QLabel {{ background: transparent; border: none; padding: 0; }}
        """)
        ctx_l = QGridLayout(ctx)
        ctx_l.setContentsMargins(12, 8, 12, 8)
        ctx_l.setVerticalSpacing(4)
        ctx_l.setHorizontalSpacing(16)

        ctx_l.addWidget(_make_label("Stage:", 8, bold=True, color=Theme.TEXT_SECONDARY), 0, 0)
        self.ctx_stage = _make_label("—", 8, color=Theme.TEXT_PRIMARY, mono=True)
        ctx_l.addWidget(self.ctx_stage, 0, 1)
        ctx_l.addWidget(_make_label("Elapsed:", 8, bold=True, color=Theme.TEXT_SECONDARY), 1, 0)
        self.ctx_elapsed = _make_label("--", 8, color=Theme.TEXT_PRIMARY, mono=True)
        ctx_l.addWidget(self.ctx_elapsed, 1, 1)
        ctx_l.addWidget(_make_label("ETA:", 8, bold=True, color=Theme.TEXT_SECONDARY), 0, 2)
        self.ctx_eta = _make_label("--", 8, color=Theme.TEXT_PRIMARY, mono=True)
        ctx_l.addWidget(self.ctx_eta, 0, 3)
        ctx_l.addWidget(_make_label("Job ID:", 8, bold=True, color=Theme.TEXT_SECONDARY), 1, 2)
        self.ctx_job_id = _make_label("—", 8, color=Theme.TEXT_SECONDARY, mono=True)
        ctx_l.addWidget(self.ctx_job_id, 1, 3)
        pl.addWidget(ctx)

        self.status_label = _make_label("Status: Idle", 9, color=Theme.TEXT_SECONDARY)
        pl.addWidget(self.status_label)

        top.addWidget(ctrl, 2)
        top.addWidget(prog, 3)

        # === Pipeline Stepper ===
        step_card = GlassCard()
        sl = QVBoxLayout(step_card)
        sl.setContentsMargins(16, 10, 16, 4)
        sl.addWidget(_make_label("PIPELINE STAGES", 10, bold=True, color=Theme.TEXT_PRIMARY))
        self.pipeline_stepper = PipelineStepper()
        sl.addWidget(self.pipeline_stepper)

        # === Log Viewer ===
        log_card = GlassCard()
        ll = QVBoxLayout(log_card)
        ll.setContentsMargins(16, 10, 16, 10)
        ll.setSpacing(6)
        log_title = _make_label("SYSTEM LOG", 10, bold=True, color=Theme.TEXT_PRIMARY)
        apply_neon_shadow(log_title, Theme.SHADOW_WHITE, radius=6)
        ll.addWidget(log_title)

        self.log_viewer = ColorLogViewer()
        self.log_viewer.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Theme.BG_LOG}; color: {Theme.TEXT_PRIMARY};
                border: 1px solid rgba(255,255,255,20); border-radius: 10px;
                padding: 8px; selection-background-color: rgba(0,191,255,80);
            }}
            QScrollBar:vertical {{ border: none; background: transparent; width: 8px; }}
            QScrollBar::handle:vertical {{
                background: qlineargradient(
                    x1:0,y1:0,x2:1,y2:0,
                    stop:0 rgba(0,255,255,160), stop:1 rgba(0,100,255,160)
                );
                border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none; background: none;
            }}
        """)
        ll.addWidget(self.log_viewer)

        content.addLayout(top, 4)
        content.addWidget(step_card, 1)
        content.addWidget(log_card, 3)

        # Wrap dashboard content in a container widget for stacking
        dashboard_page = QWidget()
        dashboard_page.setLayout(content)

        # Build the QStackedWidget with all view pages
        from gui.views.pipeline_view import PipelineView
        from gui.views.history_view import HistoryView
        from gui.views.settings_view import SettingsView

        self._stacked = QStackedWidget()
        self._stacked.addWidget(dashboard_page)   # index 0
        self._stacked.addWidget(PipelineView())    # index 1
        self._stacked.addWidget(HistoryView())     # index 2
        self._stacked.addWidget(SettingsView())    # index 3

        body.addWidget(self._stacked)

        # Connect sidebar navigation
        self.sidebar.page_changed.connect(self._switch_page)

        root.addLayout(body)

    # ------------------------------------------------------------------
    # LOGGING
    # ------------------------------------------------------------------

    def log_message(self, message):
        ts = QTime.currentTime().toString("hh:mm:ss")
        self.log_viewer.append_log(f"[{ts}] {message}")
        log.info(message)

    # ------------------------------------------------------------------
    # UTILITY
    # ------------------------------------------------------------------

    def open_output_folder(self):
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "video")
        os.makedirs(d, exist_ok=True)
        subprocess.Popen(["explorer", d])

    # ------------------------------------------------------------------
    # HEALTH MONITOR
    # ------------------------------------------------------------------

    def _start_health_monitor(self):
        self._health_thread = HealthCheckThread(parent=None)
        self._health_thread.health_updated.connect(
            self._on_health_update, Qt.ConnectionType.QueuedConnection
        )
        self._health_thread.finished.connect(self._health_thread.deleteLater)
        self._health_thread.start()

    def _on_health_update(self, data):
        status = data.get("status", "unreachable")
        redis_ok = data.get("redis", False)
        redis_ms = data.get("redis_latency_ms", -1)
        api_ms = data.get("api_latency_ms", -1)
        queue_size = data.get("queue_size", 0)
        processing = data.get("processing_count", 0)
        api_up = (status not in ("unreachable", ""))

        if not api_up:
            self.header.svc_api.set_down("OFFLINE")
            self.header.svc_redis.set_down("OFFLINE")
            self._worker_alive = False
            self.header.svc_worker.set_unknown("idle")
        else:
            api_detail = f"online ({api_ms:.0f}ms)" if api_ms >= 0 else "online"
            self.header.svc_api.set_healthy(api_detail)
            if redis_ok:
                q_info = f"{redis_ms:.0f}ms  Q:{queue_size}  P:{processing}"
                self.header.svc_redis.set_healthy(q_info)
            else:
                self.header.svc_redis.set_down("OFFLINE")

            if self._worker_alive:
                self.header.svc_worker.set_healthy("active")
            else:
                self.header.svc_worker.set_unknown("idle")

    def _switch_page(self, name: str):
        """Switch QStackedWidget page when sidebar selection changes."""
        pages = {"Dashboard": 0, "Pipeline": 1, "History": 2, "Settings": 3}
        idx = pages.get(name, 0)
        self._stacked.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # ELAPSED / ETA
    # ------------------------------------------------------------------

    def _update_elapsed(self):
        if self._job_start_time is None:
            return
        elapsed = _time.time() - self._job_start_time
        m, s = divmod(int(elapsed), 60)
        self.ctx_elapsed.setText(f"{m}m {s:02d}s")
        progress = self.current_progress
        if progress > 2:
            rate = elapsed / progress
            rem = rate * (100.0 - progress)
            rm, rs = divmod(int(rem), 60)
            self.ctx_eta.setText(f"~{rm}m {rs:02d}s")
        else:
            self.ctx_eta.setText("calculating…")

    # ------------------------------------------------------------------
    # THREAD LIFECYCLE
    # ------------------------------------------------------------------

    def _start_poller(self):
        self._stop_poller()
        with QMutexLocker(self._state_mutex):
            jid = self.job_id
        if not jid:
            return
        self._poller_thread = StatusPollerThread(jid, parent=None)
        self._poller_thread.result_ready.connect(
            self._on_status_update, Qt.ConnectionType.QueuedConnection
        )
        self._poller_thread.error_occurred.connect(
            self._on_poll_error, Qt.ConnectionType.QueuedConnection
        )
        self._poller_thread.finished.connect(self._poller_thread.deleteLater)
        self._poller_thread.start()

    def _stop_poller(self):
        if self._poller_thread is not None:
            self._poller_thread.stop()
            self._poller_thread.wait(500)
            self._poller_thread = None

    def _on_poll_error(self, msg):
        self.log_message(f"⚠ {msg}")

    # ------------------------------------------------------------------
    # JOB SUBMISSION
    # ------------------------------------------------------------------

    def start_automation(self):
        with QMutexLocker(self._state_mutex):
            if self.job_id:
                self.log_message("Job already active — attaching poller")
                self._start_poller()
                return
            self.start_btn.setEnabled(False)
            count = self._batch_count
            lbl = f"SUBMITTING {count} JOB{'S' if count > 1 else ''} …"
            self.start_btn.setText(lbl)

        voice = self._selected_voice_path
        self._submitter_thread = JobSubmitterThread(
            count=count, voice_path=voice, parent=None
        )
        self._submitter_thread.jobs_created.connect(
            self._on_jobs_created, Qt.ConnectionType.QueuedConnection
        )
        self._submitter_thread.submission_failed.connect(
            self._on_submission_failed, Qt.ConnectionType.QueuedConnection
        )
        self._submitter_thread.finished.connect(self._submitter_thread.deleteLater)
        self._submitter_thread.start()

    def _on_jobs_created(self, job_ids: list):
        """Handle batch job submission response — attach poller to first job."""
        if not job_ids:
            return
        first_id = job_ids[0]
        with QMutexLocker(self._state_mutex):
            self.job_id = first_id
            self.is_running = True
        self._job_start_time = _time.time()
        self._elapsed_timer.start()
        count = len(job_ids)
        lbl = f"MONITORING {count} JOB{'S' if count > 1 else ''} ⏳"
        self.start_btn.setText(lbl)
        self.start_btn.setEnabled(True)
        self.pipeline_stepper.reset()
        self.ctx_job_id.setText(first_id[:8] + "…")
        self.ctx_stage.setText("Queued")
        self.ctx_elapsed.setText("0m 00s")
        self.ctx_eta.setText("--")
        if count == 1:
            self.log_message(f"✅ Job submitted: {first_id[:8]}…")
        else:
            self.log_message(f"✅ Batch of {count} jobs submitted — monitoring first job")
        self._start_poller()

    # ------------------------------------------------------------------
    # VOICE BROWSER + BATCH SELECTOR HANDLERS
    # ------------------------------------------------------------------

    def _browse_voice(self):
        """Open a file dialog to select a voice sample (.wav or .mp3)."""
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Voice Sample",
            "",
            "Audio Files (*.wav *.mp3);;All Files (*)",
        )
        if path:
            import os
            self._selected_voice_path = path
            name = os.path.basename(path)
            self._voice_label.setText(name)
            self._voice_label.setStyleSheet(
                f"color: {Theme.TEXT_WHITE}; font-family: {Theme.FONT_MONO}; font-size: 8pt;"
            )
            self.log_message(f"🎙 Voice sample: {name}")

    def _on_batch_changed(self, index: int):
        """Update _batch_count when the batch ComboBox selection changes."""
        counts = [1, 3, 5, 10]
        self._batch_count = counts[index] if 0 <= index < len(counts) else 1
        if self._batch_count == 1:
            self.start_btn.setText("START AUTOMATION ▶")
        else:
            self.start_btn.setText(f"START {self._batch_count} VIDEOS ▶")

    def _on_submission_failed(self, msg):
        self.start_btn.setText("START AUTOMATION ▶")
        self.start_btn.setEnabled(True)
        self.log_message(f"❌ Submission failed: {msg}")

    # ------------------------------------------------------------------
    # STATUS UPDATE (main thread via QueuedConnection)
    # ------------------------------------------------------------------

    def _on_status_update(self, data):
        if "detail" in data and data.get("detail") == "Job not found":
            return

        progress = float(data.get("progress", 0))
        status = data.get("status", "unknown")
        stage = data.get("stage", "")

        self._worker_alive = True

        if self._job_start_time is None and status in ("running", "processing"):
            self._job_start_time = _time.time()
            self._elapsed_timer.start()

        # Progress
        self.current_progress = progress
        self.waveform_widget.setProgress(progress)
        self.percent_label.setText(f"{int(progress)}%")
        self.status_label.setText(f"Status: {status.capitalize()}")

        # Stage context
        if stage and stage != "waiting":
            idx = _STAGE_MAP.get(stage.lower(), -1)
            if idx >= 0:
                self._current_stage_idx = idx
                self._current_stage_name = _STAGE_NAMES.get(idx, stage.capitalize())
                self.ctx_stage.setText(self._current_stage_name)
                self.pipeline_stepper.set_stage(idx, "active")
        elif stage == "waiting":
            self.ctx_stage.setText("Waiting for worker…")

        if status == "complete":
            self._stop_poller()
            self._elapsed_timer.stop()
            with QMutexLocker(self._state_mutex):
                self.is_running = False
                self.job_id = None
            self.waveform_widget.setProgress(100.0)
            self.percent_label.setText("100%")
            self.pipeline_stepper.set_all_complete()
            self.start_btn.setText("NEW JOB ▶")
            self.start_btn.setEnabled(True)
            self.status_label.setText("Status: Complete")
            self.ctx_stage.setText("All stages complete")
            if self._job_start_time:
                total = _time.time() - self._job_start_time
                m, s = divmod(int(total), 60)
                self.ctx_elapsed.setText(f"{m}m {s:02d}s")
                self.ctx_eta.setText("done")
            self._job_start_time = None
            self.log_message("✅ Job completed successfully")

        elif status == "failed":
            self._stop_poller()
            self._elapsed_timer.stop()
            with QMutexLocker(self._state_mutex):
                self.is_running = False
                self.job_id = None
            error_msg = data.get("error", "Unknown error")
            if stage:
                idx = _STAGE_MAP.get(stage.lower(), -1)
                if idx >= 0:
                    self.pipeline_stepper.set_failed_at(idx)
                    self.ctx_stage.setText(f"FAILED: {_STAGE_NAMES.get(idx, stage)}")
            self.start_btn.setText("RETRY ▶")
            self.start_btn.setEnabled(True)
            self.status_label.setText("Status: Failed")
            self.ctx_eta.setText("--")
            self._job_start_time = None
            self.log_message(f"❌ Job failed: {error_msg}")

    # ------------------------------------------------------------------
    # AUTO-LAUNCH (API-based — never scans Redis)
    # ------------------------------------------------------------------

    def _auto_launch(self):
        """Wait for API health → call /active_job → attach or submit.

        Uses ActiveJobDetectorThread so no Redis import is needed.
        """
        self.log_message("Auto-launch: waiting for API health…")
        self._detector_thread = ActiveJobDetectorThread(wait_for_health=True, parent=None)
        self._detector_thread.job_found.connect(
            self._on_job_detected, Qt.ConnectionType.QueuedConnection
        )
        self._detector_thread.no_job_found.connect(
            self._on_no_job_found, Qt.ConnectionType.QueuedConnection
        )
        self._detector_thread.detection_error.connect(
            lambda msg: self.log_message(f"⚠ {msg}"),
            Qt.ConnectionType.QueuedConnection,
        )
        self._detector_thread.finished.connect(self._detector_thread.deleteLater)
        self._detector_thread.start()

    def _on_job_detected(self, job_id):
        with QMutexLocker(self._state_mutex):
            self.job_id = job_id
            self.is_running = True
        self._job_start_time = _time.time()
        self._elapsed_timer.start()
        self.start_btn.setText("MONITORING ⏳")
        self.pipeline_stepper.reset()
        self.ctx_job_id.setText(job_id[:8] + "…")
        self.ctx_stage.setText("Resuming…")
        self.log_message(f"✅ Attached to active job: {job_id[:8]}…")
        self._start_poller()

    def _on_no_job_found(self):
        self.log_message("No active job — submitting new automation job")
        self.start_automation()

    # ------------------------------------------------------------------
    # CLEAN SHUTDOWN
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._stop_poller()
        if self._health_thread is not None:
            self._health_thread.stop()
            self._health_thread.wait(1000)
            self._health_thread = None
        for t in (self._submitter_thread, self._detector_thread):
            if t is not None and t.isRunning():
                t.quit()
                t.wait(1000)
        event.accept()


# ====================================================================
# 11. ENTRY POINT
# ====================================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()