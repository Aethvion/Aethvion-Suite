"""
core/automate/automate_routes.py
════════════════════════════════
Isolated Automate module backend.
Handles workflow CRUD, node type registry, model listing, and node test-execution.

The AI execution endpoint (node/test) imports ProviderManager lazily — it uses only
the call_with_failover() utility, sharing no workflow state with other modules.
"""
from __future__ import annotations

import datetime
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/automate", tags=["automate"])

# ── Storage ───────────────────────────────────────────────────────────────────

_DATA_DIR      = Path(__file__).parent.parent.parent / "data" / "automate" / "workflows"
_REGISTRY_PATH = Path(__file__).parent.parent.parent / "data" / "config" / "model_registry.json"

# Lazy ProviderManager singleton — only initialised when an AI node is tested
_pm = None

def _get_pm():
    global _pm
    if _pm is None:
        from core.providers.provider_manager import ProviderManager  # noqa: PLC0415
        _pm = ProviderManager()
    return _pm


def _ensure_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _wf_path(wf_id: str) -> Path:
    return _DATA_DIR / f"{wf_id}.json"


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── Node type registry ────────────────────────────────────────────────────────
# Fully self-contained — not imported from or dependent on any other module.

_NODE_TYPES: list[dict] = [
    # ── Triggers ──────────────────────────────────────────────────────────────
    {
        "type": "trigger.manual",
        "label": "Manual Trigger",
        "category": "Triggers",
        "icon": "fa-hand-pointer",
        "color": "#22d3ee",
        "inputs": [],
        "outputs": [{"name": "trigger", "label": "Trigger"}],
        "properties": [],
    },
    {
        "type": "trigger.schedule",
        "label": "Schedule",
        "category": "Triggers",
        "icon": "fa-clock",
        "color": "#22d3ee",
        "inputs": [],
        "outputs": [
            {"name": "trigger", "label": "Trigger"},
            {"name": "data",    "label": "Data"},
        ],
        "properties": [
            {
                "key": "schedules",
                "label": "Schedules",
                "type": "schedule_list",
                "default": [],
            },
        ],
    },
    {
        "type": "trigger.webhook",
        "label": "Webhook",
        "category": "Triggers",
        "icon": "fa-share-nodes",
        "color": "#22d3ee",
        "inputs": [],
        "outputs": [
            {"name": "out", "label": "Request"},
            {"name": "body", "label": "Body"},
        ],
        "properties": [
            {
                "key": "path",
                "label": "Path",
                "type": "text",
                "default": "/webhook",
                "placeholder": "/my-webhook",
            },
            {
                "key": "method",
                "label": "Method",
                "type": "select",
                "default": "POST",
                "options": ["GET", "POST", "PUT", "PATCH", "DELETE"],
            },
        ],
    },
    # ── Logic ─────────────────────────────────────────────────────────────────
    {
        "type": "logic.if",
        "label": "If / Else",
        "category": "Logic",
        "icon": "fa-code-branch",
        "color": "#a78bfa",
        "inputs": [{"name": "in", "label": "Input"}],
        "outputs": [
            {"name": "true", "label": "True"},
            {"name": "false", "label": "False"},
        ],
        "properties": [
            {
                "key": "condition",
                "label": "Condition",
                "type": "text",
                "default": "",
                "placeholder": "value == 'expected'",
            },
        ],
    },
    {
        "type": "logic.delay",
        "label": "Delay",
        "category": "Logic",
        "icon": "fa-hourglass-half",
        "color": "#a78bfa",
        "inputs": [{"name": "in", "label": "Input"}],
        "outputs": [{"name": "out", "label": "After Delay"}],
        "properties": [
            {
                "key": "duration",
                "label": "Duration (ms)",
                "type": "number",
                "default": 1000,
            },
        ],
    },
    {
        "type": "logic.loop",
        "label": "Loop",
        "category": "Logic",
        "icon": "fa-rotate",
        "color": "#a78bfa",
        "inputs": [{"name": "in", "label": "Items"}],
        "outputs": [
            {"name": "item", "label": "Each Item"},
            {"name": "done", "label": "Done"},
        ],
        "properties": [
            {
                "key": "max_iterations",
                "label": "Max Iterations",
                "type": "number",
                "default": 100,
            },
        ],
    },
    # ── Actions ───────────────────────────────────────────────────────────────
    {
        "type": "action.http",
        "label": "HTTP Request",
        "category": "Actions",
        "icon": "fa-globe",
        "color": "#34d399",
        "inputs": [{"name": "in", "label": "Trigger"}],
        "outputs": [
            {"name": "out", "label": "Response"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "url",
                "label": "URL",
                "type": "text",
                "default": "",
                "placeholder": "https://example.com/api",
            },
            {
                "key": "method",
                "label": "Method",
                "type": "select",
                "default": "GET",
                "options": ["GET", "POST", "PUT", "PATCH", "DELETE"],
            },
            {
                "key": "headers",
                "label": "Headers (JSON)",
                "type": "textarea",
                "default": "{}",
            },
            {
                "key": "body",
                "label": "Body",
                "type": "textarea",
                "default": "",
                "placeholder": "Request body (JSON or plain text)",
            },
        ],
    },
    {
        "type": "action.run_script",
        "label": "Run Script",
        "category": "Actions",
        "icon": "fa-terminal",
        "color": "#34d399",
        "inputs": [{"name": "in", "label": "Trigger"}],
        "outputs": [
            {"name": "out", "label": "Result"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "script",
                "label": "Python Script",
                "type": "code",
                "default": "# Access input via `input_data`\nresult = input_data",
            },
        ],
    },
    {
        "type": "action.log",
        "label": "Log",
        "category": "Actions",
        "icon": "fa-file-lines",
        "color": "#34d399",
        "inputs": [{"name": "in", "label": "Input"}],
        "outputs": [{"name": "out", "label": "Pass-through"}],
        "properties": [
            {
                "key": "message",
                "label": "Message",
                "type": "text",
                "default": "{{input}}",
                "placeholder": "Log message…",
            },
            {
                "key": "level",
                "label": "Level",
                "type": "select",
                "default": "info",
                "options": ["debug", "info", "warning", "error"],
            },
        ],
    },
    # ── Data ──────────────────────────────────────────────────────────────────
    {
        "type": "data.format_text",
        "label": "Format Text",
        "category": "Data",
        "icon": "fa-font",
        "color": "#fb923c",
        "inputs": [{"name": "in", "label": "Input"}],
        "outputs": [{"name": "out", "label": "Text"}],
        "properties": [
            {
                "key": "template",
                "label": "Template",
                "type": "textarea",
                "default": "{{input}}",
                "placeholder": "Hello {{name}}!",
            },
        ],
    },
    {
        "type": "data.parse_json",
        "label": "Parse JSON",
        "category": "Data",
        "icon": "fa-code",
        "color": "#fb923c",
        "inputs": [{"name": "in", "label": "JSON String"}],
        "outputs": [
            {"name": "out", "label": "Parsed"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [],
    },
    {
        "type": "data.set_variable",
        "label": "Set Variable",
        "category": "Data",
        "icon": "fa-box",
        "color": "#fb923c",
        "inputs": [{"name": "in", "label": "Value"}],
        "outputs": [{"name": "out", "label": "Value"}],
        "properties": [
            {
                "key": "name",
                "label": "Variable Name",
                "type": "text",
                "default": "myVar",
                "placeholder": "myVar",
            },
        ],
    },
    {
        "type": "data.filter",
        "label": "Filter",
        "category": "Data",
        "icon": "fa-filter",
        "color": "#fb923c",
        "inputs": [{"name": "in", "label": "List"}],
        "outputs": [
            {"name": "match", "label": "Matching"},
            {"name": "rest", "label": "Rest"},
        ],
        "properties": [
            {
                "key": "expression",
                "label": "Filter Expression",
                "type": "text",
                "default": "",
                "placeholder": "item.status == 'active'",
            },
        ],
    },
    # ── Inputs ────────────────────────────────────────────────────────────────
    {
        "type": "input.text",
        "label": "Text Input",
        "category": "Inputs",
        "icon": "fa-keyboard",
        "color": "#94a3b8",
        "inputs": [],
        "outputs": [{"name": "out", "label": "Text"}],
        "properties": [
            {
                "key": "value",
                "label": "Text Value",
                "type": "textarea",
                "default": "",
                "placeholder": "Enter text here…",
            },
        ],
    },
    {
        "type": "input.number",
        "label": "Number Input",
        "category": "Inputs",
        "icon": "fa-hashtag",
        "color": "#94a3b8",
        "inputs": [],
        "outputs": [{"name": "out", "label": "Number"}],
        "properties": [
            {
                "key": "value",
                "label": "Value",
                "type": "number",
                "default": 0,
            },
        ],
    },
    # ── Outputs ───────────────────────────────────────────────────────────────
    {
        "type": "output.display",
        "label": "Display",
        "category": "Outputs",
        "icon": "fa-eye",
        "color": "#e879f9",
        "inputs": [{"name": "in", "label": "Data"}],
        "outputs": [],
        "properties": [
            {
                "key": "label",
                "label": "Display Label",
                "type": "text",
                "default": "Result",
                "placeholder": "Result label…",
            },
        ],
    },
    # ── AI ────────────────────────────────────────────────────────────────────
    {
        "type": "ai.google",
        "label": "Google AI",
        "category": "AI",
        "icon": "fa-brain",
        "color": "#4ade80",
        "inputs": [
            {"name": "in",            "label": "Input Data"},
            {"name": "model",         "label": "Model"},
            {"name": "system_prompt", "label": "System Prompt"},
            {"name": "prompt_prefix", "label": "Prefix"},
            {"name": "prompt_suffix", "label": "Suffix"},
            {"name": "temperature",   "label": "Temperature"},
        ],
        "outputs": [
            {"name": "out", "label": "Response"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "model",
                "label": "Model",
                "type": "model_select",
                "source": "/api/automate/models?provider=google_ai",
                "default": "",
                "placeholder": "Select a Google AI model…",
            },
            {
                "key": "system_prompt",
                "label": "System Prompt",
                "type": "textarea",
                "default": "You are a helpful assistant.",
                "placeholder": "System instructions for the AI…",
            },
            {
                "key": "prompt_prefix",
                "label": "Prompt Prefix",
                "type": "textarea",
                "default": "",
                "placeholder": "Text added before the input data…",
            },
            {
                "key": "prompt_suffix",
                "label": "Prompt Suffix",
                "type": "textarea",
                "default": "",
                "placeholder": "Text added after the input data…",
            },
            {
                "key": "temperature",
                "label": "Temperature",
                "type": "number",
                "default": 0.7,
            },
            {
                "key": "show_result",
                "label": "Show Result on Node",
                "type": "toggle",
                "default": True,
            },
        ],
    },
    {
        "type": "ai.any",
        "label": "AI Model",
        "category": "AI",
        "icon": "fa-robot",
        "color": "#60a5fa",
        "inputs": [
            {"name": "in",            "label": "Input Data"},
            {"name": "model",         "label": "Model"},
            {"name": "system_prompt", "label": "System Prompt"},
            {"name": "prompt_prefix", "label": "Prefix"},
            {"name": "prompt_suffix", "label": "Suffix"},
            {"name": "temperature",   "label": "Temperature"},
        ],
        "outputs": [
            {"name": "out", "label": "Response"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "model",
                "label": "Model",
                "type": "model_select",
                "source": "/api/automate/models",
                "default": "",
                "placeholder": "Select any configured model…",
            },
            {
                "key": "system_prompt",
                "label": "System Prompt",
                "type": "textarea",
                "default": "",
                "placeholder": "System instructions for the AI…",
            },
            {
                "key": "prompt_prefix",
                "label": "Prompt Prefix",
                "type": "textarea",
                "default": "",
                "placeholder": "Text added before the input data…",
            },
            {
                "key": "prompt_suffix",
                "label": "Prompt Suffix",
                "type": "textarea",
                "default": "",
                "placeholder": "Text added after the input data…",
            },
            {
                "key": "temperature",
                "label": "Temperature",
                "type": "number",
                "default": 0.7,
            },
            {
                "key": "show_result",
                "label": "Show Result on Node",
                "type": "toggle",
                "default": True,
            },
        ],
    },
    {
        "type": "transform.combine",
        "label": "Combine Text",
        "category": "Data",
        "icon": "fa-compress-arrows-alt",
        "color": "#fb923c",
        "inputs": [
            {"name": "a", "label": "Text A"},
            {"name": "b", "label": "Text B"},
        ],
        "outputs": [{"name": "out", "label": "Combined"}],
        "properties": [
            {
                "key": "separator",
                "label": "Separator",
                "type": "text",
                "default": "\\n",
                "placeholder": "\\n or space or custom…",
            },
        ],
    },
    # ── Sprint 1: Data ────────────────────────────────────────────────────────
    {
        "type": "data.template",
        "label": "Template",
        "category": "Data",
        "icon": "fa-file-code",
        "color": "#fb923c",
        "inputs": [
            {"name": "in",    "label": "Data Object"},
            {"name": "var_a", "label": "Variable A"},
            {"name": "var_b", "label": "Variable B"},
            {"name": "var_c", "label": "Variable C"},
        ],
        "outputs": [
            {"name": "out",   "label": "Rendered Text"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "template",
                "label": "Template",
                "type": "textarea",
                "default": "",
                "placeholder": "Hello {{name}}! You live in {{city|unknown}}.",
            },
        ],
    },
    {
        "type": "data.extract_json",
        "label": "Extract JSON",
        "category": "Data",
        "icon": "fa-magnifying-glass",
        "color": "#fb923c",
        "inputs": [{"name": "in", "label": "JSON Input"}],
        "outputs": [
            {"name": "out",   "label": "Value"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "key",
                "label": "Key Path",
                "type": "text",
                "default": "",
                "placeholder": "user.address.city",
            },
            {
                "key": "default",
                "label": "Default Value",
                "type": "text",
                "default": "",
                "placeholder": "(empty = error if key missing)",
            },
            {
                "key": "output_as",
                "label": "Output As",
                "type": "select",
                "default": "auto",
                "options": ["auto", "string", "json"],
            },
        ],
    },
    {
        "type": "data.type_convert",
        "label": "Type Convert",
        "category": "Data",
        "icon": "fa-arrows-left-right",
        "color": "#fb923c",
        "inputs": [{"name": "in", "label": "Input"}],
        "outputs": [
            {"name": "out",   "label": "Converted"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "to",
                "label": "Convert To",
                "type": "select",
                "default": "string",
                "options": ["string", "integer", "float", "boolean", "json"],
            },
            {
                "key": "true_values",
                "label": "True Values",
                "type": "text",
                "default": "true,yes,1,on",
            },
            {
                "key": "false_values",
                "label": "False Values",
                "type": "text",
                "default": "false,no,0,off",
            },
        ],
    },
    # ── Sprint 2: Memory ─────────────────────────────────────────────────────
    {
        "type": "memory.store",
        "label": "Memory Store",
        "category": "Memory",
        "icon": "fa-database",
        "color": "#f59e0b",
        "inputs": [
            {"name": "in",  "label": "Value"},
            {"name": "key", "label": "Key Override"},
        ],
        "outputs": [
            {"name": "out",   "label": "Pass-through"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "key",
                "label": "Storage Key",
                "type": "text",
                "default": "",
                "placeholder": "myworkflow.result",
            },
            {
                "key": "scope",
                "label": "Scope",
                "type": "select",
                "default": "global",
                "options": ["global", "workflow"],
            },
            {
                "key": "ttl",
                "label": "TTL (hours)",
                "type": "number",
                "default": 0,
            },
        ],
    },
    {
        "type": "memory.retrieve",
        "label": "Memory Retrieve",
        "category": "Memory",
        "icon": "fa-memory",
        "color": "#f59e0b",
        "inputs": [],
        "outputs": [
            {"name": "out",   "label": "Value"},
            {"name": "found", "label": "Found"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "key",
                "label": "Storage Key",
                "type": "text",
                "default": "",
                "placeholder": "myworkflow.result",
            },
            {
                "key": "scope",
                "label": "Scope",
                "type": "select",
                "default": "global",
                "options": ["global", "workflow"],
            },
            {
                "key": "default",
                "label": "Default Value",
                "type": "text",
                "default": "",
            },
        ],
    },
    # ── Sprint 2: Logic ───────────────────────────────────────────────────────
    {
        "type": "logic.try_catch",
        "label": "Try / Catch",
        "category": "Logic",
        "icon": "fa-shield-halved",
        "color": "#a78bfa",
        "inputs": [
            {"name": "in",       "label": "Input"},
            {"name": "error_in", "label": "Error Input"},
        ],
        "outputs": [
            {"name": "try",    "label": "Try (success)"},
            {"name": "catch",  "label": "Catch (error)"},
            {"name": "always", "label": "Always"},
        ],
        "properties": [
            {
                "key": "error_contains",
                "label": "Error Filter",
                "type": "text",
                "default": "",
                "placeholder": "(blank = catch all errors)",
            },
        ],
    },
    {
        "type": "logic.switch",
        "label": "Switch",
        "category": "Logic",
        "icon": "fa-shuffle",
        "color": "#a78bfa",
        "inputs": [{"name": "in", "label": "Input"}],
        "outputs": [
            {"name": "case_1",  "label": "Case 1"},
            {"name": "case_2",  "label": "Case 2"},
            {"name": "case_3",  "label": "Case 3"},
            {"name": "case_4",  "label": "Case 4"},
            {"name": "default", "label": "Default"},
        ],
        "properties": [
            {
                "key": "switch_on",
                "label": "Switch On (JSON key)",
                "type": "text",
                "default": "",
                "placeholder": "(blank = compare raw input string)",
            },
            {
                "key": "num_cases",
                "label": "Number of Cases",
                "type": "number",
                "default": 2,
            },
            {"key": "case_1", "label": "Case 1 Value", "type": "text", "default": ""},
            {"key": "case_2", "label": "Case 2 Value", "type": "text", "default": ""},
            {"key": "case_3", "label": "Case 3 Value", "type": "text", "default": ""},
            {"key": "case_4", "label": "Case 4 Value", "type": "text", "default": ""},
        ],
    },
    {
        "type": "logic.merge",
        "label": "Merge",
        "category": "Logic",
        "icon": "fa-code-merge",
        "color": "#a78bfa",
        "inputs": [
            {"name": "a", "label": "Branch A"},
            {"name": "b", "label": "Branch B"},
            {"name": "c", "label": "Branch C"},
            {"name": "d", "label": "Branch D"},
        ],
        "outputs": [
            {"name": "out",    "label": "Output"},
            {"name": "source", "label": "Source Port"},
        ],
        "properties": [
            {
                "key": "num_inputs",
                "label": "Number of Inputs",
                "type": "number",
                "default": 2,
            },
            {
                "key": "mode",
                "label": "Mode",
                "type": "select",
                "default": "first",
                "options": ["first", "all"],
            },
        ],
    },
    # ── Sprint 2: Data ────────────────────────────────────────────────────────
    {
        "type": "data.split_text",
        "label": "Split Text",
        "category": "Data",
        "icon": "fa-scissors",
        "color": "#fb923c",
        "inputs": [{"name": "in", "label": "Text"}],
        "outputs": [
            {"name": "out",   "label": "All Parts"},
            {"name": "first", "label": "First Part"},
            {"name": "last",  "label": "Last Part"},
            {"name": "count", "label": "Count"},
        ],
        "properties": [
            {
                "key": "mode",
                "label": "Split Mode",
                "type": "select",
                "default": "delimiter",
                "options": ["delimiter", "lines", "words", "chunks"],
            },
            {
                "key": "delimiter",
                "label": "Delimiter",
                "type": "text",
                "default": ",",
            },
            {
                "key": "chunk_size",
                "label": "Chunk Size",
                "type": "number",
                "default": 500,
            },
            {
                "key": "trim",
                "label": "Trim Parts",
                "type": "toggle",
                "default": True,
            },
            {
                "key": "remove_empty",
                "label": "Remove Empty Parts",
                "type": "toggle",
                "default": True,
            },
        ],
    },
    {
        "type": "data.regex",
        "label": "Regex",
        "category": "Data",
        "icon": "fa-asterisk",
        "color": "#fb923c",
        "inputs": [
            {"name": "in",      "label": "Text Input"},
            {"name": "pattern", "label": "Pattern Override"},
        ],
        "outputs": [
            {"name": "out",     "label": "Result"},
            {"name": "matches", "label": "All Matches"},
            {"name": "matched", "label": "Did Match"},
            {"name": "error",   "label": "Error"},
        ],
        "properties": [
            {
                "key": "pattern",
                "label": "Pattern",
                "type": "text",
                "default": "",
                "placeholder": "(\\w+)",
            },
            {
                "key": "mode",
                "label": "Mode",
                "type": "select",
                "default": "extract",
                "options": ["match", "extract", "replace"],
            },
            {
                "key": "replacement",
                "label": "Replacement",
                "type": "text",
                "default": "",
                "placeholder": "\\1",
            },
            {
                "key": "flags",
                "label": "Flags",
                "type": "text",
                "default": "",
                "placeholder": "i / m / s",
            },
            {
                "key": "all_matches",
                "label": "Return All Matches",
                "type": "toggle",
                "default": False,
            },
        ],
    },
    # ── Sprint 1: Actions ─────────────────────────────────────────────────────
    {
        "type": "action.file_read",
        "label": "File Read",
        "category": "Actions",
        "icon": "fa-file-arrow-up",
        "color": "#34d399",
        "inputs": [
            {"name": "in",   "label": "Trigger"},
            {"name": "path", "label": "File Path"},
        ],
        "outputs": [
            {"name": "out",   "label": "File Content"},
            {"name": "path",  "label": "Resolved Path"},
            {"name": "size",  "label": "File Size"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "path",
                "label": "File Path",
                "type": "text",
                "default": "",
                "placeholder": "C:/Users/me/document.txt",
                "picker": "file",
            },
            {
                "key": "encoding",
                "label": "Encoding",
                "type": "select",
                "default": "utf-8",
                "options": ["utf-8", "latin-1", "ascii", "binary"],
            },
            {
                "key": "strip",
                "label": "Strip Whitespace",
                "type": "toggle",
                "default": False,
            },
            {
                "key": "max_bytes",
                "label": "Max Size (bytes)",
                "type": "number",
                "default": 0,
            },
        ],
    },
    {
        "type": "action.file_write",
        "label": "File Write",
        "category": "Actions",
        "icon": "fa-file-arrow-down",
        "color": "#34d399",
        "inputs": [
            {"name": "in",   "label": "Content"},
            {"name": "path", "label": "File Path Override"},
        ],
        "outputs": [
            {"name": "out",   "label": "Pass-through"},
            {"name": "path",  "label": "Written Path"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "path",
                "label": "File Path",
                "type": "text",
                "default": "",
                "placeholder": "C:/Users/me/output.txt",
                "picker": "file",
            },
            {
                "key": "mode",
                "label": "Write Mode",
                "type": "select",
                "default": "overwrite",
                "options": ["overwrite", "append", "prepend"],
            },
            {
                "key": "encoding",
                "label": "Encoding",
                "type": "select",
                "default": "utf-8",
                "options": ["utf-8", "latin-1", "ascii"],
            },
            {
                "key": "newline",
                "label": "Add Trailing Newline",
                "type": "toggle",
                "default": True,
            },
            {
                "key": "create_dirs",
                "label": "Create Missing Directories",
                "type": "toggle",
                "default": True,
            },
        ],
    },
    {
        "type": "action.notify",
        "label": "Notify",
        "category": "Actions",
        "icon": "fa-bell",
        "color": "#34d399",
        "inputs": [
            {"name": "in",      "label": "Input"},
            {"name": "title",   "label": "Title Override"},
            {"name": "message", "label": "Message Override"},
        ],
        "outputs": [
            {"name": "out",   "label": "Pass-through"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "title",
                "label": "Notification Title",
                "type": "text",
                "default": "Aethvion",
            },
            {
                "key": "message",
                "label": "Message",
                "type": "textarea",
                "default": "Workflow completed.",
                "placeholder": "Use {{input}} to include the input value.",
            },
            {
                "key": "sound",
                "label": "Play Sound",
                "type": "toggle",
                "default": False,
            },
        ],
    },
    # ── Sprint 3: Inputs ──────────────────────────────────────────────────────
    {
        "type": "input.file",
        "label": "File Input",
        "category": "Inputs",
        "icon": "fa-file-import",
        "color": "#94a3b8",
        "inputs": [],
        "outputs": [
            {"name": "out",  "label": "File Content"},
            {"name": "path", "label": "File Path"},
            {"name": "name", "label": "File Name"},
            {"name": "size", "label": "File Size"},
        ],
        "properties": [
            {
                "key": "path",
                "label": "File Path",
                "type": "text",
                "default": "",
                "placeholder": "C:/path/to/file.txt",
                "picker": "file",
            },
            {
                "key": "encoding",
                "label": "Encoding",
                "type": "select",
                "default": "utf-8",
                "options": ["utf-8", "latin-1", "ascii", "binary"],
            },
            {
                "key": "strip",
                "label": "Strip Whitespace",
                "type": "toggle",
                "default": False,
            },
        ],
    },
    {
        "type": "input.list",
        "label": "List Input",
        "category": "Inputs",
        "icon": "fa-list",
        "color": "#94a3b8",
        "inputs": [],
        "outputs": [
            {"name": "out",   "label": "List"},
            {"name": "count", "label": "Count"},
            {"name": "first", "label": "First"},
        ],
        "properties": [
            {
                "key": "items",
                "label": "Items (one per line)",
                "type": "textarea",
                "default": "",
                "placeholder": "item one\nitem two\nitem three",
            },
            {
                "key": "trim",
                "label": "Trim Items",
                "type": "toggle",
                "default": True,
            },
            {
                "key": "remove_empty",
                "label": "Remove Empty Lines",
                "type": "toggle",
                "default": True,
            },
        ],
    },
    # ── Sprint 3: Outputs ─────────────────────────────────────────────────────
    {
        "type": "output.file",
        "label": "File Output",
        "category": "Outputs",
        "icon": "fa-file-export",
        "color": "#e879f9",
        "inputs": [{"name": "in", "label": "Data"}],
        "outputs": [],
        "properties": [
            {
                "key": "path",
                "label": "Output File Path",
                "type": "text",
                "default": "",
                "placeholder": "C:/output/result_{{timestamp}}.txt",
                "picker": "folder",
            },
            {
                "key": "mode",
                "label": "Write Mode",
                "type": "select",
                "default": "overwrite",
                "options": ["overwrite", "append", "new_file"],
            },
            {
                "key": "encoding",
                "label": "Encoding",
                "type": "select",
                "default": "utf-8",
                "options": ["utf-8", "latin-1", "ascii"],
            },
            {
                "key": "format",
                "label": "Auto Format",
                "type": "select",
                "default": "auto",
                "options": ["auto", "json_pretty", "lines"],
            },
            {
                "key": "create_dirs",
                "label": "Create Missing Directories",
                "type": "toggle",
                "default": True,
            },
        ],
    },
    {
        "type": "output.clipboard",
        "label": "Clipboard Output",
        "category": "Outputs",
        "icon": "fa-clipboard-check",
        "color": "#e879f9",
        "inputs": [{"name": "in", "label": "Data"}],
        "outputs": [],
        "properties": [
            {
                "key": "format",
                "label": "Format",
                "type": "select",
                "default": "auto",
                "options": ["auto", "json_pretty", "trim"],
            },
            {
                "key": "notify",
                "label": "Show Notification",
                "type": "toggle",
                "default": True,
            },
        ],
    },
    # ── Sprint 3: Actions ─────────────────────────────────────────────────────
    {
        "type": "action.clipboard",
        "label": "Clipboard",
        "category": "Actions",
        "icon": "fa-clipboard",
        "color": "#34d399",
        "inputs": [{"name": "in", "label": "Text to Copy"}],
        "outputs": [
            {"name": "out",   "label": "Clipboard Content"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "mode",
                "label": "Mode",
                "type": "select",
                "default": "write",
                "options": ["write", "read", "read_then_clear"],
            },
        ],
    },
    # ── Sprint 3: Data ────────────────────────────────────────────────────────
    {
        "type": "data.merge_objects",
        "label": "Merge Objects",
        "category": "Data",
        "icon": "fa-object-group",
        "color": "#fb923c",
        "inputs": [
            {"name": "a", "label": "Object A"},
            {"name": "b", "label": "Object B"},
            {"name": "c", "label": "Object C"},
            {"name": "d", "label": "Object D"},
        ],
        "outputs": [
            {"name": "out",   "label": "Merged Object"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "merge_mode",
                "label": "Merge Mode",
                "type": "select",
                "default": "shallow",
                "options": ["shallow", "deep"],
            },
            {
                "key": "output_as",
                "label": "Output As",
                "type": "select",
                "default": "json_string",
                "options": ["json_string", "object"],
            },
        ],
    },
    {
        "type": "data.list_item",
        "label": "List Item",
        "category": "Data",
        "icon": "fa-list-ol",
        "color": "#fb923c",
        "inputs": [
            {"name": "in",    "label": "List"},
            {"name": "index", "label": "Index Override"},
        ],
        "outputs": [
            {"name": "out",   "label": "Item"},
            {"name": "count", "label": "Count"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "index",
                "label": "Index",
                "type": "number",
                "default": 0,
            },
            {
                "key": "slice_end",
                "label": "Slice End (optional, 0 = disabled)",
                "type": "number",
                "default": 0,
            },
        ],
    },
    # ── Sprint 3: AI ──────────────────────────────────────────────────────────
    {
        "type": "ai.summarize",
        "label": "Summarize",
        "category": "AI",
        "icon": "fa-compress",
        "color": "#4ade80",
        "inputs": [
            {"name": "in",     "label": "Text to Summarize"},
            {"name": "model",  "label": "Model Override"},
            {"name": "length", "label": "Length Override"},
        ],
        "outputs": [
            {"name": "out",   "label": "Summary"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "model",
                "label": "Model",
                "type": "model_select",
                "source": "/api/automate/models",
                "default": "",
                "placeholder": "Select a model…",
            },
            {
                "key": "style",
                "label": "Summary Style",
                "type": "select",
                "default": "paragraph",
                "options": ["paragraph", "bullets", "headline", "tldr"],
            },
            {
                "key": "length",
                "label": "Length",
                "type": "select",
                "default": "medium",
                "options": ["short", "medium", "long"],
            },
            {
                "key": "language",
                "label": "Output Language",
                "type": "text",
                "default": "",
                "placeholder": "English / Dutch / … (blank = match input)",
            },
            {
                "key": "show_result",
                "label": "Show Result on Node",
                "type": "toggle",
                "default": True,
            },
        ],
    },
    {
        "type": "ai.classify",
        "label": "Classify",
        "category": "AI",
        "icon": "fa-tags",
        "color": "#4ade80",
        "inputs": [
            {"name": "in",     "label": "Text to Classify"},
            {"name": "model",  "label": "Model Override"},
            {"name": "labels", "label": "Labels Override"},
        ],
        "outputs": [
            {"name": "label",     "label": "Matched Label"},
            {"name": "reasoning", "label": "Reasoning"},
            {"name": "all",       "label": "All Results"},
            {"name": "error",     "label": "Error"},
        ],
        "properties": [
            {
                "key": "model",
                "label": "Model",
                "type": "model_select",
                "source": "/api/automate/models",
                "default": "",
                "placeholder": "Select a model…",
            },
            {
                "key": "labels",
                "label": "Categories (comma-separated)",
                "type": "textarea",
                "default": "",
                "placeholder": "positive, negative, neutral",
            },
            {
                "key": "context",
                "label": "Classification Context",
                "type": "textarea",
                "default": "",
                "placeholder": "Classify the sentiment of customer support emails.",
            },
            {
                "key": "show_result",
                "label": "Show Result on Node",
                "type": "toggle",
                "default": True,
            },
        ],
    },
    {
        "type": "ai.extract_data",
        "label": "Extract Data",
        "category": "AI",
        "icon": "fa-wand-magic-sparkles",
        "color": "#4ade80",
        "inputs": [
            {"name": "in",     "label": "Text to Extract From"},
            {"name": "model",  "label": "Model Override"},
            {"name": "schema", "label": "Schema Override"},
        ],
        "outputs": [
            {"name": "out",   "label": "Extracted JSON"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "model",
                "label": "Model",
                "type": "model_select",
                "source": "/api/automate/models",
                "default": "",
                "placeholder": "Select a model…",
            },
            {
                "key": "fields",
                "label": "Fields to Extract (one per line: name: description)",
                "type": "textarea",
                "default": "",
                "placeholder": "name: Full name of the person\ndate: Date in ISO format\namount: Dollar amount as a number",
            },
            {
                "key": "context",
                "label": "Context",
                "type": "textarea",
                "default": "",
                "placeholder": "This is a customer support email.",
            },
            {
                "key": "missing_value",
                "label": "Missing Value",
                "type": "text",
                "default": "",
                "placeholder": "(blank = empty string for missing fields)",
            },
            {
                "key": "show_result",
                "label": "Show Result on Node",
                "type": "toggle",
                "default": True,
            },
        ],
    },
    # ── Sprint 5: Triggers ────────────────────────────────────────────────────
    {
        "type": "trigger.app_event",
        "label": "App Event",
        "category": "Triggers",
        "icon": "fa-bolt",
        "color": "#22d3ee",
        "inputs": [],
        "outputs": [
            {"name": "trigger",    "label": "Trigger"},
            {"name": "event_type", "label": "Event Type"},
            {"name": "source",     "label": "Source"},
            {"name": "data",       "label": "Event Data"},
        ],
        "properties": [
            {
                "key": "event_type",
                "label": "Event Type Filter",
                "type": "select",
                "default": "any",
                "options": ["any", "companion.message", "agent.completed",
                            "memory.written", "workflow.completed", "custom"],
            },
            {
                "key": "source",
                "label": "Source Filter",
                "type": "text",
                "default": "",
                "placeholder": "(blank = all sources)",
            },
        ],
    },
    # ── Sprint 4: Triggers ────────────────────────────────────────────────────
    {
        "type": "trigger.file_watch",
        "label": "File Watch",
        "category": "Triggers",
        "icon": "fa-folder-open",
        "color": "#22d3ee",
        "inputs": [],
        "outputs": [
            {"name": "trigger", "label": "Trigger"},
            {"name": "path",    "label": "Changed Path"},
            {"name": "event",   "label": "Event Type"},
        ],
        "properties": [
            {
                "key": "path",
                "label": "Watch Path",
                "type": "text",
                "default": "",
                "placeholder": "C:/path/to/folder or file",
                "picker": "folder",
            },
            {
                "key": "watch_mode",
                "label": "Watch Mode",
                "type": "select",
                "default": "directory",
                "options": ["file", "directory"],
            },
            {
                "key": "event_types",
                "label": "Event Types",
                "type": "text",
                "default": "created,modified,deleted",
                "placeholder": "created, modified, deleted",
            },
            {
                "key": "recursive",
                "label": "Watch Subdirectories",
                "type": "toggle",
                "default": False,
            },
        ],
    },
    # ── Sprint 4: Logic ───────────────────────────────────────────────────────
    {
        "type": "logic.repeat",
        "label": "Repeat",
        "category": "Logic",
        "icon": "fa-repeat",
        "color": "#a78bfa",
        "inputs": [{"name": "in", "label": "Input"}],
        "outputs": [
            {"name": "out",   "label": "Repeated List"},
            {"name": "count", "label": "Count"},
        ],
        "properties": [
            {
                "key": "count",
                "label": "Repeat Count",
                "type": "number",
                "default": 3,
            },
        ],
    },
    # ── Sprint 4: Data ────────────────────────────────────────────────────────
    {
        "type": "data.csv_parse",
        "label": "CSV Parse",
        "category": "Data",
        "icon": "fa-table",
        "color": "#fb923c",
        "inputs": [{"name": "in", "label": "CSV Text"}],
        "outputs": [
            {"name": "out",     "label": "Parsed Data"},
            {"name": "rows",    "label": "Row Count"},
            {"name": "headers", "label": "Headers"},
            {"name": "error",   "label": "Error"},
        ],
        "properties": [
            {
                "key": "delimiter",
                "label": "Delimiter",
                "type": "text",
                "default": ",",
                "placeholder": ", or ; or \\t",
            },
            {
                "key": "has_header",
                "label": "First Row is Header",
                "type": "toggle",
                "default": True,
            },
            {
                "key": "output_as",
                "label": "Output As",
                "type": "select",
                "default": "objects",
                "options": ["objects", "arrays"],
            },
            {
                "key": "skip_empty_rows",
                "label": "Skip Empty Rows",
                "type": "toggle",
                "default": True,
            },
        ],
    },
    # ── Sprint 4: Actions ─────────────────────────────────────────────────────
    {
        "type": "action.run_command",
        "label": "Run Command",
        "category": "Actions",
        "icon": "fa-square-terminal",
        "color": "#34d399",
        "inputs": [
            {"name": "in",  "label": "Trigger"},
            {"name": "cmd", "label": "Command Override"},
        ],
        "outputs": [
            {"name": "out",       "label": "stdout"},
            {"name": "stderr",    "label": "stderr"},
            {"name": "exit_code", "label": "Exit Code"},
            {"name": "error",     "label": "Error"},
        ],
        "properties": [
            {
                "key": "command",
                "label": "Command",
                "type": "text",
                "default": "",
                "placeholder": "python script.py --arg value",
            },
            {
                "key": "working_dir",
                "label": "Working Directory",
                "type": "text",
                "default": "",
                "placeholder": "C:/my/project (blank = current dir)",
                "picker": "folder",
            },
            {
                "key": "shell",
                "label": "Run via Shell",
                "type": "toggle",
                "default": False,
            },
            {
                "key": "timeout",
                "label": "Timeout (seconds)",
                "type": "number",
                "default": 30,
            },
        ],
    },
    {
        "type": "action.file_list",
        "label": "File List",
        "category": "Actions",
        "icon": "fa-folder-tree",
        "color": "#34d399",
        "inputs": [
            {"name": "path", "label": "Folder Path Override"},
        ],
        "outputs": [
            {"name": "out",   "label": "File List"},
            {"name": "count", "label": "Count"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "path",
                "label": "Folder Path",
                "type": "text",
                "default": "",
                "placeholder": "C:/path/to/folder",
                "picker": "folder",
            },
            {
                "key": "pattern",
                "label": "File Pattern (glob)",
                "type": "text",
                "default": "*",
                "placeholder": "*.txt or *.{jpg,png}",
            },
            {
                "key": "recursive",
                "label": "Search Recursively",
                "type": "toggle",
                "default": False,
            },
            {
                "key": "include_dirs",
                "label": "Include Directories",
                "type": "toggle",
                "default": False,
            },
            {
                "key": "sort_by",
                "label": "Sort By",
                "type": "select",
                "default": "name",
                "options": ["name", "size", "modified"],
            },
            {
                "key": "output_as",
                "label": "Output As",
                "type": "select",
                "default": "paths",
                "options": ["paths", "objects"],
            },
        ],
    },
    {
        "type": "action.web_scrape",
        "label": "Web Scrape",
        "category": "Actions",
        "icon": "fa-spider",
        "color": "#34d399",
        "inputs": [
            {"name": "url", "label": "URL Override"},
        ],
        "outputs": [
            {"name": "out",   "label": "Content"},
            {"name": "title", "label": "Page Title"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "url",
                "label": "URL",
                "type": "text",
                "default": "",
                "placeholder": "https://example.com",
            },
            {
                "key": "mode",
                "label": "Output Mode",
                "type": "select",
                "default": "text",
                "options": ["text", "markdown", "html"],
            },
            {
                "key": "max_chars",
                "label": "Max Characters (0 = unlimited)",
                "type": "number",
                "default": 0,
            },
            {
                "key": "user_agent",
                "label": "User Agent",
                "type": "text",
                "default": "Mozilla/5.0 (compatible; AethvionBot/1.0)",
            },
        ],
    },
    # ── Sprint 4: Integrations ────────────────────────────────────────────────
    {
        "type": "companion.ask",
        "label": "Ask Companion",
        "category": "Companions",
        "icon": "fa-comments",
        "color": "#f472b6",
        "inputs": [
            {"name": "in",     "label": "Prompt"},
            {"name": "model",  "label": "Model Override"},
            {"name": "system", "label": "System Prompt Override"},
        ],
        "outputs": [
            {"name": "out",   "label": "Response"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "companion_id",
                "label": "Companion",
                "type": "companion_select",
                "default": "",
                "placeholder": "Select a companion…",
            },
            {
                "key": "model",
                "label": "Model Override",
                "type": "model_select",
                "source": "/api/automate/models",
                "default": "",
                "placeholder": "(blank = companion default)",
            },
            {
                "key": "system_prompt",
                "label": "System Prompt Override",
                "type": "textarea",
                "default": "",
                "placeholder": "(blank = use companion's built-in persona)",
            },
            {
                "key": "temperature",
                "label": "Temperature",
                "type": "number",
                "default": 0.7,
            },
            {
                "key": "show_result",
                "label": "Show Result on Node",
                "type": "toggle",
                "default": True,
            },
        ],
    },
    {
        "type": "integration.discord",
        "label": "Discord",
        "category": "Integrations",
        "icon": "fa-discord",
        "color": "#818cf8",
        "inputs": [
            {"name": "in",      "label": "Message"},
            {"name": "title",   "label": "Embed Title"},
            {"name": "webhook", "label": "Webhook URL Override"},
        ],
        "outputs": [
            {"name": "out",   "label": "Pass-through"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "webhook_url",
                "label": "Webhook URL",
                "type": "text",
                "default": "",
                "placeholder": "https://discord.com/api/webhooks/…",
            },
            {
                "key": "username",
                "label": "Bot Username",
                "type": "text",
                "default": "Aethvion",
            },
            {
                "key": "title",
                "label": "Embed Title",
                "type": "text",
                "default": "",
                "placeholder": "(blank = send as plain message)",
            },
            {
                "key": "colour",
                "label": "Embed Colour (hex int)",
                "type": "number",
                "default": 5793266,
            },
            {
                "key": "avatar_url",
                "label": "Avatar URL",
                "type": "text",
                "default": "",
            },
        ],
    },
    {
        "type": "integration.slack",
        "label": "Slack",
        "category": "Integrations",
        "icon": "fa-slack",
        "color": "#818cf8",
        "inputs": [
            {"name": "in",      "label": "Message"},
            {"name": "title",   "label": "Header Title"},
            {"name": "webhook", "label": "Webhook URL Override"},
        ],
        "outputs": [
            {"name": "out",   "label": "Pass-through"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "webhook_url",
                "label": "Incoming Webhook URL",
                "type": "text",
                "default": "",
                "placeholder": "https://hooks.slack.com/services/…",
            },
            {
                "key": "title",
                "label": "Header Title",
                "type": "text",
                "default": "",
                "placeholder": "(blank = message only)",
            },
            {
                "key": "icon_emoji",
                "label": "Icon Emoji",
                "type": "text",
                "default": ":robot_face:",
            },
        ],
    },
    # ── Sprint 5: Actions ─────────────────────────────────────────────────────
    {
        "type": "action.screenshot",
        "label": "Screenshot",
        "category": "Actions",
        "icon": "fa-camera",
        "color": "#34d399",
        "inputs": [
            {"name": "path", "label": "Save Path Override"},
        ],
        "outputs": [
            {"name": "out",    "label": "File Path"},
            {"name": "path",   "label": "File Path"},
            {"name": "width",  "label": "Width"},
            {"name": "height", "label": "Height"},
            {"name": "error",  "label": "Error"},
        ],
        "properties": [
            {
                "key": "path",
                "label": "Save Path",
                "type": "text",
                "default": "",
                "placeholder": "(blank = auto-generated temp file)",
                "picker": "folder",
            },
            {
                "key": "monitor",
                "label": "Monitor Index",
                "type": "number",
                "default": 0,
            },
        ],
    },
    {
        "type": "action.camera_capture",
        "label": "Camera Capture",
        "category": "Actions",
        "icon": "fa-video",
        "color": "#34d399",
        "inputs": [
            {"name": "path", "label": "Save Path Override"},
        ],
        "outputs": [
            {"name": "out",    "label": "File Path"},
            {"name": "path",   "label": "File Path"},
            {"name": "width",  "label": "Width"},
            {"name": "height", "label": "Height"},
            {"name": "error",  "label": "Error"},
        ],
        "properties": [
            {
                "key": "path",
                "label": "Save Path",
                "type": "text",
                "default": "",
                "placeholder": "(blank = auto-generated temp file)",
                "picker": "folder",
            },
            {
                "key": "camera_index",
                "label": "Camera Index",
                "type": "number",
                "default": 0,
            },
            {
                "key": "width",
                "label": "Capture Width",
                "type": "number",
                "default": 1280,
            },
            {
                "key": "height",
                "label": "Capture Height",
                "type": "number",
                "default": 720,
            },
        ],
    },
    {
        "type": "action.run_agent",
        "label": "Run Agent",
        "category": "Actions",
        "icon": "fa-microchip-ai",
        "color": "#34d399",
        "inputs": [
            {"name": "in",    "label": "Goal / Prompt"},
            {"name": "model", "label": "Model Override"},
        ],
        "outputs": [
            {"name": "out",   "label": "Agent Output"},
            {"name": "agent", "label": "Agent Name"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "model",
                "label": "Model",
                "type": "model_select",
                "source": "/api/automate/models",
                "default": "",
                "placeholder": "Select a model…",
            },
            {
                "key": "domain",
                "label": "Domain",
                "type": "text",
                "default": "Automate",
                "placeholder": "Analytics / Research / Writing…",
            },
            {
                "key": "action",
                "label": "Action",
                "type": "text",
                "default": "Execute",
                "placeholder": "Generate / Analyze / Summarize…",
            },
            {
                "key": "object",
                "label": "Object",
                "type": "text",
                "default": "Task",
                "placeholder": "Report / Email / Code…",
            },
            {
                "key": "instructions",
                "label": "Additional Instructions",
                "type": "textarea",
                "default": "",
                "placeholder": "Extra constraints or context for the agent…",
            },
            {
                "key": "temperature",
                "label": "Temperature",
                "type": "number",
                "default": 0.7,
            },
            {
                "key": "max_tokens",
                "label": "Max Tokens (0 = default)",
                "type": "number",
                "default": 0,
            },
            {
                "key": "show_result",
                "label": "Show Result on Node",
                "type": "toggle",
                "default": True,
            },
        ],
    },
    # ── Sprint 5: AI ──────────────────────────────────────────────────────────
    {
        "type": "ai.analyze_image",
        "label": "Analyze Image",
        "category": "AI",
        "icon": "fa-image",
        "color": "#4ade80",
        "inputs": [
            {"name": "in",    "label": "Question / Prompt"},
            {"name": "image", "label": "Image Path or Data URI"},
            {"name": "model", "label": "Model Override"},
        ],
        "outputs": [
            {"name": "out",   "label": "Analysis"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "model",
                "label": "Model",
                "type": "model_select",
                "source": "/api/automate/models",
                "default": "",
                "placeholder": "Select a vision-capable model…",
            },
            {
                "key": "image_path",
                "label": "Image Path",
                "type": "text",
                "default": "",
                "placeholder": "C:/path/to/image.jpg",
            },
            {
                "key": "question",
                "label": "Question",
                "type": "textarea",
                "default": "Describe this image in detail.",
                "placeholder": "What does this image show?",
            },
            {
                "key": "system_prompt",
                "label": "System Prompt",
                "type": "textarea",
                "default": "You are a helpful vision assistant.",
            },
            {
                "key": "temperature",
                "label": "Temperature",
                "type": "number",
                "default": 0.3,
            },
            {
                "key": "show_result",
                "label": "Show Result on Node",
                "type": "toggle",
                "default": True,
            },
        ],
    },
    {
        "type": "ai.generate_image",
        "label": "Generate Image",
        "category": "AI",
        "icon": "fa-palette",
        "color": "#4ade80",
        "inputs": [
            {"name": "in",   "label": "Prompt"},
            {"name": "path", "label": "Save Path Override"},
        ],
        "outputs": [
            {"name": "out",   "label": "Saved File Path"},
            {"name": "path",  "label": "Saved File Path"},
            {"name": "count", "label": "Images Generated"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "model",
                "label": "Model",
                "type": "text",
                "default": "imagen-3.0-generate-002",
                "placeholder": "imagen-3.0-generate-002",
            },
            {
                "key": "aspect_ratio",
                "label": "Aspect Ratio",
                "type": "select",
                "default": "1:1",
                "options": ["1:1", "16:9", "9:16", "4:3", "3:4"],
            },
            {
                "key": "path",
                "label": "Save Path",
                "type": "text",
                "default": "",
                "placeholder": "(blank = auto-generated temp file)",
                "picker": "folder",
            },
        ],
    },
    {
        "type": "ai.text_to_speech",
        "label": "Text to Speech",
        "category": "AI",
        "icon": "fa-volume-high",
        "color": "#4ade80",
        "inputs": [
            {"name": "in",   "label": "Text"},
            {"name": "path", "label": "Save Path Override"},
        ],
        "outputs": [
            {"name": "out",         "label": "Audio File Path"},
            {"name": "path",        "label": "Audio File Path"},
            {"name": "duration_ms", "label": "Duration (ms)"},
            {"name": "error",       "label": "Error"},
        ],
        "properties": [
            {
                "key": "model_id",
                "label": "TTS Model",
                "type": "text",
                "default": "kokoro",
                "placeholder": "kokoro / xtts / …",
            },
            {
                "key": "voice_id",
                "label": "Voice",
                "type": "text",
                "default": "",
                "placeholder": "(blank = model default)",
            },
            {
                "key": "language",
                "label": "Language",
                "type": "text",
                "default": "en",
                "placeholder": "en / nl / de / …",
            },
            {
                "key": "speed",
                "label": "Speed",
                "type": "number",
                "default": 1.0,
            },
            {
                "key": "device",
                "label": "Device",
                "type": "select",
                "default": "cpu",
                "options": ["cpu", "cuda"],
            },
            {
                "key": "path",
                "label": "Save Path",
                "type": "text",
                "default": "",
                "placeholder": "(blank = auto-generated temp file)",
                "picker": "folder",
            },
        ],
    },
    {
        "type": "ai.speech_to_text",
        "label": "Speech to Text",
        "category": "AI",
        "icon": "fa-microphone",
        "color": "#4ade80",
        "inputs": [
            {"name": "path", "label": "Audio File Path Override"},
        ],
        "outputs": [
            {"name": "out",      "label": "Transcription"},
            {"name": "language", "label": "Detected Language"},
            {"name": "error",    "label": "Error"},
        ],
        "properties": [
            {
                "key": "path",
                "label": "Audio File Path",
                "type": "text",
                "default": "",
                "placeholder": "C:/path/to/audio.wav",
                "picker": "file",
            },
            {
                "key": "model_id",
                "label": "STT Model",
                "type": "text",
                "default": "whisper",
                "placeholder": "whisper",
            },
            {
                "key": "language",
                "label": "Language Hint",
                "type": "text",
                "default": "",
                "placeholder": "(blank = auto-detect)",
            },
            {
                "key": "device",
                "label": "Device",
                "type": "select",
                "default": "cpu",
                "options": ["cpu", "cuda"],
            },
        ],
    },
    # ── Sprint 5: Memory ──────────────────────────────────────────────────────
    {
        "type": "memory.search_semantic",
        "label": "Memory Search",
        "category": "Memory",
        "icon": "fa-magnifying-glass-chart",
        "color": "#f59e0b",
        "inputs": [{"name": "in", "label": "Search Query"}],
        "outputs": [
            {"name": "out",   "label": "Results (JSON)"},
            {"name": "count", "label": "Result Count"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "scope",
                "label": "Scope",
                "type": "select",
                "default": "all",
                "options": ["all", "global", "workflow"],
            },
            {
                "key": "limit",
                "label": "Max Results",
                "type": "number",
                "default": 5,
            },
            {
                "key": "min_score",
                "label": "Min Relevance Score (0–1)",
                "type": "number",
                "default": 0.0,
            },
        ],
    },
    # ── Sprint 5: Integrations ────────────────────────────────────────────────
    {
        "type": "aethviondb.search",
        "label": "AethvionDB Search",
        "category": "Integrations",
        "icon": "fa-database",
        "color": "#818cf8",
        "inputs": [{"name": "in", "label": "Search Query"}],
        "outputs": [
            {"name": "out",   "label": "Results (JSON)"},
            {"name": "count", "label": "Result Count"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "database",
                "label": "Database Name",
                "type": "text",
                "default": "default",
                "placeholder": "default",
            },
            {
                "key": "bake_name",
                "label": "Bake Name",
                "type": "text",
                "default": "default",
                "placeholder": "(blank = use most recent bake)",
            },
            {
                "key": "entity_type",
                "label": "Entity Type Filter",
                "type": "text",
                "default": "",
                "placeholder": "(blank = all types)",
            },
            {
                "key": "limit",
                "label": "Max Results",
                "type": "number",
                "default": 10,
            },
            {
                "key": "min_score",
                "label": "Min Relevance Score (0–1)",
                "type": "number",
                "default": 0.0,
            },
        ],
    },
    # ── Sprint 4+5 (placed here to keep categories together) ─────────────────
    {
        "type": "integration.email",
        "label": "Send Email",
        "category": "Integrations",
        "icon": "fa-envelope",
        "color": "#818cf8",
        "inputs": [
            {"name": "in",      "label": "Email Body"},
            {"name": "to",      "label": "To Override"},
            {"name": "subject", "label": "Subject Override"},
        ],
        "outputs": [
            {"name": "out",   "label": "Pass-through"},
            {"name": "error", "label": "Error"},
        ],
        "properties": [
            {
                "key": "to",
                "label": "To (recipient)",
                "type": "text",
                "default": "",
                "placeholder": "recipient@example.com",
            },
            {
                "key": "subject",
                "label": "Subject",
                "type": "text",
                "default": "Aethvion Notification",
            },
            {
                "key": "format",
                "label": "Body Format",
                "type": "select",
                "default": "plain",
                "options": ["plain", "html"],
            },
            {
                "key": "smtp_host",
                "label": "SMTP Host",
                "type": "text",
                "default": "",
                "placeholder": "smtp.gmail.com",
            },
            {
                "key": "smtp_port",
                "label": "SMTP Port",
                "type": "number",
                "default": 587,
            },
            {
                "key": "smtp_user",
                "label": "SMTP Username",
                "type": "text",
                "default": "",
                "placeholder": "your@email.com",
            },
            {
                "key": "smtp_pass",
                "label": "SMTP Password",
                "type": "password",
                "default": "",
            },
            {
                "key": "from_addr",
                "label": "From Address",
                "type": "text",
                "default": "",
                "placeholder": "(blank = same as SMTP username)",
            },
        ],
    },
]


# ── Pydantic models ───────────────────────────────────────────────────────────

class WorkflowCreate(BaseModel):
    name: str
    nodes: list[dict[str, Any]] = []
    connections: list[dict[str, Any]] = []


class WorkflowUpdate(BaseModel):
    name: str | None = None
    nodes: list[dict[str, Any]] | None = None
    connections: list[dict[str, Any]] | None = None


class NodeTestRequest(BaseModel):
    node: dict[str, Any]
    input_data: str = ""


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/node-types")
async def get_node_types():
    """Return all available node type definitions."""
    return {"node_types": _NODE_TYPES}


@router.get("/models")
async def get_models(provider: Optional[str] = None):
    """
    Return configured chat-capable models from the model registry.
    Pass ?provider=google_ai to filter to a specific provider.
    """
    try:
        registry = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"models": []}

    models = []
    for prov_id, prov_data in registry.get("providers", {}).items():
        if not prov_data.get("active", False):
            continue
        if provider and prov_id != provider:
            continue
        prov_name = prov_data.get("name", prov_id)
        for model_id, model_data in prov_data.get("models", {}).items():
            caps = [c.upper() for c in model_data.get("capabilities", [])]
            if "CHAT" not in caps:
                continue
            models.append({
                "id": model_id,
                "provider_id": prov_id,
                "provider_name": prov_name,
                "label": model_id if provider else f"{model_id}  ({prov_name})",
                "description": model_data.get("description", ""),
            })

    return {"models": models}


@router.post("/node/test")
async def test_node(body: NodeTestRequest):
    """
    Execute a single AI node with the provided input and return the result.
    Only ai.* node types are supported for direct test execution.
    """
    node = body.node
    node_type = node.get("type", "")
    props = node.get("properties", {})

    if not node_type.startswith("ai."):
        raise HTTPException(400, "Only AI nodes (ai.*) can be tested directly.")

    model_id = str(props.get("model", "")).strip()
    if not model_id:
        raise HTTPException(400, "No model selected. Open the node properties and pick a model first.")

    system_prompt = str(props.get("system_prompt", "")).strip() or None
    prefix        = str(props.get("prompt_prefix", "")).strip()
    suffix        = str(props.get("prompt_suffix", "")).strip()
    temperature   = float(props.get("temperature", 0.7))
    input_data    = (body.input_data or "").strip()

    # Build full prompt
    parts = [p for p in [prefix, input_data, suffix] if p]
    prompt = "\n\n".join(parts) if parts else "(no input)"

    try:
        pm   = _get_pm()
        resp = pm.call_with_failover(
            prompt=prompt,
            trace_id=f"automate-test-{uuid.uuid4().hex[:8]}",
            system_prompt=system_prompt,
            temperature=temperature,
            model=model_id,
            request_type="generation",
            source="automate-node-test",
        )
        if not resp.success:
            return {"ok": False, "error": resp.error or "AI call failed"}
        return {"ok": True, "result": resp.content, "model": model_id}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/workflows")
async def list_workflows():
    """List all saved workflows (summary only)."""
    _ensure_dir()
    items = []
    for p in sorted(_DATA_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            wf = json.loads(p.read_text(encoding="utf-8"))
            items.append({
                "id": wf.get("id"),
                "name": wf.get("name", "Unnamed"),
                "node_count": len(wf.get("nodes", [])),
                "updated": wf.get("updated"),
            })
        except Exception:
            pass
    return {"workflows": items}


@router.post("/workflows")
async def create_workflow(body: WorkflowCreate):
    """Create a new workflow."""
    _ensure_dir()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    wf_id = uuid.uuid4().hex
    wf = {
        "id": wf_id,
        "name": body.name,
        "created": now,
        "updated": now,
        "nodes": body.nodes,
        "connections": body.connections,
    }
    _atomic_write(_wf_path(wf_id), wf)
    return {"workflow": wf}


@router.get("/workflows/{wf_id}")
async def get_workflow(wf_id: str):
    """Get a workflow by ID (full detail)."""
    p = _wf_path(wf_id)
    if not p.exists():
        raise HTTPException(404, "Workflow not found")
    return {"workflow": json.loads(p.read_text(encoding="utf-8"))}


@router.put("/workflows/{wf_id}")
async def update_workflow(wf_id: str, body: WorkflowUpdate):
    """Save (update) a workflow."""
    p = _wf_path(wf_id)
    if not p.exists():
        raise HTTPException(404, "Workflow not found")
    wf = json.loads(p.read_text(encoding="utf-8"))
    if body.name is not None:
        wf["name"] = body.name
    if body.nodes is not None:
        wf["nodes"] = body.nodes
    if body.connections is not None:
        wf["connections"] = body.connections
    wf["updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _atomic_write(p, wf)
    return {"workflow": wf}


@router.delete("/workflows/{wf_id}")
async def delete_workflow(wf_id: str):
    """Delete a workflow."""
    p = _wf_path(wf_id)
    if not p.exists():
        raise HTTPException(404, "Workflow not found")
    p.unlink()
    return {"ok": True}


@router.post("/workflows/{wf_id}/run")
async def run_workflow(wf_id: str):
    """Execute a workflow and return the full result including per-node status and outputs."""
    p = _wf_path(wf_id)
    if not p.exists():
        raise HTTPException(404, "Workflow not found")
    wf = json.loads(p.read_text(encoding="utf-8"))

    from core.automate.executor import WorkflowExecutor  # noqa: PLC0415
    executor = WorkflowExecutor(wf)
    result   = await asyncio.to_thread(executor.execute)
    return result


# ── Examples + Import/Export/Share ────────────────────────────────────────────

_EXAMPLES_DIR = Path(__file__).parent / "examples"
_SHARE_DIR    = Path(__file__).parent.parent.parent / "data" / "automate" / "shared"


async def _import_workflow_data(data: dict, name_suffix: str = "") -> dict:
    """Create a new workflow from a raw workflow dict (example load or JSON import)."""
    _ensure_dir()
    now    = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_id = uuid.uuid4().hex

    # Remap every node to a fresh UUID so imported/example workflows don't share IDs
    old_nodes: list[dict] = data.get("nodes", [])
    id_map: dict[str, str] = {
        nd["id"]: uuid.uuid4().hex
        for nd in old_nodes
        if isinstance(nd.get("id"), str)
    }

    new_nodes = []
    for nd in old_nodes:
        new_nd = dict(nd)
        new_nd["id"] = id_map.get(str(nd.get("id", "")), uuid.uuid4().hex)
        new_nodes.append(new_nd)

    new_conns = []
    for conn in data.get("connections", []):
        new_conn = dict(conn)
        new_conn["id"]           = uuid.uuid4().hex
        new_conn["sourceNodeId"] = id_map.get(str(conn.get("sourceNodeId", "")),
                                               str(conn.get("sourceNodeId", "")))
        new_conn["targetNodeId"] = id_map.get(str(conn.get("targetNodeId", "")),
                                               str(conn.get("targetNodeId", "")))
        new_conns.append(new_conn)

    base_name = str(data.get("name", "Imported Workflow")).strip()
    wf = {
        "id":          new_id,
        "name":        base_name + name_suffix if name_suffix else base_name,
        "created":     now,
        "updated":     now,
        "nodes":       new_nodes,
        "connections": new_conns,
    }
    _atomic_write(_wf_path(new_id), wf)
    return {"workflow": wf}


@router.get("/examples")
async def list_examples():
    """Return metadata for all built-in example workflows."""
    if not _EXAMPLES_DIR.exists():
        return {"examples": []}
    examples = []
    for p in sorted(_EXAMPLES_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            examples.append({
                "id":          p.stem,
                "name":        data.get("name", p.stem),
                "description": data.get("description", ""),
                "node_count":  len(data.get("nodes", [])),
                "tags":        data.get("tags", []),
            })
        except Exception:
            pass
    return {"examples": examples}


@router.post("/examples/{example_id}/load")
async def load_example(example_id: str):
    """Create a new editable workflow from a built-in example."""
    # Sanitise path component
    if "/" in example_id or "\\" in example_id or ".." in example_id:
        raise HTTPException(400, "Invalid example ID")
    p = _EXAMPLES_DIR / f"{example_id}.json"
    if not p.exists():
        raise HTTPException(404, "Example not found")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(500, f"Failed to read example: {exc}")
    return await _import_workflow_data(data)


@router.get("/workflows/{wf_id}/export")
async def export_workflow(wf_id: str):
    """Download the workflow as a JSON file."""
    p = _wf_path(wf_id)
    if not p.exists():
        raise HTTPException(404, "Workflow not found")
    wf = json.loads(p.read_text(encoding="utf-8"))
    from fastapi.responses import JSONResponse  # noqa: PLC0415
    safe_name = (wf.get("name") or wf_id).replace(" ", "_")
    filename  = safe_name + ".json"
    return JSONResponse(
        content=wf,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class ImportBody(BaseModel):
    workflow: dict[str, Any]


@router.post("/workflows/import")
async def import_workflow(body: ImportBody):
    """Create a new workflow from an uploaded JSON payload."""
    return await _import_workflow_data(body.workflow)


def _share_path(code: str) -> Path:
    return _SHARE_DIR / f"{code}.json"


def _gen_share_code() -> str:
    import random  # noqa: PLC0415
    import string  # noqa: PLC0415
    chars = string.ascii_uppercase + string.digits
    for _ in range(100):
        code = "".join(random.choices(chars, k=8))
        if not _share_path(code).exists():
            return code
    raise RuntimeError("Could not generate a unique share code")


@router.post("/workflows/{wf_id}/share")
async def share_workflow(wf_id: str):
    """Generate a short share code for the workflow."""
    p = _wf_path(wf_id)
    if not p.exists():
        raise HTTPException(404, "Workflow not found")
    wf   = json.loads(p.read_text(encoding="utf-8"))
    code = _gen_share_code()
    _SHARE_DIR.mkdir(parents=True, exist_ok=True)
    _share_path(code).write_text(
        json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {"code": code}


@router.get("/share/{code}")
async def get_shared_workflow(code: str):
    """Fetch a workflow by share code."""
    if not code.isalnum() or len(code) > 16:
        raise HTTPException(400, "Invalid share code")
    p = _share_path(code.upper())
    if not p.exists():
        raise HTTPException(404, "Share code not found")
    wf = json.loads(p.read_text(encoding="utf-8"))
    return {"workflow": wf}


@router.get("/pick")
async def pick_path(
    mode: str = "file",
    initial: str = "",
    title: str = "",
):
    """
    Open the native OS file or folder picker dialog and return the chosen path.
    mode="file"   → askopenfilename (pick an existing file)
    mode="folder" → askdirectory   (pick a directory)
    Returns { path, cancelled }.
    """
    from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

    def _open_dialog() -> str | None:
        try:
            import tkinter as tk           # noqa: PLC0415
            from tkinter import filedialog  # noqa: PLC0415
            root = tk.Tk()
            root.withdraw()
            root.wm_attributes("-topmost", True)
            initial_dir = ""
            if initial:
                p = Path(initial)
                initial_dir = str(p.parent) if p.is_file() else str(p) if p.is_dir() else str(Path.home())
            else:
                initial_dir = str(Path.home())

            dlg_title = title or ("Select file" if mode == "file" else "Select folder")
            if mode == "file":
                result = filedialog.askopenfilename(
                    parent=root,
                    initialdir=initial_dir,
                    title=dlg_title,
                )
            else:
                result = filedialog.askdirectory(
                    parent=root,
                    initialdir=initial_dir,
                    title=dlg_title,
                )
            root.destroy()
            return result or None
        except Exception:
            return None

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        chosen = await loop.run_in_executor(pool, _open_dialog)

    if chosen:
        return {"path": str(Path(chosen)), "cancelled": False}
    return {"path": None, "cancelled": True}
