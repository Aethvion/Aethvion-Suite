"""
core/automate/nodes/inputs_outputs.py
══════════════════════════════════════
Handler functions for input.* and output.* node types.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from ._utils import _to_str


# Inputs

def input_text(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p = node.get("properties", {})
    return {"out": str(p.get("value", ""))}


def input_number(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p = node.get("properties", {})
    try:
        return {"out": float(p.get("value", 0))}
    except (ValueError, TypeError):
        return {"out": 0.0}


def input_file(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    import base64  # noqa: PLC0415

    p         = node.get("properties", {})
    file_path = str(p.get("path", "")).strip()

    if not file_path:
        raise ValueError("input.file: No file path configured")

    encoding = str(p.get("encoding", "utf-8"))
    strip    = bool(p.get("strip", False))

    size = os.path.getsize(file_path)

    if encoding == "binary":
        with open(file_path, "rb") as fh:
            content = base64.b64encode(fh.read()).decode("ascii")
    else:
        with open(file_path, "r", encoding=encoding, errors="replace") as fh:
            content = fh.read()

    if strip:
        content = content.strip()

    return {
        "out":  content,
        "path": file_path,
        "name": os.path.basename(file_path),
        "size": size,
    }


def input_list(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p    = node.get("properties", {})
    raw  = str(p.get("items", ""))
    trim = bool(p.get("trim", True))
    clean = bool(p.get("remove_empty", True))

    lines = raw.splitlines()
    if trim:
        lines = [ln.strip() for ln in lines]
    if clean:
        lines = [ln for ln in lines if ln]

    first = lines[0] if lines else ""
    return {"out": json.dumps(lines, ensure_ascii=False), "count": len(lines), "first": first}


# Outputs

def output_display(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    # _display prefix tells the executor log summary to skip this port,
    # but the frontend reads it for the Display node card.
    return {"_display": inputs.get("in", "")}


def output_file(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p        = node.get("properties", {})
    in_val   = inputs.get("in", "")
    path_tpl = str(p.get("path", "")).strip()
    mode     = str(p.get("mode", "overwrite"))
    encoding = str(p.get("encoding", "utf-8"))
    fmt      = str(p.get("format", "auto"))

    if not path_tpl:
        raise ValueError("output.file: No output file path configured")

    # Resolve {{timestamp}} and {{date}} placeholders
    now       = datetime.now()
    file_path = (
        path_tpl
        .replace("{{timestamp}}", now.strftime("%Y%m%d_%H%M%S"))
        .replace("{{date}}", now.strftime("%Y-%m-%d"))
    )

    if bool(p.get("create_dirs", True)):
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)

    # Format content
    if fmt == "json_pretty" or (fmt == "auto" and isinstance(in_val, (dict, list))):
        content = json.dumps(in_val, indent=2, ensure_ascii=False)
    elif fmt == "lines" and isinstance(in_val, list):
        content = "\n".join(str(x) for x in in_val)
    else:
        content = _to_str(in_val)

    # Handle new_file mode — auto-increment if file already exists
    if mode == "new_file" and os.path.exists(file_path):
        base, ext = os.path.splitext(file_path)
        i = 1
        while os.path.exists(f"{base}_{i}{ext}"):
            i += 1
        file_path = f"{base}_{i}{ext}"

    write_mode = "a" if mode == "append" else "w"
    with open(file_path, write_mode, encoding=encoding) as fh:
        fh.write(content)

    # _file_path prefix keeps this out of the log summary
    return {"_file_path": file_path}


def output_clipboard(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    from .actions import _clipboard_write  # noqa: PLC0415

    p      = node.get("properties", {})
    in_val = inputs.get("in", "")
    fmt    = str(p.get("format", "auto"))

    # Format content
    if fmt == "json_pretty" and isinstance(in_val, (dict, list)):
        content = json.dumps(in_val, indent=2, ensure_ascii=False)
    elif fmt == "trim":
        content = _to_str(in_val).strip()
    else:
        content = _to_str(in_val)

    try:
        _clipboard_write(content)
    except Exception as exc:
        return {"_copied": False, "_error": str(exc)}

    # Optional desktop notification
    if bool(p.get("notify", True)):
        _notify_clipboard_done()

    return {"_copied": True}


def _notify_clipboard_done() -> None:
    """Fire-and-forget desktop notification confirming clipboard copy."""
    import subprocess, sys  # noqa: PLC0415
    try:
        if sys.platform == "win32":
            ps_cmd = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$n = New-Object System.Windows.Forms.NotifyIcon; "
                "$n.Icon = [System.Drawing.SystemIcons]::Information; "
                "$n.Visible = $true; "
                '$n.ShowBalloonTip(2000, "Aethvion", "Copied to clipboard", '
                "[System.Windows.Forms.ToolTipIcon]::Info); "
                "Start-Sleep 3; $n.Visible = $false"
            )
            subprocess.Popen(  # noqa: S603
                ["powershell", "-NoProfile", "-NonInteractive",
                 "-WindowStyle", "Hidden", "-Command", ps_cmd],
                creationflags=0x08000000,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "darwin":
            subprocess.Popen(  # noqa: S603
                ["osascript", "-e",
                 'display notification "Copied to clipboard" with title "Aethvion"'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(  # noqa: S603
                ["notify-send", "Aethvion", "Copied to clipboard"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass  # Notification failure should never break the workflow
