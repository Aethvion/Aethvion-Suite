"""
core/companions/companion_routes.py
═════════════════════════════════════
Unified dynamic router for all Aethvion companions.
"""

from typing import List, Optional, Any
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
import shutil
from pathlib import Path
from core.utils.paths import COMPANIONS
from pydantic import BaseModel

from core.companions.registry import CompanionRegistry
from core.companions.companion_engine import CompanionEngine
from core.companions.engine.memory import CompanionMemory
from core.companions.engine.history import CompanionHistory
from core.workspace.workspace_utils import load_workspaces, save_workspaces
from core.bridges.bridge_manager import get_registry

router = APIRouter(prefix="/api/companions", tags=["companions"])

class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage]

class InitiateRequest(BaseModel):
    trigger: str = "startup"

class WorkspaceRequest(BaseModel):
    label: str
    path: str
    permissions: List[str]
    recursive: bool = True

class SpotifyAuthRequest(BaseModel):
    client_id: str
    client_secret: str
    redirect_uri: str = "http://localhost:8080/callback"

def _get_cfg(cid: str):
    if not (cfg := CompanionRegistry.get_companion(cid)):
        raise HTTPException(status_code=404, detail=f"Companion '{cid}' not found")
    return cfg

@router.get("/list")
async def list_companions():
    return {"companions": CompanionRegistry.list_companions()}

@router.get("/{companion_id}/memory")
async def get_memory(companion_id: str):
    cfg = _get_cfg(companion_id)
    memory = CompanionMemory(cfg.data_dir, cfg._raw_config.get("personality_defaults", {}))
    return memory.load()

@router.get("/{companion_id}/history")
async def get_history(companion_id: str, offset_days: int = 0, limit_days: int = 3):
    cfg = _get_cfg(companion_id)
    history = CompanionHistory(cfg.history_dir, cfg.name)
    return history.load_days(offset_days, limit_days)

@router.post("/{companion_id}/initiate")
async def initiate(companion_id: str, request: InitiateRequest):
    return await CompanionEngine.initiate_response(_get_cfg(companion_id), request.trigger)

@router.post("/{companion_id}/chat")
async def chat(companion_id: str, request: ChatRequest):
    return StreamingResponse(
        CompanionEngine.chat_response(_get_cfg(companion_id), request.message, request.history),
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
    
    file_path = upload_dir / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    return {
        "filename": file.filename,
        "path": str(file_path),
        "is_image": file.content_type.startswith("image/")
    }

@router.get("/{companion_id}/expressions")
async def get_expressions(companion_id: str):
    return _get_cfg(companion_id).expressions

# --- Managerial Routes (Workspaces & Bridges) ---

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
