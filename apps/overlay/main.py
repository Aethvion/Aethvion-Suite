"""
apps/overlay/main.py
Aethvion Suite — Desktop Overlay Sidecar

Hotkey : Ctrl+Shift+Space  (captures screen → opens floating input window)
Tray   : right-click icon for quick actions

Features:
  • Resizable frameless window
  • Screenshot shown immediately on open
  • 📷 New Screenshot — replaces image, continues same conversation thread
  • ⊕ New Thread — fresh session + new screenshot (like pressing the hotkey fresh)
  • History panel with pagination (10/page, stored to data/overlay/history/)
  • Per-month file layout matching data/history/chat/
  • Independent background vs text opacity

Dependencies (pip install ...):
    PyQt6   pystray   Pillow   mss   keyboard
"""
from __future__ import annotations

import base64
import html as _html_mod
import io
import json
import re as _re
import secrets
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

# Project root
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

OVERLAY_HISTORY_DIR = ROOT / "data" / "overlay" / "history"
_CONFIG_PATH        = ROOT / "data" / "overlay" / "config.json"
_HIST_PAGE_SIZE     = 10

# Config

def _load_overlay_config() -> dict:
    defaults = {"bg_opacity": 0.93, "text_opacity": 1.0, "font_size": 11,
                "hotkey": "ctrl+shift+space"}
    try:
        if _CONFIG_PATH.exists():
            data = json.loads(_CONFIG_PATH.read_text("utf-8"))
            if "opacity" in data and "bg_opacity" not in data:
                data["bg_opacity"] = data.pop("opacity")
            return {**defaults, **data}
    except Exception:
        pass
    return defaults

# Persistent history helpers

def _new_session_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(3)}"

def _month_dir(session_id: str) -> Path:
    return OVERLAY_HISTORY_DIR / f"{session_id[:4]}-{session_id[4:6]}"

def save_session(session: dict) -> None:
    """Persist a session to disk (call after every answer)."""
    sid = session.get("id")
    if not sid:
        return
    md = _month_dir(sid)
    (md / "sessions").mkdir(parents=True, exist_ok=True)
    (md / "thumbs").mkdir(parents=True, exist_ok=True)

    # Write session JSON (without thumb — stored as separate file)
    session_data = {k: v for k, v in session.items() if k != "thumb_b64"}
    (md / "sessions" / f"{sid}.json").write_text(
        json.dumps(session_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Write thumbnail
    if session.get("thumb_b64"):
        try:
            (md / "thumbs" / f"{sid}.jpg").write_bytes(
                base64.b64decode(session["thumb_b64"])
            )
        except Exception:
            pass

    # Update month index
    index_path = md / "index.json"
    try:
        index: list = json.loads(index_path.read_text("utf-8")) if index_path.exists() else []
    except Exception:
        index = []
    index = [e for e in index if e.get("id") != sid]
    first_q = session["pairs"][0]["q"] if session.get("pairs") else ""
    index.append({
        "id":                 sid,
        "time":               session.get("time", ""),
        "date":               session.get("date", ""),
        "first_q":            first_q[:120],
        "pairs_count":        len(session.get("pairs", [])),
        "is_pinned":          bool(session.get("is_pinned", False)),
        "promoted":           bool(session.get("promoted", False)),
        "promoted_thread_id": session.get("promoted_thread_id"),
    })
    index.sort(key=lambda e: e["id"], reverse=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def load_history_page(page: int, pinned_only: bool = False) -> tuple[list[dict], int]:
    """Return (entries, total_pages) for the given page (0-indexed)."""
    if not OVERLAY_HISTORY_DIR.exists():
        return [], 1
    all_entries: list[dict] = []
    try:
        for md in sorted(OVERLAY_HISTORY_DIR.iterdir(), reverse=True):
            if not md.is_dir():
                continue
            ip = md / "index.json"
            if ip.exists():
                try:
                    for e in json.loads(ip.read_text("utf-8")):
                        e["_month_dir"] = str(md)
                        all_entries.append(e)
                except Exception:
                    pass
    except Exception:
        pass
    all_entries.sort(key=lambda e: e.get("id", ""), reverse=True)
    if pinned_only:
        all_entries = [e for e in all_entries if e.get("is_pinned")]
    total = len(all_entries)
    total_pages = max(1, (total + _HIST_PAGE_SIZE - 1) // _HIST_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * _HIST_PAGE_SIZE
    return all_entries[start:start + _HIST_PAGE_SIZE], total_pages


def load_session_full(session_id: str) -> Optional[dict]:
    """Load a full session dict from disk, injecting thumb_b64 if available."""
    md = _month_dir(session_id)
    sp = md / "sessions" / f"{session_id}.json"
    if not sp.exists():
        return None
    try:
        data = json.loads(sp.read_text("utf-8"))
        tp = md / "thumbs" / f"{session_id}.jpg"
        if tp.exists():
            data["thumb_b64"] = base64.b64encode(tp.read_bytes()).decode("utf-8")
        return data
    except Exception:
        return None

# Dashboard port discovery

def _find_dashboard_port() -> int:
    try:
        pf = ROOT / "data" / "system" / "ports.json"
        if pf.exists():
            data = json.loads(pf.read_text(encoding="utf-8"))
            for port, name in data.items():
                if "dashboard" in str(name).lower() or "nexus" in str(name).lower():
                    return int(port)
    except Exception:
        pass
    return 8080

DASHBOARD_URL = f"http://localhost:{_find_dashboard_port()}"

# Qt
try:
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout,
        QTextEdit, QPushButton, QLabel, QFrame, QComboBox,
        QTextBrowser, QSizeGrip,
    )
    from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, pyqtSlot, QObject, QPoint, QSize, QUrl
    from PyQt6.QtGui import QFont
    HAS_QT = True
except ImportError:
    HAS_QT = False

# Screenshot / thumbnail

def list_monitors() -> list[dict]:
    try:
        import mss
        with mss.mss() as sct:
            return [
                {"index": i, "label": "All Screens Combined" if i == 0
                 else f"Screen {i}  ({m['width']}×{m['height']})",
                 "width": m["width"], "height": m["height"]}
                for i, m in enumerate(sct.monitors)
            ]
    except Exception:
        return [{"index": 1, "label": "Primary Screen", "width": 0, "height": 0}]


def take_screenshot_b64(monitor_index: int = 1) -> Optional[str]:
    try:
        import mss
        with mss.mss() as sct:
            monitors = sct.monitors
            idx = max(0, min(monitor_index, len(monitors) - 1))
            sct_img = sct.grab(monitors[idx])
        from PIL import Image
        img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except ImportError as e:
        print(f"[Overlay] Screenshot dep missing ({e}).")
        return None
    except Exception as e:
        print(f"[Overlay] Screenshot failed: {e}")
        return None


def make_thumb(screenshot_b64: str, max_width: int = 200) -> Optional[str]:
    """Downscale screenshot to a small JPEG thumbnail. Fast (<30ms for 200px)."""
    try:
        from PIL import Image
        raw = base64.b64decode(screenshot_b64)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        img = img.resize((max_width, int(h * max_width / w)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=55, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return None

# API worker

class AskWorker(QObject):
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, question: str, screenshot_b64: Optional[str],
                 dashboard_url: str, history: Optional[list] = None):
        super().__init__()
        self.question       = question
        self.screenshot_b64 = screenshot_b64
        self.dashboard_url  = dashboard_url
        self.history        = history or []

    def run(self) -> None:
        import urllib.request, urllib.error
        payload = json.dumps({
            "question":       self.question,
            "screenshot_b64": self.screenshot_b64,
            "history":        [{"q": p["q"], "a": p["a"]} for p in self.history
                                if p.get("q") and p.get("a")],
        }).encode()
        req = urllib.request.Request(
            f"{self.dashboard_url}/api/overlay/ask",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                self.finished.emit(json.loads(resp.read().decode()).get("answer", "(no response)"))
        except urllib.error.HTTPError as e:
            try:    detail = json.loads(e.read().decode()).get("detail", str(e))
            except Exception: detail = str(e)
            self.error.emit(f"Server error {e.code}: {detail}")
        except urllib.error.URLError as e:
            self.error.emit(f"Could not reach dashboard: {e.reason}")
        except Exception as e:
            self.error.emit(str(e))

# Chat input

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
                background: rgba(18,18,32,210); color: rgba(220,220,245,255);
                border: 1px solid rgba(99,102,241,100); border-radius: 9px; padding: 3px 6px;
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

# Main overlay window

_RESIZE_GRIP   = 18
_CAPTURE_NEW   = "new_thread"   # _capture_mode values
_CAPTURE_SAME  = "same_thread"


class OverlayWindow(QWidget):
    show_overlay      = pyqtSignal(str)   # screenshot b64 → new session
    _request_capture  = pyqtSignal()      # hide first, then capture
    _replace_shot     = pyqtSignal(str)   # screenshot b64 → same session

    def __init__(self, dashboard_url: str):
        super().__init__()
        self._dashboard_url           = dashboard_url
        self._screenshot_b64: Optional[str]  = None
        self._pending_thumb:  Optional[str]  = None
        self._drag_pos: Optional[QPoint]     = None
        self._resizing                        = False
        self._resize_start_global: Optional[QPoint] = None
        self._resize_start_size:   Optional[QSize]  = None
        self._worker_thread: Optional[QThread]      = None
        self._worker:        Optional[AskWorker]    = None
        self._selected_monitor: int = 1
        self._capture_mode: str = _CAPTURE_NEW

        # Current active session (in memory + saved to disk incrementally)
        self._current_entry: Optional[dict] = None

        # History panel state
        self._show_history        = False
        self._hist_pinned_only    = False
        self._hist_page           = 0
        self._hist_total_pages    = 1
        self._hist_detail_session: Optional[dict] = None  # full session loaded from disk

        # Appearance
        cfg = _load_overlay_config()
        self._bg_opacity   = float(cfg.get("bg_opacity",   0.93))
        self._text_opacity = float(cfg.get("text_opacity", 1.0))
        self._font_size    = int(cfg.get("font_size",      11))

        self._build_ui()
        self.show_overlay.connect(self._on_show_overlay)
        self._request_capture.connect(self._on_request_capture)
        self._replace_shot.connect(self._on_replace_shot)

    # Appearance

    def _apply_appearance(self) -> None:
        bg_a   = int(self._bg_opacity * 255)
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
                border-radius: 9px; padding: 6px;
            }}
            QScrollBar:vertical {{
                background: rgba(20,20,35,180); width: 6px; border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(99,102,241,150); border-radius: 3px;
            }}
        """)
        self._response.document().setDefaultStyleSheet(f"""
            body {{ color: rgba(210,210,235,{txt_a}); }}
            h1,h2,h3,h4 {{ color: #818cf8; margin-top:6px; margin-bottom:2px; font-weight:bold; }}
            code {{
                background-color: rgba(99,102,241,40); color: rgba(226,232,240,{txt_a});
                font-family: 'Consolas','Cascadia Code','Courier New',monospace;
                padding: 2px 4px; border-radius: 4px;
            }}
            pre {{
                background-color: rgba(0,0,0,100); border: 1px solid rgba(99,102,241,60);
                padding: 12px; border-radius: 8px; margin: 8px 0;
                font-family: 'Consolas','Cascadia Code','Courier New',monospace;
            }}
            a {{ color: #818cf8; text-decoration: none; }}
            li {{ margin-bottom: 4px; }}
            blockquote {{
                border-left: 3px solid rgba(99,102,241,150);
                padding-left: 10px; font-style: italic;
                color: rgba(210,210,235,{int(self._text_opacity * 180)});
            }}
        """)
        self._response.setFont(QFont("Segoe UI", self._font_size))
        self._input.setFont(QFont("Segoe UI", self._font_size))

    def _ta(self, base: float = 1.0) -> int:
        """Text alpha scaled by text_opacity."""
        return int(base * self._text_opacity * 255)

    # UI construction

    def _build_ui(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(420, 300)
        self.resize(560, 460)

        self.setStyleSheet("background: transparent; border: none;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)

        self._container = QFrame(self)
        self._container.setObjectName("aovContainer")
        outer.addWidget(self._container)

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        # Title bar
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        dot   = QLabel("◈")
        dot.setStyleSheet("color:rgba(99,102,241,255);font-size:15px;")
        title = QLabel("Ask about screen")
        title.setStyleSheet("color:rgba(200,200,224,220);font-size:13px;font-weight:600;")
        self._hotkey_lbl = QLabel("Ctrl+Shift+Space")
        self._hotkey_lbl.setStyleSheet("color:rgba(120,120,150,180);font-size:11px;")

        _icon_btn_css = """
            QPushButton { background:transparent; color:rgba(160,160,200,200);
                border:none; border-radius:13px; font-size:13px; }
            QPushButton:hover   { background:rgba(99,102,241,120); }
            QPushButton:checked { background:rgba(99,102,241,180); color:white; }
        """
        self._hist_btn = QPushButton("🕐")
        self._hist_btn.setFixedSize(26, 26)
        self._hist_btn.setCheckable(True)
        self._hist_btn.setToolTip("Browse history")
        self._hist_btn.setStyleSheet(_icon_btn_css)
        self._hist_btn.toggled.connect(self._on_history_toggled)

        self._pinned_btn = QPushButton("📌")
        self._pinned_btn.setFixedSize(26, 26)
        self._pinned_btn.setCheckable(True)
        self._pinned_btn.setToolTip("Pinned sessions")
        self._pinned_btn.setStyleSheet(_icon_btn_css)
        self._pinned_btn.toggled.connect(self._on_pinned_toggled)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setStyleSheet("""
            QPushButton { background:transparent; color:rgba(160,160,180,200);
                border:none; border-radius:13px; font-size:12px; }
            QPushButton:hover { background:rgba(220,55,55,180); color:white; }
        """)
        close_btn.clicked.connect(self.hide)

        title_row.addWidget(dot)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(self._hotkey_lbl)
        title_row.addWidget(self._pinned_btn)
        title_row.addWidget(self._hist_btn)
        title_row.addWidget(close_btn)
        layout.addLayout(title_row)

        # Action row (screen selector + two screenshot buttons)
        action_row = QHBoxLayout()
        action_row.setSpacing(6)

        screen_lbl = QLabel("Screen:")
        screen_lbl.setStyleSheet("color:rgba(140,140,170,200);font-size:11px;")

        self._screen_combo = QComboBox()
        self._screen_combo.setFixedHeight(26)
        self._screen_combo.setStyleSheet("""
            QComboBox { background:rgba(18,18,32,210); color:rgba(200,200,224,220);
                border:1px solid rgba(99,102,241,80); border-radius:6px;
                padding:2px 8px; font-size:11px; }
            QComboBox::drop-down { border:none; width:18px; }
            QComboBox QAbstractItemView { background:rgba(12,12,22,240); color:rgba(200,200,224,220);
                selection-background-color:rgba(99,102,241,180);
                border:1px solid rgba(99,102,241,100); }
        """)
        self._populate_screen_combo()
        self._screen_combo.currentIndexChanged.connect(self._on_screen_changed)

        _btn_css = """
            QPushButton { background:rgba(99,102,241,120); color:rgba(220,220,245,255);
                border:none; border-radius:6px; padding:2px 8px; font-size:11px; }
            QPushButton:hover   { background:rgba(99,102,241,200); }
            QPushButton:pressed { background:rgba(79,82,221,255); }
            QPushButton:disabled { background:rgba(40,40,60,140); color:rgba(100,100,120,180); }
        """

        # 📷 New Screenshot — same thread (replaces image, keeps conversation)
        self._new_scr_btn = QPushButton("📷 New Screenshot")
        self._new_scr_btn.setFixedHeight(26)
        self._new_scr_btn.setToolTip("Capture a new screenshot and continue this conversation")
        self._new_scr_btn.setStyleSheet(_btn_css)
        self._new_scr_btn.clicked.connect(self._take_new_screenshot_same_thread)

        # ⊕ New Thread — fresh session
        self._new_thread_btn = QPushButton("⊕ New Thread")
        self._new_thread_btn.setFixedHeight(26)
        self._new_thread_btn.setToolTip("Start a fresh conversation with a new screenshot")
        self._new_thread_btn.setStyleSheet(_btn_css)
        self._new_thread_btn.clicked.connect(self._take_new_thread)

        action_row.addWidget(screen_lbl)
        action_row.addWidget(self._screen_combo, 1)
        action_row.addWidget(self._new_scr_btn)
        action_row.addWidget(self._new_thread_btn)
        layout.addLayout(action_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setMaximumHeight(1)
        sep.setStyleSheet("background:rgba(99,102,241,55);")
        layout.addWidget(sep)

        # Response area
        self._response = QTextBrowser()
        self._response.setOpenExternalLinks(False)
        self._response.setReadOnly(True)
        self._response.setMinimumHeight(120)
        self._response.setPlaceholderText("Screenshot will appear here…")
        self._response.anchorClicked.connect(self._on_anchor_clicked)
        layout.addWidget(self._response, 1)

        # Input row
        self._input_row_widget = QWidget()
        ir = QHBoxLayout(self._input_row_widget)
        ir.setContentsMargins(0, 0, 0, 0)
        ir.setSpacing(8)

        self._input = ChatInput(font_size=self._font_size)
        self._input.send_requested.connect(self._send)

        self._send_btn = QPushButton("Ask")
        self._send_btn.setFixedSize(64, 38)
        self._send_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._send_btn.setStyleSheet("""
            QPushButton { background:rgba(99,102,241,210); color:white; border:none; border-radius:9px; }
            QPushButton:hover   { background:rgba(99,102,241,255); }
            QPushButton:pressed { background:rgba(79,82,221,255); }
            QPushButton:disabled { background:rgba(50,50,70,160); color:rgba(110,110,130,200); }
        """)
        self._send_btn.clicked.connect(self._send)

        ir.addWidget(self._input)
        ir.addWidget(self._send_btn)
        layout.addWidget(self._input_row_widget)

        # Bottom: status + resize grip
        bot = QHBoxLayout()
        bot.setContentsMargins(0, 0, 0, 0)
        self._status = QLabel("")
        self._status.setStyleSheet("color:rgba(130,130,158,200);font-size:11px;")
        bot.addWidget(self._status, 1)
        grip = QSizeGrip(self)
        grip.setFixedSize(16, 16)
        grip.setStyleSheet("QSizeGrip { background:transparent; }")
        bot.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        layout.addLayout(bot)

        self._apply_appearance()

        scr = QApplication.primaryScreen()
        if scr:
            sg = scr.availableGeometry()
            self.move(sg.center().x() - self.width() // 2, sg.center().y() - self.height() // 2)

    # Screen helpers

    def _populate_screen_combo(self) -> None:
        self._screen_combo.blockSignals(True)
        self._screen_combo.clear()
        monitors = list_monitors()
        for m in monitors:
            self._screen_combo.addItem(m["label"], userData=m["index"])
        dp = 1 if len(monitors) > 1 else 0
        self._screen_combo.setCurrentIndex(dp)
        self._selected_monitor = monitors[dp]["index"]
        self._screen_combo.blockSignals(False)

    def _on_screen_changed(self, ci: int) -> None:
        idx = self._screen_combo.itemData(ci)
        if idx is not None:
            self._selected_monitor = idx

    # Capture flow

    def _take_new_screenshot_same_thread(self) -> None:
        """Capture new screenshot, stay in current session."""
        self._capture_mode = _CAPTURE_SAME
        self._new_scr_btn.setEnabled(False)
        self._new_scr_btn.setText("Capturing…")
        self._request_capture.emit()

    def _take_new_thread(self) -> None:
        """Capture new screenshot and start a fresh session."""
        self._capture_mode = _CAPTURE_NEW
        self._new_thread_btn.setEnabled(False)
        self._new_thread_btn.setText("Capturing…")
        self._request_capture.emit()

    def _on_request_capture(self) -> None:
        """Main-thread: hide window, then capture after OS clears the frame."""
        self.hide()
        QTimer.singleShot(220, self._do_capture)

    def _do_capture(self) -> None:
        mode = self._capture_mode
        def _grab():
            scr = take_screenshot_b64(self._selected_monitor)
            if mode == _CAPTURE_SAME:
                self._replace_shot.emit(scr or "")
            else:
                self.show_overlay.emit(scr or "")
        threading.Thread(target=_grab, daemon=True).start()

    def _reset_capture_buttons(self) -> None:
        self._new_scr_btn.setEnabled(True)
        self._new_scr_btn.setText("📷 New Screenshot")
        self._new_thread_btn.setEnabled(True)
        self._new_thread_btn.setText("⊕ New Thread")

    # Session lifecycle

    def _on_show_overlay(self, screenshot_b64: str) -> None:
        """New thread: reload config, store screenshot, show immediately."""
        cfg = _load_overlay_config()
        self._bg_opacity   = float(cfg.get("bg_opacity",   0.93))
        self._text_opacity = float(cfg.get("text_opacity", 1.0))
        if (nf := int(cfg.get("font_size", 11))) != self._font_size:
            self._font_size = nf
        self._apply_appearance()

        self._screenshot_b64 = screenshot_b64 or None
        # Generate thumbnail synchronously — fast (<30ms for 200px output)
        self._pending_thumb  = make_thumb(screenshot_b64) if screenshot_b64 else None
        self._current_entry  = None   # created on first send

        self._show_history       = False
        self._hist_detail_session = None
        self._hist_btn.setChecked(False)
        self._reset_capture_buttons()
        self._input_row_widget.setVisible(True)
        self._populate_screen_combo()
        hint = "Screenshot captured." if screenshot_b64 else "No screenshot."
        self._status.setText(f"{hint}  Type your question and press Enter.")

        self._show_screenshot_preview()
        self.show(); self.raise_(); self.activateWindow()
        self._input.setFocus(); self._input.selectAll()

    def _on_replace_shot(self, screenshot_b64: str) -> None:
        """Same thread: add screenshot to history instead of clearing it."""
        self._screenshot_b64 = screenshot_b64 or None
        self._pending_thumb  = make_thumb(screenshot_b64) if screenshot_b64 else None

        if self._current_entry:
            # Update root thumb so history list shows the latest shot
            self._current_entry["thumb_b64"] = self._pending_thumb
            
            # Append a screenshot marker to the chat flow
            now = datetime.now()
            self._current_entry["pairs"].append({
                "type": "screenshot",
                "thumb_b64": self._pending_thumb,
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M")
            })

        self._reset_capture_buttons()
        self._status.setText("Captured. New context added to conversation.")
        self.show(); self.raise_(); self.activateWindow()
        self._input.setFocus()

        if self._current_entry:
            self._render_session(self._current_entry)
        else:
            self._show_screenshot_preview()

    # Screenshot preview (before first question)

    def _show_screenshot_preview(self) -> None:
        """Display the current screenshot as a preview in the response area."""
        self._response.clear()
        if not self._pending_thumb:
            return
        ta = self._ta(0.6)
        self._response.append(
            f"<div style='margin-bottom:6px;'>"
            f"<img src='data:image/jpeg;base64,{self._pending_thumb}' "
            f"width='200' style='border-radius:7px;border:1px solid rgba(99,102,241,0.28);display:block;'>"
            f"<div style='color:rgba(140,140,170,{ta});font-size:10px;margin-top:3px;'>"
            f"📷 Ready — ask anything about this screen</div>"
            f"</div>"
        )

    # History toggle

    def _on_history_toggled(self, checked: bool) -> None:
        self._show_history = checked
        if checked:
            self._hist_detail_session = None
            self._hist_pinned_only    = False
            self._pinned_btn.blockSignals(True)
            self._pinned_btn.setChecked(False)
            self._pinned_btn.blockSignals(False)
            self._input_row_widget.setVisible(False)
            self._hist_page = 0
            self._load_and_render_history_list()
        else:
            self._pinned_btn.blockSignals(True)
            self._pinned_btn.setChecked(False)
            self._pinned_btn.blockSignals(False)
            self._input_row_widget.setVisible(True)
            if self._current_entry:
                self._render_session(self._current_entry)
            else:
                self._show_screenshot_preview()
            self._status.setText("Type your question and press Enter.")

    def _on_pinned_toggled(self, checked: bool) -> None:
        self._hist_pinned_only = checked
        if checked:
            self._hist_detail_session = None
            self._show_history = True
            self._hist_btn.blockSignals(True)
            self._hist_btn.setChecked(False)
            self._hist_btn.blockSignals(False)
            self._input_row_widget.setVisible(False)
            self._hist_page = 0
            self._load_and_render_history_list()
        else:
            self._hist_btn.blockSignals(True)
            self._hist_btn.setChecked(True)
            self._hist_btn.blockSignals(False)
            self._hist_pinned_only = False
            self._load_and_render_history_list()

    # History list (paginated disk read)

    @pyqtSlot()
    def _load_and_render_history_list(self) -> None:
        entries, total_pages = load_history_page(self._hist_page, pinned_only=self._hist_pinned_only)
        self._hist_total_pages = total_pages
        self._render_history_list(entries)

    def _render_history_list(self, entries: list[dict]) -> None:
        self._response.clear()
        if not entries:
            self._response.append(
                "<div style='color:rgba(160,160,190,160);font-size:12px;text-align:center;"
                "margin-top:20px;'>No history yet — send a question to start recording.</div>"
            )
            self._status.setText("No history.")
            return

        current_sid = self._current_entry.get("id") if self._current_entry else None

        for e in entries:
            sid       = e.get("id", "")
            q_esc     = _html_mod.escape((e.get("first_q") or "")[:75])
            if len(e.get("first_q", "")) > 75:
                q_esc += "…"
            n         = e.get("pairs_count", 0)
            label     = f"{n} exchange{'s' if n != 1 else ''}"
            is_cur    = sid == current_sid
            is_pinned = bool(e.get("is_pinned"))

            if is_cur:
                border = "rgba(99,102,241,0.7)"
                bg     = "rgba(99,102,241,0.1)"
            elif is_pinned:
                border = "rgba(13,148,136,0.55)"
                bg     = "rgba(13,148,136,0.08)"
            else:
                border = "rgba(99,102,241,0.18)"
                bg     = "rgba(20,20,35,0.5)"

            cur_tag  = (" &nbsp;<span style='color:rgba(148,150,255,0.8);font-size:10px;"
                        "font-weight:600;'>◈ active</span>") if is_cur else ""
            pin_ind  = (" &nbsp;<span style='color:#2dd4bf;font-size:10px;'>📌</span>") if is_pinned else ""
            pin_color = "#2dd4bf" if is_pinned else "rgba(160,160,190,0.45)"
            pin_icon  = "📌" if is_pinned else "📍"
            pin_link  = (
                f"<a href='pin://{sid}' style='text-decoration:none;'>"
                f"<span style='font-size:12px;color:{pin_color};padding:0 3px;'>"
                f"{pin_icon}</span></a>"
            )

            # Thumbnail from disk
            md = Path(e.get("_month_dir", "")) if e.get("_month_dir") else None
            thumb_html = ""
            if md and sid:
                tp = md / "thumbs" / f"{sid}.jpg"
                if tp.exists():
                    try:
                        b64 = base64.b64encode(tp.read_bytes()).decode()
                        thumb_html = (
                            f"<img src='data:image/jpeg;base64,{b64}' width='96' "
                            f"style='border-radius:5px;border:1px solid rgba(99,102,241,0.2);"
                            f"vertical-align:top;margin-right:9px;flex-shrink:0;'>"
                        )
                    except Exception:
                        pass

            date_str = e.get("date", "")
            time_str = e.get("time", "")
            ts_label = f"{date_str} {time_str}".strip() if date_str else time_str

            self._response.append(
                f"<a href='session://{sid}' style='text-decoration:none;display:block;"
                f"margin:4px 0;'>"
                f"<div style='padding:9px 10px;border:1px solid {border};"
                f"border-radius:10px;background:{bg};'>"
                f"<table width='100%' border='0' cellspacing='0' cellpadding='0'><tr>"
                f"<td style='vertical-align:top;width:106px;'>{thumb_html}</td>"
                f"<td style='vertical-align:top;'>"
                f"<table width='100%' border='0' cellspacing='0' cellpadding='0'"
                f" style='margin-bottom:3px;'><tr>"
                f"<td><span style='color:rgba(180,182,255,0.85);font-weight:600;font-size:11px;'>"
                f"{ts_label}{cur_tag}{pin_ind}</span></td>"
                f"<td align='right'>{pin_link}</td>"
                f"</tr></table>"
                f"<div style='color:rgba(210,215,240,0.78);font-size:11px;line-height:1.4;"
                f"margin-bottom:3px;'>{q_esc}</div>"
                f"<div style='color:rgba(140,140,170,0.55);font-size:10px;'>{label}</div>"
                f"</td></tr></table>"
                f"</div></a>"
            )

        # Pagination controls
        page_info = f"Page {self._hist_page + 1} / {self._hist_total_pages}"
        prev_link = (f"<a href='histpage://{self._hist_page - 1}' style='text-decoration:none;"
                     f"color:#818cf8;'>◀ Prev</a>") if self._hist_page > 0 else ""
        next_link = (f"<a href='histpage://{self._hist_page + 1}' style='text-decoration:none;"
                     f"color:#818cf8;'>Next ▶</a>") if self._hist_page < self._hist_total_pages - 1 else ""

        self._response.append(
            f"<div style='text-align:center;margin-top:8px;font-size:11px;"
            f"color:rgba(140,140,170,0.8);'>"
            f"{prev_link}{'&nbsp;&nbsp;' if prev_link else ''}"
            f"{page_info}"
            f"{'&nbsp;&nbsp;' if next_link else ''}{next_link}</div>"
        )
        count = len(entries)
        self._status.setText(f"History — {page_info}, {count} session(s) on this page")
        self._response.verticalScrollBar().setValue(0)

    # Markdown → inline HTML helper (avoids split append/insertMarkdown calls)

    def _md_html(self, text: str) -> str:
        """Convert markdown text to an embeddable HTML fragment for QTextBrowser.

        Uses Qt's own markdown parser (QTextDocument.setMarkdown) then extracts
        the body HTML so we can embed it inside table cells without the
        append() / insertMarkdown() split that leaks raw closing tags.
        """
        from PyQt6.QtGui import QTextDocument  # local import — Qt must be up
        doc = QTextDocument()
        try:
            doc.setMarkdown(text)
        except Exception:
            return _html_mod.escape(text).replace("\n", "<br>")
        full = doc.toHtml()
        m = _re.search(r"<body[^>]*>(.*?)</body>", full, _re.DOTALL)
        if not m:
            return _html_mod.escape(text).replace("\n", "<br>")
        body = m.group(1).strip()
        # Qt adds default inline colours/fonts — strip them so our dark-theme
        # container colour shows through instead.
        body = _re.sub(r'\s*style="[^"]*"', "", body)
        # Remove empty leading/trailing <p></p>
        body = _re.sub(r"^(<p>\s*</p>\s*)+", "", body)
        body = _re.sub(r"(<p>\s*</p>\s*)+$", "", body)
        return body

    # Session renderer

    def _render_session(self, session: dict) -> None:
        """Render a full session with left (AI) / right (user) bubble layout.

        Every Q/A pair is emitted as one self-contained HTML string so that
        QTextBrowser never sees dangling closing tags from a prior append().
        """
        self._response.clear()
        dim_a = 0.55

        pairs = session.get("pairs", [])
        show_root_thumb = not (pairs and pairs[0].get("type") == "screenshot")

        # Screenshot at top
        thumb = session.get("thumb_b64") or self._pending_thumb
        if thumb and show_root_thumb:
            date_str = f"{session.get('date','')} {session.get('time','')}".strip()
            self._response.append(
                f"<div style='margin-bottom:10px;'>"
                f"<img src='data:image/jpeg;base64,{thumb}' width='190' "
                f"style='border-radius:8px;border:1px solid rgba(99,102,241,0.3);display:block;'>"
                f"<div style='color:rgba(140,140,170,{dim_a});font-size:10px;margin-top:3px;'>"
                f"📷 {date_str}</div>"
                f"</div>"
            )

        fs = self._font_size

        for item in pairs:
            # ── Inline screenshot separator ──────────────────────────────────
            if item.get("type") == "screenshot":
                it_thumb = item.get("thumb_b64")
                ts = item.get("time", "")
                sep_html = (
                    f"<p style='text-align:center;color:rgba(120,120,150,{dim_a});"
                    f"font-size:9px;margin:8px 0 4px;'>"
                    f"── 📷 new screenshot {ts} ──</p>"
                )
                if it_thumb:
                    sep_html += (
                        f"<img src='data:image/jpeg;base64,{it_thumb}' width='170' "
                        f"style='border-radius:6px;border:1px solid rgba(99,102,241,0.22);"
                        f"display:block;margin-bottom:6px;'>"
                    )
                self._response.append(sep_html)
                continue

            # ── User bubble (right-shifted via empty left column) ────────────
            q_esc = _html_mod.escape(item.get("q", ""))
            user_html = (
                f"<table width='100%' border='0' cellspacing='0' cellpadding='0'"
                f" style='margin:6px 0 2px;'><tr>"
                f"<td width='20%'></td>"
                f"<td style='background-color:rgba(42,38,95,1);border:1px solid rgba(99,102,241,0.5);"
                f"border-radius:12px;padding:8px 11px;'>"
                f"<p style='color:rgba(148,150,255,1);font-size:9px;font-weight:600;"
                f"letter-spacing:1px;margin:0 0 4px 0;'>YOU</p>"
                f"<p style='color:rgba(228,228,250,1);font-size:{fs}px;"
                f"line-height:1.5;margin:0;'>{q_esc}</p>"
                f"</td></tr></table>"
            )
            self._response.append(user_html)

            # ── AI bubble (left, with left-border accent) ────────────────────
            if item.get("a") is None:
                a_html = (f"<p style='color:rgba(99,102,241,0.7);font-style:italic;"
                          f"font-size:{fs}px;margin:0;'>Thinking…</p>")
            else:
                a_html = self._md_html(item["a"])

            ai_html = (
                f"<table width='100%' border='0' cellspacing='0' cellpadding='0'"
                f" style='margin:2px 0 10px;'><tr>"
                f"<td width='80%' style='border-left:2px solid rgba(99,102,241,0.35);"
                f"padding:6px 10px;'>"
                f"<p style='color:rgba(148,150,255,0.55);font-size:9px;font-weight:600;"
                f"letter-spacing:1px;margin:0 0 5px 0;'>◈ AETHVION</p>"
                f"{a_html}"
                f"</td><td width='20%'></td></tr></table>"
            )
            self._response.append(ai_html)

        self._response.verticalScrollBar().setValue(
            self._response.verticalScrollBar().maximum()
        )

    # Anchor / link handling

    def _on_anchor_clicked(self, url: QUrl) -> None:
        s = url.toString()

        if s.startswith("session://"):
            sid = s[len("session://"):]
            # Check in-memory current entry first
            if self._current_entry and self._current_entry.get("id") == sid:
                full = self._current_entry
            else:
                full = load_session_full(sid)
            if full:
                self._current_entry = full
                self._hist_detail_session = full
                self._input_row_widget.setVisible(True)
                self._response.clear()
                # Back button
                self._response.append(
                    "<a href='history://back' style='text-decoration:none;'>"
                    "<div style='display:inline-block;padding:4px 10px;margin-bottom:8px;"
                    "border:1px solid rgba(99,102,241,0.3);border-radius:6px;"
                    "color:rgba(140,140,200,0.85);font-size:11px;'>← Back to history</div></a>"
                )
                self._render_session(full)
                self._status.setText(
                    f"Continuing session from {full.get('date','')} — "
                    f"{len(full.get('pairs',[]))} Q/A(s)"
                )
                # If promoted, fetch any new Chat messages in the background
                if full.get("promoted") and full.get("promoted_thread_id"):
                    threading.Thread(
                        target=self._fetch_promoted_tasks,
                        args=(full["promoted_thread_id"],),
                        daemon=True,
                    ).start()
            else:
                self._status.setText(f"Could not load session {sid}")

        elif s.startswith("pin://"):
            sid = s[len("pin://"):]
            threading.Thread(target=self._toggle_pin, args=(sid,), daemon=True).start()

        elif s.startswith("histpage://"):
            try:
                page = int(s[len("histpage://"):])
                self._hist_page = max(0, min(page, self._hist_total_pages - 1))
                self._load_and_render_history_list()
            except ValueError:
                pass

        elif s == "history://back":
            self._hist_detail_session = None
            self._input_row_widget.setVisible(False)
            self._load_and_render_history_list()

    def _fetch_promoted_tasks(self, thread_id: str) -> None:
        """Background: fetch post-promotion Chat tasks, pre-fetch image bytes, queue UI update."""
        try:
            import requests as _req
            import urllib.parse as _ul
            res = _req.get(f"{DASHBOARD_URL}/api/tasks/thread/{thread_id}", timeout=6)
            if not res.ok:
                return
            tasks = res.json().get("tasks", [])
            new_tasks = [
                t for t in tasks
                if t.get("metadata", {}).get("source") != "overlay"
                and t.get("status") == "completed"
                and t.get("result", {}).get("response")
            ]
            if not new_tasks:
                return
            new_tasks.sort(key=lambda t: t.get("created_at", ""))

            # Pre-fetch attached images as base64 so QTextBrowser can render them
            for task in new_tasks:
                for att in (task.get("metadata") or {}).get("attached_files", []):
                    if not att.get("is_image"):
                        continue
                    url = att.get("url", "")
                    if not url and att.get("path"):
                        url = "/api/workspace/files/serve?path=" + _ul.quote(att["path"])
                    if not url:
                        continue
                    full_url = (DASHBOARD_URL + url) if url.startswith("/") else url
                    try:
                        img_res = _req.get(full_url, timeout=5)
                        if img_res.ok:
                            mime = img_res.headers.get("content-type", "image/png")
                            att["_data_uri"] = (
                                f"data:{mime};base64,"
                                + base64.b64encode(img_res.content).decode("utf-8")
                            )
                    except Exception:
                        pass

            self._pending_chat_tasks = new_tasks
        except Exception as e:
            print(f"[Overlay] Could not fetch promoted tasks: {e}")
            return
        from PyQt6.QtCore import QMetaObject, Qt as _Qt
        QMetaObject.invokeMethod(
            self, "_append_promoted_tasks",
            _Qt.ConnectionType.QueuedConnection,
        )

    @pyqtSlot()
    def _append_promoted_tasks(self) -> None:
        """Main-thread: render post-promotion Chat messages after the overlay pairs."""
        tasks = getattr(self, "_pending_chat_tasks", [])
        if not tasks:
            return
        self._pending_chat_tasks = []

        self._response.append(
            "<div style='border-top:1px solid rgba(13,148,136,0.4);margin:14px 0 8px;"
            "text-align:center;'>"
            "<span style='color:rgba(13,148,136,0.7);font-size:10px;letter-spacing:0.05em;'>"
            "── continued in Chat ──</span></div>"
        )

        fs = self._font_size
        for task in tasks:
            q_esc    = _html_mod.escape(task.get("prompt", ""))
            a        = (task.get("result") or {}).get("response", "")
            attached = (task.get("metadata") or {}).get("attached_files", [])

            # Build any attached-image HTML — each image in its own <p> so
            # QTextBrowser renders it as a proper block below the prompt text.
            img_html = ""
            for att in attached:
                if not att.get("is_image"):
                    continue
                src = att.get("_data_uri", "")
                if src:
                    img_html += (
                        f"<p style='margin:6px 0 0;'>"
                        f"<img src='{src}' width='180' "
                        f"style='border-radius:6px;border:1px solid rgba(13,148,136,0.3);'>"
                        f"</p>"
                    )

            # User bubble — teal tint (from Chat) — complete in one string
            self._response.append(
                f"<table width='100%' border='0' cellspacing='0' cellpadding='0'"
                f" style='margin:6px 0 2px;'><tr>"
                f"<td width='20%'></td>"
                f"<td style='background-color:rgba(8,46,46,1);border:1px solid rgba(13,148,136,0.45);"
                f"border-radius:12px;padding:8px 11px;'>"
                f"<p style='color:rgba(45,212,191,0.65);font-size:9px;font-weight:600;"
                f"letter-spacing:1px;margin:0 0 4px 0;'>YOU · CHAT</p>"
                f"<p style='color:rgba(220,248,248,1);font-size:{fs}px;"
                f"line-height:1.5;margin:0;'>{q_esc}</p>"
                f"{img_html}"
                f"</td></tr></table>"
            )

            # AI bubble — teal left border (Chat response) — complete in one string
            a_html = self._md_html(a) if a else (
                f"<p style='color:rgba(45,212,191,0.5);font-style:italic;margin:0;'>"
                f"No response recorded.</p>"
            )
            self._response.append(
                f"<table width='100%' border='0' cellspacing='0' cellpadding='0'"
                f" style='margin:2px 0 10px;'><tr>"
                f"<td width='80%' style='border-left:2px solid rgba(13,148,136,0.35);"
                f"padding:6px 10px;'>"
                f"<p style='color:rgba(45,212,191,0.45);font-size:9px;font-weight:600;"
                f"letter-spacing:1px;margin:0 0 5px 0;'>◈ AETHVION · CHAT</p>"
                f"{a_html}"
                f"</td><td width='20%'></td></tr></table>"
            )

        self._response.verticalScrollBar().setValue(
            self._response.verticalScrollBar().maximum()
        )

    def _toggle_pin(self, session_id: str) -> None:
        """Toggle pin state via the dashboard API, then refresh the history list."""
        try:
            import requests as _req
            _req.post(
                f"{DASHBOARD_URL}/api/overlay/history/{session_id}/pin",
                timeout=5,
            )
        except Exception as e:
            print(f"[Overlay] Pin toggle failed for {session_id}: {e}")
        # Refresh the list on the Qt main thread
        from PyQt6.QtCore import QMetaObject, Qt as _Qt
        QMetaObject.invokeMethod(
            self, "_load_and_render_history_list",
            _Qt.ConnectionType.QueuedConnection,
        )

    # Send / receive

    def _send(self) -> None:
        question = self._input.toPlainText().strip()
        if not question:
            return

        self._input.clear()
        self._send_btn.setEnabled(False)
        self._status.setText("Thinking…")

        if self._current_entry is None:
            # First question for this screenshot — create history entry now
            sid = _new_session_id()
            now = datetime.now()
            self._current_entry = {
                "id":              sid,
                "time":            now.strftime("%H:%M"),
                "date":            now.strftime("%Y-%m-%d"),
                "pairs":           [],
                "thumb_b64":       self._pending_thumb,
                "is_pinned":       False,
                "promoted":        False,
                "promoted_thread_id": None,
            }

        self._current_entry["pairs"].append({"q": question, "a": None})
        self._render_session(self._current_entry)

        # Build history list for same-thread multi-turn (exclude the just-added None pair)
        history_pairs = [p for p in self._current_entry["pairs"][:-1] if p.get("a")]

        if self._worker_thread and self._worker_thread.isRunning():
            self._worker_thread.quit()
            self._worker_thread.wait(2000)

        self._worker_thread = QThread()
        self._worker = AskWorker(
            question, self._screenshot_b64, self._dashboard_url,
            history=history_pairs,
        )
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
        self._render_session(self._current_entry)
        self._status.setText("Done.")
        self._send_btn.setEnabled(True)
        # Persist to disk in background
        if self._current_entry:
            entry = dict(self._current_entry)
            threading.Thread(target=save_session, args=(entry,), daemon=True).start()

    def _on_error(self, err: str) -> None:
        if self._current_entry and self._current_entry["pairs"]:
            self._current_entry["pairs"][-1]["a"] = f"### ⚠ Error\n\n{err}"
        self._render_session(self._current_entry)
        self._status.setText("Request failed.")
        self._send_btn.setEnabled(True)
        if self._current_entry:
            entry = dict(self._current_entry)
            threading.Thread(target=save_session, args=(entry,), daemon=True).start()

    # Drag & resize

    def _in_title_area(self, pos: QPoint) -> bool:
        return pos.y() < 52

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            local, gpos = event.position().toPoint(), event.globalPosition().toPoint()
            if local.x() > self.width() - _RESIZE_GRIP and local.y() > self.height() - _RESIZE_GRIP:
                self._resizing = True; self._resize_start_global = gpos; self._resize_start_size = self.size()
            elif self._in_title_area(local):
                self._drag_pos = gpos - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        gpos = event.globalPosition().toPoint()
        if self._resizing and self._resize_start_global and self._resize_start_size:
            dx = gpos.x() - self._resize_start_global.x()
            dy = gpos.y() - self._resize_start_global.y()
            self.resize(max(self.minimumWidth(),  self._resize_start_size.width()  + dx),
                        max(self.minimumHeight(), self._resize_start_size.height() + dy))
        elif self._drag_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(gpos - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None; self._resizing = False
        self._resize_start_global = None; self._resize_start_size = None


# Hotkey

def start_hotkey_listener(window: OverlayWindow) -> None:
    def _run():
        try:
            import keyboard as kb
            kb.add_hotkey("ctrl+shift+space",
                          lambda: (setattr(window, "_capture_mode", _CAPTURE_NEW),
                                   window._request_capture.emit()),
                          suppress=False)
            print("[Overlay] Hotkey registered: Ctrl+Shift+Space")
            kb.wait()
        except ImportError:
            print("[Overlay] 'keyboard' not installed — hotkey disabled.")
        except Exception as e:
            print(f"[Overlay] Hotkey error: {e}")
    threading.Thread(target=_run, daemon=True, name="overlay-hotkey").start()


# Tray

def _make_tray_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([1, 1, 30, 30], fill=(99, 102, 241, 255))
    try: draw.text((9, 6), "A", fill=(255, 255, 255, 255))
    except Exception: pass
    return img


def start_tray(window: OverlayWindow, qt_app: QApplication) -> None:
    def _run():
        try:
            import pystray
            def _ask(i, it):
                setattr(window, "_capture_mode", _CAPTURE_NEW)
                window._request_capture.emit()
            menu = pystray.Menu(
                pystray.MenuItem("Ask about screen  (Ctrl+Shift+Space)", _ask, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Open Dashboard",
                                 lambda i, it: __import__("webbrowser").open(DASHBOARD_URL)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit Overlay", lambda i, it: (i.stop(), qt_app.quit())),
            )
            icon = pystray.Icon("aethvion-overlay", _make_tray_image(), "Aethvion Overlay", menu)
            print("[Overlay] Tray icon active.")
            icon.run()
        except ImportError as e:
            print(f"[Overlay] Tray dep missing ({e}).")
        except Exception as e:
            print(f"[Overlay] Tray error: {e}")
    threading.Thread(target=_run, daemon=True, name="overlay-tray").start()


# Entry point

def main() -> None:
    if not HAS_QT:
        print("[Overlay] PyQt6 not installed. Run: pip install PyQt6"); sys.exit(1)
    if sys.platform == "win32":
        try:
            import ctypes; ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception: pass
    url    = f"http://localhost:{_find_dashboard_port()}"
    app    = QApplication(sys.argv)
    app.setApplicationName("Aethvion Overlay")
    app.setQuitOnLastWindowClosed(False)
    window = OverlayWindow(dashboard_url=url)
    start_hotkey_listener(window)
    start_tray(window, app)
    print(f"[Overlay] Started — {url}\n[Overlay] Ctrl+Shift+Space to activate.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
