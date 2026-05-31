"""
core/automate/automate_routes.py
════════════════════════════════
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
from core.providers import get_provider_manager as _get_pm

router = APIRouter(prefix="/api/automate", tags=["automate"])

# ── Storage ───────────────────────────────────────────────────────────────────

_DATA_DIR      = Path(__file__).parent.parent.parent / "data" / "automate" / "workflows"
_REGISTRY_PATH = Path(__file__).parent.parent.parent / "data" / "config" / "model_registry.json"


def _ensure_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _wf_path(wf_id: str) -> Path:
    return _DATA_DIR / f"{wf_id}.json"


# ── Node type registry (lazy) ─────────────────────────────────────
# Loaded on first request — not at import time — so startup pays no
# cost if the user never opens the Automate page.
_NODES_DIR         = Path(__file__).parent.parent / "config" / "automate" / "nodes"
_node_types_cache: list[dict] | None = None


def _get_node_types() -> list[dict]:
    global _node_types_cache
    if _node_types_cache is None:
        _node_types_cache = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(_NODES_DIR.glob("*.json"))
        ]
    return _node_types_cache


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
    return {"node_types": _get_node_types()}


@router.get("/models")
async def get_models(provider: Optional[str] = None):
    """
    Return configured chat-capable models from the model registry.
    Pass ?provider=google_ai to filter to a specific provider.
    """
    registry = load_json(_REGISTRY_PATH, default={})
    if not registry:
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
    wf["updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    atomic_json_write(p, wf)
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
