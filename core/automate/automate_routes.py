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
from fastapi.responses import StreamingResponse
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
    # ── Global — public workflow parameters ───────────────────────────────────
    {
        "type":     "global.text",
        "label":    "Text",
        "category": "Global",
        "icon":     "fa-globe",
        "color":    "#f59e0b",
        "inputs":   [],
        "outputs": [
            {"name": "out", "label": "Value",
             "description": "The text string. Exposed as a named API parameter — callers can override the default at runtime."},
        ],
        "properties": [
            {"key": "name",        "label": "Parameter Name", "type": "text",
             "default": "myText",  "placeholder": "myText"},
            {"key": "value",       "label": "Default Value",  "type": "text",
             "default": "",        "placeholder": "default text"},
            {"key": "description", "label": "Description",    "type": "text",
             "default": "",        "placeholder": "What this parameter does…"},
        ],
    },
    {
        "type":     "global.number",
        "label":    "Number",
        "category": "Global",
        "icon":     "fa-globe",
        "color":    "#f59e0b",
        "inputs":   [],
        "outputs": [
            {"name": "out", "label": "Value",
             "description": "The numeric value. Exposed as a named API parameter."},
        ],
        "properties": [
            {"key": "name",        "label": "Parameter Name", "type": "text",
             "default": "myNumber","placeholder": "myNumber"},
            {"key": "value",       "label": "Default Value",  "type": "number",
             "default": 0},
            {"key": "description", "label": "Description",    "type": "text",
             "default": "",        "placeholder": "What this parameter does…"},
        ],
    },
    {
        "type":     "global.toggle",
        "label":    "Toggle",
        "category": "Global",
        "icon":     "fa-globe",
        "color":    "#f59e0b",
        "inputs":   [],
        "outputs": [
            {"name": "out", "label": "Value",
             "description": "The boolean value. Exposed as a named API parameter."},
        ],
        "properties": [
            {"key": "name",        "label": "Parameter Name", "type": "text",
             "default": "myFlag",  "placeholder": "myFlag"},
            {"key": "value",       "label": "Default Value",  "type": "toggle",
             "default": False},
            {"key": "description", "label": "Description",    "type": "text",
             "default": "",        "placeholder": "What this parameter does…"},
        ],
    },
    {
        "type":     "global.database",
        "label":    "Database",
        "category": "Global",
        "icon":     "fa-globe",
        "color":    "#f59e0b",
        "inputs":   [],
        "outputs": [
            {"name": "out", "label": "Database Name",
             "description": "The selected database name. Wire this into the 'database' port of any AethvionDB node to drive them all from one place."},
        ],
        "properties": [
            {"key": "name",        "label": "Parameter Name", "type": "text",
             "default": "database","placeholder": "database"},
            {"key": "value",       "label": "Database",       "type": "aethviondb_db",
             "default": "default"},
            {"key": "description", "label": "Description",    "type": "text",
             "default": "",        "placeholder": ""},
        ],
    },
    {
        "type":     "global.snapshot",
        "label":    "Snapshot",
        "category": "Global",
        "icon":     "fa-globe",
        "color":    "#f59e0b",
        "inputs":   [],
        "outputs": [
            {"name": "out", "label": "Snapshot Name",
             "description": "The selected snapshot name. Wire into the 'snapshot' port of AethvionDB snapshot nodes."},
        ],
        "properties": [
            {"key": "name",        "label": "Parameter Name",  "type": "text",
             "default": "snapshot","placeholder": "snapshot"},
            {"key": "database",    "label": "Database",        "type": "aethviondb_db",
             "default": "default"},
            {"key": "value",       "label": "Snapshot",        "type": "aethviondb_snap",
             "db_key": "database", "default": ""},
            {"key": "description", "label": "Description",     "type": "text",
             "default": "",        "placeholder": ""},
        ],
    },
    # ── Triggers ──────────────────────────────────────────────────────────────
    {
        "type": "trigger.manual",
        "label": "Manual Trigger",
        "category": "Triggers",
        "icon": "fa-hand-pointer",
        "color": "#22d3ee",
        "inputs": [],
        "outputs": [{"name": "trigger", "label": "Trigger", "description": "Fires when this workflow is started manually."}],
        "properties": [
            {"key": "name", "label": "Name", "type": "text", "default": "", "placeholder": "e.g. Run Report"},
        ],
    },
    {
        "type": "trigger.schedule",
        "label": "Schedule",
        "category": "Triggers",
        "icon": "fa-clock",
        "color": "#22d3ee",
        "inputs": [],
        "outputs": [
            {"name": "trigger", "label": "Trigger", "description": "Fires at each scheduled time."},
            {"name": "data",    "label": "Data",    "description": "Metadata for this firing: date, time, and rule."},
        ],
        "properties": [
            {"key": "name", "label": "Name", "type": "text", "default": "", "placeholder": "e.g. Daily Sync"},
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
            {"name": "out",  "label": "Request", "description": "Full request object — includes method, headers, body, and query params."},
            {"name": "body", "label": "Body",    "description": "Parsed request body: a JSON object if content-type is JSON, otherwise raw text."},
        ],
        "properties": [
            {"key": "name", "label": "Name", "type": "text", "default": "", "placeholder": "e.g. Inbound Hook"},
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
        "inputs": [{"name": "in", "label": "Input", "description": "Value evaluated against the condition expression."}],
        "outputs": [
            {"name": "true",  "label": "True",  "description": "Continues here when the condition evaluates to true."},
            {"name": "false", "label": "False", "description": "Continues here when the condition evaluates to false."},
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
        "inputs": [{"name": "in", "label": "Input", "description": "Activates this node; the value is forwarded to the Trigger output after the delay."}],
        "outputs": [{"name": "trigger", "label": "Trigger", "description": "Fires after the configured delay, carrying the input value."}],
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
        "inputs": [{"name": "in", "label": "Items", "description": "List to iterate over — each element fires the 'Each Item' output."}],
        "outputs": [
            {"name": "item", "label": "Each Item", "description": "Fires once per item in the list, carrying that item's value."},
            {"name": "done", "label": "Done",      "description": "Fires once after all items have been processed."},
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
        "inputs": [{"name": "in", "label": "Trigger", "description": "Activates this node when a value arrives."}],
        "outputs": [
            {"name": "out",   "label": "Response", "description": "Response body — JSON parsed if content-type is application/json, otherwise raw text."},
            {"name": "error", "label": "Error",    "description": "Error message if the request failed or returned a non-2xx status."},
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
        "inputs": [{"name": "in", "label": "Trigger", "description": "Activates this node; the value is available as `input_data` in the script."}],
        "outputs": [
            {"name": "out",   "label": "Result", "description": "Value assigned to the `result` variable in the script."},
            {"name": "error", "label": "Error",  "description": "Exception message if the script raised an error."},
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
        "inputs": [{"name": "in", "label": "Input", "description": "Value available as {{input}} in the message template."}],
        "outputs": [{"name": "out", "label": "Pass-through", "description": "Passes the input value unchanged so the node can be chained."}],
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
        "inputs": [{"name": "in", "label": "Input", "description": "Value accessible as {{input}} inside the template."}],
        "outputs": [{"name": "out", "label": "Text", "description": "Rendered text after all {{placeholders}} have been substituted."}],
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
        "inputs": [{"name": "in", "label": "JSON String", "description": "Raw JSON text to parse into an object or array."}],
        "outputs": [
            {"name": "out",   "label": "Parsed", "description": "Resulting object or array after successful parsing."},
            {"name": "error", "label": "Error",  "description": "Error message if the JSON string was invalid."},
        ],
        "properties": [],
    },
    {
        "type": "data.set_variable",
        "label": "Set Variable",
        "category": "Data",
        "icon": "fa-box",
        "color": "#fb923c",
        "inputs": [{"name": "in", "label": "Value", "description": "Value to store under the configured variable name."}],
        "outputs": [{"name": "out", "label": "Value", "description": "The value that was stored, passed through for chaining."}],
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
        "inputs": [{"name": "in", "label": "List", "description": "Array to filter — each element is evaluated against the expression."}],
        "outputs": [
            {"name": "match", "label": "Matching", "description": "Items where the filter expression returned true."},
            {"name": "rest",  "label": "Rest",     "description": "Items that did not match the filter expression."},
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
        "inputs": [{"name": "in", "label": "Data", "description": "Value to display on the node card after the workflow runs."}],
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
            {"name": "in",            "label": "Input Data",     "description": "Main content passed to the model as the user message."},
            {"name": "model",         "label": "Model",          "description": "Overrides the configured model at runtime."},
            {"name": "system_prompt", "label": "System Prompt",  "description": "Overrides the configured system prompt at runtime."},
            {"name": "prompt_prefix", "label": "Prefix",         "description": "Text prepended to the input before sending to the model."},
            {"name": "prompt_suffix", "label": "Suffix",         "description": "Text appended to the input before sending to the model."},
            {"name": "temperature",   "label": "Temperature",    "description": "Overrides the configured temperature (creativity) at runtime."},
        ],
        "outputs": [
            {"name": "out",   "label": "Response", "description": "AI-generated text response."},
            {"name": "error", "label": "Error",    "description": "Error message if the AI call failed."},
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
            {"name": "in",            "label": "Input Data",    "description": "Main content passed to the model as the user message."},
            {"name": "model",         "label": "Model",         "description": "Overrides the configured model at runtime."},
            {"name": "system_prompt", "label": "System Prompt", "description": "Overrides the configured system prompt at runtime."},
            {"name": "prompt_prefix", "label": "Prefix",        "description": "Text prepended to the input before sending to the model."},
            {"name": "prompt_suffix", "label": "Suffix",        "description": "Text appended to the input before sending to the model."},
            {"name": "temperature",   "label": "Temperature",   "description": "Overrides the configured temperature (creativity) at runtime."},
        ],
        "outputs": [
            {"name": "out",   "label": "Response", "description": "AI-generated text response."},
            {"name": "error", "label": "Error",    "description": "Error message if the AI call failed."},
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
            {"name": "a", "label": "Text A", "description": "First text to join."},
            {"name": "b", "label": "Text B", "description": "Second text to join."},
        ],
        "outputs": [{"name": "out", "label": "Combined", "description": "Result of joining Text A and Text B with the configured separator."}],
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
            {"name": "in",    "label": "Data Object", "description": "Object whose keys are available as {{key}} placeholders in the template."},
            {"name": "var_a", "label": "Variable A",  "description": "Bound to {{var_a}} in the template."},
            {"name": "var_b", "label": "Variable B",  "description": "Bound to {{var_b}} in the template."},
            {"name": "var_c", "label": "Variable C",  "description": "Bound to {{var_c}} in the template."},
        ],
        "outputs": [
            {"name": "out",   "label": "Rendered Text", "description": "Final text after all {{placeholders}} have been substituted."},
            {"name": "error", "label": "Error",         "description": "Error message if rendering failed."},
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
        "inputs": [{"name": "in", "label": "JSON Input", "description": "JSON string or object to extract a value from."}],
        "outputs": [
            {"name": "out",   "label": "Value", "description": "Extracted value at the specified key path."},
            {"name": "error", "label": "Error", "description": "Error message if the key was not found and no default was set."},
        ],
        "properties": [
            {
                "key": "key",
                "label": "Key Path",
                "type": "text",
                "default": "",
                "placeholder": "[0].name  or  user.address.city  or  results[0].score",
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
        "inputs": [{"name": "in", "label": "Input", "description": "Value to convert to the selected type."}],
        "outputs": [
            {"name": "out",   "label": "Converted", "description": "The value cast to the configured target type."},
            {"name": "error", "label": "Error",     "description": "Error message if the conversion was not possible."},
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
            {"name": "in",  "label": "Value",       "description": "Data to persist in memory under the configured key."},
            {"name": "key", "label": "Key Override", "description": "Overrides the configured storage key at runtime."},
        ],
        "outputs": [
            {"name": "out",   "label": "Pass-through", "description": "The stored value, passed unchanged for chaining."},
            {"name": "error", "label": "Error",        "description": "Error message if the memory write failed."},
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
            {"name": "out",   "label": "Value", "description": "Data retrieved from memory, or the configured default if not found."},
            {"name": "found", "label": "Found", "description": "True if the key existed in memory, false if the default was used."},
            {"name": "error", "label": "Error", "description": "Error message if the memory read failed."},
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
            {"name": "in",       "label": "Input",       "description": "Data to pass into the protected block."},
            {"name": "error_in", "label": "Error Input", "description": "Wire an error output here to catch and re-route it."},
        ],
        "outputs": [
            {"name": "try",    "label": "Try (success)", "description": "Continues here when no error occurred."},
            {"name": "catch",  "label": "Catch (error)", "description": "Continues here when an error was caught, carrying the error message."},
            {"name": "always", "label": "Always",        "description": "Always continues regardless of success or failure."},
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
        "inputs": [{"name": "in", "label": "Input", "description": "Value compared against each case to determine which branch fires."}],
        "outputs": [
            {"name": "case_1",  "label": "Case 1",  "description": "Fires when the input matches the Case 1 value."},
            {"name": "case_2",  "label": "Case 2",  "description": "Fires when the input matches the Case 2 value."},
            {"name": "case_3",  "label": "Case 3",  "description": "Fires when the input matches the Case 3 value."},
            {"name": "case_4",  "label": "Case 4",  "description": "Fires when the input matches the Case 4 value."},
            {"name": "default", "label": "Default", "description": "Fires when the input does not match any configured case."},
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
            {"name": "a", "label": "Branch A", "description": "Data flowing in from one branch."},
            {"name": "b", "label": "Branch B", "description": "Data flowing in from one branch."},
            {"name": "c", "label": "Branch C", "description": "Data flowing in from one branch."},
            {"name": "d", "label": "Branch D", "description": "Data flowing in from one branch."},
        ],
        "outputs": [
            {"name": "out",    "label": "Output",      "description": "Value from whichever branch arrived (first, or all in 'all' mode)."},
            {"name": "source", "label": "Source Port", "description": "Name of the input port that delivered the value (a, b, c, or d)."},
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
        "inputs": [{"name": "in", "label": "Text", "description": "Text to split into parts."}],
        "outputs": [
            {"name": "out",   "label": "All Parts",  "description": "Array of all split segments."},
            {"name": "first", "label": "First Part", "description": "First segment only."},
            {"name": "last",  "label": "Last Part",  "description": "Last segment only."},
            {"name": "count", "label": "Count",      "description": "Number of segments produced."},
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
            {"name": "in",      "label": "Text Input",       "description": "Text to match, extract from, or apply replacements to."},
            {"name": "pattern", "label": "Pattern Override", "description": "Regex pattern to use instead of the configured one."},
        ],
        "outputs": [
            {"name": "out",     "label": "Result",      "description": "First match (extract mode) or replaced text (replace mode)."},
            {"name": "matches", "label": "All Matches", "description": "Array of all matches found (when 'Return All Matches' is on)."},
            {"name": "matched", "label": "Did Match",   "description": "True if at least one match was found, false otherwise."},
            {"name": "error",   "label": "Error",       "description": "Error message if the regex pattern was invalid."},
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
            {"name": "in",   "label": "Trigger",   "description": "Activates this node when a value arrives."},
            {"name": "path", "label": "File Path", "description": "Overrides the configured file path at runtime."},
        ],
        "outputs": [
            {"name": "out",   "label": "File Content",  "description": "Full text content of the file."},
            {"name": "path",  "label": "Resolved Path", "description": "Absolute path of the file that was read."},
            {"name": "size",  "label": "File Size",     "description": "File size in bytes."},
            {"name": "error", "label": "Error",         "description": "Error message if the file could not be read."},
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
            {"name": "in",   "label": "Content",          "description": "Text content to write to the file."},
            {"name": "path", "label": "File Path Override", "description": "Overrides the configured file path at runtime."},
        ],
        "outputs": [
            {"name": "out",   "label": "Pass-through", "description": "The content that was written, passed unchanged for chaining."},
            {"name": "path",  "label": "Written Path", "description": "Absolute path of the file that was written."},
            {"name": "error", "label": "Error",        "description": "Error message if the file could not be written."},
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
            {"name": "in",      "label": "Value (pass-through)", "description": "Passed through to the output unchanged. Use {{input}} in the Message to embed this value in the notification."},
            {"name": "title",   "label": "Title Override",       "description": "Overrides the configured notification title at runtime."},
            {"name": "message", "label": "Message Override",     "description": "Overrides the configured message at runtime."},
        ],
        "outputs": [
            {"name": "out",   "label": "Pass-through", "description": "The input value, passed unchanged so this node can be chained."},
            {"name": "error", "label": "Error",        "description": "Error message if the notification could not be sent."},
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
                "placeholder": "Use {{input}} to embed the wired-in value.",
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
            {"name": "out",  "label": "File Content", "description": "Text content read from the file."},
            {"name": "path", "label": "File Path",    "description": "Full absolute path to the file."},
            {"name": "name", "label": "File Name",    "description": "Filename portion only (e.g. report.txt)."},
            {"name": "size", "label": "File Size",    "description": "File size in bytes."},
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
            {"name": "out",   "label": "List",  "description": "The items as an array."},
            {"name": "count", "label": "Count", "description": "Number of items in the list."},
            {"name": "first", "label": "First", "description": "First item in the list only."},
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
        "inputs": [{"name": "in", "label": "Data", "description": "Content to write to the output file."}],
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
        "inputs": [{"name": "in", "label": "Data", "description": "Content to copy to the clipboard."}],
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
        "inputs": [{"name": "in", "label": "Text to Copy", "description": "Text to write to the clipboard (only used in 'write' mode)."}],
        "outputs": [
            {"name": "out",   "label": "Clipboard Content", "description": "Current clipboard text, populated when mode is read or read_then_clear."},
            {"name": "error", "label": "Error",             "description": "Error message if the clipboard operation failed."},
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
            {"name": "a", "label": "Object A", "description": "Object to include in the merge."},
            {"name": "b", "label": "Object B", "description": "Object to include in the merge."},
            {"name": "c", "label": "Object C", "description": "Object to include in the merge."},
            {"name": "d", "label": "Object D", "description": "Object to include in the merge."},
        ],
        "outputs": [
            {"name": "out",   "label": "Merged Object", "description": "Combined result of all wired input objects."},
            {"name": "error", "label": "Error",         "description": "Error message if merging failed (e.g. non-object input)."},
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
            {"name": "in",    "label": "List",          "description": "Array to extract an item from."},
            {"name": "index", "label": "Index Override", "description": "Zero-based index to use, overriding the configured value."},
        ],
        "outputs": [
            {"name": "out",   "label": "Item",  "description": "Item at the specified index (or slice if Slice End is set)."},
            {"name": "count", "label": "Count", "description": "Total number of items in the input list."},
            {"name": "error", "label": "Error", "description": "Error message if the index was out of range."},
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
            {"name": "in",     "label": "Text to Summarize", "description": "Long-form content to condense into a summary."},
            {"name": "model",  "label": "Model Override",    "description": "Overrides the configured model at runtime."},
            {"name": "length", "label": "Length Override",   "description": "One of: short, medium, long — overrides the configured length."},
        ],
        "outputs": [
            {"name": "out",   "label": "Summary", "description": "AI-generated summary of the input text."},
            {"name": "error", "label": "Error",   "description": "Error message if the AI call failed."},
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
            {"name": "in",     "label": "Text to Classify", "description": "Text to be assigned to one of the configured labels."},
            {"name": "model",  "label": "Model Override",   "description": "Overrides the configured model at runtime."},
            {"name": "labels", "label": "Labels Override",  "description": "Comma-separated list of categories, overriding the configured setting."},
        ],
        "outputs": [
            {"name": "label",     "label": "Matched Label", "description": "Category the text was assigned to."},
            {"name": "reasoning", "label": "Reasoning",     "description": "Explanation of why this label was chosen."},
            {"name": "all",       "label": "All Results",   "description": "Ranked list of all labels with confidence scores."},
            {"name": "error",     "label": "Error",         "description": "Error message if the AI call failed."},
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
            {"name": "in",     "label": "Text to Extract From", "description": "Source text to extract structured data from."},
            {"name": "model",  "label": "Model Override",       "description": "Overrides the configured model at runtime."},
            {"name": "schema", "label": "Schema Override",      "description": "JSON schema overriding the configured fields to extract."},
        ],
        "outputs": [
            {"name": "out",   "label": "Extracted JSON", "description": "Structured object with the extracted fields as key-value pairs."},
            {"name": "error", "label": "Error",          "description": "Error message if the AI call or extraction failed."},
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
            {"name": "trigger",    "label": "Trigger",    "description": "Fires when the configured app event occurs."},
            {"name": "event_type", "label": "Event Type", "description": "Type identifier of the event that fired (e.g. companion.message)."},
            {"name": "source",     "label": "Source",     "description": "Component that emitted the event."},
            {"name": "data",       "label": "Event Data", "description": "Payload data attached to the event."},
        ],
        "properties": [
            {"key": "name", "label": "Name", "type": "text", "default": "", "placeholder": "e.g. On Message"},
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
            {"name": "trigger", "label": "Trigger",      "description": "Fires when a file system change is detected."},
            {"name": "path",    "label": "Changed Path", "description": "Full path of the file or folder that changed."},
            {"name": "event",   "label": "Event Type",   "description": "One of: created, modified, deleted."},
        ],
        "properties": [
            {"key": "name", "label": "Name", "type": "text", "default": "", "placeholder": "e.g. Watch Folder"},
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
        "inputs": [{"name": "in", "label": "Input", "description": "Value to repeat N times into a list."}],
        "outputs": [
            {"name": "out",   "label": "Repeated List", "description": "Array containing the input value repeated N times."},
            {"name": "count", "label": "Count",         "description": "Number of repetitions (same as the configured count)."},
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
        "inputs": [{"name": "in", "label": "CSV Text", "description": "Raw CSV text to parse into structured data."}],
        "outputs": [
            {"name": "out",     "label": "Parsed Data", "description": "Array of row objects (or arrays) parsed from the CSV."},
            {"name": "rows",    "label": "Row Count",   "description": "Number of data rows (excluding the header if present)."},
            {"name": "headers", "label": "Headers",     "description": "Array of column header names from the first row."},
            {"name": "error",   "label": "Error",       "description": "Error message if the CSV could not be parsed."},
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
            {"name": "in",  "label": "Trigger",          "description": "Activates this node when a value arrives."},
            {"name": "cmd", "label": "Command Override", "description": "Overrides the configured command at runtime."},
        ],
        "outputs": [
            {"name": "out",       "label": "stdout",    "description": "Standard output captured from the process."},
            {"name": "stderr",    "label": "stderr",    "description": "Standard error output from the process."},
            {"name": "exit_code", "label": "Exit Code", "description": "Process exit code — 0 means success."},
            {"name": "error",     "label": "Error",     "description": "Error message if the process could not be started."},
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
            {"name": "path", "label": "Folder Path Override", "description": "Overrides the configured folder path at runtime."},
        ],
        "outputs": [
            {"name": "out",   "label": "File List", "description": "Array of file paths matching the configured pattern."},
            {"name": "count", "label": "Count",     "description": "Number of files found."},
            {"name": "error", "label": "Error",     "description": "Error message if the folder could not be read."},
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
            {"name": "url", "label": "URL Override", "description": "Overrides the configured URL at runtime."},
        ],
        "outputs": [
            {"name": "out",   "label": "Content",    "description": "Page content as text, Markdown, or HTML depending on the mode setting."},
            {"name": "title", "label": "Page Title", "description": "The <title> element value from the page."},
            {"name": "error", "label": "Error",      "description": "Error message if the page could not be fetched."},
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
            {"name": "in",     "label": "Prompt",                "description": "Message or question sent to the companion."},
            {"name": "model",  "label": "Model Override",         "description": "Overrides the companion's default model for this call."},
            {"name": "system", "label": "System Prompt Override", "description": "Overrides the companion's built-in persona for this call."},
        ],
        "outputs": [
            {"name": "out",   "label": "Response", "description": "The companion's text reply."},
            {"name": "error", "label": "Error",    "description": "Error message if the companion call failed."},
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
            {"name": "in",      "label": "Message",             "description": "Text body of the Discord message or embed description."},
            {"name": "title",   "label": "Embed Title",         "description": "Overrides the configured embed title at runtime."},
            {"name": "webhook", "label": "Webhook URL Override", "description": "Overrides the configured webhook URL at runtime."},
        ],
        "outputs": [
            {"name": "out",   "label": "Pass-through", "description": "The message that was sent, passed unchanged for chaining."},
            {"name": "error", "label": "Error",        "description": "Error message if sending to Discord failed."},
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
            {"name": "in",      "label": "Message",             "description": "Text to post in the Slack channel."},
            {"name": "title",   "label": "Header Title",        "description": "Overrides the configured header title at runtime."},
            {"name": "webhook", "label": "Webhook URL Override", "description": "Overrides the configured webhook URL at runtime."},
        ],
        "outputs": [
            {"name": "out",   "label": "Pass-through", "description": "The message that was sent, passed unchanged for chaining."},
            {"name": "error", "label": "Error",        "description": "Error message if sending to Slack failed."},
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
            {"name": "path", "label": "Save Path Override", "description": "Overrides the configured save path at runtime."},
        ],
        "outputs": [
            {"name": "out",    "label": "File Path",     "description": "Path where the screenshot was saved."},
            {"name": "image",  "label": "Image Preview", "description": "Data URI of the screenshot — wire to Analyze Image for AI vision."},
            {"name": "width",  "label": "Width",         "description": "Screenshot width in pixels."},
            {"name": "height", "label": "Height",        "description": "Screenshot height in pixels."},
            {"name": "error",  "label": "Error",         "description": "Error message if the screenshot failed."},
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
            {"name": "path", "label": "Save Path Override", "description": "Overrides the configured save path at runtime."},
        ],
        "outputs": [
            {"name": "out",    "label": "File Path",     "description": "Path where the captured image was saved."},
            {"name": "image",  "label": "Image Preview", "description": "Data URI of the captured image — wire to Analyze Image for AI vision."},
            {"name": "width",  "label": "Width",         "description": "Captured image width in pixels."},
            {"name": "height", "label": "Height",        "description": "Captured image height in pixels."},
            {"name": "error",  "label": "Error",         "description": "Error message if the camera capture failed."},
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
        "type": "action.ocr",
        "label": "OCR — Extract Text",
        "category": "Actions",
        "icon": "fa-glasses",
        "color": "#34d399",
        "inputs": [
            {"name": "image", "label": "Image (path or data URI)", "description": "Image file path or a data URI — e.g. from a Screenshot or Camera Capture node."},
        ],
        "outputs": [
            {"name": "out",   "label": "Extracted Text", "description": "All text recognized in the image."},
            {"name": "error", "label": "Error",          "description": "Error message if OCR failed."},
        ],
        "properties": [
            {
                "key": "image_path",
                "label": "Image Path",
                "type": "text",
                "default": "",
                "placeholder": "Path to image file, or leave blank and wire an image input",
                "picker": "file",
            },
            {
                "key": "language",
                "label": "Language",
                "type": "text",
                "default": "eng",
                "placeholder": "eng, fra, deu, chi_sim, … (Tesseract lang code)",
            },
            {
                "key": "config",
                "label": "Tesseract Config",
                "type": "text",
                "default": "",
                "placeholder": "e.g. --psm 6  (optional extra flags)",
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
            {"name": "in",    "label": "Goal / Prompt",  "description": "Task description sent to the autonomous agent."},
            {"name": "model", "label": "Model Override", "description": "Overrides the configured model at runtime."},
        ],
        "outputs": [
            {"name": "out",   "label": "Agent Output", "description": "Final result produced by the agent."},
            {"name": "agent", "label": "Agent Name",   "description": "Name of the agent that was selected to run the task."},
            {"name": "error", "label": "Error",        "description": "Error message if the agent failed."},
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
            {"name": "in",    "label": "Question / Prompt",    "description": "Question to ask about the image."},
            {"name": "image", "label": "Image Path or Data URI", "description": "Wire from a Screenshot or Camera Capture node, or provide a file path."},
            {"name": "model", "label": "Model Override",        "description": "Overrides the configured model at runtime."},
        ],
        "outputs": [
            {"name": "out",   "label": "Analysis", "description": "AI-generated description or answer about the image."},
            {"name": "error", "label": "Error",    "description": "Error message if the image analysis failed."},
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
            {"name": "in",   "label": "Prompt",            "description": "Text description of the image to generate."},
            {"name": "path", "label": "Save Path Override", "description": "Overrides the configured save path at runtime."},
        ],
        "outputs": [
            {"name": "out",   "label": "Saved File Path",    "description": "Path where the generated image was saved."},
            {"name": "path",  "label": "Saved File Path",    "description": "Alias of the 'out' port — same path value."},
            {"name": "count", "label": "Images Generated",   "description": "Number of images created."},
            {"name": "error", "label": "Error",              "description": "Error message if image generation failed."},
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
            {"name": "in",   "label": "Text",             "description": "Text to convert to spoken audio."},
            {"name": "path", "label": "Save Path Override", "description": "Overrides the configured save path at runtime."},
        ],
        "outputs": [
            {"name": "out",         "label": "Audio File Path", "description": "Path to the generated audio file."},
            {"name": "path",        "label": "Audio File Path", "description": "Alias of the 'out' port — same path value."},
            {"name": "duration_ms", "label": "Duration (ms)",  "description": "Length of the generated audio in milliseconds."},
            {"name": "error",       "label": "Error",          "description": "Error message if speech synthesis failed."},
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
            {"name": "path", "label": "Audio File Path Override", "description": "Overrides the configured audio file path at runtime."},
        ],
        "outputs": [
            {"name": "out",      "label": "Transcription",     "description": "Full transcribed text from the audio."},
            {"name": "language", "label": "Detected Language", "description": "Language code detected in the audio (e.g. en, nl)."},
            {"name": "error",    "label": "Error",             "description": "Error message if transcription failed."},
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
        "inputs": [{"name": "in", "label": "Search Query", "description": "Natural-language query to find relevant content in memory."}],
        "outputs": [
            {"name": "out",   "label": "Results (JSON)", "description": "Array of matching memory entries with content and relevance score."},
            {"name": "count", "label": "Result Count",  "description": "Number of results returned."},
            {"name": "error", "label": "Error",         "description": "Error message if the search failed."},
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
    # ── AethvionDB ────────────────────────────────────────────────────────────
    {
        "type": "aethviondb.search",
        "label": "AethvionDB Search",
        "category": "AethvionDB",
        "icon": "fa-database",
        "color": "#818cf8",
        "inputs": [{"name": "in", "label": "Search Query", "description": "Natural-language query to search the AethvionDB database."}],
        "outputs": [
            {"name": "out",   "label": "Results (JSON)", "description": "Array of matching entities with scores and metadata."},
            {"name": "count", "label": "Result Count",  "description": "Number of results returned."},
            {"name": "speed", "label": "Speed",         "description": "Search execution time in milliseconds."},
            {"name": "error", "label": "Error",         "description": "Error message if the search failed."},
        ],
        "properties": [
            {
                "key": "database",
                "label": "Database",
                "type": "aethviondb_db",
                "default": "default",
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
                "label": "Min Score (0–1)",
                "type": "number",
                "default": 0.0,
            },
        ],
    },
    {
        "type": "aethviondb.snapshot_search",
        "label": "AethvionDB Snapshot Search",
        "category": "AethvionDB",
        "icon": "fa-database",
        "color": "#a78bfa",
        "inputs": [{"name": "in", "label": "Search Query", "description": "Natural-language query to search within the snapshot."}],
        "outputs": [
            {"name": "out",   "label": "Results (JSON)", "description": "Array of matching entities from the snapshot with scores."},
            {"name": "count", "label": "Result Count",  "description": "Number of results returned."},
            {"name": "speed", "label": "Speed",         "description": "Search execution time in milliseconds."},
            {"name": "error", "label": "Error",         "description": "Error message if the search failed."},
        ],
        "properties": [
            {
                "key": "database",
                "label": "Database",
                "type": "aethviondb_db",
                "default": "default",
            },
            {
                "key": "snapshot",
                "label": "Snapshot",
                "type": "aethviondb_snap",
                "db_key": "database",
                "default": "",
                "placeholder": "(most recent)",
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
                "label": "Min Score (0–1)",
                "type": "number",
                "default": 0.0,
            },
        ],
    },
    {
        "type": "aethviondb.semantic_search",
        "label": "AethvionDB Semantic Search",
        "category": "AethvionDB",
        "icon": "fa-brain",
        "color": "#c084fc",
        "inputs": [
            {"name": "in", "label": "Search Query", "description": "Natural-language query — entities are ranked by semantic similarity to this text."},
        ],
        "outputs": [
            {"name": "out",   "label": "Results (JSON)",    "description": "Array of matching entities ranked by cosine similarity score (0–1)."},
            {"name": "count", "label": "Result Count",      "description": "Number of results returned."},
            {"name": "speed", "label": "Speed",             "description": "Total execution time including embedding generation."},
            {"name": "error", "label": "Error / Warning",   "description": "Error message, or a warning when some entities were skipped due to missing embeddings."},
        ],
        "properties": [
            {
                "key": "database",
                "label": "Database",
                "type": "aethviondb_db",
                "default": "default",
            },
            {
                "key": "model",
                "label": "Embedding Model",
                "type": "select",
                "options": [
                    {"value": "text-embedding-004",    "label": "Gemini text-embedding-004 (Google)"},
                    {"value": "embedding-001",         "label": "Gemini embedding-001 (Google)"},
                    {"value": "text-embedding-3-small","label": "text-embedding-3-small (OpenAI)"},
                    {"value": "text-embedding-3-large","label": "text-embedding-3-large (OpenAI)"},
                    {"value": "text-embedding-ada-002","label": "text-embedding-ada-002 (OpenAI)"},
                ],
                "default": "text-embedding-004",
                "description": "Must match the model used when vectorizing the database.",
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
                "label": "Min Similarity (0–1)",
                "type": "number",
                "default": 0.5,
            },
        ],
    },
    {
        "type": "aethviondb.snapshot_semantic_search",
        "label": "AethvionDB Snapshot Semantic Search",
        "category": "AethvionDB",
        "icon": "fa-brain",
        "color": "#a78bfa",
        "inputs": [
            {"name": "in", "label": "Search Query", "description": "Natural-language query — entities are ranked by semantic similarity to this text."},
        ],
        "outputs": [
            {"name": "out",   "label": "Results (JSON)",   "description": "Array of matching entities ranked by cosine similarity score (0–1)."},
            {"name": "count", "label": "Result Count",     "description": "Number of results returned."},
            {"name": "speed", "label": "Speed",            "description": "Total execution time including embedding generation."},
            {"name": "error", "label": "Error / Warning",  "description": "Error, or a warning when some entities were skipped due to missing embeddings."},
        ],
        "properties": [
            {
                "key": "database",
                "label": "Database",
                "type": "aethviondb_db",
                "default": "default",
            },
            {
                "key": "snapshot",
                "label": "Snapshot",
                "type": "aethviondb_snap",
                "db_key": "database",
                "default": "",
                "placeholder": "(most recent)",
                "description": "Must be baked with 'Include Vectors' enabled. Leave blank to use the most recent bake.",
            },
            {
                "key": "model",
                "label": "Embedding Model",
                "type": "select",
                "options": [
                    {"value": "text-embedding-004",     "label": "Gemini text-embedding-004 (Google)"},
                    {"value": "embedding-001",          "label": "Gemini embedding-001 (Google)"},
                    {"value": "text-embedding-3-small", "label": "text-embedding-3-small (OpenAI)"},
                    {"value": "text-embedding-3-large", "label": "text-embedding-3-large (OpenAI)"},
                    {"value": "text-embedding-ada-002", "label": "text-embedding-ada-002 (OpenAI)"},
                ],
                "default": "text-embedding-004",
                "description": "Must match the model used when baking the snapshot with vectors.",
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
                "label": "Min Similarity (0–1)",
                "type": "number",
                "default": 0.5,
            },
        ],
    },
    # ── AethvionDB — database ─────────────────────────────────────────────────
    {
        "type":     "aethviondb.create_database",
        "label":    "Create Database",
        "category": "AethvionDB",
        "icon":     "fa-circle-plus",
        "color":    "#34d399",
        "inputs": [
            {"name": "in", "label": "Database Name",
             "description": "Name for the new database (overrides the Name property)."},
        ],
        "outputs": [
            {"name": "out",   "label": "Entry (JSON)",   "description": "Registry entry for the created database."},
            {"name": "name",  "label": "Database Name",  "description": "Confirmed name of the new database."},
            {"name": "path",  "label": "Path",           "description": "Absolute filesystem path of the database root."},
            {"name": "error", "label": "Error",          "description": "Error message if creation failed."},
        ],
        "properties": [
            {"key": "name",        "label": "Database Name", "type": "text",
             "default": "",        "placeholder": "my-database"},
            {"key": "description", "label": "Description",   "type": "text",
             "default": "",        "placeholder": "Optional description"},
            {"key": "path",        "label": "Custom Path",   "type": "text",
             "default": "",        "placeholder": "(auto — leave blank)"},
        ],
    },
    {
        "type":     "aethviondb.get_stats",
        "label":    "Database Stats",
        "category": "AethvionDB",
        "icon":     "fa-chart-pie",
        "color":    "#34d399",
        "inputs":  [],
        "outputs": [
            {"name": "out",     "label": "Stats (JSON)", "description": "Full stats object with counts by status."},
            {"name": "total",   "label": "Total",        "description": "Total entity count (all statuses)."},
            {"name": "active",  "label": "Active",       "description": "Fully-expanded active entities."},
            {"name": "stubs",   "label": "Stubs",        "description": "Stub entities awaiting expansion."},
            {"name": "deleted", "label": "Deleted",      "description": "Soft-deleted entities."},
            {"name": "error",   "label": "Error",        "description": "Error message if stats could not be read."},
        ],
        "properties": [
            {"key": "database", "label": "Database", "type": "aethviondb_db", "default": "default"},
        ],
    },
    # ── AethvionDB — entity CRUD ──────────────────────────────────────────────
    {
        "type":     "aethviondb.list_entities",
        "label":    "List Entities",
        "category": "AethvionDB",
        "icon":     "fa-list",
        "color":    "#818cf8",
        "inputs":  [],
        "outputs": [
            {"name": "out",   "label": "Entities (JSON)", "description": "Array of entity summaries matching the filters."},
            {"name": "count", "label": "Count",           "description": "Number of entities returned."},
            {"name": "error", "label": "Error",           "description": "Error message if the query failed."},
        ],
        "properties": [
            {"key": "database",    "label": "Database",     "type": "aethviondb_db", "default": "default"},
            {"key": "entity_type", "label": "Type Filter",  "type": "text", "default": "",
             "placeholder": "(blank = all types)"},
            {"key": "status",      "label": "Status Filter","type": "select",
             "options": [
                 {"value": "",        "label": "All"},
                 {"value": "active",  "label": "Active only"},
                 {"value": "stub",    "label": "Stubs only"},
                 {"value": "deleted", "label": "Deleted only"},
             ], "default": ""},
            {"key": "limit",       "label": "Max Results",  "type": "number", "default": 50},
        ],
    },
    {
        "type":     "aethviondb.get_entity",
        "label":    "Get Entity",
        "category": "AethvionDB",
        "icon":     "fa-file-lines",
        "color":    "#818cf8",
        "inputs": [
            {"name": "in", "label": "Entity ID or Name",
             "description": "Entity ID (ws_…) or exact name to retrieve."},
        ],
        "outputs": [
            {"name": "out",         "label": "Entity (JSON)", "description": "Full entity JSON including all sections."},
            {"name": "entity_id",   "label": "Entity ID",     "description": "Resolved entity ID."},
            {"name": "entity_name", "label": "Name",          "description": "Entity display name."},
            {"name": "error",       "label": "Error",         "description": "Error if the entity was not found."},
        ],
        "properties": [
            {"key": "database",   "label": "Database",        "type": "aethviondb_db", "default": "default"},
            {"key": "entity_ref", "label": "Entity ID / Name","type": "text", "default": "",
             "placeholder": "Fallback when 'in' port is empty"},
        ],
    },
    {
        "type":     "aethviondb.create_entity",
        "label":    "Create Entity",
        "category": "AethvionDB",
        "icon":     "fa-file-circle-plus",
        "color":    "#818cf8",
        "inputs": [
            {"name": "in", "label": "Entity Name",
             "description": "Name for the new entity (overrides the Name property)."},
        ],
        "outputs": [
            {"name": "out",         "label": "Entity (JSON)", "description": "Newly created entity record."},
            {"name": "entity_id",   "label": "Entity ID",     "description": "ID of the created entity."},
            {"name": "was_created", "label": "Was Created",   "description": "'true' if new, 'false' if already existed."},
            {"name": "error",       "label": "Error",         "description": "Error message if creation failed."},
        ],
        "properties": [
            {"key": "database",    "label": "Database",     "type": "aethviondb_db", "default": "default"},
            {"key": "name",        "label": "Entity Name",  "type": "text", "default": "",
             "placeholder": "Fallback when 'in' port is empty"},
            {"key": "entity_type", "label": "Entity Type",  "type": "select",
             "options": [
                 {"value": "other",        "label": "Other"},
                 {"value": "person",       "label": "Person"},
                 {"value": "place",        "label": "Place"},
                 {"value": "event",        "label": "Event"},
                 {"value": "concept",      "label": "Concept"},
                 {"value": "organization", "label": "Organization"},
                 {"value": "artifact",     "label": "Artifact"},
                 {"value": "creature",     "label": "Creature"},
                 {"value": "substance",    "label": "Substance"},
                 {"value": "process",      "label": "Process"},
                 {"value": "phenomenon",   "label": "Phenomenon"},
                 {"value": "work",         "label": "Work"},
                 {"value": "species",      "label": "Species"},
                 {"value": "universe",     "label": "Universe"},
             ], "default": "other"},
            {"key": "source", "label": "Source Tag", "type": "text", "default": "workflow"},
        ],
    },
    {
        "type":     "aethviondb.update_entity",
        "label":    "Update Entity",
        "category": "AethvionDB",
        "icon":     "fa-file-pen",
        "color":    "#818cf8",
        "inputs": [
            {"name": "entity", "label": "Entity ID or Name",
             "description": "Entity to update — accepts ID or exact name."},
            {"name": "in",     "label": "JSON Patch",
             "description": "JSON object with fields to update, e.g. {\"type\":\"person\",\"sections\":{\"core\":{\"summary\":\"New text\"}}}."},
        ],
        "outputs": [
            {"name": "out",       "label": "Entity (JSON)", "description": "Updated entity after the patch was applied."},
            {"name": "entity_id", "label": "Entity ID",     "description": "ID of the updated entity."},
            {"name": "error",     "label": "Error",         "description": "Error message if update failed."},
        ],
        "properties": [
            {"key": "database",    "label": "Database",     "type": "aethviondb_db", "default": "default"},
            {"key": "entity_ref",  "label": "Entity ID / Name", "type": "text", "default": "",
             "placeholder": "Fallback when 'entity' port is empty"},
            {"key": "entity_type", "label": "Override Type",    "type": "text", "default": "",
             "placeholder": "(leave blank to keep existing)"},
            {"key": "summary",     "label": "Override Summary", "type": "textarea", "default": "",
             "placeholder": "(leave blank to keep existing)"},
        ],
    },
    {
        "type":     "aethviondb.delete_entity",
        "label":    "Delete Entity",
        "category": "AethvionDB",
        "icon":     "fa-file-circle-minus",
        "color":    "#f87171",
        "inputs": [
            {"name": "in", "label": "Entity ID or Name",
             "description": "Entity to soft-delete."},
        ],
        "outputs": [
            {"name": "out",       "label": "Success",    "description": "'true' if deleted, 'false' if not found."},
            {"name": "entity_id", "label": "Entity ID",  "description": "Resolved entity ID."},
            {"name": "error",     "label": "Error",      "description": "Error message if deletion failed."},
        ],
        "properties": [
            {"key": "database",   "label": "Database",        "type": "aethviondb_db", "default": "default"},
            {"key": "entity_ref", "label": "Entity ID / Name","type": "text", "default": "",
             "placeholder": "Fallback when 'in' port is empty"},
        ],
    },
    # ── AethvionDB — AI operations ────────────────────────────────────────────
    {
        "type":     "aethviondb.distill",
        "label":    "Distil Content",
        "category": "AethvionDB",
        "icon":     "fa-flask",
        "color":    "#c084fc",
        "inputs": [
            {"name": "in", "label": "Source Text",
             "description": "Any text to distil — article, notes, book excerpt, raw document. The AI identifies the subject and writes a structured entity."},
        ],
        "outputs": [
            {"name": "out",         "label": "Entity (JSON)", "description": "Distilled entity record."},
            {"name": "entity_id",   "label": "Entity ID",     "description": "ID of the created/updated entity."},
            {"name": "entity_name", "label": "Name",          "description": "Entity name identified by the AI."},
            {"name": "stub_count",  "label": "Stubs Created", "description": "Number of stub sub-topics created alongside the main entity."},
            {"name": "error",       "label": "Error",         "description": "Error message if distillation failed."},
        ],
        "properties": [
            {"key": "database",  "label": "Database",       "type": "aethviondb_db",  "default": "default"},
            {"key": "model",     "label": "AI Model",       "type": "model_select",   "default": "auto"},
            {"key": "auto_save", "label": "Save to Database","type": "toggle", "default": True,
             "description": "Turn off to preview the distilled entity without writing to disk."},
        ],
    },
    {
        "type":     "aethviondb.expand_entity",
        "label":    "Expand Entity",
        "category": "AethvionDB",
        "icon":     "fa-wand-sparkles",
        "color":    "#c084fc",
        "inputs": [
            {"name": "in",      "label": "Entity ID or Name",
             "description": "Stub entity to expand. Already-active entities pass through untouched."},
            {"name": "context", "label": "Source Material (optional)",
             "description": "Extra reference text for the AI to use when generating content (distil-style)."},
        ],
        "outputs": [
            {"name": "out",         "label": "Entity (JSON)", "description": "Expanded entity record."},
            {"name": "entity_id",   "label": "Entity ID",     "description": "ID of the expanded entity."},
            {"name": "entity_name", "label": "Name",          "description": "Entity display name."},
            {"name": "error",       "label": "Error",         "description": "Error message if expansion failed."},
        ],
        "properties": [
            {"key": "database",      "label": "Database",       "type": "aethviondb_db", "default": "default"},
            {"key": "model",         "label": "AI Model",       "type": "model_select",  "default": "auto"},
            {"key": "entity_ref",    "label": "Entity ID / Name","type": "text", "default": "",
             "placeholder": "Fallback when 'in' port is empty"},
            {"key": "extra_context", "label": "Source Material","type": "textarea", "default": "",
             "placeholder": "Fallback when 'context' port is empty"},
        ],
    },
    {
        "type":     "aethviondb.deepen_entity",
        "label":    "Deepen Entity",
        "category": "AethvionDB",
        "icon":     "fa-layer-group",
        "color":    "#c084fc",
        "inputs": [
            {"name": "in",      "label": "Entity ID or Name",
             "description": "Active entity whose stub sub-topics should be expanded."},
            {"name": "context", "label": "Source Material (optional)",
             "description": "Extra reference text to guide the AI when deepening."},
        ],
        "outputs": [
            {"name": "out",       "label": "Report (JSON)", "description": "Lists of applied and failed expansions."},
            {"name": "entity_id", "label": "Entity ID",     "description": "ID of the entity that was deepened."},
            {"name": "applied",   "label": "Applied",       "description": "Number of sub-topics successfully expanded."},
            {"name": "failed",    "label": "Failed",        "description": "Number of sub-topics that could not be expanded."},
            {"name": "error",     "label": "Error",         "description": "Error message if deepening failed entirely."},
        ],
        "properties": [
            {"key": "database",      "label": "Database",        "type": "aethviondb_db", "default": "default"},
            {"key": "model",         "label": "AI Model",        "type": "model_select",  "default": "auto"},
            {"key": "max_stubs",     "label": "Max Sub-topics",  "type": "number", "default": 5,
             "description": "Maximum number of stubs to expand in one run (1–20)."},
            {"key": "entity_ref",    "label": "Entity ID / Name","type": "text", "default": "",
             "placeholder": "Fallback when 'in' port is empty"},
            {"key": "extra_context", "label": "Source Material", "type": "textarea", "default": "",
             "placeholder": "Fallback when 'context' port is empty"},
        ],
    },
    # ── AethvionDB — snapshots ────────────────────────────────────────────────
    {
        "type":     "aethviondb.create_snapshot",
        "label":    "Create Snapshot",
        "category": "AethvionDB",
        "icon":     "fa-camera",
        "color":    "#38bdf8",
        "inputs": [
            {"name": "in", "label": "Snapshot Name",
             "description": "Name for the snapshot file (overrides Snapshot Name property)."},
        ],
        "outputs": [
            {"name": "out",   "label": "Meta (JSON)", "description": "Snapshot metadata including path, counts and timing."},
            {"name": "path",  "label": "Output Path", "description": "Absolute path to the baked snapshot file."},
            {"name": "count", "label": "Entity Count","description": "Number of entities written to the snapshot."},
            {"name": "speed", "label": "Speed",       "description": "Bake duration in milliseconds."},
            {"name": "error", "label": "Error",       "description": "Error message if baking failed."},
        ],
        "properties": [
            {"key": "database",        "label": "Database",       "type": "aethviondb_db", "default": "default"},
            {"key": "snapshot_name",   "label": "Snapshot Name",  "type": "text", "default": "snapshot"},
            {"key": "format",          "label": "Format",         "type": "select",
             "options": [
                 {"value": "jsonl",    "label": "JSONL (streaming / vector-DB ready)"},
                 {"value": "json",     "label": "JSON (single document)"},
                 {"value": "markdown", "label": "Markdown (RAG / LLM prompts)"},
                 {"value": "txt",      "label": "Plain text (compact)"},
             ], "default": "jsonl"},
            {"key": "include_stubs",   "label": "Include Stubs",   "type": "toggle", "default": True},
            {"key": "include_vectors", "label": "Include Vectors", "type": "toggle", "default": False},
        ],
    },
    {
        "type":     "aethviondb.list_snapshots",
        "label":    "List Snapshots",
        "category": "AethvionDB",
        "icon":     "fa-camera-rotate",
        "color":    "#38bdf8",
        "inputs":  [],
        "outputs": [
            {"name": "out",   "label": "Snapshots (JSON)", "description": "Array of snapshot metadata objects, newest first."},
            {"name": "count", "label": "Count",            "description": "Number of snapshots found."},
            {"name": "error", "label": "Error",            "description": "Error message if listing failed."},
        ],
        "properties": [
            {"key": "database", "label": "Database", "type": "aethviondb_db", "default": "default"},
        ],
    },
    # ── AethvionDB — maintenance ──────────────────────────────────────────────
    {
        "type":     "aethviondb.validate",
        "label":    "Validate Database",
        "category": "AethvionDB",
        "icon":     "fa-shield-check",
        "color":    "#fb923c",
        "inputs": [
            {"name": "in", "label": "Entity ID or Name (optional)",
             "description": "Leave empty to validate the entire database. Connect an entity ID/name to validate a single entity."},
        ],
        "outputs": [
            {"name": "out",    "label": "Report (JSON)", "description": "Validation report with total, ok, errors and issues list."},
            {"name": "total",  "label": "Total",         "description": "Total entities checked."},
            {"name": "ok",     "label": "OK",            "description": "Entities with no errors."},
            {"name": "errors", "label": "Errors",        "description": "Entities with at least one error."},
            {"name": "error",  "label": "Node Error",    "description": "Non-empty only if the node itself failed."},
        ],
        "properties": [
            {"key": "database",   "label": "Database",        "type": "aethviondb_db", "default": "default"},
            {"key": "entity_ref", "label": "Entity ID / Name","type": "text", "default": "",
             "placeholder": "Fallback when 'in' port is empty — blank = whole DB"},
        ],
    },
    {
        "type":     "aethviondb.generate_vectors",
        "label":    "Generate Vectors",
        "category": "AethvionDB",
        "icon":     "fa-microchip",
        "color":    "#fb923c",
        "inputs":  [],
        "outputs": [
            {"name": "out",        "label": "Report (JSON)", "description": "Summary with model, counts and speed."},
            {"name": "vectorized", "label": "Vectorized",    "description": "Entities successfully embedded."},
            {"name": "skipped",    "label": "Skipped",       "description": "Entities skipped (already had embeddings, or stubs when include_stubs is off)."},
            {"name": "failed",     "label": "Failed",        "description": "Entities that failed to embed."},
            {"name": "speed",      "label": "Speed",         "description": "Total vectorization time."},
            {"name": "error",      "label": "Error",         "description": "Error message if vectorization failed."},
        ],
        "properties": [
            {"key": "database",      "label": "Database",       "type": "aethviondb_db", "default": "default"},
            {"key": "model",         "label": "Embedding Model","type": "select",
             "options": [
                 {"value": "text-embedding-004",     "label": "Gemini text-embedding-004 (Google)"},
                 {"value": "embedding-001",          "label": "Gemini embedding-001 (Google)"},
                 {"value": "text-embedding-3-small", "label": "text-embedding-3-small (OpenAI)"},
                 {"value": "text-embedding-3-large", "label": "text-embedding-3-large (OpenAI)"},
                 {"value": "text-embedding-ada-002", "label": "text-embedding-ada-002 (OpenAI)"},
             ], "default": "text-embedding-004"},
            {"key": "force_rewrite", "label": "Re-embed All",    "type": "toggle", "default": False,
             "description": "Re-generate embeddings even for entities that already have them."},
            {"key": "include_stubs", "label": "Include Stubs",   "type": "toggle", "default": False,
             "description": "Also embed stub entities (not yet expanded)."},
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
    viewport: dict[str, Any] | None = None


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


@router.get("/aethviondb/databases")
async def get_aethviondb_databases():
    """Return all registered AethvionDB database names."""
    try:
        from core.aethviondb.db_registry import list_dbs  # noqa: PLC0415
        names = [d["name"] for d in list_dbs()]
        if not names:
            names = ["default"]
    except Exception:
        names = ["default"]
    return {"databases": names}


@router.get("/aethviondb/snapshots")
async def get_aethviondb_snapshots(db: str = "default"):
    """Return all snapshot names for a given AethvionDB database, newest-first."""
    try:
        from core.aethviondb.db_registry import resolve_db_root  # noqa: PLC0415
        from core.aethviondb.baker import list_bakes              # noqa: PLC0415
        root   = resolve_db_root(db)
        bakes  = list_bakes(root)
        names  = [b["name"] for b in bakes if b.get("name")]
    except Exception:
        names = []
    return {"snapshots": names}


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
    if body.viewport is not None:
        wf["viewport"] = body.viewport
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


class RunWorkflowBody(BaseModel):
    variables:  Optional[dict] = None  # {name: value} — injected into global.* nodes at runtime
    trigger_id: Optional[str]  = None  # node id of the specific trigger to run from


@router.post("/workflows/{wf_id}/run")
async def run_workflow(wf_id: str, body: RunWorkflowBody = RunWorkflowBody()):
    """Execute a workflow and return the full result including per-node status and outputs."""
    p = _wf_path(wf_id)
    if not p.exists():
        raise HTTPException(404, "Workflow not found")
    wf = json.loads(p.read_text(encoding="utf-8"))

    from core.automate.executor import WorkflowExecutor  # noqa: PLC0415
    executor = WorkflowExecutor(wf, variables=body.variables or {}, trigger_id=body.trigger_id)
    result   = await asyncio.to_thread(executor.execute)
    return result


@router.post("/workflows/{wf_id}/run-stream")
async def run_workflow_stream(wf_id: str, body: RunWorkflowBody = RunWorkflowBody()):
    """
    Execute a workflow and stream node-level progress as SSE events.

    Each event is a JSON object on a ``data:`` line followed by two newlines.
    Event types:
        {type: "node_status", node_id, status: "running"|"done"|"error"|"skipped",
         outputs?, error?}
        {type: "log", level: "info"|"warning"|"error", msg, ts}
        {type: "done", result}   — last event; ``result`` is the full executor result dict
    """
    p = _wf_path(wf_id)
    if not p.exists():
        raise HTTPException(404, "Workflow not found")
    wf = json.loads(p.read_text(encoding="utf-8"))

    loop  = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _emit(event: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    async def _generate():
        from core.automate.executor import WorkflowExecutor  # noqa: PLC0415

        async def _run_executor():
            executor = WorkflowExecutor(
                wf,
                variables=body.variables or {},
                trigger_id=body.trigger_id,
                event_callback=_emit,
            )
            result = await asyncio.to_thread(executor.execute)
            queue.put_nowait({"type": "done", "result": result})

        task = asyncio.create_task(_run_executor())

        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get("type") == "done":
                break

        await task  # surface any unhandled exception

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Examples + Import/Export/Share ────────────────────────────────────────────

_EXAMPLES_DIR = Path(__file__).parent / "config"
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


# ── Compile ───────────────────────────────────────────────────────────────────

class CompileOptions(BaseModel):
    include_packages: bool = True
    include_api_key:  bool = False
    include_snapshot: bool = False


def _human_size(n: int) -> str:
    """Format a byte count as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n} {unit}"
        n //= 1024
    return f"{n} TB"


@router.get("/workflows/{wf_id}/compile-info")
async def get_compile_info(wf_id: str):
    """
    Return pre-flight information about what options are relevant for compiling
    this workflow.  Used by the UI to conditionally show/hide compile options.

    Returns:
        needs_api_key      — True when the workflow contains nodes that use API keys
        has_snapshot_nodes — True when the workflow contains aethviondb.snapshot_search nodes
        has_live_db_search — True when the workflow contains aethviondb.search nodes
        snapshot_info      — list of {db, snap_name, size_bytes, size_display} per unique snapshot
    """
    p = _wf_path(wf_id)
    if not p.exists():
        raise HTTPException(404, "Workflow not found")

    wf = json.loads(p.read_text(encoding="utf-8"))

    try:
        from core.automate.compiler import _analyze_workflow  # noqa: PLC0415
    except ImportError as exc:
        raise HTTPException(500, f"Compiler module not available: {exc}")

    analysis = _analyze_workflow(wf)

    snapshot_info = [
        {
            "db":           s["db"],
            "snap_name":    s["snap_name"],
            "size_bytes":   s["size_bytes"],
            "size_display": _human_size(s["size_bytes"]),
        }
        for s in analysis.get("snapshot_nodes", [])
    ]

    return {
        "needs_api_key":      analysis.get("needs_api_key", False),
        "has_snapshot_nodes": analysis.get("has_snapshot_nodes", False),
        "has_live_db_search": analysis.get("has_live_db_search", False),
        "snapshot_info":      snapshot_info,
    }


@router.post("/workflows/{wf_id}/compile")
async def compile_workflow(wf_id: str, body: CompileOptions):
    """
    Compile a workflow into a standalone zip bundle.

    The zip contains run.py (embedded executor + FastAPI server + web UI),
    workflow.json, requirements.txt, .env, start.bat, start.sh, and
    optionally a packages/ folder with pre-downloaded pip wheels.
    """
    p = _wf_path(wf_id)
    if not p.exists():
        raise HTTPException(404, "Workflow not found")

    wf = json.loads(p.read_text(encoding="utf-8"))

    try:
        from core.automate.compiler import compile_workflow as _compile  # noqa: PLC0415
    except ImportError as exc:
        raise HTTPException(500, f"Compiler module not available: {exc}")

    # Run in a thread — pip download can be slow
    import re as _re
    from fastapi.responses import Response  # noqa: PLC0415

    def _run_compile():
        return _compile(wf, {
            "include_packages": body.include_packages,
            "include_api_key":  body.include_api_key,
            "include_snapshot": body.include_snapshot,
        })

    try:
        zip_bytes, warnings = await asyncio.to_thread(_run_compile)
    except Exception as exc:
        raise HTTPException(500, f"Compilation failed: {exc}")

    safe_name = _re.sub(r"[^\w\-]", "_", wf.get("name", "workflow"))
    filename  = f"{safe_name}_standalone.zip"

    headers: dict[str, str] = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Compile-Warnings":  "; ".join(warnings)[:500] if warnings else "",
    }

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers=headers,
    )
