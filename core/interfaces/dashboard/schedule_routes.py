"""
Aethvion Suite - Schedule Routes
REST API for the Schedule tab: recurring AI task management.
"""
import json
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/schedule", tags=["schedule"])


# ── Request models ─────────────────────────────────────────────────────────────

class CreateTaskRequest(BaseModel):
    model_id: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    model_id: Optional[str] = None

class UpdateSettingsRequest(BaseModel):
    name:      Optional[str] = None
    queue_max: Optional[int] = None
    model_id:  Optional[str] = None


# ── AI system prompt ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a scheduling assistant for Aethvion Suite. You help users set up recurring AI tasks.

YOUR JOB:
1. Listen to what the user wants to automate / schedule.
2. If you need more information (e.g. what time, what day, how often, what timezone), ask for it clearly.
3. Once you have enough info, confirm the schedule and output a SCHEDULE_UPDATE block.

OUTPUT FORMAT — write on its own line, exactly as shown:
SCHEDULE_UPDATE: {{"name": "Task Name", "cron": "0 9 * * 1", "cron_human": "Every Monday at 9:00 AM", "prompt": "The prompt the AI will receive on each run", "timezone": "Europe/Amsterdam"}}

CRON REFERENCE (5 fields: minute hour day-of-month month day-of-week):
  Every day at 9:00 AM      → 0 9 * * *
  Every Monday at 9:00 AM   → 0 9 * * 1
  Every weekday at 8:30 AM  → 30 8 * * 1-5
  Every hour                → 0 * * * *
  Every 30 minutes          → */30 * * * *
  Every Sunday at noon      → 0 12 * * 0
  Day-of-week: 0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday, 5=Friday, 6=Saturday

TIMEZONE:
The "timezone" field must be a valid IANA timezone name (e.g. "Europe/Amsterdam", "America/New_York", "Asia/Tokyo").
The cron times are interpreted in this timezone. If the user doesn't specify, ask them or use their system timezone.
Default is "UTC" if unspecified.

PROMPT FIELD:
The "prompt" is what the AI receives automatically when the schedule fires.
Make it specific and self-contained — the AI won't have prior context.
Example: "Review my workout routine progress for the week and give me a brief motivational summary with 2-3 actionable suggestions."

PAUSING / RESUMING:
To pause: include "status": "paused" in SCHEDULE_UPDATE.
To resume: include "status": "active" in SCHEDULE_UPDATE.

CURRENT TASK STATE:
{task_info}

After outputting SCHEDULE_UPDATE, always confirm the schedule in plain, friendly language including the timezone.
Keep responses concise. Do not repeat information the user already knows.
"""


def _task_info_block(task: dict) -> str:
    parts = []
    parts.append(f"Name: {task.get('name', 'Unnamed')}")
    if task.get('cron_human'):
        parts.append(f"Schedule: {task['cron_human']} (cron: {task.get('cron', '?')})")
    elif task.get('cron'):
        parts.append(f"Cron: {task['cron']}")
    else:
        parts.append("Schedule: Not yet configured")
    parts.append(f"Timezone: {task.get('timezone', 'UTC')}")
    if task.get('prompt'):
        parts.append(f"Prompt: {task['prompt']}")
    parts.append(f"Status: {task.get('status', 'draft')}")
    parts.append(f"Queue max: {task.get('queue_max', 1)} (1 = skip duplicate runs)")
    return '\n'.join(parts)


def _build_prompt(task: dict, system: str) -> str:
    parts = [system]
    for msg in task.get('thread', []):
        role    = msg.get('role', 'user')
        content = msg.get('content', '')
        if role == 'user':
            parts.append(f"User: {content}")
        else:
            parts.append(f"Assistant: {content}")
    return "\n\n".join(parts)


def _parse_schedule_update(text: str) -> Optional[dict]:
    """Extract the first SCHEDULE_UPDATE JSON from the AI reply."""
    match = re.search(r'SCHEDULE_UPDATE:\s*(\{[^}]+\})', text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except Exception:
        return None


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/tasks")
async def list_tasks():
    from core.schedulers.schedule_manager import get_schedule_manager
    return {"tasks": get_schedule_manager().list_tasks()}


@router.post("/tasks", status_code=201)
async def create_task(req: CreateTaskRequest):
    from core.schedulers.schedule_manager import get_schedule_manager
    return get_schedule_manager().create_task(model_id=req.model_id)


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    from core.schedulers.schedule_manager import get_schedule_manager
    task = get_schedule_manager().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    from core.schedulers.schedule_manager import get_schedule_manager
    if not get_schedule_manager().delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}


@router.patch("/tasks/{task_id}")
async def update_settings(task_id: str, req: UpdateSettingsRequest):
    from core.schedulers.schedule_manager import get_schedule_manager
    updates = {k: v for k, v in req.dict().items() if v is not None}
    task = get_schedule_manager().update_task(task_id, **updates)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {k: v for k, v in task.items() if k not in ('thread', 'runs')}


@router.post("/tasks/{task_id}/chat")
async def chat(task_id: str, req: ChatRequest):
    """Send a user message; AI responds and optionally configures the schedule."""
    from core.schedulers.schedule_manager import get_schedule_manager
    from core.interfaces.dashboard.server import nexus as _nexus

    mgr = get_schedule_manager()
    task = mgr.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Persist user message first
    mgr.add_message(task_id, 'user', req.message)
    task = mgr.get_task(task_id)  # reload with new message

    # Build full prompt
    system = _SYSTEM_PROMPT.format(task_info=_task_info_block(task))
    prompt = _build_prompt(task, system)

    # Call AI
    try:
        if not _nexus:
            ai_reply = "(Aethvion is still starting up — please wait a moment and try again.)"
        else:
            model = req.model_id or task.get('model_id')
            response = _nexus.provider_manager.call_with_failover(
                prompt=prompt,
                trace_id=f"sched-chat-{task_id[:8]}",
                temperature=0.7,
                model=model if model and model != 'auto' else None,
                request_type='generation',
                source='schedule',
            )
            ai_reply = response.content
    except Exception as exc:
        logger.error("[schedule/chat] AI call failed: %s", exc)
        ai_reply = f"Error communicating with AI: {exc}"

    # Apply any schedule updates embedded in the reply
    update = _parse_schedule_update(ai_reply)
    if update:
        allowed = {'name', 'cron', 'cron_human', 'prompt', 'status', 'timezone'}
        filtered = {k: v for k, v in update.items() if k in allowed and v}
        if filtered:
            task = mgr.update_task(task_id, **filtered) or task

    # Strip SCHEDULE_UPDATE line before saving / returning
    clean_reply = re.sub(r'SCHEDULE_UPDATE:\s*\{[^}]+\}', '', ai_reply, flags=re.DOTALL).strip()
    mgr.add_message(task_id, 'assistant', clean_reply)

    # Return full task metadata (without thread) so frontend can update info card
    fresh = mgr.get_task(task_id) or task
    return {
        'reply': clean_reply,
        'task':  {k: v for k, v in fresh.items() if k not in ('thread', 'runs')},
    }


@router.post("/tasks/{task_id}/run")
async def run_now(task_id: str):
    from core.schedulers.schedule_manager import get_schedule_manager
    mgr = get_schedule_manager()
    task = mgr.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    # Give nexus to manager if not yet set
    try:
        from core.interfaces.dashboard.server import nexus as _nexus
        if _nexus:
            mgr.set_nexus(_nexus)
    except Exception:
        pass
    return mgr.run_now(task_id)


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    from core.schedulers.schedule_manager import get_schedule_manager
    task = get_schedule_manager().update_task(task_id, status='paused')
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": task.get("status")}


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    from core.schedulers.schedule_manager import get_schedule_manager
    task = get_schedule_manager().update_task(task_id, status='active')
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": task.get("status")}
