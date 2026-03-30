"""
Aethvion Suite - Agent Corp API Routes
"""
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from core.orchestrator.corp_manager import get_corp_manager
from core.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/corp", tags=["corp"])


# ── Request models ────────────────────────────────────────────────────────────

class CreateCorpRequest(BaseModel):
    name: str
    description: str = ""
    workspace_path: str = ""
    goal: str = ""


class UpdateCorpRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    workspace_path: Optional[str] = None
    goal: Optional[str] = None


class AddWorkerRequest(BaseModel):
    name: str
    role: str
    model: str = "claude-sonnet-4-5"
    personality: str = ""
    color: str = "#7c3aed"
    can_create_tasks: bool = False


class UpdateWorkerRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    model: Optional[str] = None
    personality: Optional[str] = None
    color: Optional[str] = None
    can_create_tasks: Optional[bool] = None
    paused: Optional[bool] = None


class CreateTaskRequest(BaseModel):
    title: str
    description: str
    assigned_to: str = "any"
    priority: str = "medium"


class UpdateTaskRequest(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    priority: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class SteerRequest(BaseModel):
    message: str


# ── Corp CRUD ─────────────────────────────────────────────────────────────────

@router.get("/list")
async def list_corps():
    return get_corp_manager().list_corps()


@router.post("/create")
async def create_corp(req: CreateCorpRequest):
    return get_corp_manager().create_corp(req.name, req.description, req.workspace_path, req.goal)


@router.get("/{corp_id}")
async def get_corp(corp_id: str):
    try:
        return get_corp_manager().get_corp(corp_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Corp {corp_id} not found")


@router.patch("/{corp_id}")
async def update_corp(corp_id: str, req: UpdateCorpRequest):
    fields = {k: v for k, v in req.dict().items() if v is not None}
    try:
        return get_corp_manager().update_corp(corp_id, **fields)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Corp {corp_id} not found")


@router.delete("/{corp_id}")
async def delete_corp(corp_id: str):
    mgr = get_corp_manager()
    await mgr.stop_corp(corp_id)
    mgr.delete_corp(corp_id)
    return {"ok": True}


# ── Worker CRUD ───────────────────────────────────────────────────────────────

@router.post("/{corp_id}/workers")
async def add_worker(corp_id: str, req: AddWorkerRequest):
    try:
        return get_corp_manager().add_worker(
            corp_id, req.name, req.role, req.model, req.personality, req.color, req.can_create_tasks
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Corp {corp_id} not found")


@router.patch("/{corp_id}/workers/{worker_id}")
async def update_worker(corp_id: str, worker_id: str, req: UpdateWorkerRequest):
    fields = {k: v for k, v in req.dict().items() if v is not None}
    get_corp_manager().update_worker(corp_id, worker_id, **fields)
    return {"ok": True}


@router.delete("/{corp_id}/workers/{worker_id}")
async def remove_worker(corp_id: str, worker_id: str):
    get_corp_manager().remove_worker(corp_id, worker_id)
    return {"ok": True}


@router.post("/{corp_id}/workers/{worker_id}/pause")
async def pause_worker(corp_id: str, worker_id: str):
    get_corp_manager().pause_worker(corp_id, worker_id)
    return {"ok": True}


@router.post("/{corp_id}/workers/{worker_id}/resume")
async def resume_worker(corp_id: str, worker_id: str):
    get_corp_manager().resume_worker(corp_id, worker_id)
    return {"ok": True}


# ── Corp control ──────────────────────────────────────────────────────────────

@router.post("/{corp_id}/start")
async def start_corp(corp_id: str):
    try:
        await get_corp_manager().start_corp(corp_id)
        return {"ok": True, "status": "running"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Corp {corp_id} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{corp_id}/stop")
async def stop_corp(corp_id: str):
    await get_corp_manager().stop_corp(corp_id)
    return {"ok": True, "status": "stopped"}


# ── Task management ───────────────────────────────────────────────────────────

@router.get("/{corp_id}/tasks")
async def get_tasks(corp_id: str):
    return get_corp_manager().get_tasks(corp_id)


@router.post("/{corp_id}/tasks")
async def create_task(corp_id: str, req: CreateTaskRequest):
    return get_corp_manager().add_task(
        corp_id, req.title, req.description, req.assigned_to, req.priority
    )


@router.patch("/{corp_id}/tasks/{task_id}")
async def update_task(corp_id: str, task_id: str, req: UpdateTaskRequest):
    fields = {k: v for k, v in req.dict().items() if v is not None}
    get_corp_manager().update_task(corp_id, task_id, **fields)
    return {"ok": True}


@router.post("/{corp_id}/tasks/{task_id}/reject")
async def reject_task(corp_id: str, task_id: str):
    mgr = get_corp_manager()
    mgr.update_task(corp_id, task_id, status="rejected")
    mgr.emit(corp_id, {
        "type":    "task_update",
        "task_id": task_id,
        "status":  "rejected",
    })
    return {"ok": True}


# ── Message log ───────────────────────────────────────────────────────────────

@router.get("/{corp_id}/log")
async def get_log(corp_id: str):
    return {"log": get_corp_manager().read_log(corp_id, last_n=100)}


@router.post("/{corp_id}/message")
async def send_message(corp_id: str, req: SteerRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    get_corp_manager().send_user_message(corp_id, req.message.strip())
    return {"ok": True}


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/{corp_id}/stats")
async def get_stats(corp_id: str):
    """Return per-worker stats — live if running, loaded from disk if not."""
    try:
        return get_corp_manager().get_all_worker_stats(corp_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Corp not found")


@router.get("/{corp_id}/feed")
async def get_feed(corp_id: str, last_n: int = 200):
    """Return the last N persisted feed events for display on page load."""
    return get_corp_manager().get_feed(corp_id, last_n=last_n)


# ── SSE event stream ──────────────────────────────────────────────────────────

@router.get("/{corp_id}/events")
async def corp_events(corp_id: str):
    async def generate():
        try:
            async for event in get_corp_manager().subscribe(corp_id):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error(f"[corp_events] SSE error for {corp_id}: {e}")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
