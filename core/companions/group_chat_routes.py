"""
core/companions/group_chat_routes.py
FastAPI router for Companion Group Chats.
Supports group creation, member invite/kick, message dispatch, companion turn triggers,
chat speed / pacing control, and multi-agent group scratchpad collaboration.
"""

from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Optional
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.companions.group_chat_engine import GroupChatEngine, _group_dir
from core.companions.group_conductor import get_conductor
from core.companions.engine.scratchpad import CompanionScratchpad
from core.utils import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/companions/groups", tags=["companion_groups"])


# Pydantic Schemas

class CreateGroupRequest(BaseModel):
    title: str
    description: Optional[str] = ""
    companion_ids: Optional[List[str]] = None
    avatar_symbol: Optional[str] = "🚀"
    accent_color: Optional[str] = "#8b5cf6"
    chat_speed_seconds: Optional[float] = 3.0
    pace: Optional[str] = "natural"


class GroupSettingsRequest(BaseModel):
    chat_speed_seconds: Optional[float] = None
    auto_reply_enabled: Optional[bool] = None
    max_turns_per_batch: Optional[int] = None
    pace: Optional[str] = None                  # natural | lively | quiet | manual
    paused: Optional[bool] = None
    ambient_enabled: Optional[bool] = None      # companions may start conversations after a silence
    active_hours_start: Optional[int] = None
    active_hours_end: Optional[int] = None
    max_ambient_per_day: Optional[int] = None
    max_messages_per_hour: Optional[int] = None


class NudgeRequest(BaseModel):
    companion_id: Optional[str] = None


class MemberActionRequest(BaseModel):
    companion_id: str


class GroupMessageRequest(BaseModel):
    content: str
    attachments: Optional[List[Dict[str, Any]]] = None


class AgentMessageRequest(BaseModel):
    content: str
    author_id: Optional[str] = "antigravity"
    author_name: Optional[str] = "Antigravity"
    avatar_symbol: Optional[str] = "◈"
    accent_color: Optional[str] = "#38bdf8"
    attachments: Optional[List[Dict[str, Any]]] = None
    trigger_replies: Optional[bool] = True


class CompanionTurnRequest(BaseModel):
    companion_id: str
    reason: Optional[str] = "manual"


class ScratchpadAppendRequest(BaseModel):
    text: str
    section: Optional[str] = None
    author: Optional[str] = "Marcel"
    tags: Optional[List[str]] = None


# Routes

@router.get("")
async def list_groups():
    """List all companion group chats."""
    get_conductor().ensure_started()
    groups = await asyncio.to_thread(GroupChatEngine.list_groups)
    return {"groups": groups}


@router.post("")
async def create_group(req: CreateGroupRequest):
    """Create a new group chat with chosen companions."""
    group = await asyncio.to_thread(
        GroupChatEngine.create_group,
        title=req.title,
        description=req.description or "",
        companion_ids=req.companion_ids or ["misakacipher"],
        avatar_symbol=req.avatar_symbol or "🚀",
        accent_color=req.accent_color or "#8b5cf6",
        chat_speed_seconds=req.chat_speed_seconds if req.chat_speed_seconds is not None else 3.0,
        pace=req.pace or "natural",
    )
    return {"success": True, "group": group}


@router.get("/{group_id}")
async def get_group(group_id: str):
    """Get group details, members, message history, and scratchpad summary."""
    group = await asyncio.to_thread(GroupChatEngine.get_group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")
    return {"group": group}


@router.delete("/{group_id}")
async def delete_group(group_id: str):
    """Delete a group chat."""
    ok = await asyncio.to_thread(GroupChatEngine.delete_group, group_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")
    return {"success": True, "deleted": group_id}


@router.patch("/{group_id}/settings")
async def update_settings(group_id: str, req: GroupSettingsRequest):
    """Update pacing, chat speed, or auto-reply settings."""
    settings = req.dict(exclude_none=True)
    meta = await asyncio.to_thread(GroupChatEngine.update_settings, group_id, settings)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")
    if settings.get("paused") or settings.get("pace") == "manual":
        get_conductor().cancel_pending(group_id)
    return {"success": True, "group": meta}


@router.post("/{group_id}/members/invite")
async def invite_member(group_id: str, req: MemberActionRequest):
    """Invite a companion to the group chat."""
    meta = await asyncio.to_thread(GroupChatEngine.invite_companion, group_id, req.companion_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")
    return {"success": True, "group": meta}


@router.post("/{group_id}/members/kick")
async def kick_member(group_id: str, req: MemberActionRequest):
    """Remove a companion from the group chat."""
    meta = await asyncio.to_thread(GroupChatEngine.kick_companion, group_id, req.companion_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")
    return {"success": True, "group": meta}


@router.post("/{group_id}/messages")
async def post_user_message(group_id: str, req: GroupMessageRequest):
    """Post a message from the user to the group chat, detecting any @mentions."""
    try:
        msg, mentioned = await asyncio.to_thread(
            GroupChatEngine.post_user_message,
            group_id=group_id,
            content=req.content,
            attachments=req.attachments,
        )
        conductor = get_conductor()
        conductor.ensure_started()
        responders = conductor.on_message(group_id, msg)
        return {
            "success": True,
            "message": msg,
            "mentioned_companions": mentioned,
            "responders": [r["id"] for r in responders],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{group_id}/agent-message")
async def post_agent_message(group_id: str, req: AgentMessageRequest):
    """Post a message from an external agent (e.g. Antigravity) into the group chat."""
    try:
        msg = await asyncio.to_thread(
            GroupChatEngine.post_agent_message,
            group_id=group_id,
            content=req.content,
            author_id=req.author_id or "antigravity",
            author_name=req.author_name or "Antigravity",
            avatar_symbol=req.avatar_symbol or "◈",
            accent_color=req.accent_color or "#38bdf8",
            attachments=req.attachments,
        )
        conductor = get_conductor()
        conductor.ensure_started()
        responders = []
        if req.trigger_replies:
            room = conductor.room(group_id)
            room.energy = max(room.energy, 0.85)
            room.streak = 0
            responders = conductor.on_message(group_id, msg)
        else:
            conductor._emit(conductor.room(group_id), {"type": "message", "message": msg})
        return {
            "success": True,
            "message": msg,
            "responders": [r["id"] for r in responders],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{group_id}/turn")
async def companion_turn(group_id: str, req: CompanionTurnRequest):
    """Trigger a conversational turn for a specific companion in the group."""
    try:
        result = await GroupChatEngine.generate_companion_turn(
            group_id=group_id,
            companion_id=req.companion_id,
            trigger_reason=req.reason or "manual",
        )
        if result.get("message"):
            get_conductor().on_message(group_id, result["message"])
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Group turn error ({group_id}/{req.companion_id}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{group_id}/nudge")
async def nudge_group(group_id: str, req: NudgeRequest):
    """Ask one companion (chosen automatically unless given) to say something now."""
    if not _group_dir(group_id).exists():
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")
    cid = get_conductor().nudge(group_id, req.companion_id)
    return {"success": bool(cid), "companion_id": cid}


@router.get("/{group_id}/status")
async def group_status(group_id: str):
    """Live pacing state: who is typing, room energy, message counts."""
    if not _group_dir(group_id).exists():
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")
    return {"status": get_conductor().status(group_id)}


@router.get("/{group_id}/events")
async def group_events(group_id: str, request: Request):
    """Server-sent events for one group: message, typing, reaction, notice."""
    if not _group_dir(group_id).exists():
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")
    conductor = get_conductor()
    conductor.ensure_started()
    queue = conductor.subscribe(group_id)

    async def stream():
        try:
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            conductor.unsubscribe(group_id, queue)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# Group Scratchpad Routes

@router.get("/{group_id}/scratchpad")
async def get_group_scratchpad(group_id: str):
    """Load the shared multi-agent scratchpad ledger for this group."""
    g_dir = _group_dir(group_id)
    if not g_dir.exists():
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")
    sp = CompanionScratchpad(g_dir, "Group")
    data = await asyncio.to_thread(sp.load)
    return {"scratchpad": data}


@router.post("/{group_id}/scratchpad/append")
async def append_group_scratchpad(group_id: str, req: ScratchpadAppendRequest):
    """Append a collaborative idea, task, or mechanic to the group scratchpad."""
    g_dir = _group_dir(group_id)
    if not g_dir.exists():
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")
    sp = CompanionScratchpad(g_dir, "Group")
    res = await asyncio.to_thread(
        sp.append_note,
        text=req.text,
        section=req.section or "Ideas",
        author=req.author or "Marcel",
    )
    return {"success": True, "scratchpad": res}


@router.post("/{group_id}/scratchpad/clear")
async def clear_group_scratchpad(group_id: str):
    """Clear the group scratchpad."""
    g_dir = _group_dir(group_id)
    if not g_dir.exists():
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")
    sp = CompanionScratchpad(g_dir, "Group")
    await asyncio.to_thread(sp.clear)
    return {"success": True, "scratchpad": await asyncio.to_thread(sp.load)}
