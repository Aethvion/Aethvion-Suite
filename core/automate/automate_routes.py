"""
core/automate/automate_routes.py
Isolated Automate module backend.
Handles workflow CRUD, node type registry, model listing, and node test-execution.

The AI execution endpoint (node/test) imports ProviderManager lazily — it uses only
the call_with_failover() utility, sharing no workflow state with other modules.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.utils import atomic_json_write, load_json
from core.utils.paths import LOCAL_MODELS_GGUF, MODEL_REGISTRY
from core.providers import get_provider_manager as _get_pm

router = APIRouter(prefix="/api/automate", tags=["automate"])

# Storage

_DATA_DIR      = Path(__file__).parent.parent.parent / "data" / "automate" / "workflows"
_REGISTRY_PATH = MODEL_REGISTRY


def _ensure_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _wf_path(wf_id: str) -> Path:
    return _DATA_DIR / f"{wf_id}.json"


def _get_installed_local_models() -> list[dict[str, Any]]:
    """Scan local models directory and registry for installed offline models."""
    items = []
    seen = set()

    # 1. Scan filesystem for downloaded .gguf files
    if LOCAL_MODELS_GGUF.exists():
        for f in sorted(LOCAL_MODELS_GGUF.glob("*.gguf")):
            fname = f.name
            seen.add(fname)
            try:
                size_mb = round(f.stat().st_size / (1024 * 1024), 1)
            except Exception:
                size_mb = None
            clean_name = fname.replace(".gguf", "").replace("-", " ").replace("_", " ").title()
            items.append({
                "id": fname,
                "filename": fname,
                "label": clean_name,
                "size_mb": size_mb,
                "provider": "local"
            })

    # 2. Check registry for local / ollama registered models
    reg = load_json(_REGISTRY_PATH, default={})
    providers = reg.get("providers", {})
    for prov_id in ("local", "ollama"):
        p_info = providers.get(prov_id, {})
        for m_id, m_data in p_info.get("models", {}).items():
            if m_id and m_id not in seen:
                seen.add(m_id)
                clean_name = m_id.replace(".gguf", "").replace("-", " ").replace("_", " ").title()
                items.append({
                    "id": m_id,
                    "filename": m_id,
                    "label": clean_name,
                    "size_mb": None,
                    "provider": prov_id
                })

    return items


# Node type registry (lazy)
_NODES_DIR = Path(__file__).parent.parent / "config" / "automate" / "nodes"
_base_node_types_cache: list[dict] | None = None


def _get_node_types() -> list[dict]:
    global _base_node_types_cache
    if _base_node_types_cache is None:
        _base_node_types_cache = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(_NODES_DIR.glob("*.json"))
        ]
    
    # Start with base nodes (shallow copies)
    result = [dict(t) for t in _base_node_types_cache]

    # Dynamically inject dedicated node cards for each installed local model
    installed_locals = _get_installed_local_models()
    for m in installed_locals:
        slug = m["id"].replace(".", "_").replace("-", "_").lower()
        size_tag = f" ({m['size_mb']} MB)" if m.get("size_mb") else ""
        result.append({
            "type": f"ai.local.{slug}",
            "label": f"{m['label']}{size_tag}",
            "category": "Installed Models",
            "icon": "fa-microchip",
            "color": "#10b981",
            "inputs": [
                {
                    "name": "in",
                    "label": "Input Data",
                    "description": f"Main content passed to {m['label']}."
                },
                {
                    "name": "system_prompt",
                    "label": "System Prompt",
                    "description": "Overrides default instructions."
                },
                {
                    "name": "prompt_prefix",
                    "label": "Prefix",
                    "description": "Text prepended to input."
                },
                {
                    "name": "prompt_suffix",
                    "label": "Suffix",
                    "description": "Text appended to input."
                },
                {
                    "name": "temperature",
                    "label": "Temperature",
                    "description": "Overrides creativity at runtime (0.0 - 1.0)."
                }
            ],
            "outputs": [
                {
                    "name": "out",
                    "label": "Response",
                    "description": "AI-generated text response."
                },
                {
                    "name": "error",
                    "label": "Error",
                    "description": "Error details if offline inference failed."
                }
            ],
            "properties": [
                {
                    "key": "model",
                    "label": "Model File",
                    "type": "text",
                    "default": m["id"],
                    "placeholder": m["id"]
                },
                {
                    "key": "system_prompt",
                    "label": "System Prompt",
                    "type": "textarea",
                    "default": "You are a helpful offline assistant.",
                    "placeholder": "System instructions..."
                },
                {
                    "key": "prompt_prefix",
                    "label": "Prompt Prefix",
                    "type": "textarea",
                    "default": "",
                    "placeholder": "Text added before input..."
                },
                {
                    "key": "prompt_suffix",
                    "label": "Prompt Suffix",
                    "type": "textarea",
                    "default": "",
                    "placeholder": "Text added after input..."
                },
                {
                    "key": "temperature",
                    "label": "Temperature",
                    "type": "number",
                    "default": 0.7
                },
                {
                    "key": "show_result",
                    "label": "Show Result on Node",
                    "type": "toggle",
                    "default": True
                }
            ]
        })

    return result


# Pydantic models

class WorkflowCreate(BaseModel):
    name: str
    nodes: list[dict[str, Any]] = []
    connections: list[dict[str, Any]] = []
    active: bool = False


class WorkflowUpdate(BaseModel):
    name: str | None = None
    nodes: list[dict[str, Any]] | None = None
    connections: list[dict[str, Any]] | None = None
    viewport: dict[str, Any] | None = None
    active: bool | None = None


class NodeTestRequest(BaseModel):
    node: dict[str, Any]
    input_data: str = ""


# Routes

@router.get("/node-types")
async def get_node_types():
    """Return all available node type definitions."""
    return {"node_types": _get_node_types()}


@router.get("/models")
async def get_models(provider: Optional[str] = None):
    """
    Return configured chat-capable models from the model registry and local model directory.
    Pass ?provider=local to filter to installed offline models (GGUF / Ollama).
    Pass ?provider=google_ai to filter to Google AI models.
    """
    models = []
    seen_ids = set()

    # 1. Local / Ollama models
    if provider in (None, "", "local", "any"):
        installed_locals = _get_installed_local_models()
        for lm in installed_locals:
            seen_ids.add(lm["id"])
            size_str = f" ({lm['size_mb']} MB)" if lm.get("size_mb") else ""
            prov_label = "Local GGUF" if lm["provider"] == "local" else "Ollama"
            models.append({
                "id": lm["id"],
                "provider_id": lm["provider"],
                "provider_name": prov_label,
                "label": f"{lm['label']}{size_str} [{prov_label}]",
                "description": f"Installed offline model: {lm['filename']}",
            })

    # If caller only wants local models, return them immediately
    if provider == "local":
        return {"models": models}

    # 2. Registry cloud & API models
    registry = load_json(_REGISTRY_PATH, default={})
    if registry:
        for prov_id, prov_data in registry.get("providers", {}).items():
            if not prov_data.get("active", False):
                continue
            if provider and prov_id != provider:
                continue
            prov_name = prov_data.get("name", prov_id)
            for model_id, model_data in prov_data.get("models", {}).items():
                if model_id in seen_ids:
                    continue
                caps = [c.upper() for c in model_data.get("capabilities", [])]
                if "CHAT" not in caps:
                    continue
                seen_ids.add(model_id)
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
                "active": bool(wf.get("active", False)),
            })
        except Exception:
            pass
    return {"workflows": items}


@router.get("/workflows/active")
async def get_active_workflows():
    """Return all active workflows summary and total count."""
    _ensure_dir()
    active = []
    for p in sorted(_DATA_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            wf = json.loads(p.read_text(encoding="utf-8"))
            if wf.get("active"):
                active.append({
                    "id": wf.get("id"),
                    "name": wf.get("name", "Unnamed"),
                    "node_count": len(wf.get("nodes", [])),
                    "updated": wf.get("updated"),
                    "active": True,
                })
        except Exception:
            pass
    return {"active_workflows": active, "count": len(active)}


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
        "active": body.active,
        "nodes": body.nodes,
        "connections": body.connections,
    }
    atomic_json_write(_wf_path(wf_id), wf)
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
    if body.active is not None:
        wf["active"] = bool(body.active)
    wf["updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    atomic_json_write(p, wf)
    return {"workflow": wf}


@router.patch("/workflows/{wf_id}/toggle-active")
async def toggle_workflow_active(wf_id: str):
    """Toggle the active status of a workflow."""
    p = _wf_path(wf_id)
    if not p.exists():
        raise HTTPException(404, "Workflow not found")
    wf = json.loads(p.read_text(encoding="utf-8"))
    wf["active"] = not bool(wf.get("active", False))
    wf["updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    atomic_json_write(p, wf)
    return {"id": wf_id, "active": wf["active"], "name": wf.get("name", "Unnamed")}


@router.post("/workflows/{wf_id}/duplicate")
async def duplicate_workflow(wf_id: str):
    """Duplicate an existing workflow with fresh IDs."""
    p = _wf_path(wf_id)
    if not p.exists():
        raise HTTPException(404, "Workflow not found")
    wf = json.loads(p.read_text(encoding="utf-8"))
    return await _import_workflow_data(wf, name_suffix=" (Copy)")


@router.delete("/workflows/{wf_id}")
async def delete_workflow(wf_id: str):
    """Delete a workflow."""
    p = _wf_path(wf_id)
    if not p.exists():
        raise HTTPException(404, "Workflow not found")
    p.unlink()
    return {"ok": True}


class RunWorkflowBody(BaseModel):
    variables:  Optional[dict] = None  # {name: value} - injected into global.* / flow.input nodes at runtime
    trigger_id: Optional[str]  = None  # node id of the specific trigger to run from


# Run registry + history
#
# Every run gets an id.  While it is executing it can be cancelled; when it finishes a
# trimmed copy of the result is written to data/automate/runs/<run_id>.json so past runs
# (status, log, outputs, produced assets) can be looked at again.

_RUNS_DIR      = Path(__file__).parent.parent.parent / "data" / "automate" / "runs"
_RUNS_KEEP     = 300          # newest N run records kept on disk
_ACTIVE_RUNS: dict[str, Any] = {}   # run_id -> WorkflowExecutor


def _trim_for_history(val: Any, depth: int = 0) -> Any:
    """Make a node output safe to keep: drop inline binaries, cap long strings."""
    if isinstance(val, str):
        if val.startswith("data:") and len(val) > 256:
            return f"[inline data, {len(val):,} chars - not stored]"
        return val if len(val) <= 4000 else val[:4000] + f"... [+{len(val) - 4000:,} chars]"
    if isinstance(val, dict):
        if depth > 6:
            return "[nested object]"
        return {k: _trim_for_history(v, depth + 1) for k, v in list(val.items())[:200]}
    if isinstance(val, (list, tuple)):
        if depth > 6:
            return "[nested list]"
        return [_trim_for_history(v, depth + 1) for v in list(val)[:200]]
    if isinstance(val, (bytes, bytearray)):
        return f"[{len(val):,} bytes]"
    return val


def _record_run(wf: dict, result: dict, started_at: str, trigger_id: Optional[str]) -> None:
    try:
        _RUNS_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "run_id":        result.get("run_id"),
            "workflow_id":   wf.get("id"),
            "workflow_name": wf.get("name"),
            "trigger_id":    trigger_id,
            "started_at":    started_at,
            "finished_at":   datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "ok":            result.get("ok"),
            "cancelled":     result.get("cancelled", False),
            "fatal":         result.get("fatal"),
            "node_status":   result.get("node_status", {}),
            "node_durations": result.get("node_durations", {}),
            "node_errors":   result.get("node_errors", {}),
            "node_outputs":  _trim_for_history(result.get("node_outputs", {})),
            "returns":       _trim_for_history(result.get("returns", {})),
            "log":           (result.get("log") or [])[-1500:],
        }
        atomic_json_write(_RUNS_DIR / f"{record['run_id']}.json", record)
        files = sorted(_RUNS_DIR.glob("run_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        for old in files[_RUNS_KEEP:]:
            old.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001 - history is best-effort and must never fail a run
        pass


def _load_workflow_or_404(wf_id: str) -> dict:
    p = _wf_path(wf_id)
    if not p.exists():
        raise HTTPException(404, "Workflow not found")
    return json.loads(p.read_text(encoding="utf-8"))


@router.post("/workflows/{wf_id}/run")
async def run_workflow(wf_id: str, body: RunWorkflowBody = RunWorkflowBody()):
    """Execute a workflow and return the full result including per-node status and outputs."""
    wf = _load_workflow_or_404(wf_id)

    from core.automate.executor import WorkflowExecutor  # noqa: PLC0415
    started  = datetime.datetime.now(datetime.timezone.utc).isoformat()
    executor = WorkflowExecutor(wf, variables=body.variables or {}, trigger_id=body.trigger_id)
    _ACTIVE_RUNS[executor.run_id] = executor
    try:
        result = await asyncio.to_thread(executor.execute)
    finally:
        _ACTIVE_RUNS.pop(executor.run_id, None)
    _record_run(wf, result, started, body.trigger_id)
    return result


@router.post("/workflows/{wf_id}/run-stream")
async def run_workflow_stream(wf_id: str, body: RunWorkflowBody = RunWorkflowBody()):
    """
    Execute a workflow and stream node-level progress as SSE events.

    Each event is a JSON object on a ``data:`` line followed by two newlines.
    Event types:
        {type: "run_started", run_id}   - first event; use run_id to cancel the run
        {type: "node_status", node_id, status: "running"|"done"|"error"|"skipped",
         outputs?, error?, reason?}
        {type: "log", level: "info"|"warning"|"error", msg, ts}
        {type: "done", result}   - last event; ``result`` is the full executor result dict
    """
    wf = _load_workflow_or_404(wf_id)

    loop  = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _emit(event: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    async def _generate():
        from core.automate.executor import WorkflowExecutor  # noqa: PLC0415

        started  = datetime.datetime.now(datetime.timezone.utc).isoformat()
        executor = WorkflowExecutor(
            wf,
            variables=body.variables or {},
            trigger_id=body.trigger_id,
            event_callback=_emit,
        )
        _ACTIVE_RUNS[executor.run_id] = executor

        async def _run_executor():
            try:
                result = await asyncio.to_thread(executor.execute)
            finally:
                _ACTIVE_RUNS.pop(executor.run_id, None)
            _record_run(wf, result, started, body.trigger_id)
            queue.put_nowait({"type": "done", "result": result})

        task = asyncio.create_task(_run_executor())
        yield f"data: {json.dumps({'type': 'run_started', 'run_id': executor.run_id})}\n\n"

        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
                if event.get("type") == "done":
                    break
            await task  # surface any unhandled exception
        finally:
            # Client went away mid-run (tab closed, Stop pressed): stop scheduling new nodes.
            if not task.done():
                executor.cancel()

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    """Ask a running workflow to stop. Nodes already running finish; nothing new starts."""
    executor = _ACTIVE_RUNS.get(run_id)
    if not executor:
        raise HTTPException(404, "Run is not active (already finished, or unknown id)")
    executor.cancel()
    return {"ok": True, "run_id": run_id}


@router.get("/runs/active")
async def active_runs():
    return {"runs": [{"run_id": rid, "workflow_id": ex.workflow.get("id"),
                      "workflow_name": ex.workflow.get("name")} for rid, ex in _ACTIVE_RUNS.items()]}


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    if not run_id.startswith("run_") or not run_id.replace("_", "").isalnum():
        raise HTTPException(400, "Bad run id")
    p = _RUNS_DIR / f"{run_id}.json"
    if not p.exists():
        raise HTTPException(404, "Run not found")
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/workflows/{wf_id}/runs")
async def list_runs(wf_id: str, limit: int = 30):
    """Recent runs of one workflow (summaries, newest first). Use wf_id='all' for every workflow."""
    items = []
    if _RUNS_DIR.exists():
        files = sorted(_RUNS_DIR.glob("run_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        for f in files:
            rec = load_json(f, default=None)
            if not isinstance(rec, dict) or (wf_id != "all" and rec.get("workflow_id") != wf_id):
                continue
            statuses = list((rec.get("node_status") or {}).values())
            items.append({
                "run_id": rec.get("run_id"), "workflow_id": rec.get("workflow_id"),
                "workflow_name": rec.get("workflow_name"), "started_at": rec.get("started_at"),
                "finished_at": rec.get("finished_at"), "ok": rec.get("ok"),
                "cancelled": rec.get("cancelled", False),
                "nodes_done": statuses.count("done"), "nodes_error": statuses.count("error"),
                "nodes_skipped": statuses.count("skipped"),
            })
            if len(items) >= max(1, min(limit, 200)):
                break
    return {"runs": items}


@router.get("/workflow-options")
async def workflow_options():
    """Saved workflows shaped for a `model_select` property - used by the Flow nodes."""
    _ensure_dir()
    opts = []
    for p in sorted(_DATA_DIR.glob("*.json")):
        try:
            wf = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        types = [n.get("type", "") for n in wf.get("nodes", [])]
        ins  = sum(1 for t in types if t == "flow.input" or t.startswith("global."))
        outs = types.count("flow.return")
        opts.append({"id": wf.get("id", p.stem), "label": wf.get("name", p.stem),
                     "description": f"{len(types)} nodes, {ins} input(s), {outs} return(s)"})
    opts.sort(key=lambda o: o["label"].lower())
    return {"models": opts}


# Examples + Import/Export/Share

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
    atomic_json_write(_wf_path(new_id), wf)
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

    # Examples that call sub-workflows list them under "requires". Import any that are
    # not in the workspace yet (matched by name) so the example runs straight away.
    also_loaded: list[str] = []
    existing = {str(o["label"]).strip().lower() for o in (await workflow_options())["models"]}
    for req_id in data.get("requires", []) or []:
        rp = _EXAMPLES_DIR / f"{Path(str(req_id)).name}.json"
        if not rp.exists():
            continue
        try:
            req_data = json.loads(rp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(req_data.get("name", "")).strip().lower() not in existing:
            await _import_workflow_data(req_data)
            also_loaded.append(req_data.get("name", req_id))

    result = await _import_workflow_data(data)
    result["also_loaded"] = also_loaded
    return result


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


# Compile

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
