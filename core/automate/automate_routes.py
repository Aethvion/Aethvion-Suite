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
        "outputs": [{"name": "out", "label": "Trigger"}],
        "properties": [],
    },
    {
        "type": "trigger.schedule",
        "label": "Schedule",
        "category": "Triggers",
        "icon": "fa-clock",
        "color": "#22d3ee",
        "inputs": [],
        "outputs": [{"name": "out", "label": "Trigger"}],
        "properties": [
            {
                "key": "cron",
                "label": "Cron Expression",
                "type": "text",
                "default": "0 * * * *",
                "placeholder": "0 * * * * (every hour)",
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
        "inputs": [{"name": "in", "label": "Input Data"}],
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
        "inputs": [{"name": "in", "label": "Input Data"}],
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
    """Trigger workflow execution (stub — execution engine coming in a future version)."""
    p = _wf_path(wf_id)
    if not p.exists():
        raise HTTPException(404, "Workflow not found")
    wf = json.loads(p.read_text(encoding="utf-8"))
    return {
        "ok": True,
        "message": f"Workflow '{wf['name']}' queued for execution. (Execution engine coming soon.)",
        "workflow_id": wf_id,
    }
