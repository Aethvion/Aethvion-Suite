"""
core/utils/browser.py
─────────────────────
Open a URL in browser "App Mode" — no URL bar, no tab strip, no bookmarks bar.
Tries Chrome first, then Edge, then falls back to the default system browser.

Respects the AETHVION_NO_BROWSER=1 environment variable so the master launcher
can suppress per-server browser opens when it manages the suite itself.

Usage
─────
    from core.utils.browser import open_app_window

    # Non-blocking — returns immediately, opens after `delay` seconds
    open_app_window("http://localhost:8080", delay=1.5)

    # Block until the window is open (rare; prefer non-blocking)
    open_app_window("http://localhost:8080", delay=0, background=False)
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

# ── Browser executable search paths ───────────────────────────────────────────

_CHROME_PATHS: list[str] = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    # Linux (common locations)
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
]

_EDGE_PATHS: list[str] = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    # macOS
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    # Linux
    "/usr/bin/microsoft-edge",
    "/usr/bin/microsoft-edge-stable",
]


def _find_app_browser() -> str | None:
    """Return the path to the first available Chromium-family browser, or None."""
    for path in _CHROME_PATHS + _EDGE_PATHS:
        try:
            if Path(path).is_file():
                return path
        except Exception:
            continue
    return None


# ── Public API ─────────────────────────────────────────────────────────────────

def open_app_window(
    url: str,
    delay: float = 1.5,
    background: bool = True,
    app_mode: bool = True,
) -> None:
    """
    Open *url* in the browser.

    Parameters
    ----------
    url      : Full URL to open, e.g. "http://localhost:8080"
    delay    : Seconds to wait before opening (lets the server start up).
               Set to 0 to open immediately.
    background : If True (default) runs in a daemon thread so the caller is
                 not blocked.  If False, blocks until the browser is launched.
    app_mode : If True (default) uses Chrome/Edge ``--app=`` flag which strips
               the URL bar, tab strip and bookmarks bar, giving a native-app
               feel.  If False, opens a normal browser tab instead.
    """
    if os.environ.get("AETHVION_NO_BROWSER") == "1":
        return

    def _launch() -> subprocess.Popen | None:
        if delay > 0:
            time.sleep(delay)

        exe = _find_app_browser()
        if exe:
            try:
                # CREATE_NO_WINDOW on Windows so no flash of a CMD box
                kwargs: dict = {}
                if os.name == "nt":
                    kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

                cmd = [exe, f"--app={url}"] if app_mode else [exe, url]
                return subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **kwargs,
                )
            except Exception:
                pass  # fall through to webbrowser

        # Fallback — opens in whatever the OS default browser is
        webbrowser.open(url)
        return None

    if background:
        # We can't easily return the proc from a daemon thread's start
        t = threading.Thread(target=_launch, daemon=True)
        t.start()
        return None
    else:
        return _launch()
