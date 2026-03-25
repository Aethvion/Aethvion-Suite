"""
Agent Workspace Routes
REST API endpoints for Agent Workspaces and Threads (/api/agents/...)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import asyncio
import os
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

        # If the path doesn't exist or isn't a directory, walk up to a valid parent
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
