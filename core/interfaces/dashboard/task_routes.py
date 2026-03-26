"""
Misaka Cipher - Task Queue API Routes
REST API endpoints for task queue management
"""

import asyncio
import json as _json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from core.orchestrator.task_queue import get_task_queue_manager, cancel_agent_task
from core.orchestrator.agent_events import get_snapshot
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
                # Skip agent workspace threads — they belong to the Agents tab only
                thread_id = getattr(thread, 'id', '') or ''
                if thread_id.startswith('agents-'):
                    continue
                threads.append(thread.to_dict())
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
        thread.updated_at = datetime.now()
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
        thread.updated_at = datetime.now()
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
