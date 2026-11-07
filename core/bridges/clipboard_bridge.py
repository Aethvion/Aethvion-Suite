"""
core/bridges/clipboard_bridge.py
System Clipboard Co-Pilot Connector.
Reads and writes system clipboard text so users can copy code/errors and type '/clipboard'
or let companions copy generated snippets directly to the clipboard.
"""

import ctypes
import platform
import subprocess

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def _win32_get_clipboard_text() -> str:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = ctypes.c_bool
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool

    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr) or ""
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _win32_set_clipboard_text(text: str) -> bool:
    res = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
        input=text,
        text=True,
        capture_output=True,
        timeout=5,
    )
    return res.returncode == 0


def get_clipboard(args: dict = None) -> str:
    """Read current text from the system clipboard."""
    if args is None:
        args = {}
    max_chars = int(args.get("max_chars", 12000) or 12000)

    text = ""
    if platform.system() == "Windows":
        try:
            text = _win32_get_clipboard_text()
        except Exception:
            try:
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                    capture_output=True,
                    text=True,
                    timeout=4,
                )
                text = res.stdout or ""
            except Exception:
                text = ""

    text = (text or "").strip()
    if not text:
        return "Clipboard is currently empty (or contains non-text data)."
    if len(text) > max_chars:
        return f"Clipboard Text (truncated to {max_chars} chars):\n{text[:max_chars]}\n...[truncated]"
    return f"Clipboard Content:\n{text}"


def set_clipboard(args: dict = None) -> str:
    """Copy the provided 'text' argument into the system clipboard."""
    if args is None:
        args = {}
    text = str(args.get("text") or args.get("content") or "").strip()
    if not text:
        return "Clipboard Error: Provide 'text' argument to copy to clipboard."
    if platform.system() == "Windows":
        try:
            ok = _win32_set_clipboard_text(text)
            if ok:
                return f"Successfully copied {len(text)} characters to the system clipboard."
        except Exception as e:
            return f"Clipboard Error: {e}"
    return "Clipboard Error: Could not write to system clipboard on this platform."
