"""
core/companions/group_chat_routes.py
FastAPI router for Companion Group Chats.
Supports group creation, member invite/kick, message dispatch, companion turn triggers,
chat speed / pacing control, and multi-agent group scratchpad collaboration.
"""

from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.companions.group_chat_engine import GroupChatEngine, _group_dir
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


class GroupSettingsRequest(BaseModel):
    chat_speed_seconds: Optional[float] = None
    auto_reply_enabled: Optional[bool] = None
    max_turns_per_batch: Optional[int] = None


class MemberActionRequest(BaseModel):
    companion_id: str


class GroupMessageRequest(BaseModel):
    content: str
    attachments: Optional[List[Dict[str, Any]]] = None


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
        chat_speed_seconds=req.chat_speed_seconds or 3.0,
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
        return {
            "success": True,
            "message": msg,
            "mentioned_companions": mentioned,
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
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Group turn error ({group_id}/{req.companion_id}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
    sp = CompanionScratchpad(g_dir, req.author or "Marcel")
    res = await asyncio.to_thread(
        sp.append_note,
        note=req.text,
        section=req.section or "Ideas",
        author=req.author or "Marcel",
    )
    return {"success": True, "scratchpad": res}


@router.post("/{group_id}/scratchpad/clear")
async def clear_group_scratchpad(group_id: str):
    """Reset the group scratchpad to default template."""
    g_dir = _group_dir(group_id)
    if not g_dir.exists():
        raise HTTPException(status_code=404, detail=f"Group '{group_id}' not found")
    sp = CompanionScratchpad(g_dir, "Group")
    meta = GroupChatEngine.get_group(group_id)
    title = meta.get("title", "Group") if meta else "Group"
    await asyncio.to_thread(
        sp.initialize_template,
        title=f"Shared Brainstorming Canvas — {title}",
        subtitle="Collaborative scratchpad for group chat members.",
    )
    return {"success": True, "scratchpad": sp.load()}
