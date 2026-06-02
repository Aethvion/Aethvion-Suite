"""
core/automate/compiler.py
Compile a workflow into a standalone runnable bundle (zip file).

Bundle layout:
  run.py            — embedded executor + node handlers + FastAPI server + web UI
  workflow.json     — the workflow definition
  requirements.txt  — auto-detected pip packages
  .env              — API keys (if include_api_key=True)
  start.bat         — Windows launcher
  start.sh          — Unix launcher
  packages/         — pre-downloaded wheels (if include_packages=True)

Implementation note — `except Exception` patterns
The majority of `except Exception` clauses in this file live inside Python
*template strings* (the `_HANDLER_CODE` dict and the run.py generation
template).  These strings are *data* — they are written verbatim into the
generated `run.py` of each compiled bundle, not executed here.  They represent
appropriate workflow-runtime error handling (return an error dict, log a
warning, etc.) and are intentional.

The handful of `except` blocks in the *compiler's own code* (outside the
template strings) are either proper fallbacks with explicit return values or
are followed by a `logger.warning()` / `return False, str(exc)` call.
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

from core.utils import get_logger

logger = get_logger(__name__)

# AethvionDB registry helper
# Reads _db_registry.json directly so compiler.py stays self-contained with no
# cross-module imports.

_SUITE_ROOT    = Path(__file__).parent.parent.parent
_DB_REGISTRY   = _SUITE_ROOT / "data" / "aethviondb" / "_db_registry.json"
_DEFAULT_DB_ROOT = _SUITE_ROOT / "data" / "aethviondb"


def _resolve_db_root(db_name: str) -> Path:
    """Return the filesystem root for a named AethvionDB database.

    Reads the registry file to honour custom paths; falls back to the default
    data/aethviondb/<db_name> location when the registry has no entry or the
    registered path no longer exists on disk.
    """
    try:
        raw = json.loads(_DB_REGISTRY.read_text(encoding="utf-8"))
        entry = raw.get("databases", {}).get(db_name)
        if entry and entry.get("path"):
            p = Path(entry["path"])
            if p.exists():
                return p
    except Exception as exc:
        logger.debug("Could not read AethvionDB registry (%s); using default path", exc)
    return _DEFAULT_DB_ROOT / db_name


# Dependency map
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
    "aethviondb.search":                   {"pip": [],  "keys": [], "aethviondb": True, "ai": False},
    "aethviondb.semantic_search":          {"pip": [],  "keys": [], "aethviondb": True, "ai": False},
    "aethviondb.snapshot_search":          {"pip": [],  "keys": [], "aethviondb": True, "ai": False},
    # keys/pip added dynamically per-node in _analyze_workflow based on model property
    "aethviondb.snapshot_semantic_search": {"pip": [],  "keys": [], "aethviondb": True, "ai": False},
    "companion.ask":      {"pip": ["google-generativeai"],         "keys": ["GOOGLE_AI_API_KEY"], "aethviondb": False, "ai": True},
    "integration.discord":{"pip": ["httpx"],                       "keys": [], "aethviondb": False, "ai": False},
    "integration.email":  {"pip": [],                              "keys": [], "aethviondb": False, "ai": False},
    "integration.slack":  {"pip": ["httpx"],                       "keys": [], "aethviondb": False, "ai": False},
}

_BASE_REQS = ["fastapi", "uvicorn[standard]", "python-dotenv"]

# Handler code blocks (lazy)
# Loaded on first compile — not at import time — so startup pays no cost if
# the user never compiles a workflow.
_HANDLERS_DIR       = Path(__file__).parent.parent / "config" / "automate" / "handlers"
_handler_code_cache: dict[str, str] | None = None


def _get_handler_code() -> dict[str, str]:
    global _handler_code_cache
    if _handler_code_cache is None:
        _handler_code_cache = {
            p.stem: p.read_text(encoding="utf-8")
            for p in sorted(_HANDLERS_DIR.glob("*.py"))
        }
    return _handler_code_cache


# Generator functions

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

    # AethvionDB: distinguish live search vs. bundlable snapshot search
    has_live_db_search = False
    snapshot_nodes: list[dict] = []

    _OPENAI_EMBED_MODELS = {"text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"}

    for node in workflow.get("nodes", []):
        t = node.get("type", "")
        if t in ("aethviondb.search", "aethviondb.semantic_search"):
            has_live_db_search = True
        elif t == "aethviondb.snapshot_semantic_search":
            props     = node.get("properties", {})
            db_name   = str(props.get("database", "default")).strip() or "default"
            snap_name = str(props.get("snapshot", "")).strip()
            model     = str(props.get("model", "text-embedding-004")).strip() or "text-embedding-004"
            # Resolve API key / pip dep based on the selected embedding model
            if model in _OPENAI_EMBED_MODELS:
                key_deps.add("OPENAI_API_KEY")
                pip_deps.add("openai")
            else:
                key_deps.add("GOOGLE_AI_API_KEY")
                pip_deps.add("google-generativeai")
            # Locate snapshot file on disk (honours custom db paths)
            baked_dir = _resolve_db_root(db_name) / "baked"
            snap_path: Any = None
            if baked_dir.exists():
                if snap_name:
                    candidate = baked_dir / f"{snap_name}.jsonl"
                    if candidate.exists():
                        snap_path = candidate
                if snap_path is None:
                    files = sorted(
                        baked_dir.glob("*.jsonl"),
                        key=lambda f: f.stat().st_mtime,
                        reverse=True,
                    )
                    if files:
                        snap_path = files[0]
            size_bytes = int(snap_path.stat().st_size) if snap_path else 0
            entry = {
                "db":         db_name,
                "snap_name":  snap_path.stem if snap_path else (snap_name or "unknown"),
                "path":       str(snap_path) if snap_path else None,
                "size_bytes": size_bytes,
            }
            if not any(
                s["db"] == entry["db"] and s["snap_name"] == entry["snap_name"]
                for s in snapshot_nodes
            ):
                snapshot_nodes.append(entry)
        elif t == "aethviondb.snapshot_search":
            props = node.get("properties", {})
            db_name  = str(props.get("database", "default")).strip() or "default"
            snap_name = str(props.get("snapshot", "")).strip()
            # Locate the actual .jsonl file on disk (honours custom db paths)
            baked_dir = _resolve_db_root(db_name) / "baked"
            snap_path: Any = None
            if baked_dir.exists():
                if snap_name:
                    candidate = baked_dir / f"{snap_name}.jsonl"
                    if candidate.exists():
                        snap_path = candidate
                if snap_path is None:
                    files = sorted(
                        baked_dir.glob("*.jsonl"),
                        key=lambda f: f.stat().st_mtime,
                        reverse=True,
                    )
                    if files:
                        snap_path = files[0]
            size_bytes = int(snap_path.stat().st_size) if snap_path else 0
            entry = {
                "db":         db_name,
                "snap_name":  snap_path.stem if snap_path else (snap_name or "unknown"),
                "path":       str(snap_path) if snap_path else None,
                "size_bytes": size_bytes,
            }
            # Deduplicate by (db, snap_name)
            if not any(
                s["db"] == entry["db"] and s["snap_name"] == entry["snap_name"]
                for s in snapshot_nodes
            ):
                snapshot_nodes.append(entry)

    # Collect global nodes (global.* — always exposed via API & compiled bundles)
    _GLOBAL_VAR_TYPE: dict[str, str] = {
        "global.text":     "string",
        "global.number":   "number",
        "global.toggle":   "boolean",
        "global.database": "string",
        "global.snapshot": "string",
    }
    public_vars: list[dict] = []
    seen_names: set[str] = set()
    for node in workflow.get("nodes", []):
        node_type = node.get("type", "")
        if not node_type.startswith("global."):
            continue
        props = node.get("properties", {})
        name = str(props.get("name", "param")).strip() or "param"
        if name in seen_names:
            continue   # deduplicate by name
        seen_names.add(name)
        public_vars.append({
            "name":        name,
            "varType":     _GLOBAL_VAR_TYPE.get(node_type, "string"),
            "default":     props.get("value", ""),
            "description": str(props.get("description", "")),
        })

    # Collect named triggers (trigger.* nodes — always included, slug used for API routes)
    triggers: list[dict] = []
    seen_slugs: set[str] = set()
    for node in workflow.get("nodes", []):
        t = node.get("type", "")
        if not t.startswith("trigger."):
            continue
        props = node.get("properties", {})
        name = str(props.get("name", "")).strip()
        if not name:
            name = node.get("label", t)
        # Build a URL-safe slug: lowercase, replace non-alphanum runs with dash
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        if not slug:
            slug = "trigger"
        # Deduplicate slugs
        base_slug, n = slug, 1
        while slug in seen_slugs:
            n += 1
            slug = f"{base_slug}-{n}"
        seen_slugs.add(slug)
        triggers.append({
            "id":   node["id"],
            "name": name,
            "slug": slug,
            "type": t,
        })

    return {
        "used_types":          sorted(used_types),
        "pip_deps":            sorted(pip_deps),
        "key_deps":            sorted(key_deps),
        "needs_aethviondb":    needs_aethviondb,
        "needs_ai":            needs_ai,
        "needs_api_key":       bool(key_deps),
        "has_live_db_search":  has_live_db_search,
        "has_snapshot_nodes":  bool(snapshot_nodes),
        "snapshot_nodes":      snapshot_nodes,
        "public_vars":         public_vars,
        "triggers":            triggers,
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


# Web UI HTML (lazy)
_html_template_cache: str | None = None


def _get_html_template() -> str:
    global _html_template_cache
    if _html_template_cache is None:
        _html_template_cache = (
            Path(__file__).parent.parent / "config" / "automate" / "standalone_ui.html"
        ).read_text(encoding="utf-8")
    return _html_template_cache


# run.py generator

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
# Shared AI model handler (used by ai.google and ai.any)
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
        code = _get_handler_code().get(ntype)
        if code:
            handler_blocks.append(code)

    # Build registry — function name derived from node type by convention
    registry_lines = []
    for ntype in sorted(used):
        if ntype in _get_handler_code():
            fn = "_h_" + ntype.replace(".", "_")
            registry_lines.append(f'    {repr(ntype)}: {fn},')

    # AI section
    ai_section = ""
    if needs_ai:
        ai_section = '''\
# Standalone AI client
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
    triggers         = analysis.get("triggers", [])
    triggers_json    = json.dumps(triggers, ensure_ascii=False)
    html_content     = _get_html_template().replace("%%NAME%%", wf_name)

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

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  # python-dotenv not installed — set env vars manually

# Utilities

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

def _output_summary(outputs: dict) -> str:
    """Return a short log preview of the most informative non-private output port.

    Pass 1: skip trivially-empty JSON (empty array/object) so nodes like
            search that return no results don't hide the error/count ports.
    Pass 2: if nothing useful was found in pass 1, fall back to any non-empty value.
    """
    if not outputs:
        return ""
    _TRIVIAL = frozenset({"[]", "{{}}", "null", "None"})
    def _fmt(port, s):
        preview = s[:80].replace("\\n", " ")
        return '[%s] "%s%s"' % (port, preview, "\\u2026" if len(s) > 80 else "")
    # Pass 1 — skip trivially-empty values
    for port, val in outputs.items():
        if port.startswith("_"):
            continue
        s = _to_str(val)
        if s and s not in _TRIVIAL:
            return _fmt(port, s)
    # Pass 2 — anything non-empty (catches counts, speeds, etc.)
    for port, val in outputs.items():
        if port.startswith("_"):
            continue
        s = _to_str(val)
        if s:
            return _fmt(port, s)
    return ""

# WorkflowExecutor

class WorkflowExecutor:
    def __init__(self, workflow: dict, variables: dict | None = None,
                 trigger_id: str | None = None) -> None:
        self.workflow    = workflow
        self.nodes: dict[str, dict] = {{n["id"]: n for n in workflow.get("nodes", [])}}
        self.connections = workflow.get("connections", [])
        self._outputs: dict[str, dict[str, Any]] = {{}}
        self._status:  dict[str, str] = {{}}
        self._errors:  dict[str, str] = {{}}
        self._log:     list[dict]     = []
        self._vars:    dict[str, Any] = dict(variables or {{}})  # pre-seed with injected values
        self._trigger_id: str | None  = trigger_id

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
                _summary = _output_summary(self._outputs[nid])
                if _summary:
                    self._info('  \\u2713 %s: %s' % (label, _summary))
                else:
                    self._info('  \\u2713 %s' % label)
            except Exception as exc:
                self._status[nid] = "error"
                self._errors[nid] = str(exc)
                self._error('  \\u2717 %s: %s' % (label, exc))
        errors = sum(1 for s in self._status.values() if s == "error")
        self._warn('Workflow finished with %d error(s).' % errors) if errors else self._info("Workflow completed successfully.")
        return self._build_result()

    def _reachable_from_triggers(self) -> set[str]:
        # Three-phase algorithm: forward from active trigger, then backward from
        # that set (stopping at other triggers' territory) to pull in data suppliers.
        fwd: dict[str, list[str]] = {{nid: [] for nid in self.nodes}}
        rev: dict[str, list[str]] = {{nid: [] for nid in self.nodes}}
        for c in self.connections:
            s, t = c.get("sourceNodeId"), c.get("targetNodeId")
            if s in self.nodes and t in self.nodes:
                fwd[s].append(t); rev[t].append(s)
        all_triggers = [nid for nid, n in self.nodes.items()
                        if n.get("type", "").startswith("trigger.")]
        def _fwd_bfs(seeds):
            vis = set(seeds); q = list(seeds)
            while q:
                nid = q.pop(0)
                for nb in fwd[nid]:
                    if nb not in vis: vis.add(nb); q.append(nb)
            return vis
        # Phase 1: forward from active seeds
        if self._trigger_id:
            active = [self._trigger_id] if self._trigger_id in self.nodes else []
        else:
            active = list(all_triggers)
        forward = _fwd_bfs(active)
        # Phase 2: other triggers' territory
        other = set()
        for t in all_triggers:
            if t not in active: other |= _fwd_bfs([t])
        # Phase 3: backward from forward set, blocked by triggers + other territory
        blocked   = set(all_triggers) | other
        reachable = set(forward)
        queue     = [nid for nid in forward if nid not in set(all_triggers)]
        while queue:
            nid = queue.pop(0)
            for up in rev[nid]:
                if up not in reachable and up not in blocked:
                    reachable.add(up); queue.append(up)
        return reachable

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

# Runtime state
_INPUT_OVERRIDES: dict[str, Any] = {{}}
_OUTPUT_RESULTS:  list[dict]     = []
_MEMORY_STORE:    dict[str, Any] = {{}}

{ai_section}
# Node handlers
{"".join(handler_blocks)}
# Handler registry
_REGISTRY: dict[str, Any] = {{
{"".join(registry_lines)}
}}

# Workflow
with open(Path(__file__).parent / "workflow.json", encoding="utf-8") as _f:
    _WORKFLOW = json.load(_f)

_INPUT_NODES = [n for n in _WORKFLOW.get("nodes", []) if n.get("type","").startswith("input.")]

# Public variables (baked in at compile time)
# Each entry: {{name, varType, default, description}}
_PUBLIC_VARS: list[dict] = {public_vars_json}

# Named triggers (baked in at compile time)
# Each entry: {{id, name, slug, type}}
_TRIGGERS: list[dict] = {triggers_json}

# FastAPI server
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
    # Build per-trigger endpoint entries dynamically
    trig_endpoints = []
    for _t in _TRIGGERS:
        trig_endpoints.append({{
            "method": "POST", "path": "/run/" + _t["slug"],
            "description": "Run from trigger: " + _t["name"],
            "body": {{"variables": {{"<name>": "<value>"}}}},
            "response": {{"ok": True, "log": [], "node_status": {{}}}},
        }})
        trig_endpoints.append({{
            "method": "GET", "path": "/stream/" + _t["slug"],
            "description": "SSE stream from trigger: " + _t["name"],
            "query_params": {{"variables": "JSON object mapping variable names to values"}},
            "events": [{{"level": "info|warning|error", "msg": "...", "ts": "..."}},
                       {{"done": True, "ok": True}}],
        }})
    schema = {{
        "workflow": {repr(wf_name)},
        "public_variables": _PUBLIC_VARS,
        "triggers": _TRIGGERS,
        "endpoints": [
            {{
                "method": "GET", "path": "/",
                "description": "Web dashboard — run the workflow interactively in a browser.",
            }},
            {{
                "method": "POST", "path": "/run",
                "description": "Run the workflow from all triggers and return the full result as JSON.",
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
                "description": "Server-Sent Events stream — receive log lines in real time (all triggers).",
                "query_params": {{
                    "variables": "JSON object mapping variable names to values",
                    "overrides": "JSON object mapping input-node IDs to values",
                }},
                "events": [
                    {{"level": "info | warning | error", "msg": "...", "ts": "..."}},
                    {{"done": True, "ok": True}},
                ],
            }},
        ] + trig_endpoints + [
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
                          "public_vars": [v["name"] for v in _PUBLIC_VARS],
                          "triggers": [{{"name": t["name"], "slug": t["slug"]}} for t in _TRIGGERS]}})

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

@app.post("/run/{{trigger_slug}}")
async def run_named_trigger(trigger_slug: str, request: Request):
    """Run from a specific named trigger. Available slugs: see /api/schema."""
    global _INPUT_OVERRIDES, _OUTPUT_RESULTS
    trig = next((t for t in _TRIGGERS if t["slug"] == trigger_slug), None)
    if trig is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Unknown trigger slug: " + trigger_slug +
                            ". Available: " + ", ".join(t["slug"] for t in _TRIGGERS))
    body = {{}}
    try: body = await request.json()
    except Exception: pass
    _INPUT_OVERRIDES = body.get("overrides", {{}})
    _var_overrides   = body.get("variables", {{}})
    _OUTPUT_RESULTS.clear()
    ex = WorkflowExecutor(_WORKFLOW, variables=_var_overrides, trigger_id=trig["id"])
    result = ex.execute()
    return JSONResponse(result)

@app.get("/stream/{{trigger_slug}}")
async def stream_named_trigger(trigger_slug: str, variables: str = "{{}}"):
    """SSE stream from a specific named trigger."""
    global _OUTPUT_RESULTS
    trig = next((t for t in _TRIGGERS if t["slug"] == trigger_slug), None)
    if trig is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Unknown trigger slug: " + trigger_slug)
    try: _var_ov = json.loads(variables)
    except Exception: _var_ov = {{}}
    _OUTPUT_RESULTS.clear()
    async def _named_ev():
        loop = asyncio.get_event_loop()
        def _run():
            ex = WorkflowExecutor(_WORKFLOW, variables=_var_ov, trigger_id=trig["id"])
            return ex, ex.execute()
        executor, result = await loop.run_in_executor(None, _run)
        for entry in executor._log:
            yield f"data: {{json.dumps(entry)}}\\n\\n"
            await asyncio.sleep(0)
        yield f"data: {{json.dumps({{'done': True, 'ok': result['ok']}})}}\\n\\n"
    return StreamingResponse(_named_ev(), media_type="text/event-stream",
                             headers={{"Cache-Control":"no-cache","X-Accel-Buffering":"no"}})

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
    if _TRIGGERS:
        print(f"  Triggers: {{', '.join(t['name'] for t in _TRIGGERS)}}")
        for t in _TRIGGERS:
            print(f"    POST /run/{{t['slug']}}  — {{t['name']}}")
    print(f"")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
'''

    return src


# Package downloader

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


# Public API

def compile_workflow(workflow: dict, options: dict) -> tuple[bytes, list[str]]:
    """
    Compile *workflow* into a zip bundle.

    Options:
        include_packages  (bool, default True)  — pip download wheels into packages/
        include_api_key   (bool, default False) — embed API keys from live .env
        include_snapshot  (bool, default False) — bundle AethvionDB snapshot .jsonl files

    Returns:
        (zip_bytes, warnings)  where warnings is a list of non-fatal messages.
    """
    include_packages = bool(options.get("include_packages", True))
    include_api_key  = bool(options.get("include_api_key",  False))
    include_snapshot = bool(options.get("include_snapshot", False))

    analysis    = _analyze_workflow(workflow)
    wf_name     = workflow.get("name", "Workflow")
    safe_name   = re.sub(r"[^\w\-]", "_", wf_name)
    warnings: list[str] = []

    # Warn about live AethvionDB Search nodes — they can't work in a bundle
    if analysis.get("has_live_db_search"):
        warnings.append(
            "This workflow contains AethvionDB Search nodes — these require a live "
            "database and will be skipped in the compiled bundle. "
            "Use AethvionDB Snapshot Search instead for offline use."
        )

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

        if include_snapshot and analysis.get("snapshot_nodes"):
            for snap in analysis["snapshot_nodes"]:
                snap_path_str = snap.get("path")
                if snap_path_str:
                    snap_path = Path(snap_path_str)
                    if snap_path.exists():
                        arc_path = (
                            prefix
                            + "data/aethviondb/"
                            + snap["db"]
                            + "/baked/"
                            + snap_path.name
                        )
                        zf.write(snap_path, arc_path)
                    else:
                        warnings.append(
                            f"Snapshot '{snap['snap_name']}' for database '{snap['db']}' "
                            "was not found on disk — it was not included in the bundle."
                        )
                else:
                    warnings.append(
                        f"No snapshot file found for database '{snap['db']}' "
                        "— it was not included in the bundle."
                    )

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
