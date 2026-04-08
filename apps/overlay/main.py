"""
apps/overlay/main.py
────────────────────
Aethvion Suite — Desktop Overlay Sidecar

A lightweight system-tray companion that lets you ask questions about your
screen without opening the dashboard browser tab.

Hotkey : Ctrl+Shift+Space  (captures screen → opens floating input window)
Tray   : right-click icon for quick actions

Dependencies (pip install ...):
    PyQt6   pystray   Pillow   mss   keyboard

Usage:
    python apps/overlay/main.py
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# ── Project root on sys.path ──────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

# ── Discover dashboard port ───────────────────────────────────────────────────
def _find_dashboard_port() -> int:
    """Read data/system/ports.json written by the launcher to find the live port."""
    try:
        ports_file = ROOT / "data" / "system" / "ports.json"
        if ports_file.exists():
            data = json.loads(ports_file.read_text(encoding="utf-8"))
            for port, name in data.items():
                if "dashboard" in str(name).lower() or "nexus" in str(name).lower():
                    return int(port)
    except Exception:
        pass
    return 8080  # safe default


DASHBOARD_URL = f"http://localhost:{_find_dashboard_port()}"

# ── Qt availability check ─────────────────────────────────────────────────────
try:
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QHBoxLayout,
        QTextEdit, QLineEdit, QPushButton, QLabel, QFrame, QComboBox,
        QTextBrowser,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QPoint
    from PyQt6.QtGui import QFont, QTextCursor

    HAS_QT = True
except ImportError:
    HAS_QT = False

# ── Screenshot helper ─────────────────────────────────────────────────────────

def list_monitors() -> list[dict]:
    """Return a list of available monitors as dicts {index, label, width, height}."""
    try:
        import mss
        with mss.mss() as sct:
            result = []
            # monitors[0] = virtual combined screen, monitors[1..n] = real displays
            for i, m in enumerate(sct.monitors):
                if i == 0:
                    label = "All Screens Combined"
                else:
                    label = f"Screen {i}  ({m['width']}×{m['height']})"
                result.append({"index": i, "label": label, "width": m["width"], "height": m["height"]})
            return result
    except Exception:
        return [{"index": 1, "label": "Primary Screen", "width": 0, "height": 0}]


def take_screenshot_b64(monitor_index: int = 1) -> Optional[str]:
    """
    Capture the specified monitor and return a base64-encoded PNG string.

    Args:
        monitor_index: Index into mss.monitors list.
                       0 = all screens combined, 1 = primary (default), 2+ = secondary.
    """
    try:
        import mss
        with mss.mss() as sct:
            monitors = sct.monitors
            # Clamp index to valid range
            idx = max(0, min(monitor_index, len(monitors) - 1))
            if not monitors:
                return None
            monitor = monitors[idx]
            sct_img = sct.grab(monitor)

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


# ── API worker (runs in QThread) ──────────────────────────────────────────────

class AskWorker(QObject):
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, question: str, screenshot_b64: Optional[str], dashboard_url: str):
        super().__init__()
        self.question       = question
        self.screenshot_b64 = screenshot_b64
        self.dashboard_url  = dashboard_url

    def run(self) -> None:
        import urllib.request
        import urllib.error

        payload = json.dumps({
            "question":       self.question,
            "screenshot_b64": self.screenshot_b64,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.dashboard_url}/api/overlay/ask",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data   = json.loads(resp.read().decode("utf-8"))
                answer = data.get("answer", "(no response)")
                self.finished.emit(answer)
        except urllib.error.HTTPError as e:
            # Extract the FastAPI detail message from the JSON body
            try:
                body   = json.loads(e.read().decode("utf-8"))
                detail = body.get("detail", str(e))
            except Exception:
                detail = str(e)
            self.error.emit(f"Server error {e.code}: {detail}")
        except urllib.error.URLError as e:
            self.error.emit(f"Could not reach dashboard ({self.dashboard_url}): {e.reason}")
        except Exception as e:
            self.error.emit(str(e))


# ── Custom Input Widget ───────────────────────────────────────────────────

class ChatInput(QTextEdit):
    """
    Custom QTextEdit that sends on Enter and adds new line on Shift+Enter.
    """
    send_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("What do you want to know about this screen?")
        self.setFont(QFont("Segoe UI", 11))
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
            QTextEdit:focus {
                border-color: rgba(99,102,241,210);
            }
        """)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.send_requested.emit()
        else:
            super().keyPressEvent(event)


# ── Floating overlay window ───────────────────────────────────────────────────

class OverlayWindow(QWidget):
    """
    Borderless, always-on-top floating window with an indigo dark theme.
    Can be dragged by clicking anywhere in the title bar area.
    """

    # Signal emitted from hotkey/tray threads to trigger show
    show_overlay = pyqtSignal(str)   # base64 screenshot (may be "")

    def __init__(self, dashboard_url: str):
        super().__init__()
        self._dashboard_url  = dashboard_url
        self._screenshot_b64: Optional[str] = None
        self._drag_pos: Optional[QPoint]    = None
        self._worker_thread: Optional[QThread] = None
        self._worker: Optional[AskWorker]       = None
        self._selected_monitor: int = 1  # default = primary

        self._build_ui()

        # Cross-thread signal → main-thread slot
        self.show_overlay.connect(self._on_show_overlay)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool          # omit from taskbar
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(480, 320)
        self.resize(540, 400)

        # Outer layout (transparent gap around container for shadow illusion)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        container = QFrame(self)
        container.setObjectName("aovContainer")
        outer.addWidget(container)

        container.setStyleSheet("""
            QFrame#aovContainer {
                background-color: rgba(12, 12, 22, 230);
                border: 1px solid rgba(99, 102, 241, 130);
                border-radius: 14px;
            }
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        # ── Title bar ─────────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        dot = QLabel("◈")
        dot.setStyleSheet("color: rgba(99,102,241,255); font-size: 15px;")

        title = QLabel("Ask about screen")
        title.setStyleSheet(
            "color: rgba(200,200,224,220); font-size: 13px; font-weight: 600;"
        )

        self._hotkey_lbl = QLabel("Ctrl+Shift+Space")
        self._hotkey_lbl.setStyleSheet(
            "color: rgba(120,120,150,180); font-size: 11px;"
        )

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(160,160,180,200);
                border: none;
                border-radius: 13px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(220,55,55,180);
                color: white;
            }
        """)
        close_btn.clicked.connect(self.hide)

        title_row.addWidget(dot)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(self._hotkey_lbl)
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
                background: rgba(18,18,32,210);
                color: rgba(200,200,224,220);
                border: 1px solid rgba(99,102,241,80);
                border-radius: 6px;
                padding: 2px 8px;
                font-size: 11px;
            }
            QComboBox::drop-down { border: none; width: 18px; }
            QComboBox QAbstractItemView {
                background: rgba(12,12,22,240);
                color: rgba(200,200,224,220);
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
                background: rgba(99,102,241,120);
                color: rgba(220,220,245,255);
                border: none;
                border-radius: 6px;
                padding: 2px 10px;
                font-size: 11px;
            }
            QPushButton:hover   { background: rgba(99,102,241,200); }
            QPushButton:pressed { background: rgba(79,82,221,255); }
        """)
        self._new_scr_btn.clicked.connect(self._take_new_screenshot)

        screen_row.addWidget(screen_lbl)
        screen_row.addWidget(self._screen_combo, 1)
        screen_row.addWidget(self._new_scr_btn)
        layout.addLayout(screen_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setMaximumHeight(1)
        sep.setStyleSheet("background: rgba(99,102,241,55);")
        layout.addWidget(sep)

        # ── Response area ─────────────────────────────────────────────────────
        self._response = QTextBrowser()
        self._response.setOpenExternalLinks(True)
        self._response.setReadOnly(True)
        self._response.setMinimumHeight(150)
        self._response.setPlaceholderText("Response will appear here…")
        self._response.setFont(QFont("Segoe UI", 11))
        self._response.setStyleSheet("""
            QTextBrowser {
                background: rgba(8, 8, 18, 190);
                color: rgba(210,210,235,245);
                border: 1px solid rgba(99,102,241,55);
                border-radius: 9px;
                padding: 6px;
            }
            QScrollBar:vertical {
                background: rgba(20,20,35,180);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(99,102,241,150);
                border-radius: 3px;
            }
        """)

        # Better markdown styling via default document stylesheet
        self._response.document().setDefaultStyleSheet("""
            h1, h2, h3, h4 { color: #818cf8; margin-top: 6px; margin-bottom: 2px; font-weight: bold; }
            code { 
                background-color: rgba(99, 102, 241, 40); 
                color: #e2e8f0; 
                font-family: 'Consolas', 'Cascadia Code', 'Courier New', monospace;
                padding: 2px 4px;
                border-radius: 4px;
            }
            pre { 
                background-color: rgba(0, 0, 0, 100); 
                border: 1px solid rgba(99, 102, 241, 60);
                padding: 12px; 
                border-radius: 8px;
                margin: 8px 0px;
                font-family: 'Consolas', 'Cascadia Code', 'Courier New', monospace;
            }
            a { color: #818cf8; text-decoration: none; }
            li { margin-bottom: 4px; }
            blockquote { 
                border-left: 3px solid rgba(99, 102, 241, 150);
                padding-left: 10px;
                color: rgba(210, 210, 235, 180);
                font-style: italic;
            }
        """)
        layout.addWidget(self._response)

        # ── Input row ─────────────────────────────────────────────────────────
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._input = ChatInput()
        self._input.send_requested.connect(self._send)

        self._send_btn = QPushButton("Ask")
        self._send_btn.setFixedSize(64, 38)
        self._send_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._send_btn.setStyleSheet("""
            QPushButton {
                background: rgba(99,102,241,210);
                color: white;
                border: none;
                border-radius: 9px;
            }
            QPushButton:hover   { background: rgba(99,102,241,255); }
            QPushButton:pressed { background: rgba(79,82,221,255); }
            QPushButton:disabled {
                background: rgba(50,50,70,160);
                color: rgba(110,110,130,200);
            }
        """)
        self._send_btn.clicked.connect(self._send)

        input_row.addWidget(self._input)
        input_row.addWidget(self._send_btn)
        layout.addLayout(input_row)

        # Status label
        self._status = QLabel("")
        self._status.setStyleSheet("color: rgba(130,130,158,200); font-size: 11px;")
        layout.addWidget(self._status)

        # Centre on primary screen
        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            self.move(
                sg.center().x() - self.width() // 2,
                sg.center().y() - self.height() // 2,
            )

    # ── Screen selector helpers ───────────────────────────────────────────────

    def _populate_screen_combo(self) -> None:
        """Fill the screen combo with available monitors."""
        self._screen_combo.blockSignals(True)
        self._screen_combo.clear()
        monitors = list_monitors()
        for m in monitors:
            self._screen_combo.addItem(m["label"], userData=m["index"])
        # Default to primary (index 1 if available, else 0)
        default_pos = 1 if len(monitors) > 1 else 0
        self._screen_combo.setCurrentIndex(default_pos)
        self._selected_monitor = monitors[default_pos]["index"]
        self._screen_combo.blockSignals(False)

    def _on_screen_changed(self, combo_idx: int) -> None:
        monitor_index = self._screen_combo.itemData(combo_idx)
        if monitor_index is not None:
            self._selected_monitor = monitor_index

    def _take_new_screenshot(self) -> None:
        """Grab a fresh screenshot of the selected screen."""
        self._new_scr_btn.setEnabled(False)
        self._new_scr_btn.setText("Capturing…")
        self.hide()   # hide overlay so it doesn't appear in the screenshot

        import threading

        def _grab() -> None:
            import time
            time.sleep(0.15)   # short delay so window fully hides first
            scr = take_screenshot_b64(self._selected_monitor)
            # Re-show on main thread via signal
            self.show_overlay.emit(scr or "")

        threading.Thread(target=_grab, daemon=True).start()

    # ── Slot: activated by hotkey / tray ─────────────────────────────────────

    def _on_show_overlay(self, screenshot_b64: str) -> None:
        self._screenshot_b64 = screenshot_b64 or None
        self._response.clear()
        self._input.clear()
        self._send_btn.setEnabled(True)
        self._new_scr_btn.setEnabled(True)
        self._new_scr_btn.setText("📷 New Screenshot")
        # Refresh monitor list each time the overlay opens (monitors may have changed)
        self._populate_screen_combo()
        hint = "Screenshot captured." if screenshot_b64 else "No screenshot available."
        self._status.setText(f"{hint}  Type your question and press Enter.")
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()
        self._input.selectAll()

    # ── Send question ─────────────────────────────────────────────────────────

    def _send(self) -> None:
        question = self._input.toPlainText().strip()
        if not question:
            return

        # Clear input and disable UI
        self._input.clear()
        self._send_btn.setEnabled(False)
        self._status.setText("Thinking…")

        # Add separator if history exists
        if self._response.toPlainText().strip():
            self._response.append("<hr style='border: 1px solid rgba(99, 102, 241, 40);'>")

        # Append user message
        self._response.append(f"<div style='color: #818cf8; font-weight: bold;'>Me:</div> {question}")
        
        # Append thinking indicator as a new block we can find later
        self._response.append("<div style='color: #6366f1; font-style: italic;'>Thinking...</div>")
        
        # Auto-scroll to bottom
        self._response.verticalScrollBar().setValue(self._response.verticalScrollBar().maximum())

        # Clean up any previous thread
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

    def _replace_thinking(self, content_markdown: str) -> None:
        """Replace the last block (our 'Thinking...' indicator) with actual content."""
        cursor = QTextCursor(self._response.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Move to the start of the current block (the indicator) and select it
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        
        # Insert the response
        cursor.insertMarkdown(content_markdown)
        
        # Ensure scroll follows
        self._response.verticalScrollBar().setValue(self._response.verticalScrollBar().maximum())

    def _on_response(self, text: str) -> None:
        self._replace_thinking(text)
        self._status.setText("Done.")
        self._send_btn.setEnabled(True)

    def _on_error(self, err: str) -> None:
        self._replace_thinking(f"### ⚠ Error\n\n{err}")
        self._status.setText("Request failed.")
        self._send_btn.setEnabled(True)

    # ── Drag the frameless window by clicking anywhere ────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None


# ── Hotkey listener (daemon thread) ──────────────────────────────────────────

def start_hotkey_listener(window: OverlayWindow) -> None:
    """Register Ctrl+Shift+Space as a global hotkey in a background thread."""

    def _run() -> None:
        try:
            import keyboard as kb

            def _trigger() -> None:
                # Capture the selected screen BEFORE the overlay appears
                scr = take_screenshot_b64(window._selected_monitor)
                window.show_overlay.emit(scr or "")

            kb.add_hotkey("ctrl+shift+space", _trigger, suppress=False)
            print("[Overlay] Hotkey registered: Ctrl+Shift+Space")
            kb.wait()          # blocks thread until keyboard exits
        except ImportError:
            print("[Overlay] 'keyboard' not installed — hotkey disabled. Run: pip install keyboard")
        except Exception as e:
            print(f"[Overlay] Hotkey listener error: {e}")

    t = threading.Thread(target=_run, daemon=True, name="overlay-hotkey")
    t.start()


# ── Tray icon (daemon thread) ─────────────────────────────────────────────────

def _make_tray_image():
    """Return a 32×32 RGBA Pillow image for the tray icon."""
    from PIL import Image, ImageDraw, ImageFont

    img  = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Indigo filled circle
    draw.ellipse([1, 1, 30, 30], fill=(99, 102, 241, 255))
    # Simple "A" letter
    try:
        draw.text((9, 6), "A", fill=(255, 255, 255, 255))
    except Exception:
        pass
    return img


def start_tray(window: OverlayWindow, qt_app: QApplication) -> None:
    """Create a system tray icon in a background thread."""

    def _run() -> None:
        try:
            import pystray

            img = _make_tray_image()

            def _on_ask(icon, item) -> None:
                scr = take_screenshot_b64(window._selected_monitor)
                window.show_overlay.emit(scr or "")

            def _on_dashboard(icon, item) -> None:
                import webbrowser
                webbrowser.open(DASHBOARD_URL)

            def _on_quit(icon, item) -> None:
                icon.stop()
                qt_app.quit()

            menu = pystray.Menu(
                pystray.MenuItem(
                    "Ask about screen  (Ctrl+Shift+Space)",
                    _on_ask,
                    default=True,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Open Dashboard", _on_dashboard),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit Overlay", _on_quit),
            )

            icon = pystray.Icon(
                name="aethvion-overlay",
                icon=img,
                title="Aethvion Overlay",
                menu=menu,
            )
            print("[Overlay] Tray icon active.")
            icon.run()

        except ImportError as e:
            print(f"[Overlay] Tray dependency missing ({e}). Run: pip install pystray Pillow")
        except Exception as e:
            print(f"[Overlay] Tray error: {e}")

    t = threading.Thread(target=_run, daemon=True, name="overlay-tray")
    t.start()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if not HAS_QT:
        print(
            "[Overlay] PyQt6 is not installed.\n"
            "          Run: pip install PyQt6\n"
            "          Then restart the overlay."
        )
        sys.exit(1)

    # Windows: DPI awareness so text/scaling is crisp
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    # Re-detect port now (may have changed if dashboard restarted)
    url = f"http://localhost:{_find_dashboard_port()}"

    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Aethvion Overlay")
    qt_app.setQuitOnLastWindowClosed(False)   # keep alive when overlay hides

    window = OverlayWindow(dashboard_url=url)

    start_hotkey_listener(window)
    start_tray(window, qt_app)

    print(
        f"[Overlay] Started — dashboard at {url}\n"
        "[Overlay] Press Ctrl+Shift+Space or use the tray icon to activate."
    )

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
