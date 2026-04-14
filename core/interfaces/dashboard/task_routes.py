"""
Aethvion Suite - Task Queue API Routes
REST API endpoints for task queue management
"""

import asyncio
import json as _json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from core.orchestrator.task_queue import get_task_queue_manager, cancel_agent_task
from core.orchestrator.agent_events import get_snapshot
from core.utils import utcnow_iso
from core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskSubmitRequest(BaseModel):
    """Request to submit a new task."""
    prompt: str
    thread_id: Optional[str] = "default"
    thread_title: Optional[str] = None
    model_id: Optional[str] = None
    attached_files: Optional[List[Dict[str, Any]]] = None
    mode: Optional[str] = "auto"
    settings: Optional[Dict[str, Any]] = None
    workspace_id: Optional[str] = None       # Agent workspace ID (Agents tab)
    agent_thread_id: Optional[str] = None    # Agent thread ID (Agents tab)


class ThreadSettingsRequest(BaseModel):
    """Request to update thread settings."""
    settings: Dict[str, Any]


class TaskResponse(BaseModel):
    """Task response."""
    task_id: str
    status: str
    message: str


@router.post("/submit", response_model=TaskResponse)
async def submit_task(request: TaskSubmitRequest):
    """
    Submit a new task to the queue.
    
    The task will be executed asynchronously by a worker.
    """
    try:
        task_manager = get_task_queue_manager()
        
        # Prepend text file attachment content (images are passed via the
        # images kwarg to the provider; text files are embedded in the prompt)
        prompt_text = request.prompt
        if request.attached_files:
            text_parts = []
            for file_data in request.attached_files:
                if not file_data.get('is_image') and file_data.get('content'):
                    name = file_data.get('filename', 'attachment')
                    text_parts.append(
                        f"[Attached file: {name}]\n{file_data['content']}\n[End of {name}]"
                    )
            if text_parts:
                prompt_text = "\n\n".join(text_parts) + "\n\n" + prompt_text
            
        task_id = await task_manager.submit_task(
            prompt=prompt_text,
            thread_id=request.thread_id,
            thread_title=request.thread_title,
            model_id=request.model_id,
            attached_files=request.attached_files,
            mode=request.mode,
            settings=request.settings,
            workspace_id=request.workspace_id,
            agent_thread_id=request.agent_thread_id,
        )
        
        return TaskResponse(
            task_id=task_id,
            status="queued",
            message=f"Task {task_id} submitted successfully"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """Get status of a specific task."""
    try:
        task_manager = get_task_queue_manager()
        task = task_manager.get_task(task_id)
        
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        return task.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/thread/{thread_id}")
async def get_thread_tasks(thread_id: str):
    """Get all tasks for a specific thread."""
    try:
        task_manager = get_task_queue_manager()
        thread = task_manager.get_thread(thread_id)
        
        if not thread:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
        
        tasks = task_manager.get_thread_tasks(thread_id)
        
        return {
            'thread': thread.to_dict(),
            'tasks': [task.to_dict() for task in tasks]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/status")
async def get_queue_status():
    """Get overall queue status."""
    try:
        task_manager = get_task_queue_manager()
        return task_manager.get_status()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threads")
async def list_threads():
    """List all chat threads."""
    try:
        try:
            task_manager = get_task_queue_manager()
        except ValueError:
            # Task manager not initialized yet (orchestrator not ready)
            return {"threads": [], "status": "initializing"}
            
        threads = []
        for thread in list(task_manager.threads.values()):
            try:
                thread_id = getattr(thread, 'id', '') or ''
                if thread_id.startswith('agents-') or thread_id.startswith('explained-'):
                    continue
                
                thread_data = thread.to_dict()
                
                # Get last task for preview
                last_msg = "No messages yet"
                if thread.task_ids:
                    last_task_id = thread.task_ids[-1]
                    last_task = task_manager.get_task(last_task_id)
                    if last_task:
                        if last_task.result and last_task.result.get('response'):
                            last_msg = last_task.result.get('response')
                        else:
                            last_msg = last_task.prompt
                
                thread_data['last_message'] = last_msg
                threads.append(thread_data)
            except Exception as te:
                logger.error(f"Failed to serialize thread {getattr(thread, 'id', 'unknown')}: {te}")
                continue
        return {'threads': threads}
        
    except Exception as e:
        logger.error(f"Error in list_threads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ThreadModeRequest(BaseModel):
    mode: str  # "auto" or "chat_only"


@router.delete("/thread/{thread_id}")
async def delete_thread(thread_id: str):
    """Delete a thread."""
    try:
        task_manager = get_task_queue_manager()
        success = task_manager.delete_thread(thread_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
            
        return {"status": "success", "message": f"Thread {thread_id} deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/thread/{thread_id}/mode")
async def update_thread_mode(thread_id: str, request: Dict[str, str]):
    """Update thread mode."""
    try:
        mode = request.get('mode')
        if not mode or mode not in ['auto', 'chat_only']:
            raise HTTPException(status_code=400, detail="Invalid mode")
            
        task_manager = get_task_queue_manager()
        thread = task_manager.get_thread(thread_id)
        
        if not thread:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
            
        thread.mode = mode
        thread.updated_at = datetime.now(timezone.utc)
        task_manager._save_thread(thread_id)
        
        return {"status": "success", "mode": mode}
        
    except HTTPException:
        raise
    except TypeError as e:
        # JSON serialization error
        raise HTTPException(status_code=400, detail=f"Invalid data format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/thread/{thread_id}/title")
async def update_thread_title(thread_id: str, request: Dict[str, str]):
    """Update thread title."""
    try:
        title = request.get('title')
        if not title:
            raise HTTPException(status_code=400, detail="Title is required")
            
        task_manager = get_task_queue_manager()
        success = task_manager.set_thread_title(thread_id, title)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
            
        return {"status": "success", "title": title}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/thread/{thread_id}/settings")
async def update_thread_settings(thread_id: str, request: ThreadSettingsRequest):
    """Update thread settings."""
    try:
        task_manager = get_task_queue_manager()
        success = task_manager.update_thread_settings(thread_id, request.settings)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
            
        return {"status": "success", "settings": request.settings}
        
    except HTTPException:
        raise
    except TypeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid settings format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/thread/{thread_id}/pin")
async def toggle_thread_pin(thread_id: str, request: Dict[str, bool]):
    """Toggle thread pinned status."""
    try:
        is_pinned = request.get('is_pinned', False)
        task_manager = get_task_queue_manager()
        thread = task_manager.get_thread(thread_id)
        
        if not thread:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
            
        thread.is_pinned = is_pinned
        thread.updated_at = datetime.now(timezone.utc)
        task_manager._save_thread(thread_id)
        
        return {"status": "success", "is_pinned": is_pinned}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/debug/persistence")
async def debug_persistence():
    """Debug endpoint to inspect loaded tasks and threads."""
    try:
        task_manager = get_task_queue_manager()
        return {
            "threads_count": len(task_manager.threads),
            "tasks_count": len(task_manager.tasks),
            "thread_ids": list(task_manager.threads.keys()),
            "task_ids": list(task_manager.tasks.keys()),
            "threads_raw": [t.to_dict() for t in task_manager.threads.values()]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ThreadCreateRequest(BaseModel):
    thread_id: str
    title: Optional[str] = None
    mode: Optional[str] = "auto"


@router.post("/thread/create")
async def create_thread(request: ThreadCreateRequest):
    """Explicitly create a new thread."""
    try:
        task_manager = get_task_queue_manager()
        success = task_manager.create_thread(request.thread_id, request.title, request.mode)

        if not success:
            return {"status": "exists", "message": f"Thread {request.thread_id} already exists"}

        return {"status": "success", "message": f"Thread {request.thread_id} created"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Signal a running agent task to stop after its current iteration."""
    cancel_agent_task(task_id)
    return {"ok": True, "task_id": task_id}


# ── Folder endpoints ──────────────────────────────────────────────────────────

class FolderCreateRequest(BaseModel):
    folder_id: str
    title: str
    color: Optional[str] = "#6366f1"
    context_extra: Optional[str] = ""
    shared_memory: Optional[str] = ""
    settings: Optional[Dict[str, Any]] = None


class FolderUpdateRequest(BaseModel):
    title: Optional[str] = None
    color: Optional[str] = None
    context_extra: Optional[str] = None
    shared_memory: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


@router.get("/folders")
async def list_folders():
    """List all chat folders."""
    try:
        task_manager = get_task_queue_manager()
        folders = [f.to_dict() for f in task_manager.folders.values()]
        # Attach thread count to each folder
        for fd in folders:
            fd['thread_count'] = sum(
                1 for t in task_manager.threads.values()
                if getattr(t, 'folder_id', None) == fd['id']
            )
        return {"folders": folders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/folders")
async def create_folder(request: FolderCreateRequest):
    """Create a new chat folder."""
    try:
        task_manager = get_task_queue_manager()
        success = task_manager.create_folder(
            folder_id=request.folder_id,
            title=request.title,
            color=request.color or "#6366f1",
            context_extra=request.context_extra or "",
            shared_memory=request.shared_memory or "",
            settings=request.settings or {},
        )
        if not success:
            return {"status": "exists", "message": f"Folder {request.folder_id} already exists"}
        return {"status": "success", "folder": task_manager.folders[request.folder_id].to_dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/folders/{folder_id}")
async def update_folder(folder_id: str, request: FolderUpdateRequest):
    """Update a chat folder's settings / context."""
    try:
        task_manager = get_task_queue_manager()
        kwargs = {k: v for k, v in request.model_dump().items() if v is not None}
        success = task_manager.update_folder(folder_id, **kwargs)
        if not success:
            raise HTTPException(status_code=404, detail=f"Folder {folder_id} not found")
        return {"status": "success", "folder": task_manager.folders[folder_id].to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/folders/{folder_id}")
async def delete_folder(folder_id: str):
    """Delete a folder (threads are kept, just un-assigned)."""
    try:
        task_manager = get_task_queue_manager()
        success = task_manager.delete_folder(folder_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Folder {folder_id} not found")
        return {"status": "success", "message": f"Folder {folder_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/thread/{thread_id}/folder")
async def set_thread_folder(thread_id: str, request: Dict[str, Any]):
    """Assign a thread to a folder, or remove it from its folder (folder_id=null)."""
    try:
        folder_id = request.get("folder_id")  # None removes from folder
        task_manager = get_task_queue_manager()
        success = task_manager.move_thread_to_folder(thread_id, folder_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Thread or folder not found")
        return {"status": "success", "thread_id": thread_id, "folder_id": folder_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── End Folder endpoints ───────────────────────────────────────────────────────


@router.get("/{task_id}/events")
async def stream_task_events(task_id: str):
    """SSE stream of agent step events for a task."""
    async def generate():
        sent = 0
        waited = 0.0
        max_wait = 600.0  # 10 minute timeout
        while waited < max_wait:
            snap = get_snapshot(task_id)
            if snap is None:
                # Store not created yet — task may not have started
                await asyncio.sleep(0.3)
                waited += 0.3
                continue
            events = snap["events"]
            while sent < len(events):
                yield f"data: {_json.dumps(events[sent])}\n\n"
                sent += 1
            if snap["done"] and sent >= len(events):
                break
            await asyncio.sleep(0.25)
            waited += 0.25
        yield 'data: {"type":"stream_end"}\n\n'

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{task_id}/stream-tokens")
async def stream_chat_tokens(task_id: str):
    """SSE stream of raw chat tokens for live token-by-token streaming."""
    from core.orchestrator.chat_token_store import get_token_queue, cleanup_token_queue

    async def generate():
        # Wait up to 15 s for the worker to create the queue
        max_wait = 15.0
        waited = 0.0
        q = None
        while waited < max_wait:
            q = get_token_queue(task_id)
            if q is not None:
                break
            await asyncio.sleep(0.05)
            waited += 0.05

        if q is None:
            # Task not streamable (agent mode, search, etc.) — signal immediately
            yield f'data: {_json.dumps({"type": "not_streamable"})}\n\n'
            return

        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=60.0)
                    yield f"data: {_json.dumps(event)}\n\n"
                    if event.get("type") == "done":
                        break
                except asyncio.TimeoutError:
                    yield 'data: {"type":"heartbeat"}\n\n'
        finally:
            cleanup_token_queue(task_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
