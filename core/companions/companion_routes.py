"""
core/companions/companion_routes.py
Unified dynamic router for all Aethvion companions.
"""

import asyncio
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
import json
import shutil
from pathlib import Path
from core.utils.paths import COMPANIONS
from core.utils import atomic_json_write
from pydantic import BaseModel

from core.companions.registry import CompanionRegistry
from core.companions.companion_engine import CompanionEngine
from core.companions.engine.memory import CompanionMemory
from core.companions.engine.history import CompanionHistory
from core.companions.engine.scratchpad import CompanionScratchpad
from core.companions.engine.visual_memory import CompanionVisualMemory
from core.workspace.workspace_utils import load_workspaces, save_workspaces
from core.bridges.bridge_manager import get_registry

router = APIRouter(prefix="/api/companions", tags=["companions"])

_TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".csv", ".html", ".css", ".scss", ".sql", ".sh",
    ".ps1", ".bat", ".c", ".cpp", ".h", ".hpp", ".cs", ".rs", ".go", ".java",
    ".kt", ".rb", ".php", ".xml", ".log", ".env"
}

class ScratchpadSaveRequest(BaseModel):
    content: str

class ScratchpadAppendRequest(BaseModel):
    text: str
    section: Optional[str] = None
    author: Optional[Dict[str, Any]] = None

class VisualMemoryCreateRequest(BaseModel):
    title: str
    category: str = "general"
    description: Optional[str] = ""
    key_elements: Optional[List[str]] = None
    image_path: Optional[str] = None
    monitor: int = 0
    tags: Optional[List[str]] = None

class VisualMemoryUpdateRequest(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    key_elements: Optional[List[str]] = None
    tags: Optional[List[str]] = None

class VisualMemoryCompareRequest(BaseModel):
    memory_id: Optional[str] = None
    query: Optional[str] = None
    monitor: int = 0

class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage]
    attachments: Optional[List[Dict[str, Any]]] = None

class InitiateRequest(BaseModel):
    trigger: str = "startup"
    instruction: Optional[str] = None

class CompanionTimerRequest(BaseModel):
    minutes: float = 5.0
    reason: str = "Proactive check-in"
    context: Optional[str] = None

class QuickConfigRequest(BaseModel):
    default_model: Optional[str] = None
    connector_profile: Optional[str] = None
    auto_speak: Optional[bool] = None
    proactive_enabled: Optional[bool] = None

class WorkspaceRequest(BaseModel):
    label: str
    path: str
    permissions: List[str]
    recursive: bool = True

class SpotifyAuthRequest(BaseModel):
    client_id: str
    client_secret: str
    redirect_uri: str = "http://localhost:8080/callback"

class MemoryFactRequest(BaseModel):
    key: str
    value: str

class MemoryObservationRequest(BaseModel):
    text: str

def _get_cfg(cid: str):
    if not (cfg := CompanionRegistry.get_companion(cid)):
        raise HTTPException(status_code=404, detail=f"Companion '{cid}' not found")
    return cfg

@router.get("/list")
async def list_companions():
    return {"companions": CompanionRegistry.list_companions()}

@router.get("/timers/due")
async def get_due_timers():
    """Poll and pop any companion follow-up timers that have reached due_ts."""
    from core.bridges import companion_timer_bridge
    due = await asyncio.to_thread(companion_timer_bridge.pop_due_companion_timers)
    return {"due": due}

@router.post("/timers/{timer_id}/trigger")
async def trigger_due_timer(timer_id: str):
    """Trigger a due companion timer: generates intelligent in-character follow-up check-in with stored context."""
    from core.bridges import companion_timer_bridge
    timers = await asyncio.to_thread(companion_timer_bridge._load_timers)
    target = next((t for t in timers if t.get("id") == timer_id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Timer '{timer_id}' not found")
    
    cid = target.get("companion_id", "misakacipher")
    cfg = _get_cfg(cid)
    reason = target.get("reason", "Proactive follow-up")
    context = target.get("context", reason)

    import datetime as _dt
    now = _dt.datetime.now()
    now_ts = now.timestamp()
    due_ts = float(target.get("due_ts") or now_ts)
    delay_sec = now_ts - due_ts
    now_str = now.strftime("%H:%M")

    if delay_sec > 120:
        delay_min = max(1, int(delay_sec // 60))
        timing_note = (
            f"Ground Truth Clock: The current time is {now_str}. "
            f"NOTE: This follow-up was originally scheduled for {target.get('due_str', 'earlier')} "
            f"(about {delay_min} minutes ago) and was delayed by a system hiccup. "
            f"Do NOT claim or pretend you arrived right on time or that your internal clock was perfect. "
            f"If acknowledging timing, be honest that you got delayed."
        )
    else:
        timing_note = (
            f"Ground Truth Clock: The current time is {now_str}. "
            f"You are checking in on time as scheduled ({target.get('due_str', now_str)})."
        )

    instruction = (
        f"Scheduled Follow-Up Timer Check-In: Topic is '{reason}'. "
        f"Context/Task: {context}. "
        f"{timing_note} "
        f"Speak directly to the user in character (1-2 sentences) casually following up on this specific matter. "
        f"DO NOT greet the user by name or start with 'Hey [Name]'."
    )
    
    try:
        resp = await CompanionEngine.initiate_response(
            cfg,
            trigger="timer_followup",
            instruction=instruction
        )
        # Mark timer completed with generated response
        await asyncio.to_thread(companion_timer_bridge.mark_timer_completed, timer_id, resp.get("response", ""))
        return {
            "success": True,
            "timer": target,
            "companion": resp
        }
    except Exception as e:
        logger.error(f"Error triggering timer {timer_id}: {e}", exc_info=True)
        await asyncio.to_thread(companion_timer_bridge.mark_timer_completed, timer_id, f"Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{companion_id}/config")
async def get_companion_config(companion_id: str):
    """Return the raw JSON config for a companion (used by the universal companion panel)."""
    return _get_cfg(companion_id)._raw_config

@router.patch("/{companion_id}/quick-config")
async def patch_quick_config(companion_id: str, req: QuickConfigRequest):
    """Hot-update a companion's active model, connector profile, or voice/proactive toggle from the Chat header."""
    cfg = _get_cfg(companion_id)
    override_dir = COMPANIONS / companion_id
    override_dir.mkdir(parents=True, exist_ok=True)
    override_file = override_dir / "config.json"

    if override_file.exists():
        try:
            raw = json.loads(override_file.read_text(encoding="utf-8"))
        except Exception:
            raw = dict(cfg._raw_config)
    else:
        raw = dict(cfg._raw_config)

    if req.default_model is not None:
        raw["default_model"] = req.default_model
        from core.workspace.preferences_manager import get_preferences_manager
        pm = get_preferences_manager()
        cur_pref = pm.get(companion_id, {}) or {}
        if isinstance(cur_pref, dict):
            cur_pref["model"] = req.default_model
            pm.set(companion_id, cur_pref)
    if req.connector_profile is not None:
        raw.setdefault("capabilities", {})["connector_profile"] = req.connector_profile
    if req.auto_speak is not None:
        raw.setdefault("voice", {})["auto_speak"] = req.auto_speak
    if req.proactive_enabled is not None:
        raw.setdefault("capabilities", {})["proactive_enabled"] = req.proactive_enabled
        from core.workspace.preferences_manager import get_preferences_manager
        get_preferences_manager().set(f"{companion_id}.proactive_enabled", req.proactive_enabled)

    atomic_json_write(override_file, raw, indent=2)
    CompanionRegistry.force_reload()
    return {
        "status": "updated",
        "companion_id": companion_id,
        "default_model": raw.get("default_model"),
        "connector_profile": raw.get("capabilities", {}).get("connector_profile", "full_local"),
        "auto_speak": raw.get("voice", {}).get("auto_speak", False),
        "proactive_enabled": raw.get("capabilities", {}).get("proactive_enabled", False),
    }

@router.get("/{companion_id}/memory")
async def get_memory(companion_id: str):
    cfg = _get_cfg(companion_id)
    memory = CompanionMemory(cfg.data_dir, cfg._raw_config.get("personality_defaults", {}), cfg.name)
    memory.initialize()
    return memory.load()

@router.post("/{companion_id}/memory/fact")
async def set_memory_fact(companion_id: str, req: MemoryFactRequest):
    if not req.key.strip():
        raise HTTPException(status_code=400, detail="Fact key cannot be empty.")
    cfg = _get_cfg(companion_id)
    memory = CompanionMemory(cfg.data_dir, cfg._raw_config.get("personality_defaults", {}), cfg.name)
    return memory.set_fact(req.key, req.value)

@router.delete("/{companion_id}/memory/fact/{key}")
async def delete_memory_fact(companion_id: str, key: str):
    cfg = _get_cfg(companion_id)
    memory = CompanionMemory(cfg.data_dir, cfg._raw_config.get("personality_defaults", {}), cfg.name)
    return memory.delete_fact(key)

@router.post("/{companion_id}/memory/observation")
async def add_memory_observation(companion_id: str, req: MemoryObservationRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Observation text cannot be empty.")
    cfg = _get_cfg(companion_id)
    memory = CompanionMemory(cfg.data_dir, cfg._raw_config.get("personality_defaults", {}), cfg.name)
    return memory.add_observation(req.text)

@router.put("/{companion_id}/memory/observation/{index}")
async def update_memory_observation(companion_id: str, index: int, req: MemoryObservationRequest):
    cfg = _get_cfg(companion_id)
    memory = CompanionMemory(cfg.data_dir, cfg._raw_config.get("personality_defaults", {}), cfg.name)
    return memory.update_observation(index, req.text)

@router.delete("/{companion_id}/memory/observation/{index}")
async def delete_memory_observation(companion_id: str, index: int):
    cfg = _get_cfg(companion_id)
    memory = CompanionMemory(cfg.data_dir, cfg._raw_config.get("personality_defaults", {}), cfg.name)
    return memory.delete_observation(index)

@router.delete("/{companion_id}/memory/synthesis/{index}")
async def delete_memory_synthesis(companion_id: str, index: int):
    cfg = _get_cfg(companion_id)
    memory = CompanionMemory(cfg.data_dir, cfg._raw_config.get("personality_defaults", {}), cfg.name)
    return memory.delete_synthesis_note(index)

@router.post("/{companion_id}/memory/synthesize")
async def synthesize_memory(companion_id: str):
    cfg = _get_cfg(companion_id)
    memory = CompanionMemory(cfg.data_dir, cfg._raw_config.get("personality_defaults", {}), cfg.name)
    memory.initialize()
    loaded = memory.load()
    from core.workspace.preferences_manager import get_preferences_manager
    pref_model = get_preferences_manager().get(cfg.id, {}).get("model")
    model = cfg.default_model or pref_model or "auto"
    try:
        result = await memory.run_synthesis(loaded.get("base_info", {}), loaded.get("memory", {}), model)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{companion_id}/scratchpad")
async def get_scratchpad(companion_id: str):
    """Retrieve the shared brainstorming scratchpad for the companion."""
    cfg = _get_cfg(companion_id)
    sp = CompanionScratchpad(cfg.data_dir, cfg.name)
    return sp.load()

@router.post("/{companion_id}/scratchpad")
async def save_scratchpad(companion_id: str, req: ScratchpadSaveRequest):
    """Save/overwrite the shared brainstorming scratchpad."""
    cfg = _get_cfg(companion_id)
    sp = CompanionScratchpad(cfg.data_dir, cfg.name)
    return sp.save(req.content)

@router.post("/{companion_id}/scratchpad/append")
async def append_scratchpad(companion_id: str, req: ScratchpadAppendRequest):
    """Append a note or idea to the shared scratchpad."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Note text cannot be empty.")
    cfg = _get_cfg(companion_id)
    sp = CompanionScratchpad(cfg.data_dir, cfg.name)
    return sp.append_note(req.text, section=req.section, author=req.author)

@router.post("/{companion_id}/scratchpad/clear")
async def clear_scratchpad(companion_id: str):
    """Reset the scratchpad back to the default co-working template."""
    cfg = _get_cfg(companion_id)
    sp = CompanionScratchpad(cfg.data_dir, cfg.name)
    return sp.clear(reset_template=True)

# Visual Context Memory Routes

@router.get("/{companion_id}/visual-memory")
async def get_visual_memories(companion_id: str):
    """Retrieve all visual context memories for the companion."""
    cfg = _get_cfg(companion_id)
    vmem = CompanionVisualMemory(cfg.data_dir, cfg.name)
    return vmem.load()

@router.post("/{companion_id}/visual-memory")
async def create_visual_memory(companion_id: str, req: VisualMemoryCreateRequest):
    """Create or snapshot a new visual memory."""
    cfg = _get_cfg(companion_id)
    vmem = CompanionVisualMemory(cfg.data_dir, cfg.name)
    res = vmem.remember(
        title=req.title,
        category=req.category,
        description=req.description or "",
        key_elements=req.key_elements,
        image_path=req.image_path,
        monitor=req.monitor,
        tags=req.tags,
        source="dashboard_ui"
    )
    if res.get("error"):
        raise HTTPException(status_code=500, detail=res["error"])
    return res

@router.patch("/{companion_id}/visual-memory/{memory_id}")
async def update_visual_memory(companion_id: str, memory_id: str, req: VisualMemoryUpdateRequest):
    """Update metadata of an existing visual memory."""
    cfg = _get_cfg(companion_id)
    vmem = CompanionVisualMemory(cfg.data_dir, cfg.name)
    updates = {k: v for k, v in req.dict().items() if v is not None}
    res = vmem.update(memory_id, updates)
    if not res:
        raise HTTPException(status_code=404, detail="Visual memory not found")
    return {"status": "updated", "memory": res}

@router.delete("/{companion_id}/visual-memory/{memory_id}")
async def delete_visual_memory(companion_id: str, memory_id: str):
    """Delete a visual memory and its snapshot image."""
    cfg = _get_cfg(companion_id)
    vmem = CompanionVisualMemory(cfg.data_dir, cfg.name)
    success = vmem.delete(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Visual memory not found")
    return {"status": "deleted", "id": memory_id}

@router.get("/{companion_id}/visual-memory/snapshots/{filename}")
async def get_visual_snapshot(companion_id: str, filename: str):
    """Serve a visual snapshot image file securely."""
    cfg = _get_cfg(companion_id)
    safe_name = Path(filename).name
    file_path = cfg.data_dir / "visual_snapshots" / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Snapshot image not found")
    return FileResponse(file_path, media_type="image/png")

@router.post("/{companion_id}/visual-memory/compare")
async def compare_visual_memory(companion_id: str, req: VisualMemoryCompareRequest):
    """Compare the active screen with a past visual memory."""
    cfg = _get_cfg(companion_id)
    vmem = CompanionVisualMemory(cfg.data_dir, cfg.name)
    res = vmem.compare(memory_id=req.memory_id, query=req.query, monitor=req.monitor)
    if res.get("error"):
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@router.post("/{companion_id}/history/clear")
async def clear_history_only(companion_id: str):
    """Clear chat message history while keeping persistent memory intact."""
    cfg = _get_cfg(companion_id)
    CompanionHistory(cfg.history_dir, cfg.name).clear()
    return {"status": "history_cleared"}

@router.get("/{companion_id}/history")
async def get_history(companion_id: str, offset_days: int = 0, limit_days: int = 3):
    cfg = _get_cfg(companion_id)
    history = CompanionHistory(cfg.history_dir, cfg.name)
    return history.load_days(offset_days, limit_days)

@router.post("/{companion_id}/initiate")
async def initiate(companion_id: str, request: InitiateRequest):
    return await CompanionEngine.initiate_response(
        _get_cfg(companion_id),
        trigger=request.trigger,
        instruction=request.instruction
    )

@router.get("/{companion_id}/timers")
async def get_companion_timers(companion_id: str):
    """List pending proactive follow-up timers for a companion."""
    from core.bridges import companion_timer_bridge
    timers = await asyncio.to_thread(companion_timer_bridge._load_timers)
    pending = [t for t in timers if t.get("companion_id") == companion_id and t.get("status") == "pending"]
    return {"timers": pending}

@router.post("/{companion_id}/timers")
async def create_companion_timer(companion_id: str, req: CompanionTimerRequest):
    """Schedule a proactive timer for this companion."""
    from core.bridges import companion_timer_bridge
    msg = await asyncio.to_thread(companion_timer_bridge.set_timer, {
        "companion_id": companion_id,
        "minutes": req.minutes,
        "reason": req.reason,
        "context": req.context or req.reason
    })
    return {"success": True, "message": msg}

@router.delete("/{companion_id}/timers/{timer_id}")
async def cancel_companion_timer(companion_id: str, timer_id: str):
    """Cancel a pending proactive timer for this companion."""
    from core.bridges import companion_timer_bridge
    msg = await asyncio.to_thread(companion_timer_bridge.cancel_timer, {"id": timer_id})
    return {"success": True, "message": msg}

@router.post("/{companion_id}/chat")
async def chat(companion_id: str, request: ChatRequest):
    return StreamingResponse(
        CompanionEngine.chat_response(
            _get_cfg(companion_id),
            request.message,
            request.history,
            attachments=request.attachments
        ),
        media_type="application/x-ndjson"
    )

@router.post("/{companion_id}/reset")
async def reset(companion_id: str):
    cfg = _get_cfg(companion_id)
    CompanionHistory(cfg.history_dir, cfg.name).clear()
    memory = CompanionMemory(cfg.data_dir, cfg._raw_config.get("personality_defaults", {}))
    memory.reset(); memory.initialize()
    return {"status": "reset_successful"}

@router.post("/{companion_id}/upload-context")
async def upload_context(companion_id: str, file: UploadFile = File(...)):
    _get_cfg(companion_id) # ensure it exists
    upload_dir = COMPANIONS / companion_id / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Sanitize: strip any directory components so a filename like
    # "../../evil.py" can't escape the upload directory.
    safe_name = Path(file.filename or "upload").name
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    file_path = upload_dir / safe_name

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    content_type: str = file.content_type or ""
    ext = file_path.suffix.lower()
    is_image = content_type.startswith("image/") or ext in {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    text_content = ""
    if not is_image and (content_type.startswith("text/") or ext in _TEXT_EXTENSIONS):
        try:
            raw_text = file_path.read_text(encoding="utf-8", errors="replace")
            text_content = raw_text[:20000]
        except Exception:
            text_content = ""

    return {
        "filename": safe_name,
        "path": str(file_path),
        "url": f"/api/companions/{companion_id}/uploads/{safe_name}",
        "is_image": is_image,
        "text_content": text_content,
    }

@router.get("/{companion_id}/uploads/{filename}")
async def get_uploaded_file(companion_id: str, filename: str):
    _get_cfg(companion_id)
    safe_name = Path(filename).name
    file_path = COMPANIONS / companion_id / "uploads" / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Uploaded file not found")
    return FileResponse(file_path)

@router.get("/{companion_id}/expressions")
async def get_expressions(companion_id: str):
    return _get_cfg(companion_id).expressions

# Managerial Routes (Workspaces & Bridges)

@router.get("/{companion_id}/workspaces")
async def list_companion_workspaces(companion_id: str):
    """Retrieve all workspaces for this companion."""
    return {"workspaces": load_workspaces(companion_id)}

@router.post("/{companion_id}/workspaces")
async def add_companion_workspace(companion_id: str, request: WorkspaceRequest):
    """Add a new workspace for this companion."""
    import uuid
    workspaces = load_workspaces(companion_id)
    new_ws = request.dict()
    new_ws["id"] = str(uuid.uuid4())
    workspaces.append(new_ws)
    save_workspaces(companion_id, workspaces)
    return {"status": "success", "workspace": new_ws}

@router.delete("/{companion_id}/workspaces/{ws_id}")
async def delete_companion_workspace(companion_id: str, ws_id: str):
    """Delete a workspace for this companion by ID."""
    workspaces = load_workspaces(companion_id)
    workspaces = [ws for ws in workspaces if ws.get("id") != ws_id]
    save_workspaces(companion_id, workspaces)
    return {"status": "success"}

@router.get("/{companion_id}/bridges/registry")
async def get_bridges_registry(companion_id: str):
    """Return the registry of available Bridge modules."""
    return get_registry()

@router.post("/{companion_id}/bridges/spotify/authorize")
async def authorize_spotify(companion_id: str, request: SpotifyAuthRequest):
    """Generate a Spotify authorization URL."""
    try:
        from core.bridges.spotify_bridge import get_auth_url
        url = get_auth_url(request.dict())
        return {"url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Spotify Auth Error: {str(e)}")
