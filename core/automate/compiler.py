"""
core/automate/compiler.py
═════════════════════════
Compile a workflow into a standalone runnable bundle (zip file).

Bundle layout:
  run.py            — embedded executor + node handlers + FastAPI server + web UI
  workflow.json     — the workflow definition
  requirements.txt  — auto-detected pip packages
  .env              — API keys (if include_api_key=True)
  start.bat         — Windows launcher
  start.sh          — Unix launcher
  packages/         — pre-downloaded wheels (if include_packages=True)
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Dependency map ────────────────────────────────────────────────────────────
# node_type → pip packages, required env-var keys, whether AethvionDB reader
# is needed, and whether AI calls are needed in standalone mode.

NODE_DEPS: dict[str, dict] = {
    "trigger.manual":     {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "trigger.schedule":   {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "trigger.webhook":    {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "trigger.file_watch": {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "trigger.app_event":  {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "logic.if":           {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "logic.delay":        {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "logic.loop":         {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "logic.merge":        {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "logic.repeat":       {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "logic.switch":       {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "logic.try_catch":    {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "data.csv_parse":     {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "data.extract_json":  {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "data.filter":        {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "data.format_text":   {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "data.list_item":     {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "data.merge_objects": {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "data.parse_json":    {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "data.regex":         {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "data.set_variable":  {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "data.variable":      {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "data.split_text":    {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "data.template":      {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "data.type_convert":  {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "transform.combine":  {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "action.clipboard":   {"pip": ["pyperclip"],                   "keys": [], "aethviondb": False, "ai": False},
    "action.file_list":   {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "action.file_read":   {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "action.file_write":  {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "action.http":        {"pip": ["httpx"],                       "keys": [], "aethviondb": False, "ai": False},
    "action.log":         {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "action.notify":      {"pip": ["plyer"],                       "keys": [], "aethviondb": False, "ai": False},
    "action.ocr":         {"pip": ["pytesseract", "Pillow"],       "keys": [], "aethviondb": False, "ai": False},
    "action.run_agent":   {"pip": ["google-generativeai"],         "keys": ["GOOGLE_AI_API_KEY"], "aethviondb": False, "ai": True},
    "action.run_command": {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "action.run_script":  {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "action.screenshot":  {"pip": ["mss"],                         "keys": [], "aethviondb": False, "ai": False},
    "action.camera_capture": {"pip": ["opencv-python"],            "keys": [], "aethviondb": False, "ai": False},
    "action.web_scrape":  {"pip": ["httpx", "beautifulsoup4"],     "keys": [], "aethviondb": False, "ai": False},
    "ai.google":          {"pip": ["google-generativeai"],         "keys": ["GOOGLE_AI_API_KEY"], "aethviondb": False, "ai": True},
    "ai.any":             {"pip": ["google-generativeai"],         "keys": ["GOOGLE_AI_API_KEY"], "aethviondb": False, "ai": True},
    "ai.summarize":       {"pip": ["google-generativeai"],         "keys": ["GOOGLE_AI_API_KEY"], "aethviondb": False, "ai": True},
    "ai.classify":        {"pip": ["google-generativeai"],         "keys": ["GOOGLE_AI_API_KEY"], "aethviondb": False, "ai": True},
    "ai.extract_data":    {"pip": ["google-generativeai"],         "keys": ["GOOGLE_AI_API_KEY"], "aethviondb": False, "ai": True},
    "ai.analyze_image":   {"pip": ["google-generativeai"],         "keys": ["GOOGLE_AI_API_KEY"], "aethviondb": False, "ai": True},
    "ai.generate_image":  {"pip": ["google-generativeai"],         "keys": ["GOOGLE_AI_API_KEY"], "aethviondb": False, "ai": True},
    "ai.text_to_speech":  {"pip": ["kokoro-onnx", "soundfile"],   "keys": [], "aethviondb": False, "ai": False},
    "ai.speech_to_text":  {"pip": ["openai-whisper"],             "keys": [], "aethviondb": False, "ai": False},
    "memory.store":           {"pip": [],                          "keys": [], "aethviondb": False, "ai": False},
    "memory.retrieve":        {"pip": [],                          "keys": [], "aethviondb": False, "ai": False},
    "memory.search_semantic": {"pip": [],                          "keys": [], "aethviondb": False, "ai": False},
    "input.text":         {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "input.number":       {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "input.file":         {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "input.list":         {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "output.display":     {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "output.file":        {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "output.clipboard":   {"pip": ["pyperclip"],                   "keys": [], "aethviondb": False, "ai": False},
    "aethviondb.search":          {"pip": [],                      "keys": [], "aethviondb": True,  "ai": False},
    "aethviondb.snapshot_search": {"pip": [],                      "keys": [], "aethviondb": True,  "ai": False},
    "companion.ask":      {"pip": ["google-generativeai"],         "keys": ["GOOGLE_AI_API_KEY"], "aethviondb": False, "ai": True},
    "integration.discord":{"pip": ["httpx"],                       "keys": [], "aethviondb": False, "ai": False},
    "integration.email":  {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "integration.slack":  {"pip": ["httpx"],                       "keys": [], "aethviondb": False, "ai": False},
}

_BASE_REQS = ["fastapi", "uvicorn[standard]", "python-dotenv"]

# ── Handler code blocks ───────────────────────────────────────────────────────
# Each value is a string of Python source included verbatim in run.py.
# Handler signature: (node: dict, inputs: dict, ctx: WorkflowExecutor) -> dict

_HANDLER_CODE: dict[str, str] = {

"trigger.manual": """\
def _h_trigger_manual(node, inputs, ctx):
    return {"trigger": True}
""",

"trigger.schedule": """\
def _h_trigger_schedule(node, inputs, ctx):
    return {"trigger": True, "data": None}
""",

"trigger.webhook": """\
def _h_trigger_webhook(node, inputs, ctx):
    return {"trigger": True, "out": inputs.get("body", {}), "body": inputs.get("body", {})}
""",

"trigger.file_watch": """\
def _h_trigger_file_watch(node, inputs, ctx):
    return {"trigger": True, "path": "", "event": "manual"}
""",

"trigger.app_event": """\
def _h_trigger_app_event(node, inputs, ctx):
    return {"trigger": True, "event_type": "manual", "source": "standalone", "data": None}
""",

"logic.if": """\
def _h_logic_if(node, inputs, ctx):
    p = node.get("properties", {})
    condition = str(p.get("condition", "")).strip()
    in_val = inputs.get("in")
    if not condition:
        result = bool(in_val)
    else:
        try:
            result = bool(_safe_eval(condition, {"value": in_val, "input": in_val}))
        except Exception as exc:
            ctx._warn(f"logic.if condition error: {exc}")
            result = False
    return {"true": in_val if result else None, "false": in_val if not result else None}
""",

"logic.delay": """\
def _h_logic_delay(node, inputs, ctx):
    import time as _time
    ms = float(node.get("properties", {}).get("duration", 1000) or 1000)
    _time.sleep(ms / 1000)
    return {"out": inputs.get("in")}
""",

"logic.loop": """\
def _h_logic_loop(node, inputs, ctx):
    p = node.get("properties", {})
    items = inputs.get("in", [])
    max_iter = int(p.get("max_iterations", 100) or 100)
    if isinstance(items, str):
        try: items = json.loads(items)
        except Exception: items = [items]
    if not isinstance(items, list): items = [items]
    items = items[:max_iter]
    return {"item": items[0] if items else None, "done": len(items) == 0}
""",

"logic.merge": """\
def _h_logic_merge(node, inputs, ctx):
    mode = str(node.get("properties", {}).get("mode", "first"))
    sources = [inputs[k] for k in ("a", "b", "c", "d") if inputs.get(k) is not None]
    if mode == "all":
        return {"out": sources, "source": "all"}
    return {"out": sources[0] if sources else None, "source": "a" if sources else ""}
""",

"logic.repeat": """\
def _h_logic_repeat(node, inputs, ctx):
    count = int(node.get("properties", {}).get("count", 3) or 3)
    val = inputs.get("in")
    return {"out": [val] * count, "count": count}
""",

"logic.switch": """\
def _h_logic_switch(node, inputs, ctx):
    p = node.get("properties", {})
    in_val = inputs.get("in")
    switch_on = str(p.get("switch_on", "")).strip()
    val = str(in_val.get(switch_on, "")) if (switch_on and isinstance(in_val, dict)) else _to_str(in_val)
    out = {"case_1": None, "case_2": None, "case_3": None, "case_4": None, "default": None}
    matched = False
    for i in range(1, 5):
        case_val = str(p.get(f"case_{i}", "")).strip()
        if case_val and val == case_val:
            out[f"case_{i}"] = in_val
            matched = True
            break
    if not matched:
        out["default"] = in_val
    return out
""",

"logic.try_catch": """\
def _h_logic_try_catch(node, inputs, ctx):
    p = node.get("properties", {})
    in_val = inputs.get("in")
    error_in = inputs.get("error_in")
    filter_str = str(p.get("error_contains", "")).strip()
    if error_in is not None:
        if filter_str and filter_str not in str(error_in):
            return {"try": None, "catch": None, "always": error_in}
        return {"try": None, "catch": error_in, "always": error_in}
    return {"try": in_val, "catch": None, "always": in_val}
""",

"data.format_text": """\
def _h_data_format_text(node, inputs, ctx):
    p = node.get("properties", {})
    template = str(p.get("template", "{{input}}"))
    in_val = _to_str(inputs.get("in", ""))
    out = template.replace("{{input}}", in_val).replace("{{value}}", in_val)
    return {"out": out}
""",

"data.template": """\
def _h_data_template(node, inputs, ctx):
    import re as _re
    p = node.get("properties", {})
    template = str(p.get("template", ""))
    in_val = inputs.get("in", {})
    if isinstance(in_val, str):
        try: in_val = json.loads(in_val)
        except Exception: pass
    ctx_vars = {}
    if isinstance(in_val, dict): ctx_vars.update(in_val)
    for port in ("var_a", "var_b", "var_c"):
        if port in inputs: ctx_vars[port] = inputs[port]
    def _replace(m):
        key = m.group(1).strip()
        if "|" in key:
            key, default = key.split("|", 1)
            return _to_str(ctx_vars.get(key.strip(), default.strip()))
        return _to_str(ctx_vars.get(key, ""))
    try:
        return {"out": _re.sub(r"\\{\\{([^}]+)\\}\\}", _replace, template), "error": ""}
    except Exception as exc:
        return {"out": "", "error": str(exc)}
""",

"data.parse_json": """\
def _h_data_parse_json(node, inputs, ctx):
    try:
        return {"out": json.loads(_to_str(inputs.get("in", ""))), "error": ""}
    except Exception as exc:
        return {"out": None, "error": str(exc)}
""",

"data.extract_json": """\
def _h_data_extract_json(node, inputs, ctx):
    import re as _re
    p = node.get("properties", {})
    key = str(p.get("key", "")).strip()
    default = p.get("default", "")
    output_as = str(p.get("output_as", "auto"))
    in_val = inputs.get("in")
    if isinstance(in_val, str):
        try: in_val = json.loads(in_val)
        except Exception: pass
    if not key:
        result = in_val
    else:
        try:
            parts = _re.split(r"[.\\[]", key)
            cur = in_val
            for part in parts:
                part = part.rstrip("]")
                cur = cur[int(part)] if part.isdigit() else cur[part]
            result = cur
        except Exception:
            if default != "": result = default
            else: return {"out": "", "error": f"Key '{key}' not found"}
    if output_as == "string": result = _to_str(result)
    elif output_as == "json": result = json.dumps(result, ensure_ascii=False)
    return {"out": result, "error": ""}
""",

"data.set_variable": """\
def _h_data_set_variable(node, inputs, ctx):
    name = str(node.get("properties", {}).get("name", "myVar")).strip()
    val = inputs.get("in")
    ctx._vars[name] = val
    return {"out": val}
""",

"data.variable": """\
def _h_data_variable(node, inputs, ctx):
    p = node.get("properties", {})
    name = str(p.get("name", "var")).strip() or "var"
    default = p.get("value", "")
    var_type = str(p.get("varType", "string"))
    val = ctx._vars.get(name, default)
    if var_type == "number":
        try:
            s = str(val)
            val = float(s) if "." in s else int(s)
        except (ValueError, TypeError):
            pass
    elif var_type == "boolean":
        if isinstance(val, str):
            val = val.lower() in ("true", "1", "yes")
    ctx._vars[name] = val
    return {"out": val, "value": val}
""",

"data.filter": """\
def _h_data_filter(node, inputs, ctx):
    expr = str(node.get("properties", {}).get("expression", "")).strip()
    items = inputs.get("in", [])
    if isinstance(items, str):
        try: items = json.loads(items)
        except Exception: items = [items]
    if not isinstance(items, list): items = [items]
    match, rest = [], []
    for item in items:
        try:
            ok = bool(_safe_eval(expr, {"item": item, "value": item})) if expr else bool(item)
        except Exception: ok = False
        (match if ok else rest).append(item)
    return {"match": match, "rest": rest}
""",

"data.type_convert": """\
def _h_data_type_convert(node, inputs, ctx):
    p = node.get("properties", {})
    to = str(p.get("to", "string"))
    val = inputs.get("in")
    try:
        if to == "string":  return {"out": _to_str(val), "error": ""}
        if to == "integer": return {"out": int(float(_to_str(val))), "error": ""}
        if to == "float":   return {"out": float(_to_str(val)), "error": ""}
        if to == "json":    return {"out": json.loads(_to_str(val)), "error": ""}
        if to == "boolean":
            tv = [v.strip().lower() for v in str(p.get("true_values",  "true,yes,1,on")).split(",")]
            fv = [v.strip().lower() for v in str(p.get("false_values", "false,no,0,off")).split(",")]
            s = _to_str(val).lower()
            if s in tv: return {"out": True, "error": ""}
            if s in fv: return {"out": False, "error": ""}
            return {"out": bool(val), "error": ""}
        return {"out": val, "error": ""}
    except Exception as exc:
        return {"out": None, "error": str(exc)}
""",

"data.split_text": """\
def _h_data_split_text(node, inputs, ctx):
    p = node.get("properties", {})
    mode = str(p.get("mode", "delimiter"))
    text = _to_str(inputs.get("in", ""))
    delimiter = str(p.get("delimiter", ",")).replace("\\\\n", "\\n").replace("\\\\t", "\\t")
    chunk_size = int(p.get("chunk_size", 500) or 500)
    trim = bool(p.get("trim", True))
    remove_empty = bool(p.get("remove_empty", True))
    if mode == "lines":   parts = text.splitlines()
    elif mode == "words": parts = text.split()
    elif mode == "chunks": parts = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    else: parts = text.split(delimiter)
    if trim: parts = [x.strip() for x in parts]
    if remove_empty: parts = [x for x in parts if x]
    return {"out": parts, "first": parts[0] if parts else "", "last": parts[-1] if parts else "", "count": len(parts)}
""",

"data.regex": """\
def _h_data_regex(node, inputs, ctx):
    import re as _re
    p = node.get("properties", {})
    pattern = _to_str(inputs.get("pattern") or p.get("pattern", ""))
    text = _to_str(inputs.get("in", ""))
    mode = str(p.get("mode", "extract"))
    replacement = str(p.get("replacement", ""))
    flags_str = str(p.get("flags", "")).lower()
    all_matches = bool(p.get("all_matches", False))
    flags = 0
    if "i" in flags_str: flags |= _re.IGNORECASE
    if "m" in flags_str: flags |= _re.MULTILINE
    if "s" in flags_str: flags |= _re.DOTALL
    try:
        if mode == "match":
            m = _re.search(pattern, text, flags)
            return {"out": m.group(0) if m else "", "matches": [], "matched": bool(m), "error": ""}
        if mode == "replace":
            return {"out": _re.sub(pattern, replacement, text, flags=flags), "matches": [], "matched": True, "error": ""}
        if all_matches:
            ms = _re.findall(pattern, text, flags)
            return {"out": ms[0] if ms else "", "matches": ms, "matched": bool(ms), "error": ""}
        m = _re.search(pattern, text, flags)
        if m:
            groups = list(m.groups()) if m.groups() else [m.group(0)]
            return {"out": groups[0], "matches": groups, "matched": True, "error": ""}
        return {"out": "", "matches": [], "matched": False, "error": ""}
    except Exception as exc:
        return {"out": "", "matches": [], "matched": False, "error": str(exc)}
""",

"data.csv_parse": """\
def _h_data_csv_parse(node, inputs, ctx):
    import csv as _csv, io as _io
    p = node.get("properties", {})
    text = _to_str(inputs.get("in", ""))
    delim = str(p.get("delimiter", ","))
    if delim == "\\\\t": delim = "\\t"
    has_header = bool(p.get("has_header", True))
    output_as = str(p.get("output_as", "objects"))
    skip_empty = bool(p.get("skip_empty_rows", True))
    rows = list(_csv.reader(_io.StringIO(text), delimiter=delim))
    if skip_empty: rows = [r for r in rows if any(c.strip() for c in r)]
    if has_header and rows:
        headers = rows[0]; data_rows = rows[1:]
    else:
        headers = []; data_rows = rows
    out = [dict(zip(headers, r)) for r in data_rows] if (output_as == "objects" and has_header) else data_rows
    return {"out": out, "rows": len(data_rows), "headers": headers, "error": ""}
""",

"data.merge_objects": """\
def _h_data_merge_objects(node, inputs, ctx):
    p = node.get("properties", {})
    mode = str(p.get("merge_mode", "shallow"))
    output_as = str(p.get("output_as", "json_string"))
    result = {}
    def _deep(base, overlay):
        for k, v in overlay.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict): _deep(base[k], v)
            else: base[k] = v
    for key in ("a", "b", "c", "d"):
        val = inputs.get(key)
        if val is None: continue
        if isinstance(val, str):
            try: val = json.loads(val)
            except Exception: continue
        if isinstance(val, dict):
            if mode == "deep": _deep(result, val)
            else: result.update(val)
    out = result if output_as == "object" else json.dumps(result, ensure_ascii=False)
    return {"out": out, "error": ""}
""",

"data.list_item": """\
def _h_data_list_item(node, inputs, ctx):
    p = node.get("properties", {})
    idx = int(inputs["index"] if inputs.get("index") is not None else p.get("index", 0))
    slice_end = int(p.get("slice_end", 0) or 0)
    items = inputs.get("in", [])
    if isinstance(items, str):
        try: items = json.loads(items)
        except Exception: items = [items]
    if not isinstance(items, list): items = [items]
    count = len(items)
    if slice_end > 0: return {"out": items[idx:slice_end], "count": count, "error": ""}
    if -count <= idx < count: return {"out": items[idx], "count": count, "error": ""}
    return {"out": None, "count": count, "error": f"Index {idx} out of range ({count} items)"}
""",

"transform.combine": """\
def _h_transform_combine(node, inputs, ctx):
    sep = str(node.get("properties", {}).get("separator", "\\\\n")).replace("\\\\n", "\\n").replace("\\\\t", "\\t")
    parts = [x for x in [_to_str(inputs.get("a", "")), _to_str(inputs.get("b", ""))] if x]
    return {"out": sep.join(parts)}
""",

"action.log": """\
def _h_action_log(node, inputs, ctx):
    p = node.get("properties", {})
    msg = str(p.get("message", "{{input}}")).replace("{{input}}", _to_str(inputs.get("in", "")))
    level = str(p.get("level", "info")).lower()
    if level == "error": ctx._error(f"[Log] {msg}")
    elif level == "warning": ctx._warn(f"[Log] {msg}")
    else: ctx._info(f"[Log] {msg}")
    return {"out": inputs.get("in")}
""",

"action.run_script": """\
def _h_action_run_script(node, inputs, ctx):
    script = str(node.get("properties", {}).get("script", ""))
    ns = {"input_data": inputs.get("in"), "inputs": inputs, "ctx": ctx, "json": json, "result": None}
    try:
        exec(script, ns)
        return {"out": ns.get("result", inputs.get("in")), "error": ""}
    except Exception as exc:
        return {"out": None, "error": str(exc)}
""",

"action.run_command": """\
def _h_action_run_command(node, inputs, ctx):
    import subprocess as _sp
    p = node.get("properties", {})
    cmd = _to_str(inputs.get("cmd") or p.get("command", "")).strip()
    working_dir = str(p.get("working_dir", "")).strip() or None
    shell = bool(p.get("shell", False))
    timeout = int(p.get("timeout", 30) or 30)
    if not cmd: return {"out": "", "stderr": "", "exit_code": -1, "error": "No command"}
    try:
        res = _sp.run(cmd if shell else cmd.split(), shell=shell, capture_output=True, text=True,
                      cwd=working_dir, timeout=timeout)
        return {"out": res.stdout, "stderr": res.stderr, "exit_code": res.returncode, "error": ""}
    except Exception as exc:
        return {"out": "", "stderr": "", "exit_code": -1, "error": str(exc)}
""",

"action.file_read": """\
def _h_action_file_read(node, inputs, ctx):
    p = node.get("properties", {})
    path = _to_str(inputs.get("path") or p.get("path", "")).strip()
    encoding = str(p.get("encoding", "utf-8"))
    strip = bool(p.get("strip", False))
    max_bytes = int(p.get("max_bytes", 0) or 0)
    if not path: return {"out": "", "path": "", "size": 0, "error": "No path"}
    try:
        import os.path as _op
        path = _op.expandvars(_op.expanduser(path))
        if encoding == "binary":
            data = open(path, "rb").read()
            if max_bytes: data = data[:max_bytes]
            return {"out": data.hex(), "path": path, "size": len(data), "error": ""}
        content = open(path, encoding=encoding).read()
        if max_bytes: content = content[:max_bytes]
        if strip: content = content.strip()
        return {"out": content, "path": path, "size": len(content), "error": ""}
    except Exception as exc:
        return {"out": "", "path": path, "size": 0, "error": str(exc)}
""",

"action.file_write": """\
def _h_action_file_write(node, inputs, ctx):
    p = node.get("properties", {})
    path = _to_str(inputs.get("path") or p.get("path", "")).strip()
    mode = str(p.get("mode", "overwrite"))
    encoding = str(p.get("encoding", "utf-8"))
    newline = bool(p.get("newline", True))
    create_dirs = bool(p.get("create_dirs", True))
    content = _to_str(inputs.get("in", ""))
    if not path: return {"out": content, "path": "", "error": "No path"}
    try:
        import os.path as _op
        path = _op.expandvars(_op.expanduser(path))
        if create_dirs: os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        file_mode = "a" if mode == "append" else "w"
        if mode == "prepend":
            try: existing = open(path, encoding=encoding).read()
            except Exception: existing = ""
            content = content + ("\\n" if newline else "") + existing
            file_mode = "w"
        with open(path, file_mode, encoding=encoding) as f:
            f.write(content)
            if newline and not content.endswith("\\n"): f.write("\\n")
        return {"out": content, "path": path, "error": ""}
    except Exception as exc:
        return {"out": content, "path": path, "error": str(exc)}
""",

"action.file_list": """\
def _h_action_file_list(node, inputs, ctx):
    from pathlib import Path as _P
    p = node.get("properties", {})
    path = _to_str(inputs.get("path") or p.get("path", "")).strip()
    pattern = str(p.get("pattern", "*"))
    recursive = bool(p.get("recursive", False))
    include_dirs = bool(p.get("include_dirs", False))
    sort_by = str(p.get("sort_by", "name"))
    output_as = str(p.get("output_as", "paths"))
    if not path: return {"out": [], "count": 0, "error": "No path"}
    try:
        base = _P(path)
        files = list(base.rglob(pattern) if recursive else base.glob(pattern))
        if not include_dirs: files = [f for f in files if f.is_file()]
        if sort_by == "size": files.sort(key=lambda f: f.stat().st_size)
        elif sort_by == "modified": files.sort(key=lambda f: f.stat().st_mtime)
        else: files.sort(key=lambda f: f.name)
        if output_as == "objects":
            out = [{"path": str(f), "name": f.name, "size": f.stat().st_size if f.is_file() else 0} for f in files]
        else:
            out = [str(f) for f in files]
        return {"out": out, "count": len(out), "error": ""}
    except Exception as exc:
        return {"out": [], "count": 0, "error": str(exc)}
""",

"action.notify": """\
def _h_action_notify(node, inputs, ctx):
    p = node.get("properties", {})
    title = _to_str(inputs.get("title") or p.get("title", "Workflow"))
    msg = _to_str(inputs.get("message") or p.get("message", ""))
    msg = msg.replace("{{input}}", _to_str(inputs.get("in", "")))
    try:
        from plyer import notification
        notification.notify(title=title, message=msg, timeout=5)
    except Exception as exc:
        ctx._warn(f"[Notify] {exc}")
    return {"out": inputs.get("in"), "error": ""}
""",

"action.http": """\
def _h_action_http(node, inputs, ctx):
    try: import httpx as _httpx
    except ImportError: raise RuntimeError("httpx not installed — run: pip install -r requirements.txt")
    p = node.get("properties", {})
    url = _to_str(inputs.get("in") or p.get("url", "")).strip()
    method = str(p.get("method", "GET")).upper()
    try: headers = json.loads(str(p.get("headers", "{}") or "{}"))
    except Exception: headers = {}
    body = str(p.get("body", "") or "")
    if not url: return {"out": "", "error": "No URL"}
    try:
        r = _httpx.request(method, url, headers=headers, content=body.encode() if body else None, timeout=30)
        return {"out": r.text, "error": ""}
    except Exception as exc:
        return {"out": "", "error": str(exc)}
""",

"action.web_scrape": """\
def _h_action_web_scrape(node, inputs, ctx):
    try: import httpx as _httpx
    except ImportError: raise RuntimeError("httpx not installed — run: pip install -r requirements.txt")
    p = node.get("properties", {})
    url = _to_str(inputs.get("url") or p.get("url", "")).strip()
    mode = str(p.get("mode", "text"))
    max_chars = int(p.get("max_chars", 0) or 0)
    ua = str(p.get("user_agent", "Mozilla/5.0 (compatible; AethvionBot/1.0)"))
    if not url: return {"out": "", "title": "", "error": "No URL"}
    try:
        r = _httpx.get(url, headers={"User-Agent": ua}, follow_redirects=True, timeout=30)
        if mode == "html":
            content, title = r.text, ""
        else:
            try:
                from bs4 import BeautifulSoup as _BS
                soup = _BS(r.text, "html.parser")
                title = soup.title.string.strip() if soup.title else ""
                if mode == "markdown":
                    content = "\\n".join(t.get_text() for t in soup.find_all(["p","h1","h2","h3","li"]))
                else:
                    content = soup.get_text(separator="\\n")
            except ImportError:
                import re as _re2
                content = _re2.sub(r"<[^>]+>", "", r.text)
                title = ""
        if max_chars: content = content[:max_chars]
        return {"out": content, "title": title, "error": ""}
    except Exception as exc:
        return {"out": "", "title": "", "error": str(exc)}
""",

"action.clipboard": """\
def _h_action_clipboard(node, inputs, ctx):
    try: import pyperclip as _clip
    except ImportError: raise RuntimeError("pyperclip not installed")
    mode = str(node.get("properties", {}).get("mode", "write"))
    if mode in ("read", "read_then_clear"):
        content = _clip.paste()
        if mode == "read_then_clear": _clip.copy("")
        return {"out": content, "error": ""}
    text = _to_str(inputs.get("in", ""))
    _clip.copy(text)
    return {"out": text, "error": ""}
""",

"action.screenshot": """\
def _h_action_screenshot(node, inputs, ctx):
    try: import mss as _mss, mss.tools as _mss_tools
    except ImportError: raise RuntimeError("mss not installed — run: pip install -r requirements.txt")
    p = node.get("properties", {})
    path = _to_str(inputs.get("path") or p.get("path", "")).strip()
    monitor_idx = int(p.get("monitor", 0) or 0)
    import tempfile as _tf, os as _os
    if not path:
        path = _os.path.join(_tf.gettempdir(), f"screenshot_{_ts().replace(':','').replace('.','')}.png")
    try:
        with _mss.mss() as sct:
            mon = sct.monitors[monitor_idx] if monitor_idx < len(sct.monitors) else sct.monitors[0]
            img = sct.grab(mon)
            _mss_tools.to_png(img.rgb, img.size, output=path)
        return {"out": path, "image": path, "width": img.width, "height": img.height, "error": ""}
    except Exception as exc:
        return {"out": "", "image": "", "width": 0, "height": 0, "error": str(exc)}
""",

"action.camera_capture": """\
def _h_action_camera_capture(node, inputs, ctx):
    try: import cv2 as _cv2
    except ImportError: raise RuntimeError("opencv-python not installed — run: pip install -r requirements.txt")
    p = node.get("properties", {})
    path = _to_str(inputs.get("path") or p.get("path", "")).strip()
    cam_idx = int(p.get("camera_index", 0) or 0)
    w = int(p.get("width", 1280) or 1280)
    h = int(p.get("height", 720) or 720)
    import tempfile as _tf, os as _os
    if not path:
        path = _os.path.join(_tf.gettempdir(), f"capture_{_ts().replace(':','').replace('.','')}.jpg")
    cap = _cv2.VideoCapture(cam_idx)
    try:
        cap.set(_cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(_cv2.CAP_PROP_FRAME_HEIGHT, h)
        ok, frame = cap.read()
        if not ok: return {"out": "", "image": "", "width": 0, "height": 0, "error": "Could not read camera"}
        _cv2.imwrite(path, frame)
        return {"out": path, "image": path, "width": frame.shape[1], "height": frame.shape[0], "error": ""}
    except Exception as exc:
        return {"out": "", "image": "", "width": 0, "height": 0, "error": str(exc)}
    finally:
        cap.release()
""",

"action.ocr": """\
def _h_action_ocr(node, inputs, ctx):
    try: import pytesseract as _tess; from PIL import Image as _Image
    except ImportError: raise RuntimeError("pytesseract/Pillow not installed — run: pip install -r requirements.txt")
    p = node.get("properties", {})
    image_path = _to_str(inputs.get("image") or p.get("image_path", "")).strip()
    lang = str(p.get("language", "eng"))
    config = str(p.get("config", "")).strip()
    if not image_path: return {"out": "", "error": "No image path"}
    try:
        img = _Image.open(image_path)
        text = _tess.image_to_string(img, lang=lang, config=config)
        return {"out": text.strip(), "error": ""}
    except Exception as exc:
        return {"out": "", "error": str(exc)}
""",

"action.run_agent": """\
def _h_action_run_agent(node, inputs, ctx):
    p = node.get("properties", {})
    model_id = _to_str(inputs.get("model") or p.get("model", "")).strip() or "gemini-2.0-flash"
    domain = str(p.get("domain", "Automate"))
    action = str(p.get("action", "Execute"))
    obj = str(p.get("object", "Task"))
    instructions = str(p.get("instructions", "")).strip()
    temp = float(p.get("temperature", 0.7) or 0.7)
    goal = _to_str(inputs.get("in", ""))
    system = f"You are an AI agent specialising in {domain}. Your task is to {action} the {obj}."
    if instructions: system += f"\\nAdditional instructions: {instructions}"
    try:
        out = _ai_call(model_id, system, goal, temp)
        return {"out": out, "agent": model_id, "error": ""}
    except Exception as exc:
        return {"out": "", "agent": "", "error": str(exc)}
""",

# ── AI handlers ───────────────────────────────────────────────────────────────

"ai.google": """\
def _h_ai_google(node, inputs, ctx):
    return _h_ai_model(node, inputs, ctx)
""",

"ai.any": """\
def _h_ai_any(node, inputs, ctx):
    return _h_ai_model(node, inputs, ctx)
""",

"ai.summarize": """\
def _h_ai_summarize(node, inputs, ctx):
    p = node.get("properties", {})
    model_id = _to_str(inputs.get("model") or p.get("model", "")).strip()
    if not model_id: raise ValueError("ai.summarize: No model selected")
    text = _to_str(inputs.get("in", ""))
    style = str(p.get("style", "paragraph"))
    length = _to_str(inputs.get("length") or p.get("length", "medium"))
    language = str(p.get("language", "")).strip()
    sm = {"paragraph": "Write a clear summary in flowing prose.", "bullets": "Write a bullet-point list.",
          "headline": "Write a one-sentence headline followed by 2 sentences.", "tldr": "Write a single TL;DR sentence."}
    lm = {"short": "Keep to 1-2 sentences.", "medium": "About one paragraph.",
          "long": "Multiple paragraphs covering all key points."}
    lang = f" Write in {language}." if language else ""
    system = f"You are a professional text summarizer.{lang} {sm.get(style,'')} {lm.get(length,'')}"
    try:
        return {"out": _ai_call(model_id, system, text, 0.3), "error": ""}
    except Exception as exc:
        return {"out": "", "error": str(exc)}
""",

"ai.classify": """\
def _h_ai_classify(node, inputs, ctx):
    p = node.get("properties", {})
    model_id = _to_str(inputs.get("model") or p.get("model", "")).strip()
    if not model_id: raise ValueError("ai.classify: No model selected")
    text = _to_str(inputs.get("in", ""))
    labels = [lb.strip() for lb in _to_str(inputs.get("labels") or p.get("labels", "")).split(",") if lb.strip()]
    context = str(p.get("context", "")).strip()
    if not labels: return {"label": "", "reasoning": "", "all": "{}", "error": "No categories configured"}
    system = (f"Classify the text into exactly one of: {', '.join(labels)}."
              + (f"\\nContext: {context}" if context else "")
              + '\\nRespond ONLY with JSON: {"label": "...", "reasoning": "..."}')
    try:
        resp = _ai_call(model_id, system, text, 0.1)
        parsed = _extract_json_block(resp)
        label = str(parsed.get("label", "")).strip()
        reasoning = str(parsed.get("reasoning", "")).strip()
        if label not in labels:
            lower_map = {lb.lower(): lb for lb in labels}
            label = lower_map.get(label.lower(), label or "unknown")
        return {"label": label, "reasoning": reasoning,
                "all": json.dumps({"label": label, "reasoning": reasoning}), "error": ""}
    except Exception as exc:
        return {"label": "", "reasoning": "", "all": "{}", "error": str(exc)}
""",

"ai.extract_data": """\
def _h_ai_extract_data(node, inputs, ctx):
    p = node.get("properties", {})
    model_id = _to_str(inputs.get("model") or p.get("model", "")).strip()
    if not model_id: raise ValueError("ai.extract_data: No model selected")
    text = _to_str(inputs.get("in", ""))
    fields_raw = _to_str(inputs.get("schema") or p.get("fields", ""))
    context = str(p.get("context", "")).strip()
    missing = str(p.get("missing_value", ""))
    field_defs = {}
    for line in fields_raw.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            if k.strip(): field_defs[k.strip()] = v.strip()
    if not field_defs: return {"out": "{}", "error": "No fields configured"}
    schema_desc = "\\n".join(f'- "{k}": {v}' for k, v in field_defs.items())
    system = (f"Extract fields from text as JSON.{f' Context: {context}' if context else ''}"
              f"\\nFields:\\n{schema_desc}"
              f"\\nMissing fields use {repr(missing)}. Return ONLY the JSON object.")
    try:
        resp = _ai_call(model_id, system, text, 0.1)
        parsed = _extract_json_block(resp)
        if not parsed: return {"out": resp, "error": "Could not parse JSON from AI response"}
        for k in field_defs:
            if k not in parsed: parsed[k] = missing
        return {"out": json.dumps(parsed, ensure_ascii=False), "error": ""}
    except Exception as exc:
        return {"out": "{}", "error": str(exc)}
""",

"ai.analyze_image": """\
def _h_ai_analyze_image(node, inputs, ctx):
    p = node.get("properties", {})
    model_id = _to_str(inputs.get("model") or p.get("model", "")).strip() or "gemini-1.5-flash"
    image_path = _to_str(inputs.get("image") or p.get("image_path", "")).strip()
    question = str(p.get("question", "Describe this image in detail."))
    system = str(p.get("system_prompt", "You are a helpful vision assistant."))
    temp = float(p.get("temperature", 0.3) or 0.3)
    prompt = _to_str(inputs.get("in", question))
    if not image_path: return {"out": "", "error": "No image path provided"}
    try:
        import google.generativeai as _genai
        from PIL import Image as _PIL_Image
        api_key = os.environ.get("GOOGLE_AI_API_KEY", "")
        if not api_key: raise RuntimeError("GOOGLE_AI_API_KEY not set")
        _genai.configure(api_key=api_key)
        model = _genai.GenerativeModel(model_name=model_id, system_instruction=system or None)
        img = _PIL_Image.open(image_path)
        resp = model.generate_content([prompt, img], generation_config=_genai.GenerationConfig(temperature=temp))
        return {"out": resp.text, "error": ""}
    except Exception as exc:
        return {"out": "", "error": str(exc)}
""",

"ai.generate_image": """\
def _h_ai_generate_image(node, inputs, ctx):
    p = node.get("properties", {})
    model_id = str(p.get("model", "imagen-3.0-generate-002"))
    aspect_ratio = str(p.get("aspect_ratio", "1:1"))
    path = _to_str(inputs.get("path") or p.get("path", "")).strip()
    prompt = _to_str(inputs.get("in", ""))
    if not path:
        import tempfile as _tf, os as _os
        path = _os.path.join(_tf.gettempdir(), f"imagen_{_ts().replace(':','').replace('.','')}.png")
    try:
        import google.generativeai as _genai
        api_key = os.environ.get("GOOGLE_AI_API_KEY", "")
        if not api_key: raise RuntimeError("GOOGLE_AI_API_KEY not set")
        _genai.configure(api_key=api_key)
        from google.generativeai import types as _gtypes
        model = _genai.ImageGenerationModel(model_id)
        resp = model.generate_images(prompt=prompt, number_of_images=1, aspect_ratio=aspect_ratio)
        resp.images[0].save(path)
        return {"out": path, "path": path, "count": 1, "error": ""}
    except Exception as exc:
        return {"out": "", "path": "", "count": 0, "error": str(exc)}
""",

"ai.text_to_speech": """\
def _h_ai_text_to_speech(node, inputs, ctx):
    return {"out": "", "path": "", "duration_ms": 0, "error": "TTS requires the full Aethvion Suite environment"}
""",

"ai.speech_to_text": """\
def _h_ai_speech_to_text(node, inputs, ctx):
    try: import whisper as _whisper
    except ImportError: raise RuntimeError("openai-whisper not installed")
    p = node.get("properties", {})
    path = _to_str(inputs.get("path") or p.get("path", "")).strip()
    model_id = str(p.get("model_id", "whisper") or "base")
    if model_id == "whisper": model_id = "base"
    lang = str(p.get("language", "")).strip() or None
    if not path: return {"out": "", "language": "", "error": "No audio path"}
    try:
        model = _whisper.load_model(model_id)
        result = model.transcribe(path, language=lang)
        return {"out": result.get("text", ""), "language": result.get("language", ""), "error": ""}
    except Exception as exc:
        return {"out": "", "language": "", "error": str(exc)}
""",

# ── Memory ────────────────────────────────────────────────────────────────────

"memory.store": """\
def _h_memory_store(node, inputs, ctx):
    p = node.get("properties", {})
    key = _to_str(inputs.get("key") or p.get("key", "")).strip()
    if not key: return {"out": inputs.get("in"), "error": "No key specified"}
    _MEMORY_STORE[key] = inputs.get("in")
    return {"out": inputs.get("in"), "error": ""}
""",

"memory.retrieve": """\
def _h_memory_retrieve(node, inputs, ctx):
    p = node.get("properties", {})
    key = str(p.get("key", "")).strip()
    default = p.get("default", "")
    if not key: return {"out": default, "found": False, "error": "No key specified"}
    found = key in _MEMORY_STORE
    return {"out": _MEMORY_STORE.get(key, default), "found": found, "error": ""}
""",

"memory.search_semantic": """\
def _h_memory_search_semantic(node, inputs, ctx):
    p = node.get("properties", {})
    query = _to_str(inputs.get("in", "")).lower()
    limit = int(p.get("limit", 5) or 5)
    min_score = float(p.get("min_score", 0.0) or 0.0)
    results = []
    for k, v in _MEMORY_STORE.items():
        score = 1.0 if query in k.lower() else (0.3 if any(w in k.lower() for w in query.split()) else 0.0)
        if score >= min_score: results.append({"key": k, "value": v, "_score": score})
    results.sort(key=lambda x: x["_score"], reverse=True)
    out = results[:limit]
    return {"out": json.dumps(out, ensure_ascii=False), "count": len(out), "error": ""}
""",

# ── Inputs ────────────────────────────────────────────────────────────────────

"input.text": """\
def _h_input_text(node, inputs, ctx):
    nid = node.get("id", "")
    val = _INPUT_OVERRIDES.get(nid, node.get("properties", {}).get("value", ""))
    return {"out": str(val)}
""",

"input.number": """\
def _h_input_number(node, inputs, ctx):
    nid = node.get("id", "")
    raw = _INPUT_OVERRIDES.get(nid, node.get("properties", {}).get("value", 0))
    try: return {"out": float(raw)}
    except Exception: return {"out": 0}
""",

"input.list": """\
def _h_input_list(node, inputs, ctx):
    nid = node.get("id", "")
    p = node.get("properties", {})
    raw = _INPUT_OVERRIDES.get(nid, p.get("items", ""))
    trim = bool(p.get("trim", True))
    remove_empty = bool(p.get("remove_empty", True))
    lines = str(raw).splitlines()
    if trim: lines = [ln.strip() for ln in lines]
    if remove_empty: lines = [ln for ln in lines if ln]
    return {"out": lines, "count": len(lines), "first": lines[0] if lines else ""}
""",

"input.file": """\
def _h_input_file(node, inputs, ctx):
    p = node.get("properties", {})
    path = str(p.get("path", "")).strip()
    encoding = str(p.get("encoding", "utf-8"))
    strip = bool(p.get("strip", False))
    if not path: return {"out": "", "path": "", "name": "", "size": 0}
    try:
        import os.path as _op
        path = _op.expandvars(_op.expanduser(path))
        if encoding == "binary":
            data = open(path, "rb").read()
            return {"out": data.hex(), "path": path, "name": _op.basename(path), "size": len(data)}
        content = open(path, encoding=encoding).read()
        if strip: content = content.strip()
        return {"out": content, "path": path, "name": _op.basename(path), "size": len(content)}
    except Exception as exc:
        return {"out": "", "path": path, "name": "", "size": 0, "error": str(exc)}
""",

# ── Outputs ───────────────────────────────────────────────────────────────────

"output.display": """\
def _h_output_display(node, inputs, ctx):
    p = node.get("properties", {})
    label = str(p.get("label", "Result"))
    val = inputs.get("in")
    _OUTPUT_RESULTS.append({"label": label, "value": _to_str(val) if not isinstance(val, str) else val})
    return {}
""",

"output.file": """\
def _h_output_file(node, inputs, ctx):
    import re as _re
    p = node.get("properties", {})
    path = str(p.get("path", "")).strip()
    mode = str(p.get("mode", "overwrite"))
    encoding = str(p.get("encoding", "utf-8"))
    fmt = str(p.get("format", "auto"))
    create_dirs = bool(p.get("create_dirs", True))
    val = inputs.get("in")
    if not path: return {}
    content = val if isinstance(val, str) else json.dumps(val, indent=2, ensure_ascii=False)
    if fmt == "json_pretty" and not isinstance(val, str):
        content = json.dumps(val, indent=2, ensure_ascii=False)
    elif fmt == "lines" and isinstance(val, list):
        content = "\\n".join(_to_str(v) for v in val)
    try:
        path = _re.sub(r"\\{\\{timestamp\\}\\}", datetime.now().strftime("%Y%m%d_%H%M%S"), path)
        if create_dirs: os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a" if mode == "append" else "w", encoding=encoding) as f: f.write(content)
    except Exception as exc:
        ctx._error(f"[Output.File] {exc}")
    return {}
""",

"output.clipboard": """\
def _h_output_clipboard(node, inputs, ctx):
    try: import pyperclip as _clip
    except ImportError: ctx._warn("[Clipboard] pyperclip not installed"); return {}
    p = node.get("properties", {})
    fmt = str(p.get("format", "auto"))
    val = inputs.get("in")
    text = json.dumps(val, indent=2, ensure_ascii=False) if (fmt == "json_pretty" and not isinstance(val, str)) else (_to_str(val).strip() if fmt == "trim" else _to_str(val))
    try:
        _clip.copy(text)
        if bool(p.get("notify", True)): ctx._info("[Clipboard] Copied to clipboard")
    except Exception as exc:
        ctx._warn(f"[Clipboard] {exc}")
    return {}
""",

# ── Integrations ──────────────────────────────────────────────────────────────

"integration.discord": """\
def _h_integration_discord(node, inputs, ctx):
    try: import httpx as _httpx
    except ImportError: raise RuntimeError("httpx not installed")
    p = node.get("properties", {})
    webhook_url = _to_str(inputs.get("webhook") or p.get("webhook_url", "")).strip()
    if not webhook_url: return {"out": inputs.get("in"), "error": "No webhook URL"}
    msg = _to_str(inputs.get("in", ""))
    title = _to_str(inputs.get("title") or p.get("title", "")).strip()
    username = str(p.get("username", "Aethvion"))
    payload = {"username": username}
    if title:
        payload["embeds"] = [{"title": title, "description": msg, "color": int(p.get("colour", 5793266))}]
    else:
        payload["content"] = msg
    try:
        r = _httpx.post(webhook_url, json=payload, timeout=15)
        r.raise_for_status()
        return {"out": inputs.get("in"), "error": ""}
    except Exception as exc:
        return {"out": inputs.get("in"), "error": str(exc)}
""",

"integration.slack": """\
def _h_integration_slack(node, inputs, ctx):
    try: import httpx as _httpx
    except ImportError: raise RuntimeError("httpx not installed")
    p = node.get("properties", {})
    webhook_url = _to_str(inputs.get("webhook") or p.get("webhook_url", "")).strip()
    if not webhook_url: return {"out": inputs.get("in"), "error": "No webhook URL"}
    msg = _to_str(inputs.get("in", ""))
    title = _to_str(inputs.get("title") or p.get("title", "")).strip()
    blocks = []
    if title: blocks.append({"type": "header", "text": {"type": "plain_text", "text": title}})
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": msg}})
    try:
        r = _httpx.post(webhook_url, json={"icon_emoji": str(p.get("icon_emoji",":robot_face:")), "blocks": blocks}, timeout=15)
        r.raise_for_status()
        return {"out": inputs.get("in"), "error": ""}
    except Exception as exc:
        return {"out": inputs.get("in"), "error": str(exc)}
""",

"integration.email": """\
def _h_integration_email(node, inputs, ctx):
    import smtplib
    from email.mime.text import MIMEText
    p = node.get("properties", {})
    to = _to_str(inputs.get("to") or p.get("to", "")).strip()
    subject = _to_str(inputs.get("subject") or p.get("subject", "Workflow Notification"))
    body = _to_str(inputs.get("in", ""))
    smtp_host = str(p.get("smtp_host", "")).strip()
    smtp_port = int(p.get("smtp_port", 587) or 587)
    smtp_user = str(p.get("smtp_user", "")).strip()
    smtp_pass = str(p.get("smtp_pass", "")).strip()
    if not all([to, smtp_host, smtp_user]): return {"out": body, "error": "Email not configured"}
    try:
        msg = MIMEText(body, "html" if str(p.get("format","plain"))=="html" else "plain")
        msg["Subject"] = subject; msg["From"] = smtp_user; msg["To"] = to
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls(); server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [to], msg.as_string())
        return {"out": body, "error": ""}
    except Exception as exc:
        return {"out": body, "error": str(exc)}
""",

"companion.ask": """\
def _h_companion_ask(node, inputs, ctx):
    p = node.get("properties", {})
    model_id = _to_str(inputs.get("model") or p.get("model", "")).strip() or "gemini-2.0-flash"
    system = _to_str(inputs.get("system") or p.get("system_prompt", "You are a helpful assistant."))
    prompt = _to_str(inputs.get("in", ""))
    temp = float(p.get("temperature", 0.7) or 0.7)
    try:
        return {"out": _ai_call(model_id, system, prompt, temp), "error": ""}
    except Exception as exc:
        return {"out": "", "error": str(exc)}
""",

# ── AethvionDB standalone ─────────────────────────────────────────────────────
# These two share the same scoring logic but are registered separately.

"aethviondb.search": """\
def _h_aethviondb_search(node, inputs, ctx):
    import time as _time
    p = node.get("properties", {})
    query = _to_str(inputs.get("in", "")).strip()
    db_name = str(p.get("database", "default")).strip() or "default"
    entity_type = str(p.get("entity_type", "")).strip()
    limit = max(1, int(p.get("limit", 10) or 10))
    min_score = float(p.get("min_score", 0.0) or 0.0)
    if not query: return {"out": "[]", "count": 0, "speed": "0ms", "error": "No query"}
    data_dir = Path(__file__).parent / "data" / "aethviondb" / db_name / "entities"
    if not data_dir.exists():
        return {"out": "[]", "count": 0, "speed": "0ms", "error": f"Database '{db_name}' not found in bundle"}
    t0 = _time.perf_counter()
    entities = []
    for fp in data_dir.glob("*.json"):
        try: entities.append(json.loads(fp.read_text(encoding="utf-8")))
        except Exception: pass
    if entity_type: entities = [e for e in entities if e.get("type") == entity_type]
    def _score(e):
        if not query: return 1.0
        q = query.lower()
        core = e.get("sections", {}).get("core", {})
        name = e.get("name","").lower(); summary = core.get("summary","").lower()
        aliases = " ".join(core.get("aliases",[])).lower(); tags = " ".join(core.get("tags",[])).lower()
        if name == q: return 1.0
        if q in name: return 0.90
        if q in summary[:400]: return 0.70
        if q in aliases: return 0.65
        if q in tags: return 0.60
        words = q.split()
        if len(words) > 1:
            hay = f"{name} {summary[:600]} {aliases} {tags}"
            matched = sum(1 for w in words if w in hay)
            if matched: return round(0.5 * matched / len(words), 3)
        return 0.0
    scored = [(e, _score(e)) for e in entities]
    scored = [(e, s) for e, s in scored if s >= min_score]
    scored.sort(key=lambda x: x[1], reverse=True)
    results = []
    for e, s in scored[:limit]:
        core = e.get("sections", {}).get("core", {})
        results.append({"id": e.get("id",""), "name": e.get("name",""), "type": e.get("type",""),
                         "summary": core.get("summary",""), "tags": core.get("tags",[]), "_score": round(s,3)})
    elapsed = round((_time.perf_counter() - t0) * 1000, 2)
    return {"out": json.dumps(results, ensure_ascii=False), "count": len(results), "speed": f"{elapsed}ms", "error": ""}
""",

"aethviondb.snapshot_search": """\
def _h_aethviondb_snapshot_search(node, inputs, ctx):
    import time as _time
    p = node.get("properties", {})
    query = _to_str(inputs.get("in", "")).strip()
    db_name = str(p.get("database", "default")).strip() or "default"
    snap_name = str(p.get("snapshot", "")).strip()
    entity_type = str(p.get("entity_type", "")).strip()
    limit = max(1, int(p.get("limit", 10) or 10))
    min_score = float(p.get("min_score", 0.0) or 0.0)
    if not query: return {"out": "[]", "count": 0, "speed": "0ms", "error": "No query"}
    baked_dir = Path(__file__).parent / "data" / "aethviondb" / db_name / "baked"
    if not baked_dir.exists():
        return {"out": "[]", "count": 0, "speed": "0ms", "error": f"No snapshots for '{db_name}' in bundle"}
    snap_files = sorted(baked_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    if snap_name:
        snap_files = [f for f in snap_files if f.stem == snap_name] or snap_files
    if not snap_files:
        return {"out": "[]", "count": 0, "speed": "0ms", "error": "No snapshot found"}
    t0 = _time.perf_counter()
    entities = []
    for line in snap_files[0].read_text(encoding="utf-8").splitlines():
        if line.strip():
            try: entities.append(json.loads(line))
            except Exception: pass
    if entity_type: entities = [e for e in entities if e.get("type") == entity_type]
    def _score(e):
        if not query: return 1.0
        q = query.lower()
        name = e.get("name","").lower(); summary = e.get("summary","").lower()
        tags = " ".join(e.get("tags",[])).lower(); aliases = " ".join(e.get("aliases",[])).lower()
        if name == q: return 1.0
        if q in name: return 0.90
        if q in summary[:400]: return 0.70
        if q in aliases: return 0.65
        if q in tags: return 0.60
        words = q.split()
        if len(words) > 1:
            hay = f"{name} {summary[:600]} {aliases} {tags}"
            matched = sum(1 for w in words if w in hay)
            if matched: return round(0.5 * matched / len(words), 3)
        return 0.0
    scored = [(e, _score(e)) for e in entities]
    scored = [(e, s) for e, s in scored if s >= min_score]
    scored.sort(key=lambda x: x[1], reverse=True)
    results = [{**e, "_score": round(s,3)} for e, s in scored[:limit]]
    elapsed = round((_time.perf_counter() - t0) * 1000, 2)
    return {"out": json.dumps(results, ensure_ascii=False), "count": len(results), "speed": f"{elapsed}ms", "error": ""}
""",

}  # end _HANDLER_CODE

# Map node_type → handler function name (used to build the registry)
_HANDLER_NAMES: dict[str, str] = {
    "trigger.manual":             "_h_trigger_manual",
    "trigger.schedule":           "_h_trigger_schedule",
    "trigger.webhook":            "_h_trigger_webhook",
    "trigger.file_watch":         "_h_trigger_file_watch",
    "trigger.app_event":          "_h_trigger_app_event",
    "logic.if":                   "_h_logic_if",
    "logic.delay":                "_h_logic_delay",
    "logic.loop":                 "_h_logic_loop",
    "logic.merge":                "_h_logic_merge",
    "logic.repeat":               "_h_logic_repeat",
    "logic.switch":               "_h_logic_switch",
    "logic.try_catch":            "_h_logic_try_catch",
    "data.csv_parse":             "_h_data_csv_parse",
    "data.extract_json":          "_h_data_extract_json",
    "data.filter":                "_h_data_filter",
    "data.format_text":           "_h_data_format_text",
    "data.list_item":             "_h_data_list_item",
    "data.merge_objects":         "_h_data_merge_objects",
    "data.parse_json":            "_h_data_parse_json",
    "data.regex":                 "_h_data_regex",
    "data.set_variable":          "_h_data_set_variable",
    "data.split_text":            "_h_data_split_text",
    "data.variable":              "_h_data_variable",
    "data.template":              "_h_data_template",
    "data.type_convert":          "_h_data_type_convert",
    "transform.combine":          "_h_transform_combine",
    "action.clipboard":           "_h_action_clipboard",
    "action.file_list":           "_h_action_file_list",
    "action.file_read":           "_h_action_file_read",
    "action.file_write":          "_h_action_file_write",
    "action.http":                "_h_action_http",
    "action.log":                 "_h_action_log",
    "action.notify":              "_h_action_notify",
    "action.ocr":                 "_h_action_ocr",
    "action.run_agent":           "_h_action_run_agent",
    "action.run_command":         "_h_action_run_command",
    "action.run_script":          "_h_action_run_script",
    "action.screenshot":          "_h_action_screenshot",
    "action.camera_capture":      "_h_action_camera_capture",
    "action.web_scrape":          "_h_action_web_scrape",
    "ai.google":                  "_h_ai_google",
    "ai.any":                     "_h_ai_any",
    "ai.summarize":               "_h_ai_summarize",
    "ai.classify":                "_h_ai_classify",
    "ai.extract_data":            "_h_ai_extract_data",
    "ai.analyze_image":           "_h_ai_analyze_image",
    "ai.generate_image":          "_h_ai_generate_image",
    "ai.text_to_speech":          "_h_ai_text_to_speech",
    "ai.speech_to_text":          "_h_ai_speech_to_text",
    "memory.store":               "_h_memory_store",
    "memory.retrieve":            "_h_memory_retrieve",
    "memory.search_semantic":     "_h_memory_search_semantic",
    "input.text":                 "_h_input_text",
    "input.number":               "_h_input_number",
    "input.file":                 "_h_input_file",
    "input.list":                 "_h_input_list",
    "output.display":             "_h_output_display",
    "output.file":                "_h_output_file",
    "output.clipboard":           "_h_output_clipboard",
    "aethviondb.search":          "_h_aethviondb_search",
    "aethviondb.snapshot_search": "_h_aethviondb_snapshot_search",
    "companion.ask":              "_h_companion_ask",
    "integration.discord":        "_h_integration_discord",
    "integration.email":          "_h_integration_email",
    "integration.slack":          "_h_integration_slack",
}


# ── Generator functions ───────────────────────────────────────────────────────

def _analyze_workflow(workflow: dict) -> dict:
    """Return a summary of what the workflow uses."""
    used_types: set[str] = set()
    for node in workflow.get("nodes", []):
        t = node.get("type", "")
        if t:
            used_types.add(t)

    pip_deps: set[str] = set(_BASE_REQS)
    key_deps: set[str] = set()
    needs_aethviondb = False
    needs_ai = False

    for t in used_types:
        info = NODE_DEPS.get(t, {})
        for pkg in info.get("pip", []):
            pip_deps.add(pkg)
        for key in info.get("keys", []):
            key_deps.add(key)
        if info.get("aethviondb"):
            needs_aethviondb = True
        if info.get("ai"):
            needs_ai = True

    # ai.google and ai.any both use _h_ai_model — ensure that function is included
    if "ai.google" in used_types or "ai.any" in used_types:
        needs_ai = True

    # Collect public variables (data.variable nodes where public=True)
    public_vars: list[dict] = []
    seen_names: set[str] = set()
    for node in workflow.get("nodes", []):
        if node.get("type") != "data.variable":
            continue
        props = node.get("properties", {})
        if not props.get("public"):
            continue
        name = str(props.get("name", "var")).strip() or "var"
        if name in seen_names:
            continue   # deduplicate by name
        seen_names.add(name)
        public_vars.append({
            "name":        name,
            "varType":     str(props.get("varType", "string")),
            "default":     props.get("value", ""),
            "description": str(props.get("description", "")),
        })

    return {
        "used_types":        sorted(used_types),
        "pip_deps":          sorted(pip_deps),
        "key_deps":          sorted(key_deps),
        "needs_aethviondb":  needs_aethviondb,
        "needs_ai":          needs_ai,
        "public_vars":       public_vars,
    }


def _generate_requirements(analysis: dict) -> str:
    lines = ["# Auto-generated by Aethvion Suite Compiler", ""]
    lines += sorted(analysis["pip_deps"])
    return "\n".join(lines) + "\n"


def _generate_env(analysis: dict, options: dict, env_path: Path) -> str:
    """Generate .env content. If include_api_key=True, reads keys from live .env."""
    lines = ["# Standalone workflow environment", ""]

    if options.get("include_api_key") and env_path.exists():
        raw = env_path.read_text(encoding="utf-8")
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Only include keys referenced by this workflow
            key = stripped.split("=", 1)[0].strip()
            if not analysis["key_deps"] or key in analysis["key_deps"]:
                lines.append(stripped)
    else:
        for key in analysis["key_deps"]:
            lines.append(f"{key}=YOUR_KEY_HERE")
        if analysis["key_deps"]:
            lines.append("")
            lines.append("# Fill in the values above before running.")

    return "\n".join(lines) + "\n"


def _generate_start_bat(workflow_name: str, has_packages: bool) -> str:
    safe_name = workflow_name.replace(" ", "_")
    pip_cmd = (
        "pip install --no-index --find-links packages -r requirements.txt"
        if has_packages else
        "pip install -r requirements.txt"
    )
    return (
        "@echo off\n"
        f"title {safe_name}\n"
        "echo.\n"
        f"echo  {workflow_name} - Standalone Workflow\n"
        "echo  Checking dependencies...\n"
        "echo.\n"
        f"{pip_cmd}\n"
        "echo.\n"
        "echo  Starting server on http://127.0.0.1:7700\n"
        "echo  Open the URL above in your browser.\n"
        "echo  Press Ctrl+C to stop.\n"
        "echo.\n"
        "python run.py\n"
        "pause\n"
    )


def _generate_start_sh(workflow_name: str, has_packages: bool) -> str:
    pip_cmd = (
        "pip install --no-index --find-links packages -r requirements.txt"
        if has_packages else
        "pip install -r requirements.txt"
    )
    return (
        "#!/usr/bin/env bash\n"
        "set -e\n"
        f'echo ""\n'
        f'echo "  {workflow_name} - Standalone Workflow"\n'
        f'echo "  Checking dependencies..."\n'
        f"echo ''\n"
        f"{pip_cmd}\n"
        f'echo ""\n'
        f'echo "  Starting server on http://127.0.0.1:7700"\n'
        f'echo "  Open the URL in your browser. Press Ctrl+C to stop."\n'
        f'echo ""\n'
        "python3 run.py\n"
    )


# ── Web UI HTML ───────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%%NAME%%</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f172a;color:#e2e8f0;font-family:system-ui,sans-serif;height:100vh;display:flex;flex-direction:column}
header{background:#1e293b;border-bottom:1px solid #334155;padding:.65rem 1.25rem;display:flex;align-items:center;gap:.75rem}
header h1{font-size:.92rem;font-weight:700;letter-spacing:.02em;flex:1}
.badge{background:#22d3ee1a;color:#22d3ee;border:1px solid #22d3ee44;border-radius:4px;font-size:.65rem;padding:.1rem .38rem;font-weight:700;letter-spacing:.06em;white-space:nowrap}
.pub-badge{background:#a78bfa1a;color:#a78bfa;border:1px solid #a78bfa44;border-radius:4px;font-size:.65rem;padding:.1rem .38rem;font-weight:700;letter-spacing:.06em;white-space:nowrap}
.main{display:flex;flex:1;overflow:hidden}
/* ── Sidebar ── */
.sidebar{width:280px;flex-shrink:0;background:#1e293b;border-right:1px solid #334155;overflow-y:auto;display:flex;flex-direction:column}
.sb-section{padding:.8rem 1rem;display:flex;flex-direction:column;gap:.5rem}
.sb-section+.sb-section{border-top:1px solid #1e293b}
.sb-sep{height:1px;background:#334155;margin:0 1rem}
.sb-hdr{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#475569;padding:.6rem 1rem .2rem;display:flex;align-items:center;gap:.4rem}
.field{display:flex;flex-direction:column;gap:.22rem}
.field label{font-size:.76rem;color:#94a3b8;font-weight:500;display:flex;align-items:center;gap:.35rem}
.field .desc{font-size:.68rem;color:#475569;margin-top:.05rem}
.field input,.field textarea,.field select{background:#0f172a;border:1px solid #334155;border-radius:6px;color:#e2e8f0;padding:.38rem .5rem;font-size:.8rem;outline:none;resize:vertical;width:100%}
.field input:focus,.field textarea:focus,.field select:focus{border-color:#22d3ee}
.field input[type=checkbox]{width:auto;accent-color:#22d3ee}
.run-btn{background:#22d3ee;color:#0f172a;border:none;border-radius:6px;padding:.55rem 1rem;font-size:.86rem;font-weight:700;cursor:pointer;margin:.2rem 1rem .8rem;transition:background .15s}
.run-btn:hover{background:#67e8f9}
.run-btn:disabled{opacity:.4;cursor:not-allowed}
/* ── Content pane ── */
.content{flex:1;display:flex;flex-direction:column;overflow:hidden}
.tab-bar{display:flex;border-bottom:1px solid #334155;background:#1e293b;flex-shrink:0}
.tab-btn{background:none;border:none;color:#64748b;font-size:.78rem;font-weight:600;padding:.55rem .9rem;cursor:pointer;border-bottom:2px solid transparent;transition:color .15s}
.tab-btn.active{color:#e2e8f0;border-bottom-color:#22d3ee}
.tab-pane{display:none;flex:1;overflow:hidden}
.tab-pane.active{display:flex;flex-direction:column}
/* ── Run pane ── */
.run-pane{flex:1;display:flex;flex-direction:column;padding:.8rem;gap:.7rem;overflow:hidden}
.outputs-area{display:flex;flex-direction:column;gap:.35rem}
.outputs-hdr{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#475569}
.output-item{background:#1e293b;border:1px solid #334155;border-radius:6px;padding:.42rem .65rem}
.output-label{font-size:.68rem;color:#475569;font-weight:600;margin-bottom:.18rem}
.output-val{font-size:.8rem;color:#e2e8f0;white-space:pre-wrap;word-break:break-word;max-height:180px;overflow-y:auto}
.log-area{flex:1;background:#0f172a;border:1px solid #334155;border-radius:8px;overflow-y:auto;padding:.65rem;font-family:monospace;font-size:.76rem;min-height:80px}
.log-line{padding:.06rem 0;line-height:1.45}
.log-line.info{color:#64748b}
.log-line.warning{color:#fbbf24}
.log-line.error{color:#f87171}
/* ── API pane ── */
.api-pane{flex:1;overflow-y:auto;padding:.9rem 1rem;display:flex;flex-direction:column;gap:1rem}
.api-section-hdr{font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#475569;margin-bottom:.4rem}
.api-var-table{width:100%;border-collapse:collapse;font-size:.78rem}
.api-var-table th{text-align:left;color:#475569;font-size:.68rem;font-weight:600;padding:.28rem .5rem;border-bottom:1px solid #334155}
.api-var-table td{padding:.3rem .5rem;color:#e2e8f0;border-bottom:1px solid #1e293b;vertical-align:top}
.api-var-table td.type{color:#a78bfa;font-family:monospace;font-size:.74rem}
.api-var-table td.name{font-family:monospace;color:#22d3ee}
.api-var-table td.desc{color:#64748b;font-size:.74rem}
.endpoint-card{background:#1e293b;border:1px solid #334155;border-radius:8px;overflow:hidden}
.ep-hdr{display:flex;align-items:center;gap:.5rem;padding:.5rem .75rem;cursor:pointer;user-select:none}
.ep-method{font-family:monospace;font-size:.7rem;font-weight:700;padding:.1rem .32rem;border-radius:3px;flex-shrink:0}
.ep-method.GET{background:#22d3ee22;color:#22d3ee}
.ep-method.POST{background:#4ade8022;color:#4ade80}
.ep-path{font-family:monospace;font-size:.8rem;color:#e2e8f0;flex:1}
.ep-desc{font-size:.72rem;color:#64748b}
.ep-body{padding:.5rem .75rem;border-top:1px solid #334155;display:none}
.ep-body.open{display:block}
.ep-body pre{font-size:.72rem;color:#94a3b8;white-space:pre-wrap;word-break:break-word;margin:0}
.copy-btn{background:#334155;border:none;color:#94a3b8;font-size:.68rem;padding:.18rem .4rem;border-radius:4px;cursor:pointer;float:right;margin-left:.5rem}
.copy-btn:hover{background:#475569;color:#e2e8f0}
/* ── Status bar ── */
.status-bar{background:#1e293b;border-top:1px solid #334155;padding:.3rem 1rem;font-size:.7rem;color:#475569;display:flex;gap:.5rem;align-items:center;flex-shrink:0}
.dot{width:6px;height:6px;border-radius:50%;background:#334155;display:inline-block;flex-shrink:0}
.dot.running{background:#22d3ee;animation:pulse 1s infinite}
.dot.ok{background:#4ade80}
.dot.error{background:#f87171}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
.no-vars{color:#475569;font-size:.8rem;font-style:italic;padding:.2rem 0}
</style>
</head>
<body>
<header>
  <div class="badge">STANDALONE</div>
  <h1>%%NAME%%</h1>
  <span id="pub-var-count" style="display:none" class="pub-badge"></span>
</header>
<div class="main">
  <!-- ── Sidebar ── -->
  <div class="sidebar">
    <!-- Public Variables section -->
    <div class="sb-hdr" id="vars-hdr" style="display:none">
      <i>&#x24;</i> Variables
    </div>
    <div class="sb-section" id="vars-section" style="display:none"></div>
    <div class="sb-sep" id="vars-sep" style="display:none"></div>
    <!-- Input nodes section -->
    <div class="sb-hdr" id="inp-hdr" style="display:none">&#9776; Input Nodes</div>
    <div class="sb-section" id="inp-section" style="display:none"></div>
    <button class="run-btn" id="run-btn" onclick="run()">&#9654; Run</button>
  </div>
  <!-- ── Content ── -->
  <div class="content">
    <div class="tab-bar">
      <button class="tab-btn active" onclick="showTab('run')">&#9654; Run</button>
      <button class="tab-btn" onclick="showTab('api')">&#x2756; API</button>
    </div>
    <div class="tab-pane active" id="pane-run">
      <div class="run-pane">
        <div class="outputs-area" id="out-area" style="display:none">
          <div class="outputs-hdr">Outputs</div>
          <div id="out-items"></div>
        </div>
        <div class="log-area" id="log"></div>
      </div>
    </div>
    <div class="tab-pane" id="pane-api">
      <div class="api-pane" id="api-pane"></div>
    </div>
  </div>
</div>
<div class="status-bar">
  <span class="dot" id="dot"></span>
  <span id="status">Ready — configure variables and click Run</span>
</div>
<script>
function esc(t){return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function showTab(id){
  document.querySelectorAll('.tab-btn').forEach((b,i)=>b.classList.toggle('active',['run','api'][i]===id));
  document.querySelectorAll('.tab-pane').forEach(p=>p.classList.remove('active'));
  document.getElementById('pane-'+id).classList.add('active');
}

// ── Sidebar: public variables ─────────────────────────────────────────────────
async function loadVars(){
  const r=await fetch('/api/variables');
  const vars=await r.json();
  const sec=document.getElementById('vars-section');
  const hdr=document.getElementById('vars-hdr');
  const sep=document.getElementById('vars-sep');
  const cnt=document.getElementById('pub-var-count');
  if(vars.length){
    hdr.style.display='';sep.style.display='';sec.style.display='';
    cnt.style.display='';cnt.textContent=vars.length+' public var'+(vars.length>1?'s':'');
  }
  vars.forEach(v=>{
    const d=document.createElement('div');d.className='field';
    const lb=document.createElement('label');
    lb.innerHTML='<span class="pub-badge" style="font-size:.6rem;padding:.05rem .3rem">PUBLIC</span> '+esc(v.name);
    d.appendChild(lb);
    if(v.description){const ds=document.createElement('div');ds.className='desc';ds.textContent=v.description;d.appendChild(ds);}
    let el;
    if(v.varType==='boolean'){
      el=document.createElement('select');
      el.innerHTML='<option value="true">true</option><option value="false">false</option>';
      el.value=String(v.default).toLowerCase()==='false'?'false':'true';
    } else if(v.varType==='number'){
      el=document.createElement('input');el.type='number';el.value=v.default??0;
    } else {
      el=document.createElement('input');el.type='text';el.value=v.default??'';
    }
    el.dataset.varname=v.name;el.id='v_'+v.name;d.appendChild(el);sec.appendChild(d);
  });
}

// ── Sidebar: input.* nodes ────────────────────────────────────────────────────
async function loadInputs(){
  const r=await fetch('/inputs');const ins=await r.json();
  if(!ins.length)return;
  const sec=document.getElementById('inp-section');
  document.getElementById('inp-hdr').style.display='';
  sec.style.display='';
  ins.forEach(inp=>{
    const d=document.createElement('div');d.className='field';
    const lb=document.createElement('label');lb.textContent=inp.label||inp.id;
    d.appendChild(lb);
    let el;
    if(inp.type==='number'){el=document.createElement('input');el.type='number';el.value=inp.default??0;}
    else if(inp.multiline||inp.type==='list'){el=document.createElement('textarea');el.rows=3;el.value=inp.default??'';}
    else{el=document.createElement('input');el.type='text';el.value=inp.default??'';}
    el.id='i_'+inp.id;el.dataset.nid=inp.id;d.appendChild(el);sec.appendChild(d);
  });
}

// ── Run ───────────────────────────────────────────────────────────────────────
async function run(){
  const btn=document.getElementById('run-btn');
  const log=document.getElementById('log');
  const dot=document.getElementById('dot');
  const status=document.getElementById('status');
  const outArea=document.getElementById('out-area');
  const outItems=document.getElementById('out-items');
  btn.disabled=true;log.innerHTML='';outArea.style.display='none';outItems.innerHTML='';
  dot.className='dot running';status.textContent='Running…';
  // Collect public-variable values
  const vars={};
  document.querySelectorAll('[data-varname]').forEach(e=>vars[e.dataset.varname]=e.value);
  // Collect input-node overrides
  const ov={};
  document.querySelectorAll('[data-nid]').forEach(e=>ov[e.dataset.nid]=e.value);
  const params=new URLSearchParams({
    variables:JSON.stringify(vars),
    overrides:JSON.stringify(ov)
  });
  const es=new EventSource('/stream?'+params.toString());
  es.onmessage=e=>{
    const d=JSON.parse(e.data);
    if(d.done){
      es.close();btn.disabled=false;
      dot.className='dot '+(d.ok?'ok':'error');
      status.textContent=d.ok?'Completed ✓':'Completed with errors ✗';
      loadOutputs();return;
    }
    const l=document.createElement('div');l.className='log-line '+(d.level||'info');
    l.textContent='['+(d.ts||'')+'] '+d.msg;log.appendChild(l);log.scrollTop=log.scrollHeight;
  };
  es.onerror=()=>{es.close();btn.disabled=false;dot.className='dot error';status.textContent='Connection error';};
}

async function loadOutputs(){
  const r=await fetch('/outputs');const outs=await r.json();
  if(!outs.length)return;
  const outArea=document.getElementById('out-area');
  const outItems=document.getElementById('out-items');
  outArea.style.display='';outItems.innerHTML='';
  outs.forEach(o=>{
    const item=document.createElement('div');item.className='output-item';
    item.innerHTML='<div class="output-label">'+esc(o.label)+'</div><div class="output-val">'+esc(o.value)+'</div>';
    outItems.appendChild(item);
  });
}

// ── API docs pane ─────────────────────────────────────────────────────────────
async function loadApiDocs(){
  const r=await fetch('/api/schema');
  const s=await r.json();
  const pane=document.getElementById('api-pane');
  // Variables table
  if(s.public_variables&&s.public_variables.length){
    const sec=document.createElement('div');
    sec.innerHTML='<div class="api-section-hdr">Public Variables</div>';
    const tbl=document.createElement('table');tbl.className='api-var-table';
    tbl.innerHTML='<thead><tr><th>Name</th><th>Type</th><th>Default</th><th>Description</th></tr></thead>';
    const tb=document.createElement('tbody');
    s.public_variables.forEach(v=>{
      const tr=document.createElement('tr');
      tr.innerHTML='<td class="name">$'+esc(v.name)+'</td><td class="type">'+esc(v.varType)+'</td><td>'+esc(v.default)+'</td><td class="desc">'+esc(v.description)+'</td>';
      tb.appendChild(tr);
    });
    tbl.appendChild(tb);sec.appendChild(tbl);pane.appendChild(sec);
  }
  // Endpoint cards
  const epsHdr=document.createElement('div');epsHdr.innerHTML='<div class="api-section-hdr">Endpoints</div>';pane.appendChild(epsHdr);
  s.endpoints.forEach(ep=>{
    const card=document.createElement('div');card.className='endpoint-card';
    const hdr=document.createElement('div');hdr.className='ep-hdr';
    const hasBody=ep.body||ep.query_params||ep.response||ep.events;
    hdr.innerHTML='<span class="ep-method '+ep.method+'">'+ep.method+'</span>'
      +'<span class="ep-path">'+esc(ep.path)+'</span>'
      +'<span class="ep-desc">'+esc(ep.description)+'</span>';
    if(hasBody){hdr.innerHTML+='<span style="color:#475569;font-size:.8rem;margin-left:.4rem">&#9660;</span>';}
    card.appendChild(hdr);
    if(hasBody){
      const body=document.createElement('div');body.className='ep-body';
      let content='';
      if(ep.body){content+='// Request body (JSON)\\n'+JSON.stringify(ep.body,null,2)+'\\n';}
      if(ep.query_params){content+='// Query params\\n'+JSON.stringify(ep.query_params,null,2)+'\\n';}
      if(ep.response){content+='// Response\\n'+JSON.stringify(ep.response,null,2)+'\\n';}
      if(ep.events){content+='// SSE events\\n'+JSON.stringify(ep.events,null,2)+'\\n';}
      const pre=document.createElement('pre');pre.textContent=content.trim();
      const copyBtn=document.createElement('button');copyBtn.className='copy-btn';copyBtn.textContent='Copy';
      copyBtn.onclick=(e)=>{e.stopPropagation();navigator.clipboard.writeText(content.trim()).then(()=>{copyBtn.textContent='Copied!';setTimeout(()=>copyBtn.textContent='Copy',1500);});};
      body.appendChild(copyBtn);body.appendChild(pre);card.appendChild(body);
      hdr.style.cursor='pointer';
      hdr.addEventListener('click',()=>body.classList.toggle('open'));
    }
    pane.appendChild(card);
  });
}

// ── Boot ──────────────────────────────────────────────────────────────────────
Promise.all([loadVars(),loadInputs(),loadApiDocs()]);
</script>
</body>
</html>
"""


# ── run.py generator ──────────────────────────────────────────────────────────

def _generate_run_py(workflow: dict, analysis: dict) -> str:
    """Assemble the standalone run.py source code."""
    wf_name = workflow.get("name", "Workflow")
    date_str = datetime.now().strftime("%Y-%m-%d")

    used = set(analysis["used_types"])
    needs_ai = analysis["needs_ai"]

    # Build handler code block (only used types)
    handler_blocks: list[str] = []
    # ai_model shared impl — included if any AI node uses it
    if needs_ai:
        ai_model_shared = '''\
# ── Shared AI model handler (used by ai.google and ai.any) ───────────────────
def _h_ai_model(node, inputs, ctx):
    p = node.get("properties", {})
    def _inp(port, prop, default=""):
        wired = _to_str(inputs.get(port, "")).strip()
        return wired if wired else str(p.get(prop, default)).strip()
    model_id      = _inp("model", "model")
    system_prompt = _inp("system_prompt", "system_prompt") or None
    prefix        = _inp("prompt_prefix", "prompt_prefix")
    suffix        = _inp("prompt_suffix", "prompt_suffix")
    in_val        = _to_str(inputs.get("in", ""))
    try:
        temp_raw = inputs.get("temperature")
        temperature = float(temp_raw) if temp_raw not in (None, "") else float(p.get("temperature", 0.7))
    except Exception: temperature = 0.7
    if not model_id: raise ValueError("No model selected — open node properties and pick a model.")
    parts = [x for x in [prefix, in_val, suffix] if x]
    prompt = "\\n\\n".join(parts) if parts else "(no input)"
    try:
        return {"out": _ai_call(model_id, system_prompt, prompt, temperature), "error": ""}
    except Exception as exc:
        return {"out": "", "error": str(exc)}
'''
        handler_blocks.append(ai_model_shared)

    for ntype in sorted(used):
        code = _HANDLER_CODE.get(ntype)
        if code:
            handler_blocks.append(code)

    # Build registry
    registry_lines = []
    for ntype in sorted(used):
        fn = _HANDLER_NAMES.get(ntype)
        if fn:
            registry_lines.append(f'    {repr(ntype)}: {fn},')

    # AI section
    ai_section = ""
    if needs_ai:
        ai_section = '''\
# ── Standalone AI client ──────────────────────────────────────────────────────
_ai_client = None

def _get_ai_client():
    global _ai_client
    if _ai_client is not None:
        return _ai_client
    try:
        import google.generativeai as _genai
    except ImportError:
        raise RuntimeError("google-generativeai not installed — run: pip install -r requirements.txt")
    api_key = os.environ.get("GOOGLE_AI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GOOGLE_AI_API_KEY not set — add it to .env")
    _genai.configure(api_key=api_key)
    _ai_client = _genai
    return _genai

def _ai_call(model_id: str, system_prompt, prompt: str, temperature: float = 0.7) -> str:
    genai = _get_ai_client()
    model = genai.GenerativeModel(
        model_name=model_id or "gemini-2.0-flash",
        system_instruction=system_prompt or None,
    )
    cfg = genai.GenerationConfig(temperature=temperature)
    resp = model.generate_content(prompt, generation_config=cfg)
    return resp.text

def _extract_json_block(text: str) -> dict:
    try:
        r = json.loads(text.strip())
        if isinstance(r, dict): return r
    except Exception: pass
    start = text.find("{")
    if start == -1: return {}
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    r = json.loads(text[start:i+1])
                    if isinstance(r, dict): return r
                except Exception: break
    return {}

'''

    public_vars      = analysis.get("public_vars", [])
    public_vars_json = json.dumps(public_vars, ensure_ascii=False)
    html_content     = _HTML_TEMPLATE.replace("%%NAME%%", wf_name)

    src = f'''\
#!/usr/bin/env python3
"""Standalone Workflow: {wf_name}
Compiled by Aethvion Suite Compiler on {date_str}

Usage:
    python run.py [--port 7700] [--host 127.0.0.1]
    -- or use start.bat / start.sh --
"""
from __future__ import annotations
import asyncio, csv, io, json, os, re, sys, time, uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Load .env ─────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  # python-dotenv not installed — set env vars manually

# ── Utilities ─────────────────────────────────────────────────────────────────

def _to_str(val: Any) -> str:
    if isinstance(val, str): return val
    if val is None: return ""
    if isinstance(val, (dict, list)): return json.dumps(val, ensure_ascii=False)
    return str(val)

def _safe_eval(expr: str, local_vars: dict) -> Any:
    safe = {{"len": len, "str": str, "int": int, "float": float,
              "bool": bool, "list": list, "dict": dict,
              "True": True, "False": False, "None": None}}
    return eval(expr, {{"__builtins__": safe}}, local_vars)

def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

# ── WorkflowExecutor ──────────────────────────────────────────────────────────

class WorkflowExecutor:
    def __init__(self, workflow: dict, variables: dict | None = None) -> None:
        self.workflow    = workflow
        self.nodes: dict[str, dict] = {{n["id"]: n for n in workflow.get("nodes", [])}}
        self.connections = workflow.get("connections", [])
        self._outputs: dict[str, dict[str, Any]] = {{}}
        self._status:  dict[str, str] = {{}}
        self._errors:  dict[str, str] = {{}}
        self._log:     list[dict]     = []
        self._vars:    dict[str, Any] = dict(variables or {{}})  # pre-seed with injected values

    def execute(self) -> dict:
        name = self.workflow.get("name", "Workflow")
        self._info('Starting workflow "%s"' % name)
        order = self._topo_sort()
        if order is None:
            self._error("Cycle detected — cannot execute.")
            return self._build_result(fatal="Cycle detected.")
        if not order:
            self._warn("No nodes to execute.")
            return self._build_result()
        reachable = self._reachable_from_triggers()
        run_order = [nid for nid in order if nid in reachable]
        for nid in order:
            if nid not in reachable:
                self._status[nid] = "skipped"
        if not run_order:
            self._warn("No nodes connected to a trigger.")
            return self._build_result()
        for nid in run_order:
            node  = self.nodes[nid]
            label = node.get("label", nid)
            ntype = node.get("type", "unknown")
            self._status[nid] = "running"
            self._info('\\u25b6 %s  [%s]' % (label, ntype))
            try:
                inputs  = self._gather_inputs(nid)
                handler = _REGISTRY.get(ntype)
                if handler:
                    outputs = handler(node, inputs, self)
                else:
                    self._warn('Unknown node type: %r \\u2014 pass-through' % ntype)
                    outputs = {{"out": inputs.get("in", "")}}
                self._outputs[nid] = outputs or {{}}
                self._status[nid]  = "done"
                self._info('  \\u2713 %s' % label)
            except Exception as exc:
                self._status[nid] = "error"
                self._errors[nid] = str(exc)
                self._error('  \\u2717 %s: %s' % (label, exc))
        errors = sum(1 for s in self._status.values() if s == "error")
        self._warn('Workflow finished with %d error(s).' % errors) if errors else self._info("Workflow completed successfully.")
        return self._build_result()

    def _reachable_from_triggers(self) -> set[str]:
        adj: dict[str, list[str]] = {{nid: [] for nid in self.nodes}}
        for c in self.connections:
            s, t = c.get("sourceNodeId"), c.get("targetNodeId")
            if s in self.nodes and t in self.nodes: adj[s].append(t)
        seeds = [nid for nid, n in self.nodes.items() if n.get("type","").startswith("trigger.")]
        visited = set(seeds); queue = list(seeds)
        while queue:
            nid = queue.pop(0)
            for nb in adj[nid]:
                if nb not in visited: visited.add(nb); queue.append(nb)
        return visited

    def _topo_sort(self):
        in_deg = {{nid: 0 for nid in self.nodes}}
        adj    = {{nid: [] for nid in self.nodes}}
        for c in self.connections:
            s, t = c.get("sourceNodeId"), c.get("targetNodeId")
            if s in self.nodes and t in self.nodes:
                adj[s].append(t); in_deg[t] += 1
        queue = [nid for nid, d in in_deg.items() if d == 0]
        result = []
        while queue:
            nid = queue.pop(0); result.append(nid)
            for nb in adj[nid]:
                in_deg[nb] -= 1
                if in_deg[nb] == 0: queue.append(nb)
        return result if len(result) == len(self.nodes) else None

    def _gather_inputs(self, node_id: str) -> dict[str, Any]:
        inputs: dict[str, Any] = {{}}
        for c in self.connections:
            if c.get("targetNodeId") != node_id: continue
            src_id   = c.get("sourceNodeId", "")
            src_port = c.get("sourcePort", "")
            tgt_port = c.get("targetPort", "")
            if src_id in self._outputs:
                val = self._outputs[src_id].get(src_port)
                if val is not None: inputs[tgt_port] = val
        return inputs

    def _build_result(self, fatal=None):
        return {{"ok": not (bool(self._errors) or fatal is not None), "fatal": fatal,
                 "node_status": self._status, "node_outputs": self._outputs,
                 "node_errors": self._errors, "log": self._log}}

    def _info(self, msg): self._log.append({{"level":"info",    "msg": msg, "ts": _ts()}})
    def _warn(self, msg): self._log.append({{"level":"warning", "msg": msg, "ts": _ts()}})
    def _error(self, msg): self._log.append({{"level":"error",  "msg": msg, "ts": _ts()}})

# ── Runtime state ─────────────────────────────────────────────────────────────
_INPUT_OVERRIDES: dict[str, Any] = {{}}
_OUTPUT_RESULTS:  list[dict]     = []
_MEMORY_STORE:    dict[str, Any] = {{}}

{ai_section}
# ── Node handlers ─────────────────────────────────────────────────────────────
{"".join(handler_blocks)}
# ── Handler registry ──────────────────────────────────────────────────────────
_REGISTRY: dict[str, Any] = {{
{"".join(registry_lines)}
}}

# ── Workflow ──────────────────────────────────────────────────────────────────
with open(Path(__file__).parent / "workflow.json", encoding="utf-8") as _f:
    _WORKFLOW = json.load(_f)

_INPUT_NODES = [n for n in _WORKFLOW.get("nodes", []) if n.get("type","").startswith("input.")]

# ── Public variables (baked in at compile time) ───────────────────────────────
# Each entry: {{name, varType, default, description}}
_PUBLIC_VARS: list[dict] = {public_vars_json}

# ── FastAPI server ────────────────────────────────────────────────────────────
try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
    import uvicorn
except ImportError:
    print("ERROR: FastAPI/uvicorn not installed.  Run: pip install -r requirements.txt")
    sys.exit(1)

app = FastAPI(title={repr(wf_name)}, docs_url=None, redoc_url=None)

_HTML = {repr(html_content)}

@app.get("/", response_class=HTMLResponse)
async def index():
    return _HTML

@app.get("/inputs")
async def get_inputs():
    """Input nodes (input.text / input.number / input.list) — legacy endpoint."""
    result = []
    for n in _INPUT_NODES:
        ntype = n.get("type","")
        p = n.get("properties", {{}})
        if ntype == "input.number":
            inp_type, default, multiline = "number", p.get("value", 0), False
        elif ntype == "input.list":
            inp_type, default, multiline = "list", p.get("items",""), True
        else:
            default = p.get("value","") or p.get("path","")
            inp_type = "text"
            multiline = "\\n" in str(default) or len(str(default)) > 80
        result.append({{"id": n["id"], "label": n.get("label", ntype), "type": inp_type,
                         "default": default, "multiline": multiline}})
    return JSONResponse(result)

@app.get("/api/variables")
async def api_variables():
    """List all public variables with their types, defaults and descriptions."""
    return JSONResponse(_PUBLIC_VARS)

@app.get("/api/schema")
async def api_schema():
    """Machine-readable description of every available endpoint."""
    schema = {{
        "workflow": {repr(wf_name)},
        "public_variables": _PUBLIC_VARS,
        "endpoints": [
            {{
                "method": "GET", "path": "/",
                "description": "Web dashboard — run the workflow interactively in a browser.",
            }},
            {{
                "method": "POST", "path": "/run",
                "description": "Run the workflow and return the full result as JSON.",
                "body": {{
                    "variables": {{"<name>": "<value>", "...": "..."}},
                    "overrides": {{"<node_id>": "<value>", "...": "..."}},
                }},
                "response": {{
                    "ok": True,
                    "node_status": {{"<node_id>": "done | error | skipped"}},
                    "node_outputs": {{"<node_id>": {{"<port>": "<value>"}}}},
                    "node_errors":  {{"<node_id>": "<error message>"}},
                    "log": [{{"level": "info | warning | error", "msg": "...", "ts": "HH:MM:SS.mmm"}}],
                }},
            }},
            {{
                "method": "GET", "path": "/stream",
                "description": "Server-Sent Events stream — receive log lines in real time.",
                "query_params": {{
                    "variables": "JSON object mapping variable names to values",
                    "overrides": "JSON object mapping input-node IDs to values",
                }},
                "events": [
                    {{"level": "info | warning | error", "msg": "...", "ts": "..."}},
                    {{"done": True, "ok": True}},
                ],
            }},
            {{
                "method": "GET", "path": "/outputs",
                "description": "Outputs produced by output.display nodes in the last run.",
                "response": [{{"label": "...", "value": "..."}}],
            }},
            {{
                "method": "GET", "path": "/api/variables",
                "description": "List every public variable defined in this workflow.",
                "response": [{{"name": "...", "varType": "string|number|boolean",
                               "default": "...", "description": "..."}}],
            }},
            {{
                "method": "GET", "path": "/api/schema",
                "description": "This endpoint — machine-readable API schema.",
            }},
        ],
    }}
    return JSONResponse(schema)

@app.get("/outputs")
async def get_outputs():
    return JSONResponse(_OUTPUT_RESULTS)

@app.get("/status")
async def get_status():
    return JSONResponse({{"ready": True, "workflow": {repr(wf_name)},
                          "public_vars": [v["name"] for v in _PUBLIC_VARS]}})

@app.get("/stream")
async def stream_execution(overrides: str = "{{}}", variables: str = "{{}}"):
    global _INPUT_OVERRIDES, _OUTPUT_RESULTS
    try: _INPUT_OVERRIDES = json.loads(overrides)
    except Exception: _INPUT_OVERRIDES = {{}}
    try: _var_overrides = json.loads(variables)
    except Exception: _var_overrides = {{}}
    _OUTPUT_RESULTS.clear()
    async def event_stream():
        loop = asyncio.get_event_loop()
        def _run():
            ex = WorkflowExecutor(_WORKFLOW, variables=_var_overrides)
            ex._vars.update({{k: v for k, v in _INPUT_OVERRIDES.items()
                              if not k.startswith("_node_")}})
            return ex, ex.execute()
        executor, result = await loop.run_in_executor(None, _run)
        for entry in executor._log:
            yield f"data: {{json.dumps(entry)}}\\n\\n"
            await asyncio.sleep(0)
        yield f"data: {{json.dumps({{'done': True, 'ok': result['ok']}})}}\\n\\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={{"Cache-Control":"no-cache","X-Accel-Buffering":"no"}})

@app.post("/run")
async def run_workflow(request: Request):
    global _INPUT_OVERRIDES, _OUTPUT_RESULTS
    body = {{}}
    try: body = await request.json()
    except Exception: pass
    _INPUT_OVERRIDES = body.get("overrides", {{}})
    _var_overrides   = body.get("variables", {{}})
    _OUTPUT_RESULTS.clear()
    ex = WorkflowExecutor(_WORKFLOW, variables=_var_overrides)
    result = ex.execute()
    return JSONResponse(result)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description={repr(wf_name)})
    ap.add_argument("--port", type=int, default=7700)
    ap.add_argument("--host", type=str, default="127.0.0.1")
    args = ap.parse_args()
    print(f"")
    print(f"  Standalone Workflow: {wf_name}")
    print(f"  \\033[36mhttp://{{args.host}}:{{args.port}}\\033[0m")
    if _PUBLIC_VARS:
        print(f"  Public variables: {{', '.join(v['name'] for v in _PUBLIC_VARS)}}")
    print(f"")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
'''

    return src


# ── Package downloader ────────────────────────────────────────────────────────

def _download_packages(requirements: str, dest_dir: str) -> tuple[bool, str]:
    """Run pip download into dest_dir.  Returns (success, error_message)."""
    req_tmp = os.path.join(dest_dir, "_req_tmp.txt")
    try:
        with open(req_tmp, "w", encoding="utf-8") as f:
            f.write(requirements)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "download",
             "--prefer-binary", "-d", dest_dir, "-r", req_tmp],
            capture_output=True, text=True, timeout=300,
        )
        os.unlink(req_tmp)
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "pip download timed out after 5 minutes"
    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            if os.path.exists(req_tmp):
                os.unlink(req_tmp)
        except OSError:
            pass


# ── Public API ────────────────────────────────────────────────────────────────

def compile_workflow(workflow: dict, options: dict) -> tuple[bytes, list[str]]:
    """
    Compile *workflow* into a zip bundle.

    Options:
        include_packages (bool, default True)  — pip download wheels into packages/
        include_api_key  (bool, default False) — embed API keys from live .env

    Returns:
        (zip_bytes, warnings)  where warnings is a list of non-fatal messages.
    """
    include_packages = bool(options.get("include_packages", True))
    include_api_key  = bool(options.get("include_api_key",  False))

    analysis    = _analyze_workflow(workflow)
    wf_name     = workflow.get("name", "Workflow")
    safe_name   = re.sub(r"[^\w\-]", "_", wf_name)
    warnings: list[str] = []

    # Locate live .env for key extraction
    env_path = Path(__file__).parent.parent.parent / ".env"

    run_py       = _generate_run_py(workflow, analysis)
    requirements = _generate_requirements(analysis)
    env_content  = _generate_env(analysis, {"include_api_key": include_api_key}, env_path)
    start_bat    = _generate_start_bat(wf_name, include_packages)
    start_sh     = _generate_start_sh(wf_name, include_packages)
    workflow_json = json.dumps(workflow, indent=2, ensure_ascii=False)

    # Build zip in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        prefix = safe_name + "/"
        zf.writestr(prefix + "run.py",            run_py.encode("utf-8"))
        zf.writestr(prefix + "workflow.json",     workflow_json.encode("utf-8"))
        zf.writestr(prefix + "requirements.txt",  requirements.encode("utf-8"))
        zf.writestr(prefix + ".env",              env_content.encode("utf-8"))
        zf.writestr(prefix + "start.bat",         start_bat.encode("utf-8"))
        zf.writestr(prefix + "start.sh",          start_sh.encode("utf-8"))

        if include_packages:
            with tempfile.TemporaryDirectory() as tmp:
                ok, err = _download_packages(requirements, tmp)
                if ok:
                    for wheel in Path(tmp).iterdir():
                        if wheel.is_file():
                            zf.write(wheel, prefix + "packages/" + wheel.name)
                else:
                    warnings.append(
                        f"Package download failed ({err}). "
                        "Bundle created without packages/. "
                        "Run: pip install -r requirements.txt on the target machine."
                    )

    return buf.getvalue(), warnings
