"""
apps/overlay/main.py
────────────────────
Aethvion Suite — Desktop Overlay Sidecar

A lightweight system-tray companion that lets you ask questions about your
screen without opening the dashboard browser tab.

Hotkey : Ctrl+Shift+Space  (captures screen → opens floating input window)
Tray   : right-click icon for quick actions

Features:
  • Resizable window (drag bottom-right corner)
  • Session history — last 10 screenshot sessions, browseable via History button
  • Screenshot thumbnail shown at the top of every session
  • Clear ▸ Response separator between each user question and the AI answer
  • Independent background opacity vs text opacity
  • All appearance settings driven by dashboard → Settings → Desktop Overlay

Dependencies (pip install ...):
    PyQt6   pystray   Pillow   mss   keyboard

Usage:
    python apps/overlay/main.py
"""
from __future__ import annotations

import base64
import html as _html_mod
import io
import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Project root on sys.path ──────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

# ── Config helpers ────────────────────────────────────────────────────────────
_CONFIG_PATH = ROOT / "data" / "overlay" / "config.json"

def _load_overlay_config() -> dict:
    """Read data/overlay/config.json, returning defaults for missing keys."""
    defaults = {
        "bg_opacity":   0.93,
        "text_opacity": 1.0,
        "font_size":    11,
        "hotkey":       "ctrl+shift+space",
    }
    try:
        if _CONFIG_PATH.exists():
            data = json.loads(_CONFIG_PATH.read_text("utf-8"))
            # Back-compat: migrate legacy "opacity" → "bg_opacity"
            if "opacity" in data and "bg_opacity" not in data:
                data["bg_opacity"] = data.pop("opacity")
            return {**defaults, **data}
    except Exception:
        pass
    return defaults


# ── Discover dashboard port ───────────────────────────────────────────────────
def _find_dashboard_port() -> int:
    try:
        ports_file = ROOT / "data" / "system" / "ports.json"
        if ports_file.exists():
            data = json.loads(ports_file.read_text(encoding="utf-8"))
            for port, name in data.items():
                if "dashboard" in str(name).lower() or "nexus" in str(name).lower():
                    return int(port)
    except Exception:
        pass
    return 8080


DASHBOARD_URL = f"http://localhost:{_find_dashboard_port()}"

# ── Qt availability check ─────────────────────────────────────────────────────
try:
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout,
        QTextEdit, QPushButton, QLabel, QFrame, QComboBox,
        QTextBrowser, QSizeGrip,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QPoint, QSize, QUrl
    from PyQt6.QtGui import QFont, QTextCursor

    HAS_QT = True
except ImportError:
    HAS_QT = False

# ── Screenshot / thumbnail helpers ───────────────────────────────────────────

def list_monitors() -> list[dict]:
    try:
        import mss
        with mss.mss() as sct:
            result = []
            for i, m in enumerate(sct.monitors):
                label = "All Screens Combined" if i == 0 else f"Screen {i}  ({m['width']}×{m['height']})"
                result.append({"index": i, "label": label, "width": m["width"], "height": m["height"]})
            return result
    except Exception:
        return [{"index": 1, "label": "Primary Screen", "width": 0, "height": 0}]


def take_screenshot_b64(monitor_index: int = 1) -> Optional[str]:
    try:
        import mss
        with mss.mss() as sct:
            monitors = sct.monitors
            idx = max(0, min(monitor_index, len(monitors) - 1))
            if not monitors:
                return None
            sct_img = sct.grab(monitors[idx])
        from PIL import Image
        img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except ImportError as e:
        print(f"[Overlay] Screenshot dependency missing ({e}). Install mss and Pillow.")
        return None
    except Exception as e:
        print(f"[Overlay] Screenshot failed: {e}")
        return None


def _make_thumb(screenshot_b64: str, max_width: int = 200) -> Optional[str]:
    """Downscale a full screenshot to a small JPEG thumbnail (base64)."""
    try:
        from PIL import Image
        raw = base64.b64decode(screenshot_b64)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        new_h = int(h * max_width / w)
        img = img.resize((max_width, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=55, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return None


# ── API worker ────────────────────────────────────────────────────────────────

class AskWorker(QObject):
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, question: str, screenshot_b64: Optional[str], dashboard_url: str):
        super().__init__()
        self.question       = question
        self.screenshot_b64 = screenshot_b64
        self.dashboard_url  = dashboard_url

    def run(self) -> None:
        import urllib.request, urllib.error
        payload = json.dumps({"question": self.question, "screenshot_b64": self.screenshot_b64}).encode()
        req = urllib.request.Request(
            f"{self.dashboard_url}/api/overlay/ask",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode())
                self.finished.emit(data.get("answer", "(no response)"))
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode()).get("detail", str(e))
            except Exception:
                detail = str(e)
            self.error.emit(f"Server error {e.code}: {detail}")
        except urllib.error.URLError as e:
            self.error.emit(f"Could not reach dashboard ({self.dashboard_url}): {e.reason}")
        except Exception as e:
            self.error.emit(str(e))


# ── Custom input widget ───────────────────────────────────────────────────────

class ChatInput(QTextEdit):
    send_requested = pyqtSignal()

    def __init__(self, font_size: int = 11, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("What do you want to know about this screen?")
        self.setFont(QFont("Segoe UI", font_size))
        self.setAcceptRichText(False)
        self.setFixedHeight(50)
        self.setStyleSheet("""
            QTextEdit {
                background: rgba(18,18,32,210);
                color: rgba(220,220,245,255);
                border: 1px solid rgba(99,102,241,100);
                border-radius: 9px;
                padding: 3px 6px;
            }
            QTextEdit:focus { border-color: rgba(99,102,241,210); }
        """)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.send_requested.emit()
        else:
            super().keyPressEvent(event)


# ── Main overlay window ───────────────────────────────────────────────────────

_RESIZE_GRIP = 18
_MAX_HISTORY = 10


class OverlayWindow(QWidget):
    show_overlay = pyqtSignal(str)

    def __init__(self, dashboard_url: str):
        super().__init__()
        self._dashboard_url           = dashboard_url
        self._screenshot_b64: Optional[str]  = None
        self._drag_pos: Optional[QPoint]     = None
        self._resizing                        = False
        self._resize_start_global: Optional[QPoint] = None
        self._resize_start_size:   Optional[QSize]  = None
        self._worker_thread: Optional[QThread]      = None
        self._worker:        Optional[AskWorker]    = None
        self._selected_monitor: int = 1

        # Session history — list of:
        #   {"time": str, "pairs": [{"q": str, "a": str|None}], "thumb_b64": str|None}
        self._history: list[dict]           = []
        self._current_entry: Optional[dict] = None

        # View state
        self._show_history = False          # False = current session, True = history list
        self._history_detail_idx: Optional[int] = None  # index when viewing a past session

        # Appearance (refreshed from config on each open)
        cfg = _load_overlay_config()
        self._bg_opacity   = float(cfg.get("bg_opacity",   0.93))
        self._text_opacity = float(cfg.get("text_opacity", 1.0))
        self._font_size    = int(cfg.get("font_size",      11))

        self._build_ui()
        self.show_overlay.connect(self._on_show_overlay)

    # ── Appearance ────────────────────────────────────────────────────────────

    def _apply_appearance(self) -> None:
        """Rebuild all dynamic style sheets from current _bg_opacity / _text_opacity."""
        bg_a  = int(self._bg_opacity * 255)
        res_bg = int(self._bg_opacity * 0.82 * 255)
        txt_a  = int(self._text_opacity * 255)

        self._container.setStyleSheet(f"""
            QFrame#aovContainer {{
                background-color: rgba(12, 12, 22, {bg_a});
                border: 1px solid rgba(99, 102, 241, 130);
                border-radius: 14px;
            }}
        """)
        self._response.setStyleSheet(f"""
            QTextBrowser {{
                background: rgba(8, 8, 18, {res_bg});
                color: rgba(210, 210, 235, {txt_a});
                border: 1px solid rgba(99,102,241,55);
                border-radius: 9px;
                padding: 6px;
            }}
            QScrollBar:vertical {{
                background: rgba(20,20,35,180);
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(99,102,241,150);
                border-radius: 3px;
            }}
        """)
        self._response.document().setDefaultStyleSheet(f"""
            body {{ color: rgba(210,210,235,{txt_a}); }}
            h1, h2, h3, h4 {{ color: #818cf8; margin-top: 6px; margin-bottom: 2px; font-weight: bold; }}
            code {{
                background-color: rgba(99,102,241,40);
                color: rgba(226,232,240,{txt_a});
                font-family: 'Consolas', 'Cascadia Code', 'Courier New', monospace;
                padding: 2px 4px; border-radius: 4px;
            }}
            pre {{
                background-color: rgba(0,0,0,100);
                border: 1px solid rgba(99,102,241,60);
                padding: 12px; border-radius: 8px; margin: 8px 0;
                font-family: 'Consolas', 'Cascadia Code', 'Courier New', monospace;
            }}
            a {{ color: #818cf8; text-decoration: none; }}
            li {{ margin-bottom: 4px; }}
            blockquote {{
                border-left: 3px solid rgba(99,102,241,150);
                padding-left: 10px;
                color: rgba(210,210,235,{int(self._text_opacity * 180)});
                font-style: italic;
            }}
        """)
        self._response.setFont(QFont("Segoe UI", self._font_size))
        self._input.setFont(QFont("Segoe UI", self._font_size))

    # ── Color helpers (use text_opacity) ─────────────────────────────────────

    def _c(self, r: int, g: int, b: int, base_a: float = 1.0) -> str:
        """Return an rgba(...) string scaled by text_opacity."""
        a = int(base_a * self._text_opacity * 255)
        return f"rgba({r},{g},{b},{a})"

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(420, 280)
        self.resize(540, 440)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        self._container = QFrame(self)
        self._container.setObjectName("aovContainer")
        outer.addWidget(self._container)

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        # ── Title bar ─────────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        dot = QLabel("◈")
        dot.setStyleSheet("color: rgba(99,102,241,255); font-size: 15px;")

        title_lbl = QLabel("Ask about screen")
        title_lbl.setStyleSheet("color: rgba(200,200,224,220); font-size: 13px; font-weight: 600;")

        self._hotkey_lbl = QLabel("Ctrl+Shift+Space")
        self._hotkey_lbl.setStyleSheet("color: rgba(120,120,150,180); font-size: 11px;")

        self._hist_btn = QPushButton("🕐")
        self._hist_btn.setFixedSize(26, 26)
        self._hist_btn.setCheckable(True)
        self._hist_btn.setToolTip("Browse history")
        self._hist_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(160,160,200,200);
                border: none; border-radius: 13px; font-size: 13px;
            }
            QPushButton:hover   { background: rgba(99,102,241,120); }
            QPushButton:checked { background: rgba(99,102,241,180); color: white; }
        """)
        self._hist_btn.toggled.connect(self._on_history_toggled)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(160,160,180,200);
                border: none; border-radius: 13px; font-size: 12px;
            }
            QPushButton:hover { background: rgba(220,55,55,180); color: white; }
        """)
        close_btn.clicked.connect(self.hide)

        title_row.addWidget(dot)
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        title_row.addWidget(self._hotkey_lbl)
        title_row.addWidget(self._hist_btn)
        title_row.addWidget(close_btn)
        layout.addLayout(title_row)

        # ── Screen selector row ───────────────────────────────────────────────
        screen_row = QHBoxLayout()
        screen_row.setSpacing(6)

        screen_lbl = QLabel("Screen:")
        screen_lbl.setStyleSheet("color: rgba(140,140,170,200); font-size: 11px;")

        self._screen_combo = QComboBox()
        self._screen_combo.setFixedHeight(26)
        self._screen_combo.setStyleSheet("""
            QComboBox {
                background: rgba(18,18,32,210); color: rgba(200,200,224,220);
                border: 1px solid rgba(99,102,241,80); border-radius: 6px;
                padding: 2px 8px; font-size: 11px;
            }
            QComboBox::drop-down { border: none; width: 18px; }
            QComboBox QAbstractItemView {
                background: rgba(12,12,22,240); color: rgba(200,200,224,220);
                selection-background-color: rgba(99,102,241,180);
                border: 1px solid rgba(99,102,241,100);
            }
        """)
        self._populate_screen_combo()
        self._screen_combo.currentIndexChanged.connect(self._on_screen_changed)

        self._new_scr_btn = QPushButton("📷 New Screenshot")
        self._new_scr_btn.setFixedHeight(26)
        self._new_scr_btn.setStyleSheet("""
            QPushButton {
                background: rgba(99,102,241,120); color: rgba(220,220,245,255);
                border: none; border-radius: 6px; padding: 2px 10px; font-size: 11px;
            }
            QPushButton:hover   { background: rgba(99,102,241,200); }
            QPushButton:pressed { background: rgba(79,82,221,255); }
        """)
        self._new_scr_btn.clicked.connect(self._take_new_screenshot)

        screen_row.addWidget(screen_lbl)
        screen_row.addWidget(self._screen_combo, 1)
        screen_row.addWidget(self._new_scr_btn)
        layout.addLayout(screen_row)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setMaximumHeight(1)
        sep.setStyleSheet("background: rgba(99,102,241,55);")
        layout.addWidget(sep)

        # ── Content area ──────────────────────────────────────────────────────
        self._response = QTextBrowser()
        self._response.setOpenExternalLinks(False)
        self._response.setReadOnly(True)
        self._response.setMinimumHeight(120)
        self._response.setPlaceholderText("Response will appear here…")
        self._response.anchorClicked.connect(self._on_anchor_clicked)
        layout.addWidget(self._response, 1)

        # ── Input row ─────────────────────────────────────────────────────────
        self._input_row_widget = QWidget()
        input_row = QHBoxLayout(self._input_row_widget)
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(8)

        self._input = ChatInput(font_size=self._font_size)
        self._input.send_requested.connect(self._send)

        self._send_btn = QPushButton("Ask")
        self._send_btn.setFixedSize(64, 38)
        self._send_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._send_btn.setStyleSheet("""
            QPushButton {
                background: rgba(99,102,241,210); color: white;
                border: none; border-radius: 9px;
            }
            QPushButton:hover   { background: rgba(99,102,241,255); }
            QPushButton:pressed { background: rgba(79,82,221,255); }
            QPushButton:disabled {
                background: rgba(50,50,70,160); color: rgba(110,110,130,200);
            }
        """)
        self._send_btn.clicked.connect(self._send)

        input_row.addWidget(self._input)
        input_row.addWidget(self._send_btn)
        layout.addWidget(self._input_row_widget)

        # ── Bottom row: status + resize grip ──────────────────────────────────
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)

        self._status = QLabel("")
        self._status.setStyleSheet("color: rgba(130,130,158,200); font-size: 11px;")
        bottom_row.addWidget(self._status, 1)

        grip = QSizeGrip(self)
        grip.setFixedSize(16, 16)
        grip.setStyleSheet("QSizeGrip { background: transparent; }")
        bottom_row.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        layout.addLayout(bottom_row)

        # Apply initial appearance
        self._apply_appearance()

        # Centre on primary screen
        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            self.move(sg.center().x() - self.width() // 2, sg.center().y() - self.height() // 2)

    # ── Screen helpers ────────────────────────────────────────────────────────

    def _populate_screen_combo(self) -> None:
        self._screen_combo.blockSignals(True)
        self._screen_combo.clear()
        monitors = list_monitors()
        for m in monitors:
            self._screen_combo.addItem(m["label"], userData=m["index"])
        default_pos = 1 if len(monitors) > 1 else 0
        self._screen_combo.setCurrentIndex(default_pos)
        self._selected_monitor = monitors[default_pos]["index"]
        self._screen_combo.blockSignals(False)

    def _on_screen_changed(self, combo_idx: int) -> None:
        idx = self._screen_combo.itemData(combo_idx)
        if idx is not None:
            self._selected_monitor = idx

    def _take_new_screenshot(self) -> None:
        self._new_scr_btn.setEnabled(False)
        self._new_scr_btn.setText("Capturing…")
        self.hide()

        def _grab() -> None:
            time.sleep(0.15)
            scr = take_screenshot_b64(self._selected_monitor)
            self.show_overlay.emit(scr or "")

        threading.Thread(target=_grab, daemon=True).start()

    # ── Show / session lifecycle ──────────────────────────────────────────────

    def _on_show_overlay(self, screenshot_b64: str) -> None:
        # Reload appearance from config so dashboard changes are picked up live
        cfg = _load_overlay_config()
        self._bg_opacity   = float(cfg.get("bg_opacity",   0.93))
        self._text_opacity = float(cfg.get("text_opacity", 1.0))
        new_font           = int(cfg.get("font_size", 11))
        if new_font != self._font_size:
            self._font_size = new_font
        self._apply_appearance()

        self._screenshot_b64 = screenshot_b64 or None

        # Generate thumbnail for this session
        thumb = _make_thumb(screenshot_b64) if screenshot_b64 else None

        new_entry: dict = {
            "time":      datetime.now().strftime("%H:%M"),
            "pairs":     [],
            "thumb_b64": thumb,
        }
        self._history.append(new_entry)
        if len(self._history) > _MAX_HISTORY:
            self._history = self._history[-_MAX_HISTORY:]
        self._current_entry = new_entry

        self._show_history       = False
        self._history_detail_idx = None
        self._hist_btn.setChecked(False)

        self._send_btn.setEnabled(True)
        self._new_scr_btn.setEnabled(True)
        self._new_scr_btn.setText("📷 New Screenshot")
        self._input_row_widget.setVisible(True)
        self._populate_screen_combo()
        hint = "Screenshot captured." if screenshot_b64 else "No screenshot."
        self._status.setText(f"{hint}  Type your question and press Enter.")

        self._render_display()
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()
        self._input.selectAll()

    # ── History toggle ────────────────────────────────────────────────────────

    def _on_history_toggled(self, checked: bool) -> None:
        self._show_history       = checked
        self._history_detail_idx = None
        # Hide input when browsing history so it's clear we're in read-only mode
        self._input_row_widget.setVisible(not checked)
        if checked:
            self._status.setText(f"{len(self._history)} session(s) — click any session to view")
        else:
            self._status.setText("Screenshot session. Type your question and press Enter.")
        self._render_display()

    # ── Render routing ────────────────────────────────────────────────────────

    def _render_display(self) -> None:
        if self._show_history:
            if self._history_detail_idx is not None:
                self._render_session_detail(self._history_detail_idx)
            else:
                self._render_history_list()
        else:
            self._render_current_session()

    # ── Render: current session ───────────────────────────────────────────────

    def _render_current_session(self) -> None:
        self._response.clear()
        if not self._history:
            return
        self._render_session_into_browser(self._history[-1], show_thumb=True)
        self._scroll_to_bottom()

    # ── Render: history list ──────────────────────────────────────────────────

    def _render_history_list(self) -> None:
        self._response.clear()
        if not self._history:
            self._response.setPlaceholderText("No history yet — take a screenshot to start.")
            return

        # Show sessions newest-first
        for raw_idx, entry in enumerate(reversed(self._history)):
            idx = len(self._history) - 1 - raw_idx
            first_q = entry["pairs"][0]["q"] if entry["pairs"] else "(empty session)"
            q_esc   = _html_mod.escape(first_q[:80]) + ("…" if len(first_q) > 80 else "")
            n_pairs = len(entry["pairs"])
            label   = f"{n_pairs} question{'s' if n_pairs != 1 else ''}"

            # Thumbnail inline (data URI)
            thumb_html = ""
            if entry.get("thumb_b64"):
                thumb_html = (
                    f"<img src='data:image/jpeg;base64,{entry['thumb_b64']}' "
                    f"width='120' style='border-radius:5px;border:1px solid rgba(99,102,241,0.25);"
                    f"vertical-align:middle;margin-right:10px;'>"
                )

            is_current = (idx == len(self._history) - 1)
            border_col = "rgba(99,102,241,0.55)" if is_current else "rgba(99,102,241,0.2)"
            tag_html   = "<span style='color:#818cf8;font-size:10px;'> ◈ current</span>" if is_current else ""

            self._response.append(
                f"<a href='session://{idx}' style='text-decoration:none;'>"
                f"<div style='display:block;padding:8px 10px;margin:3px 0;"
                f"border:1px solid {border_col};border-radius:9px;"
                f"background:rgba(99,102,241,0.06);'>"
                f"{thumb_html}"
                f"<div style='display:inline-block;vertical-align:middle;max-width:calc(100% - 140px);'>"
                f"<div style='color:rgba(180,182,255,0.9);font-weight:600;font-size:12px;'>"
                f"Session {entry['time']}{tag_html}</div>"
                f"<div style='color:rgba(210,210,235,0.75);font-size:11px;margin-top:2px;'>{q_esc}</div>"
                f"<div style='color:rgba(140,140,170,0.7);font-size:10px;margin-top:2px;'>{label}</div>"
                f"</div></div></a>"
            )

        self._scroll_to_top()

    # ── Render: single session detail (from history) ─────────────────────────

    def _render_session_detail(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._history):
            return
        self._response.clear()

        # Back button
        self._response.append(
            "<a href='history://back' style='text-decoration:none;'>"
            "<div style='display:inline-block;padding:4px 10px;margin-bottom:8px;"
            "border:1px solid rgba(99,102,241,0.3);border-radius:6px;"
            "color:rgba(140,140,200,0.85);font-size:11px;'>"
            "← Back to history</div></a>"
        )

        self._render_session_into_browser(self._history[idx], show_thumb=True)
        self._scroll_to_top()

    # ── Core session renderer (shared by current + detail views) ─────────────

    def _render_session_into_browser(self, entry: dict, show_thumb: bool = True) -> None:
        """Append one session's full content into self._response."""
        txt_a  = int(self._text_opacity * 255)
        dim_a  = int(self._text_opacity * 160)
        acc_a  = int(self._text_opacity * 200)

        # Screenshot thumbnail
        if show_thumb and entry.get("thumb_b64"):
            self._response.append(
                f"<div style='margin-bottom:8px;'>"
                f"<img src='data:image/jpeg;base64,{entry['thumb_b64']}' "
                f"width='200' style='border-radius:7px;"
                f"border:1px solid rgba(99,102,241,0.3);display:block;'>"
                f"<div style='color:rgba(140,140,170,{dim_a});font-size:10px;"
                f"margin-top:3px;'>📷 Session {entry['time']}</div>"
                f"</div>"
            )

        # Q/A pairs
        for j, pair in enumerate(entry["pairs"]):
            if j > 0:
                self._response.append(
                    "<div style='border-top:1px solid rgba(99,102,241,0.2);"
                    "margin:8px 0 6px;'></div>"
                )

            # Question
            q_esc = _html_mod.escape(pair["q"])
            self._response.append(
                f"<div style='color:rgba(99,102,241,{acc_a});font-weight:600;"
                f"font-size:{self._font_size - 1}px;margin-bottom:2px;'>◈ Me</div>"
                f"<div style='color:rgba(220,220,245,{txt_a});margin-bottom:5px;'>{q_esc}</div>"
            )

            # Q → A divider
            self._response.append(
                "<div style='display:flex;align-items:center;gap:6px;margin:4px 0 6px;'>"
                "<div style='flex:1;border-top:1px solid rgba(99,102,241,0.28);'></div>"
                "<span style='color:rgba(99,102,241,0.45);font-size:10px;'>▸ Response</span>"
                "<div style='flex:1;border-top:1px solid rgba(99,102,241,0.28);'></div>"
                "</div>"
            )

            # Answer
            if pair["a"] is None:
                self._response.append(
                    f"<div style='color:rgba(99,102,241,{acc_a});font-style:italic;'>Thinking…</div>"
                )
            else:
                cursor = QTextCursor(self._response.document())
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.insertMarkdown(pair["a"])

    # ── Anchor / link handling ────────────────────────────────────────────────

    def _on_anchor_clicked(self, url: QUrl) -> None:
        s = url.toString()
        if s.startswith("session://"):
            try:
                idx = int(s[len("session://"):])
                self._history_detail_idx = idx
                self._render_session_detail(idx)
                self._status.setText(
                    f"Session {self._history[idx]['time']} — "
                    f"{len(self._history[idx]['pairs'])} Q/A(s)"
                )
            except (ValueError, IndexError):
                pass
        elif s == "history://back":
            self._history_detail_idx = None
            self._render_history_list()
            self._status.setText(f"{len(self._history)} session(s) — click any session to view")

    # ── Send question ─────────────────────────────────────────────────────────

    def _send(self) -> None:
        question = self._input.toPlainText().strip()
        if not question:
            return

        self._input.clear()
        self._send_btn.setEnabled(False)
        self._status.setText("Thinking…")

        if self._current_entry is None:
            entry = {"time": datetime.now().strftime("%H:%M"), "pairs": [], "thumb_b64": None}
            self._history.append(entry)
            if len(self._history) > _MAX_HISTORY:
                self._history = self._history[-_MAX_HISTORY:]
            self._current_entry = entry

        self._current_entry["pairs"].append({"q": question, "a": None})
        self._render_display()

        if self._worker_thread and self._worker_thread.isRunning():
            self._worker_thread.quit()
            self._worker_thread.wait(2000)

        self._worker_thread = QThread()
        self._worker = AskWorker(question, self._screenshot_b64, self._dashboard_url)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_response)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.error.connect(self._worker_thread.quit)
        self._worker_thread.start()

    def _on_response(self, text: str) -> None:
        if self._current_entry and self._current_entry["pairs"]:
            self._current_entry["pairs"][-1]["a"] = text
        self._render_display()
        self._status.setText("Done.")
        self._send_btn.setEnabled(True)

    def _on_error(self, err: str) -> None:
        if self._current_entry and self._current_entry["pairs"]:
            self._current_entry["pairs"][-1]["a"] = f"### ⚠ Error\n\n{err}"
        self._render_display()
        self._status.setText("Request failed.")
        self._send_btn.setEnabled(True)

    # ── Scroll helpers ────────────────────────────────────────────────────────

    def _scroll_to_bottom(self) -> None:
        self._response.verticalScrollBar().setValue(self._response.verticalScrollBar().maximum())

    def _scroll_to_top(self) -> None:
        self._response.verticalScrollBar().setValue(0)

    # ── Drag & resize (frameless window) ─────────────────────────────────────

    def _in_title_area(self, pos: QPoint) -> bool:
        return pos.y() < 52

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            local = event.position().toPoint()
            gpos  = event.globalPosition().toPoint()
            in_resize = (local.x() > self.width() - _RESIZE_GRIP and
                         local.y() > self.height() - _RESIZE_GRIP)
            if in_resize:
                self._resizing            = True
                self._resize_start_global = gpos
                self._resize_start_size   = self.size()
            elif self._in_title_area(local):
                self._drag_pos = gpos - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        gpos = event.globalPosition().toPoint()
        if self._resizing and self._resize_start_global and self._resize_start_size:
            dx = gpos.x() - self._resize_start_global.x()
            dy = gpos.y() - self._resize_start_global.y()
            self.resize(
                max(self.minimumWidth(),  self._resize_start_size.width()  + dx),
                max(self.minimumHeight(), self._resize_start_size.height() + dy),
            )
        elif self._drag_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(gpos - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos            = None
        self._resizing            = False
        self._resize_start_global = None
        self._resize_start_size   = None


# ── Hotkey listener ───────────────────────────────────────────────────────────

def start_hotkey_listener(window: OverlayWindow) -> None:
    def _run() -> None:
        try:
            import keyboard as kb
            kb.add_hotkey(
                "ctrl+shift+space",
                lambda: window.show_overlay.emit(take_screenshot_b64(window._selected_monitor) or ""),
                suppress=False,
            )
            print("[Overlay] Hotkey registered: Ctrl+Shift+Space")
            kb.wait()
        except ImportError:
            print("[Overlay] 'keyboard' not installed — hotkey disabled.")
        except Exception as e:
            print(f"[Overlay] Hotkey listener error: {e}")

    threading.Thread(target=_run, daemon=True, name="overlay-hotkey").start()


# ── Tray icon ─────────────────────────────────────────────────────────────────

def _make_tray_image():
    from PIL import Image, ImageDraw
    img  = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([1, 1, 30, 30], fill=(99, 102, 241, 255))
    try:
        draw.text((9, 6), "A", fill=(255, 255, 255, 255))
    except Exception:
        pass
    return img


def start_tray(window: OverlayWindow, qt_app: QApplication) -> None:
    def _run() -> None:
        try:
            import pystray

            def _on_ask(icon, item) -> None:
                scr = take_screenshot_b64(window._selected_monitor)
                window.show_overlay.emit(scr or "")

            menu = pystray.Menu(
                pystray.MenuItem("Ask about screen  (Ctrl+Shift+Space)", _on_ask, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Open Dashboard", lambda i, it: __import__("webbrowser").open(DASHBOARD_URL)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit Overlay", lambda i, it: (i.stop(), qt_app.quit())),
            )
            icon = pystray.Icon("aethvion-overlay", _make_tray_image(), "Aethvion Overlay", menu)
            print("[Overlay] Tray icon active.")
            icon.run()
        except ImportError as e:
            print(f"[Overlay] Tray dependency missing ({e}).")
        except Exception as e:
            print(f"[Overlay] Tray error: {e}")

    threading.Thread(target=_run, daemon=True, name="overlay-tray").start()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if not HAS_QT:
        print("[Overlay] PyQt6 is not installed.\n          Run: pip install PyQt6")
        sys.exit(1)

    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    url    = f"http://localhost:{_find_dashboard_port()}"
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Aethvion Overlay")
    qt_app.setQuitOnLastWindowClosed(False)

    window = OverlayWindow(dashboard_url=url)
    start_hotkey_listener(window)
    start_tray(window, qt_app)

    print(f"[Overlay] Started — dashboard at {url}\n"
          "[Overlay] Press Ctrl+Shift+Space or use the tray icon to activate.")
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
