"""
Aethvion Suite - Agent Workspace Routes
REST API endpoints for Agent Workspaces and Threads (/api/agents/...)
"""

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from typing import Optional
import asyncio
import mimetypes
import os
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.utils.logger import get_logger
from core.utils.paths import HISTORY_AGENTS
from core.memory.agent_workspace_manager import AgentWorkspaceManager

logger = get_logger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])

# Singleton workspace manager — also imported by task_queue for context injection
workspace_manager = AgentWorkspaceManager(HISTORY_AGENTS)


# ── Request models ─────────────────────────────────────────────────────────────

class WorkspaceCreateRequest(BaseModel):
    path: str
    name: Optional[str] = None


class WorkspaceUpdateRequest(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None


class ThreadCreateRequest(BaseModel):
    name: Optional[str] = None


class ThreadRenameRequest(BaseModel):
    name: str


class RestoreFileRequest(BaseModel):
    path: str  # workspace-relative path to restore from .aethvion_backup/


class MemoryItemRequest(BaseModel):
    category: str             # rule | context | design | note | checklist
    text: Optional[str] = None
    title: Optional[str] = None
    items: Optional[list] = None   # checklist items [{text: str}] or [{id, text, done}]
    source: Optional[str] = "user"


class MemoryItemUpdateRequest(BaseModel):
    text: Optional[str] = None
    title: Optional[str] = None
    category: Optional[str] = None


class ChecklistItemUpdateRequest(BaseModel):
    done: bool


# ── Workspace endpoints ────────────────────────────────────────────────────────

@router.get("/workspaces")
async def list_workspaces():
    """List all agent workspaces."""
    try:
        return {"workspaces": workspace_manager.list_workspaces()}
    except Exception as e:
        logger.error(f"list_workspaces error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workspaces", status_code=201)
async def create_workspace(request: WorkspaceCreateRequest):
    """Create a new workspace."""
    try:
        ws = workspace_manager.create_workspace(request.path, request.name)
        return ws
    except Exception as e:
        logger.error(f"create_workspace error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workspaces/{workspace_id}")
async def get_workspace(workspace_id: str):
    """Get a single workspace by ID."""
    ws = workspace_manager.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.patch("/workspaces/{workspace_id}")
async def update_workspace(workspace_id: str, request: WorkspaceUpdateRequest):
    """Update workspace name or path."""
    ws = workspace_manager.update_workspace(workspace_id, name=request.name, path=request.path)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str):
    """Delete a workspace and all its threads."""
    ok = workspace_manager.delete_workspace(workspace_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"status": "deleted", "id": workspace_id}


# ── Folder browser endpoints ──────────────────────────────────────────────────

@router.get("/browse/native")
async def browse_folder_native(initial: str = Query(default="")):
    """
    Open the native OS folder-picker dialog (Windows Explorer / macOS Finder)
    and return the path the user selected. Returns cancelled=true if dismissed.
    Runs in a thread executor so the async event loop is not blocked.
    """
    def _open_dialog() -> str | None:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.wm_attributes("-topmost", True)
            initial_dir = initial if initial and os.path.isdir(initial) else str(Path.home())
            folder = filedialog.askdirectory(
                parent=root,
                initialdir=initial_dir,
                title="Select Workspace Folder",
            )
            root.destroy()
            return folder or None
        except Exception as exc:
            logger.error(f"Native folder dialog error: {exc}")
            return None

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        folder = await loop.run_in_executor(pool, _open_dialog)

    if folder:
        name = Path(folder).name or folder
        return {"path": folder, "name": name, "cancelled": False}
    return {"path": None, "name": None, "cancelled": True}


@router.get("/browse")
async def browse_folder(path: str = Query(default="")):
    """
    Server-side folder browser. Returns subdirectories at the given path.
    Starts at the user home directory if no path is supplied.
    """
    try:
        if not path:
            target = Path.home()
        else:
            target = Path(path)

        while target != target.parent and not (target.exists() and target.is_dir()):
            target = target.parent

        entries = []
        try:
            for item in sorted(target.iterdir(), key=lambda x: x.name.lower()):
                if item.is_dir() and not item.name.startswith('.'):
                    entries.append({"name": item.name, "path": str(item)})
        except PermissionError:
            pass  # Return empty entries for protected dirs

        parent = str(target.parent) if target.parent != target else None

        return {
            "path": str(target),
            "parent": parent,
            "entries": entries,
        }
    except Exception as e:
        logger.error(f"browse_folder error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Thread endpoints ───────────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/threads")
async def list_threads(workspace_id: str):
    """List all threads in a workspace."""
    if not workspace_manager.get_workspace(workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"threads": workspace_manager.list_threads(workspace_id)}


@router.post("/workspaces/{workspace_id}/threads", status_code=201)
async def create_thread(workspace_id: str, request: ThreadCreateRequest):
    """Create a new thread in a workspace."""
    thread = workspace_manager.create_thread(workspace_id, name=request.name)
    if thread is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return thread


@router.get("/workspaces/{workspace_id}/threads/{thread_id}")
async def get_thread(workspace_id: str, thread_id: str):
    """Get a thread (including messages)."""
    thread = workspace_manager.get_thread(workspace_id, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@router.patch("/workspaces/{workspace_id}/threads/{thread_id}")
async def rename_thread(workspace_id: str, thread_id: str, request: ThreadRenameRequest):
    """Rename a thread."""
    ok = workspace_manager.rename_thread(workspace_id, thread_id, request.name)
    if not ok:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"status": "renamed", "name": request.name}


@router.delete("/workspaces/{workspace_id}/threads/{thread_id}")
async def delete_thread(workspace_id: str, thread_id: str):
    """Delete a thread."""
    ok = workspace_manager.delete_thread(workspace_id, thread_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"status": "deleted", "id": thread_id}


@router.get("/workspaces/{workspace_id}/threads/{thread_id}/state")
async def get_thread_checkpoint_state(workspace_id: str, thread_id: str):
    """Return the saved AgentState checkpoint for a thread, if one exists.

    Used by the frontend to detect interrupted tasks and offer a resume option.
    """
    state_path = HISTORY_AGENTS / workspace_id / "threads" / f"{thread_id}_state.json"
    if not state_path.exists():
        return {"has_state": False, "is_interrupted": False}

    try:
        import json as _json
        data = _json.loads(state_path.read_text(encoding="utf-8"))
        plan = data.get("plan", [])
        plan_total = len(plan)
        plan_done  = sum(1 for s in plan if s.get("done"))
        is_interrupted = plan_total > 0 and plan_done < plan_total

        # Surface the last-modified time so the UI can show "interrupted 5 min ago"
        import datetime as _dt
        mtime = state_path.stat().st_mtime
        last_saved = _dt.datetime.fromtimestamp(mtime, tz=_dt.timezone.utc).isoformat()

        return {
            "has_state":      True,
            "is_interrupted": is_interrupted,
            "plan":           plan,
            "plan_total":     plan_total,
            "plan_done":      plan_done,
            "last_saved":     last_saved,
        }
    except Exception as exc:
        logger.warning(f"[checkpoint] Could not read state for {workspace_id}/{thread_id}: {exc}")
        return {"has_state": False, "is_interrupted": False}


@router.get("/workspaces/{workspace_id}/threads/{thread_id}/history")
async def get_thread_history(workspace_id: str, thread_id: str, limit: int = 20):
    """Get message history for a thread."""
    thread = workspace_manager.get_thread(workspace_id, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    messages = thread.get("messages", [])
    if limit > 0:
        messages = messages[-limit:]
    return {"messages": messages, "total": len(thread.get("messages", []))}


# ── File restore (undo) ───────────────────────────────────────────────────────

@router.post("/workspaces/{workspace_id}/restore")
async def restore_workspace_file(workspace_id: str, request: RestoreFileRequest):
    """Restore a file from its .aethvion_backup/ snapshot (created before every write/patch/delete)."""
    ws = workspace_manager.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    ws_path = Path(ws["path"])
    rel = request.path.lstrip("/\\")
    bak = ws_path / ".aethvion_backup" / rel
    if not bak.exists() or not bak.is_file():
        raise HTTPException(status_code=404, detail=f"No backup found for '{rel}'")

    fp = ws_path / rel
    try:
        fp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(bak), str(fp))
    except Exception as e:
        logger.error(f"restore_workspace_file error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "restored", "path": rel}


# ── File upload ─────────────────────────────────────────────────────────────

_AGENTS_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

@router.post("/upload")
async def upload_agent_file(
    file: UploadFile = File(...),
    workspace_id: str = Query(..., description="Target workspace ID"),
):
    """
    Upload a file into the workspace's uploads/ folder.
    Each workspace has the structure:
      data/history/agents/{workspace_id}/
        workspace.json
        threads/
        uploads/
    """
    # Validate workspace exists
    ws = workspace_manager.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' not found")

    raw = await file.read()
    if len(raw) > _AGENTS_MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size is {_AGENTS_MAX_FILE_SIZE // (1024*1024)} MB."
        )

    filename = file.filename or "attachment"
    mime_type, _ = mimetypes.guess_type(filename)
    mime_type = mime_type or "application/octet-stream"
    is_image = mime_type.startswith("image/")

    # Try to decode text content for non-images
    text_content: Optional[str] = None
    if not is_image:
        try:
            text_content = raw.decode("utf-8")
        except Exception:
            pass

    # Save into workspace uploads/ folder
    uploads_dir = HISTORY_AGENTS / workspace_id / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
    file_path = uploads_dir / safe_filename

    with open(file_path, "wb") as f:
        f.write(raw)

    return {
        "filename": filename,
        "path": str(file_path),
        "is_image": is_image,
        "mime_type": mime_type,
        "content": text_content,
        "size": len(raw),
    }


# ── Active Workspace Explorer & IDE Endpoints ─────────────────────────────────

class FileSaveRequest(BaseModel):
    path: str
    content: str


@router.get("/workspace/tree")
async def get_workspace_tree(path: str):
    """
    Given an absolute path to a workspace folder, return a list of immediate 
    files and directories to build a lazy-loaded directory tree.
    """
    try:
        target = Path(path)
        if not target.exists() or not target.is_dir():
            raise HTTPException(status_code=404, detail="Workspace directory not found")
        
        entries = []
        for item in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            # Skip hidden files/folders (starting with .)
            if item.name.startswith('.'):
                continue
            
            entries.append({
                "name": item.name,
                "path": str(item),
                "is_dir": item.is_dir(),
                "size": item.stat().st_size if item.is_file() else None,
                "ext": item.suffix.lstrip('.').lower() if item.is_file() else None
            })
        return {"path": str(target), "entries": entries}
    except Exception as e:
        logger.error(f"get_workspace_tree error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workspace/file-content")
async def get_workspace_file_content(path: str):
    """
    Read the text content of a file within the workspace safely.
    """
    try:
        target = Path(path)
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        
        # Read the file content (up to 2MB to prevent browser crash)
        size = target.stat().st_size
        if size > 2 * 1024 * 1024:
            return {"content": f"[File too large to preview - size: {size / (1024*1024):.2f}MB]", "too_large": True}
            
        try:
            content = target.read_text(encoding='utf-8', errors='ignore')
            return {"content": content, "too_large": False}
        except Exception:
            return {"content": "[Binary file - preview not available]", "binary": True}
    except Exception as e:
        logger.error(f"get_workspace_file_content error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workspace/file-save")
async def save_workspace_file_content(request: FileSaveRequest):
    """
    Save manual edits to a file within the workspace safely.
    """
    try:
        target = Path(request.path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="File not found")
        if not target.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")
        
        # Write content as UTF-8
        target.write_text(request.content, encoding='utf-8')
        return {"status": "success", "written_bytes": len(request.content.encode('utf-8'))}
    except Exception as e:
        logger.error(f"save_workspace_file_content error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workspace/search")
async def search_workspace_content(path: str, query: str):
    """
    Search for a text query recursively in files inside the workspace path.
    """
    try:
        target = Path(path)
        if not target.exists() or not target.is_dir():
            raise HTTPException(status_code=404, detail="Workspace directory not found")
        
        if len(query) < 2:
            return {"results": []}
            
        results = []
        max_results = 100
        
        # Walk directories and search file contents
        for root, dirs, files in os.walk(str(target)):
            # Skip hidden folders
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for file in files:
                if file.startswith('.'):
                    continue
                file_path = Path(root) / file
                
                # Skip large files (> 1MB) to prevent lockups
                try:
                    if file_path.stat().st_size > 1024 * 1024:
                        continue
                        
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    if query.lower() in content.lower():
                        # Find matching lines
                        lines = content.split('\n')
                        matches = []
                        for i, line in enumerate(lines):
                            if query.lower() in line.lower():
                                matches.append({
                                    "line_number": i + 1,
                                    "content": line.strip()[:150]
                                })
                        
                        results.append({
                            "filename": file,
                            "path": str(file_path),
                            "rel_path": str(file_path.relative_to(target)),
                            "matches": matches
                        })
                        
                        if len(results) >= max_results:
                            break
                except Exception:
                    continue
            
            if len(results) >= max_results:
                break
                
        return {"query": query, "results": results}
    except Exception as e:
        logger.error(f"search_workspace_content error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# ── Project Memory endpoints ──────────────────────────────────────────────────

def _get_pm(workspace_id: str):
    """Return a ProjectMemory instance for the given workspace."""
    from core.orchestrator.project_memory import ProjectMemory
    return ProjectMemory(workspace_id, HISTORY_AGENTS)


@router.get("/workspaces/{workspace_id}/memory")
async def list_memory(workspace_id: str):
    """List all project memory items for a workspace."""
    return {"items": _get_pm(workspace_id).load()}


@router.post("/workspaces/{workspace_id}/memory", status_code=201)
async def add_memory_item(workspace_id: str, req: MemoryItemRequest):
    """Add a new project memory item."""
    import uuid as _uuid
    items = req.items
    if items and isinstance(items, list) and items and isinstance(items[0], dict) and "text" in items[0] and "id" not in items[0]:
        items = [{"id": _uuid.uuid4().hex[:8], "text": i["text"], "done": False} for i in items]
    item = _get_pm(workspace_id).add_item(
        category=req.category,
        text=req.text,
        title=req.title,
        items=items,
        source=req.source or "user",
    )
    return item


@router.patch("/workspaces/{workspace_id}/memory/{item_id}")
async def update_memory_item(workspace_id: str, item_id: str, req: MemoryItemUpdateRequest):
    """Update text/title/category of a memory item."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    item = _get_pm(workspace_id).update_item(item_id, **updates)
    if not item:
        raise HTTPException(status_code=404, detail="Memory item not found")
    return item


@router.delete("/workspaces/{workspace_id}/memory/{item_id}", status_code=204)
async def delete_memory_item(workspace_id: str, item_id: str):
    """Delete a project memory item."""
    ok = _get_pm(workspace_id).delete_item(item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory item not found")


@router.patch("/workspaces/{workspace_id}/memory/{checklist_id}/items/{item_id}")
async def update_checklist_item(
    workspace_id: str,
    checklist_id: str,
    item_id: str,
    req: ChecklistItemUpdateRequest,
):
    """Toggle a checklist row's done state."""
    ok = _get_pm(workspace_id).update_checklist_item(checklist_id, item_id, req.done)
    if not ok:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    return {"ok": True}
