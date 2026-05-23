"""
core/automate/nodes/actions.py
════════════════════════════════
Handler functions for all action.* node types.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

from ._utils import _to_str, _now


def action_http(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    import urllib.request  # noqa: PLC0415

    p      = node.get("properties", {})
    url    = str(p.get("url", "")).strip()
    method = str(p.get("method", "GET")).upper()
    body   = _to_str(inputs.get("in", p.get("body", "")))

    try:
        headers = json.loads(str(p.get("headers", "{}")))
    except json.JSONDecodeError:
        headers = {}

    if not url:
        raise ValueError("HTTP node: no URL configured.")

    req = urllib.request.Request(url, method=method)
    for k, v in (headers or {}).items():
        req.add_header(str(k), str(v))

    if body and method in ("POST", "PUT", "PATCH"):
        req.data = body.encode("utf-8")
        if "Content-Type" not in headers:
            req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return {"out": raw, "error": ""}
    except Exception as exc:
        return {"out": "", "error": str(exc)}


def action_log(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p      = node.get("properties", {})
    in_val = _to_str(inputs.get("in", ""))
    msg    = str(p.get("message", "{{input}}")).replace("{{input}}", in_val)
    level  = str(p.get("level", "info")).lower()
    ctx._log.append({"level": level, "msg": f"[LOG] {msg}", "ts": _now()})
    return {"out": in_val}


def action_run_script(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p          = node.get("properties", {})
    script     = str(p.get("script", ""))
    input_data = inputs.get("in", "")
    local_ns   = {"input_data": input_data, "result": None}
    try:
        exec(compile(script, "<automate-script>", "exec"), {}, local_ns)  # noqa: S102
        return {"out": local_ns.get("result", input_data), "error": ""}
    except Exception as exc:
        return {"out": "", "error": str(exc)}


def action_file_read(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    import base64  # noqa: PLC0415

    p         = node.get("properties", {})
    file_path = str(inputs.get("path") or p.get("path", "")).strip()

    if not file_path:
        return {"out": "", "path": "", "size": 0, "error": "No file path configured"}

    encoding  = str(p.get("encoding", "utf-8"))
    strip     = bool(p.get("strip", False))
    max_bytes = int(p.get("max_bytes", 0) or 0)

    try:
        size = os.path.getsize(file_path)
        if max_bytes and size > max_bytes:
            return {"out": "", "path": file_path, "size": size,
                    "error": f"File too large: {size} bytes (max {max_bytes})"}

        if encoding == "binary":
            with open(file_path, "rb") as fh:
                content = base64.b64encode(fh.read()).decode("ascii")
        else:
            with open(file_path, "r", encoding=encoding, errors="replace") as fh:
                content = fh.read()

        if strip:
            content = content.strip()
        return {"out": content, "path": file_path, "size": size, "error": ""}
    except Exception as exc:
        return {"out": "", "path": file_path, "size": 0, "error": str(exc)}


def action_file_write(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p           = node.get("properties", {})
    file_path   = str(inputs.get("path") or p.get("path", "")).strip()
    content     = _to_str(inputs.get("in", ""))
    mode        = str(p.get("mode", "overwrite"))
    encoding    = str(p.get("encoding", "utf-8"))
    newline     = bool(p.get("newline", True))
    create_dirs = bool(p.get("create_dirs", True))

    if not file_path:
        return {"out": content, "path": "", "error": "No file path configured"}

    write_content = content
    if newline and not write_content.endswith("\n"):
        write_content += "\n"

    try:
        if create_dirs:
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)

        if mode == "overwrite":
            with open(file_path, "w", encoding=encoding) as fh:
                fh.write(write_content)
        elif mode == "append":
            with open(file_path, "a", encoding=encoding) as fh:
                fh.write(write_content)
        elif mode == "prepend":
            existing = ""
            if os.path.exists(file_path):
                with open(file_path, "r", encoding=encoding) as fh:
                    existing = fh.read()
            with open(file_path, "w", encoding=encoding) as fh:
                fh.write(write_content + existing)

        return {"out": content, "path": file_path, "error": ""}
    except Exception as exc:
        return {"out": content, "path": file_path, "error": str(exc)}


def action_notify(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p       = node.get("properties", {})
    title   = _to_str(inputs.get("title")   or p.get("title",   "Aethvion"))
    message = _to_str(inputs.get("message") or p.get("message", "Workflow completed."))
    in_val  = _to_str(inputs.get("in", ""))
    message = message.replace("{{input}}", in_val)

    # Sanitise for shell embedding — strip double-quotes to avoid injection
    title_safe   = title.replace('"', "'")
    message_safe = message.replace('"', "'")

    try:
        if sys.platform == "win32":
            try:
                from winotify import Notification  # noqa: PLC0415
                toast = Notification(app_id="Aethvion Suite", title=title_safe, msg=message_safe)
                toast.show()
            except ImportError:
                # PowerShell balloon toast — hidden window, fire-and-forget.
                ps_cmd = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "$n = New-Object System.Windows.Forms.NotifyIcon; "
                    "$n.Icon = [System.Drawing.SystemIcons]::Information; "
                    "$n.Visible = $true; "
                    f'$n.ShowBalloonTip(5000, "{title_safe}", "{message_safe}", '
                    "[System.Windows.Forms.ToolTipIcon]::Info); "
                    "Start-Sleep 6; $n.Visible = $false"
                )
                subprocess.Popen(  # noqa: S603
                    ["powershell", "-NoProfile", "-NonInteractive",
                     "-WindowStyle", "Hidden", "-Command", ps_cmd],
                    creationflags=0x08000000,   # CREATE_NO_WINDOW
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        elif sys.platform == "darwin":
            subprocess.Popen(  # noqa: S603
                ["osascript", "-e",
                 f'display notification "{message_safe}" with title "{title_safe}"'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(  # noqa: S603
                ["notify-send", title_safe, message_safe],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return {"out": in_val, "error": ""}
    except Exception as exc:
        return {"out": in_val, "error": str(exc)}
