"""
core/bridges/window_focus_bridge.py
Active Window & Open Application Focus Connector.
Allows companions and users (/window) to see which application and window title
the user is currently focused on, plus open workspace windows.
"""

import ctypes
import platform
from typing import Dict, Any
import psutil


def _get_windows_focus_info(max_windows: int = 12) -> Dict[str, Any]:
    user32 = ctypes.windll.user32

    # 1. Foreground window
    hwnd = user32.GetForegroundWindow()
    fg_title = ""
    fg_proc = ""
    fg_pid = 0
    if hwnd:
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            fg_title = buf.value.strip()
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        fg_pid = pid.value
        if fg_pid:
            try:
                fg_proc = psutil.Process(fg_pid).name()
            except Exception:
                fg_proc = ""

    # 2. Visible top-level windows
    open_windows = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    SKIP_TITLES = {
        "Program Manager",
        "Settings",
        "Microsoft Text Input Application",
        "Windows Input Experience",
        "Default IME",
        "MSCTFIME UI",
    }

    def _enum_cb(h, _lparam):
        if user32.IsWindowVisible(h):
            length = user32.GetWindowTextLengthW(h)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(h, buf, length + 1)
                title = buf.value.strip()
                if title and title not in SKIP_TITLES:
                    pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
                    pname = ""
                    try:
                        pname = psutil.Process(pid.value).name()
                    except Exception:
                        pass
                    entry = f"{pname}: {title}" if pname else title
                    if entry not in open_windows:
                        open_windows.append(entry)
        return True

    try:
        user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
    except Exception:
        pass

    return {
        "active_title": fg_title or "Desktop",
        "active_process": fg_proc or "unknown",
        "open_windows": open_windows[:max_windows],
    }


def get_active_window(args: dict = None) -> str:
    """Return the active foreground window title, process name, and open desktop windows."""
    if args is None:
        args = {}
    max_win = int(args.get("max_windows", 12) or 12)

    if platform.system() == "Windows":
        try:
            info = _get_windows_focus_info(max_windows=max_win)
            lines = [
                f"Active Window: {info['active_title']} ({info['active_process']})"
            ]
            if info["open_windows"]:
                lines.append("Open Workspace Windows:")
                for w in info["open_windows"]:
                    lines.append(f"  - {w}")
            return "\n".join(lines)
        except Exception as e:
            return f"Window Focus Error: {e}"

    # Fallback for non-Windows
    try:
        procs = []
        for p in psutil.process_iter(["name", "cpu_percent"]):
            if p.info.get("name"):
                procs.append(p.info["name"])
        unique = list(dict.fromkeys(procs))[:max_win]
        return "Active Processes: " + ", ".join(unique)
    except Exception as e:
        return f"Window Focus Error: {e}"
