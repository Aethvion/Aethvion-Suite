"""
core/automate/nodes/actions.py
════════════════════════════════
Handler functions for all action.* node types.
"""
from __future__ import annotations

import glob as _glob
import html
import json
import os
import re
import subprocess
import sys
from typing import Any

from ._utils import _to_str, _now, _get_pm


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


def action_clipboard(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p      = node.get("properties", {})
    mode   = str(p.get("mode", "write"))
    in_val = _to_str(inputs.get("in", ""))

    try:
        if mode == "write":
            _clipboard_write(in_val)
            out = in_val
        elif mode.startswith("read"):
            out = _clipboard_read()
            if mode == "read_then_clear":
                _clipboard_write("")
        else:
            out = in_val
        return {"out": out, "error": ""}
    except Exception as exc:
        return {"out": in_val, "error": str(exc)}


def _clipboard_write(text: str) -> None:
    """Write *text* to the system clipboard (no visible window on any platform)."""
    if sys.platform == "win32":
        # clip.exe accepts stdin; UTF-16-LE is reliable on all modern Windows versions.
        subprocess.run(  # noqa: S603
            "clip",
            input=text.encode("utf-16-le"),
            creationflags=0x08000000,   # CREATE_NO_WINDOW
            check=False, timeout=5,
        )
    elif sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=text.encode(), check=False, timeout=5)  # noqa: S603
    else:
        subprocess.run(  # noqa: S603
            ["xclip", "-selection", "clipboard"],
            input=text.encode(), check=False, timeout=5,
        )


def _clipboard_read() -> str:
    """Read text from the system clipboard."""
    if sys.platform == "win32":
        r = subprocess.run(  # noqa: S603
            ["powershell", "-NoProfile", "-NonInteractive",
             "-WindowStyle", "Hidden", "-Command", "Get-Clipboard"],
            capture_output=True, text=True,
            creationflags=0x08000000, timeout=5, check=False,
        )
        return r.stdout.rstrip("\n")
    elif sys.platform == "darwin":
        r = subprocess.run(["pbpaste"], capture_output=True, timeout=5, check=False)  # noqa: S603
        return r.stdout.decode("utf-8", errors="replace")
    else:
        r = subprocess.run(  # noqa: S603
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True, timeout=5, check=False,
        )
        return r.stdout.decode("utf-8", errors="replace")


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


# Sprint 4: shell / filesystem / web

def action_run_command(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p       = node.get("properties", {})
    cmd     = _to_str(inputs.get("cmd") or inputs.get("in", "") or p.get("command", "")).strip()
    cwd     = str(p.get("working_dir", "")).strip() or None
    timeout = float(p.get("timeout", 30) or 30)
    use_shell = bool(p.get("shell", False))

    if not cmd:
        return {"out": "", "stderr": "", "exit_code": -1, "error": "No command configured"}

    try:
        result = subprocess.run(  # noqa: S603
            cmd if use_shell else cmd.split(),
            capture_output=True,
            text=True,
            shell=use_shell,           # noqa: S604
            cwd=cwd,
            timeout=timeout,
        )
        return {
            "out":       result.stdout.rstrip("\n"),
            "stderr":    result.stderr.rstrip("\n"),
            "exit_code": result.returncode,
            "error":     result.stderr.rstrip("\n") if result.returncode != 0 else "",
        }
    except subprocess.TimeoutExpired:
        return {"out": "", "stderr": "", "exit_code": -1, "error": f"Command timed out after {timeout}s"}
    except Exception as exc:
        return {"out": "", "stderr": "", "exit_code": -1, "error": str(exc)}


def action_file_list(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p           = node.get("properties", {})
    folder      = _to_str(inputs.get("path") or p.get("path", "")).strip()
    pattern     = str(p.get("pattern", "*")).strip() or "*"
    recursive   = bool(p.get("recursive", False))
    incl_dirs   = bool(p.get("include_dirs", False))
    sort_by     = str(p.get("sort_by", "name"))   # "name" | "size" | "modified"
    output_mode = str(p.get("output_as", "paths")) # "paths" | "objects"

    if not folder:
        return {"out": "[]", "count": 0, "error": "No folder path configured"}
    if not os.path.isdir(folder):
        return {"out": "[]", "count": 0, "error": f"Not a directory: {folder}"}

    try:
        glob_pat = os.path.join(folder, "**", pattern) if recursive else os.path.join(folder, pattern)
        raw_paths = _glob.glob(glob_pat, recursive=recursive)

        entries = []
        for p_str in raw_paths:
            if os.path.isdir(p_str):
                if not incl_dirs:
                    continue
            entries.append(p_str)

        # Sort
        if sort_by == "size":
            entries.sort(key=lambda f: os.path.getsize(f) if os.path.isfile(f) else 0)
        elif sort_by == "modified":
            entries.sort(key=lambda f: os.path.getmtime(f))
        else:
            entries.sort()

        if output_mode == "objects":
            out_list = []
            for e in entries:
                stat = os.stat(e)
                out_list.append({
                    "path":     e,
                    "name":     os.path.basename(e),
                    "size":     stat.st_size,
                    "modified": stat.st_mtime,
                    "is_dir":   os.path.isdir(e),
                })
            out = json.dumps(out_list, ensure_ascii=False)
        else:
            out = json.dumps(entries, ensure_ascii=False)

        return {"out": out, "count": len(entries), "error": ""}
    except Exception as exc:
        return {"out": "[]", "count": 0, "error": str(exc)}


# Web scraper helpers

_TAG_RE   = re.compile(r"<[^>]+>")
_HEAD_RE  = re.compile(r"<head[^>]*>.*?</head>", re.IGNORECASE | re.DOTALL)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)

# Markdown conversion helpers
_H_RE    = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
_BOLD_RE = re.compile(r"<(b|strong)[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
_LINK_RE = re.compile(r'<a[^>]+href="([^"]*)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_P_RE    = re.compile(r"</?(p|br|div|li|tr)[^>]*>", re.IGNORECASE)


def _html_to_text(html_str: str) -> str:
    """Strip all tags and decode HTML entities → plain text."""
    cleaned = _SCRIPT_RE.sub(" ", html_str)
    cleaned = _P_RE.sub("\n", cleaned)
    cleaned = _TAG_RE.sub("", cleaned)
    cleaned = html.unescape(cleaned)
    # Collapse excessive whitespace, keep paragraph breaks
    lines = [ln.strip() for ln in cleaned.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _html_to_markdown(html_str: str) -> str:
    """Convert a subset of HTML to Markdown."""
    md = _SCRIPT_RE.sub("", html_str)
    md = _HEAD_RE.sub("", md)
    # Headings
    md = _H_RE.sub(lambda m: "#" * int(m.group(1)) + " " + _TAG_RE.sub("", m.group(2)).strip() + "\n", md)
    # Bold
    md = _BOLD_RE.sub(lambda m: "**" + _TAG_RE.sub("", m.group(2)).strip() + "**", md)
    # Links
    md = _LINK_RE.sub(lambda m: f"[{_TAG_RE.sub('', m.group(2)).strip()}]({m.group(1)})", md)
    # Block elements → newlines
    md = _P_RE.sub("\n", md)
    md = _TAG_RE.sub("", md)
    md = html.unescape(md)
    lines = [ln.strip() for ln in md.splitlines()]
    # Collapse 3+ consecutive blank lines
    result, blanks = [], 0
    for ln in lines:
        if not ln:
            blanks += 1
            if blanks <= 2:
                result.append("")
        else:
            blanks = 0
            result.append(ln)
    return "\n".join(result).strip()


def action_web_scrape(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    import urllib.request  # noqa: PLC0415

    p         = node.get("properties", {})
    url       = _to_str(inputs.get("url") or p.get("url", "")).strip()
    mode      = str(p.get("mode", "text"))     # "text" | "html" | "markdown"
    max_chars = int(p.get("max_chars", 0) or 0)
    user_agent = str(p.get("user_agent", "Mozilla/5.0 (compatible; AethvionBot/1.0)"))

    if not url:
        return {"out": "", "title": "", "error": "No URL configured"}

    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw_bytes = resp.read()
            # Detect encoding from Content-Type header or fall back to utf-8
            content_type = resp.headers.get("Content-Type", "")
            charset_match = re.search(r"charset=([\w-]+)", content_type)
            encoding = charset_match.group(1) if charset_match else "utf-8"
            html_str = raw_bytes.decode(encoding, errors="replace")
    except Exception as exc:
        return {"out": "", "title": "", "error": str(exc)}

    # Extract page title
    title_match = _TITLE_RE.search(html_str)
    title = html.unescape(_TAG_RE.sub("", title_match.group(1)).strip()) if title_match else ""

    # Convert content according to mode
    if mode == "html":
        out = html_str
    elif mode == "markdown":
        out = _html_to_markdown(html_str)
    else:
        out = _html_to_text(html_str)

    if max_chars and len(out) > max_chars:
        out = out[:max_chars]

    return {"out": out, "title": title, "error": ""}


# Sprint 5: Run Agent

def action_run_agent(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """
    Lightweight autonomous agent node.

    Uses the PM with request_type="agent_call" and a structured system prompt
    built from domain / action / object to keep the executor self-contained
    (no AetherCore instantiation required in the workflow context).
    """
    import uuid as _uuid  # noqa: PLC0415

    p            = node.get("properties", {})
    goal         = _to_str(inputs.get("in", "")).strip()
    model_id     = _to_str(inputs.get("model") or p.get("model", "")).strip()
    domain       = str(p.get("domain",       "Automate")).strip() or "Automate"
    action       = str(p.get("action",       "Execute")).strip()  or "Execute"
    obj          = str(p.get("object",       "Task")).strip()     or "Task"
    instructions = str(p.get("instructions", "")).strip()
    temperature  = float(p.get("temperature", 0.7))
    max_tokens   = int(p.get("max_tokens", 0) or 0) or None

    if not goal:
        return {"out": "", "error": "action.run_agent: No goal/prompt provided"}
    if not model_id:
        return {"out": "", "error": "action.run_agent: No model selected"}

    agent_name = f"{domain}_{action}_{obj}"
    system = (
        f"You are an autonomous AI agent named {agent_name}.\n"
        f"Domain: {domain} | Action: {action} | Object: {obj}\n"
        + (f"Additional instructions: {instructions}\n" if instructions else "")
        + "Work through the task step by step. Be thorough and precise."
    )

    pm   = _get_pm()
    resp = pm.call_with_failover(
        prompt=goal,
        trace_id=f"automate-agent-{_uuid.uuid4().hex[:8]}",
        system_prompt=system,
        temperature=temperature,
        max_tokens=max_tokens,
        model=model_id,
        request_type="agent_call",
        source="automate-execution",
    )

    if not resp.success:
        return {"out": "", "error": resp.error or "Agent call failed"}
    return {"out": resp.content, "agent": agent_name, "error": ""}
