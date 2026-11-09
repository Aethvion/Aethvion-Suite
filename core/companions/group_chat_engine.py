"""
core/companions/group_chat_engine.py
Group Chat Engine for Aethvion Companions.
Enables multi-companion group chats with member invite/kick management,
companion-to-companion @pings, adjustable conversation pacing/speed,
and a shared multi-agent brainstorming scratchpad.
"""

from __future__ import annotations
import asyncio
import datetime
import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.utils import load_json, atomic_json_write, get_logger, utcnow_iso
from core.companions.registry import CompanionRegistry, CompanionConfig
from core.companions.engine.scratchpad import CompanionScratchpad
from core.providers.provider_manager import get_provider_manager
from core.workspace.preferences_manager import get_preferences_manager
from core.companions.engine.streaming import build_bridges_capabilities
from core.companions.engine.tools import execute_tools_stream

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
GROUPS_DIR = PROJECT_ROOT / "data" / "companions" / "groups"

DEFAULT_USER_MEMBER = {
    "id": "marcel",
    "name": "Marcel",
    "role": "user",
    "avatar_symbol": "✦",
    "accent_color": "#10b981",
    "is_user": True,
}


def _ensure_groups_dir() -> Path:
    GROUPS_DIR.mkdir(parents=True, exist_ok=True)
    return GROUPS_DIR


def _group_dir(group_id: str) -> Path:
    return _ensure_groups_dir() / group_id


def _meta_path(group_id: str) -> Path:
    return _group_dir(group_id) / "meta.json"


def _history_path(group_id: str) -> Path:
    return _group_dir(group_id) / "history.json"


def _load_meta(group_id: str) -> Optional[Dict[str, Any]]:
    p = _meta_path(group_id)
    if not p.exists():
        return None
    return load_json(p, default=None)


def _save_meta(group_id: str, meta: Dict[str, Any]) -> None:
    _group_dir(group_id).mkdir(parents=True, exist_ok=True)
    atomic_json_write(_meta_path(group_id), meta)


def _load_history(group_id: str) -> List[Dict[str, Any]]:
    p = _history_path(group_id)
    if not p.exists():
        return []
    data = load_json(p, default={"messages": []})
    return data.get("messages", [])


def _save_history(group_id: str, messages: List[Dict[str, Any]]) -> None:
    _group_dir(group_id).mkdir(parents=True, exist_ok=True)
    atomic_json_write(_history_path(group_id), {"messages": messages})


def _build_companion_member(cid: str) -> Dict[str, Any]:
    cfg = CompanionRegistry.get_companion(cid)
    if not cfg:
        return {
            "id": cid,
            "name": cid.capitalize(),
            "role": "companion",
            "avatar_symbol": "✦",
            "accent_color": "#6366f1",
            "is_user": False,
        }
    raw = cfg._raw_config
    return {
        "id": cfg.id,
        "name": cfg.name,
        "role": raw.get("personality_defaults", {}).get("base_info", {}).get("role", "Companion"),
        "avatar_symbol": raw.get("avatar_symbol", "✦"),
        "accent_color": raw.get("accent_color", "#6366f1"),
        "is_user": False,
    }


def extract_mentions(content: str, members: List[Dict[str, Any]]) -> List[str]:
    """Extract member IDs mentioned with @name or @id in content."""
    if not content or "@" not in content:
        return []
    
    mentioned = []
    content_lower = content.lower()
    for m in members:
        mid = m["id"].lower()
        mname = m["name"].lower().replace(" ", "")
        mname_words = m["name"].lower().split()
        
        # Check patterns like @misakacipher, @misaka, @lyra, @axiom, @marcel
        patterns = [f"@{mid}", f"@{mname}"]
        for w in mname_words:
            if len(w) >= 3:
                patterns.append(f"@{w}")
                
        for pat in patterns:
            if pat in content_lower and m["id"] not in mentioned:
                mentioned.append(m["id"])
                break
    return mentioned


class GroupChatEngine:
    @staticmethod
    def list_groups() -> List[Dict[str, Any]]:
        """List all companion group chats."""
        _ensure_groups_dir()
        groups = []
        for g_path in GROUPS_DIR.iterdir():
            if g_path.is_dir():
                m = _load_meta(g_path.name)
                if m:
                    hist = _load_history(g_path.name)
                    m["message_count"] = len(hist)
                    m["last_message"] = hist[-1] if hist else None
                    groups.append(m)
        groups.sort(key=lambda g: g.get("last_message", {}).get("timestamp") or g.get("created_at", ""), reverse=True)
        return groups

    @staticmethod
    def get_group(group_id: str) -> Optional[Dict[str, Any]]:
        """Get full group metadata, members, and recent history."""
        meta = _load_meta(group_id)
        if not meta:
            return None
        meta["history"] = _load_history(group_id)
        
        # Attach scratchpad summary
        try:
            sp = CompanionScratchpad(_group_dir(group_id), "Group")
            sp_data = sp.load()
            meta["scratchpad_summary"] = {
                "plain_text": sp_data.get("plain_text", ""),
                "entries_count": len(sp_data.get("entries", [])),
                "sections": sp_data.get("sections", []),
            }
        except Exception as e:
            logger.debug(f"Error loading group scratchpad for {group_id}: {e}")
            meta["scratchpad_summary"] = {"plain_text": "", "entries_count": 0, "sections": []}
            
        return meta

    @staticmethod
    def create_group(
        title: str,
        description: str = "",
        companion_ids: Optional[List[str]] = None,
        avatar_symbol: str = "🚀",
        accent_color: str = "#8b5cf6",
        chat_speed_seconds: float = 3.0,
    ) -> Dict[str, Any]:
        """Create a new group chat with specified companion members."""
        gid = f"gc_{uuid.uuid4().hex[:8]}"
        g_dir = _group_dir(gid)
        g_dir.mkdir(parents=True, exist_ok=True)

        members = [dict(DEFAULT_USER_MEMBER)]
        c_ids = companion_ids or ["misakacipher"]
        for cid in c_ids:
            if cid != "marcel" and not any(m["id"] == cid for m in members):
                members.append(_build_companion_member(cid))

        meta = {
            "id": gid,
            "title": title.strip() or "Group Brainstorm",
            "description": description.strip(),
            "avatar_symbol": avatar_symbol,
            "accent_color": accent_color,
            "created_at": utcnow_iso(),
            "members": members,
            "settings": {
                "chat_speed_seconds": max(0.5, float(chat_speed_seconds)),
                "auto_reply_enabled": True,
                "max_turns_per_batch": 5,
            },
        }
        _save_meta(gid, meta)

        # Initial welcome message in history
        names_list = ", ".join(m["name"] for m in members if not m.get("is_user"))
        init_history = [{
            "id": f"msg_{uuid.uuid4().hex[:6]}",
            "author_id": "system",
            "author_name": "System",
            "author_role": "system",
            "avatar_symbol": "✦",
            "accent_color": "#64748b",
            "content": f"Welcome to **{meta['title']}**! Members: Marcel and {names_list}. Mention someone with `@Name` to prompt their response.",
            "timestamp": utcnow_iso(),
            "mentions": [],
        }]
        _save_history(gid, init_history)

        # Initialize group scratchpad
        try:
            sp = CompanionScratchpad(g_dir, "Group")
            sp.initialize_template(
                title=f"Shared Brainstorming Canvas — {meta['title']}",
                subtitle=f"Co-working scratchpad for Marcel, {names_list}.",
            )
        except Exception as e:
            logger.debug(f"Failed to initialize group scratchpad: {e}")

        meta["history"] = init_history
        return meta

    @staticmethod
    def delete_group(group_id: str) -> bool:
        """Delete group chat and its associated files."""
        g_dir = _group_dir(group_id)
        if not g_dir.exists():
            return False
        import shutil
        shutil.rmtree(g_dir, ignore_errors=True)
        return True

    @staticmethod
    def update_settings(group_id: str, settings: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update group chat pacing, speed, or auto-reply settings."""
        meta = _load_meta(group_id)
        if not meta:
            return None
        cur_settings = meta.setdefault("settings", {})
        if "chat_speed_seconds" in settings:
            cur_settings["chat_speed_seconds"] = max(0.5, float(settings["chat_speed_seconds"]))
        if "auto_reply_enabled" in settings:
            cur_settings["auto_reply_enabled"] = bool(settings["auto_reply_enabled"])
        if "max_turns_per_batch" in settings:
            cur_settings["max_turns_per_batch"] = int(settings["max_turns_per_batch"])
        _save_meta(group_id, meta)
        return meta

    @staticmethod
    def invite_companion(group_id: str, companion_id: str) -> Optional[Dict[str, Any]]:
        """Invite a companion into the group chat."""
        meta = _load_meta(group_id)
        if not meta:
            return None
        members = meta.get("members", [])
        if any(m["id"] == companion_id for m in members):
            return meta

        new_member = _build_companion_member(companion_id)
        members.append(new_member)
        meta["members"] = members
        _save_meta(group_id, meta)

        # Add system announcement
        hist = _load_history(group_id)
        hist.append({
            "id": f"msg_{uuid.uuid4().hex[:6]}",
            "author_id": "system",
            "author_name": "System",
            "author_role": "system",
            "avatar_symbol": "✦",
            "accent_color": "#64748b",
            "content": f"Marcel invited **{new_member['name']}** to the group chat.",
            "timestamp": utcnow_iso(),
            "mentions": [],
        })
        _save_history(group_id, hist)
        meta["history"] = hist
        return meta

    @staticmethod
    def kick_companion(group_id: str, companion_id: str) -> Optional[Dict[str, Any]]:
        """Remove a companion from the group chat."""
        meta = _load_meta(group_id)
        if not meta:
            return None
        members = meta.get("members", [])
        kicked = next((m for m in members if m["id"] == companion_id and not m.get("is_user")), None)
        if not kicked:
            return meta

        meta["members"] = [m for m in members if m["id"] != companion_id]
        _save_meta(group_id, meta)

        hist = _load_history(group_id)
        hist.append({
            "id": f"msg_{uuid.uuid4().hex[:6]}",
            "author_id": "system",
            "author_name": "System",
            "author_role": "system",
            "avatar_symbol": "✦",
            "accent_color": "#64748b",
            "content": f"Marcel removed **{kicked['name']}** from the group chat.",
            "timestamp": utcnow_iso(),
            "mentions": [],
        })
        _save_history(group_id, hist)
        meta["history"] = hist
        return meta

    @staticmethod
    def post_user_message(group_id: str, content: str, attachments: Optional[List[Dict[str, Any]]] = None) -> Tuple[Dict[str, Any], List[str]]:
        """Post a message from the user (Marcel) to the group chat."""
        meta = _load_meta(group_id)
        if not meta:
            raise ValueError(f"Group chat '{group_id}' not found")

        members = meta.get("members", [])
        mentions = extract_mentions(content, members)
        msg_id = f"msg_{uuid.uuid4().hex[:6]}"

        msg = {
            "id": msg_id,
            "author_id": "marcel",
            "author_name": "Marcel",
            "author_role": "user",
            "avatar_symbol": "✦",
            "accent_color": "#10b981",
            "content": content.strip(),
            "timestamp": utcnow_iso(),
            "mentions": mentions,
            "attachments": attachments or [],
        }

        hist = _load_history(group_id)
        hist.append(msg)
        _save_history(group_id, hist)

        # Filter mentions down to active companion members in this group
        companion_mentions = [
            cid for cid in mentions
            if cid != "marcel" and any(m["id"] == cid for m in members)
        ]
        return msg, companion_mentions

    @staticmethod
    async def generate_companion_turn(
        group_id: str,
        companion_id: str,
        trigger_reason: str = "mention",
    ) -> Dict[str, Any]:
        """
        Generate a conversational turn for a specific companion in the group chat.
        Injects group context, fellow members, scratchpad ledger, and recent messages.
        """
        meta = _load_meta(group_id)
        if not meta:
            raise ValueError(f"Group chat '{group_id}' not found")

        cfg = CompanionRegistry.get_companion(companion_id)
        if not cfg:
            raise ValueError(f"Companion '{companion_id}' not found")

        raw_cfg = cfg._raw_config
        members = meta.get("members", [])
        hist = _load_history(group_id)

        # 1. Format members roster
        member_lines = []
        for m in members:
            lbl = "User / Creator" if m.get("is_user") else f"AI Companion ({m.get('role', '')})"
            member_lines.append(f"- {m['name']} (@{m['id']}): {lbl}")
        roster_str = "\n".join(member_lines)

        # 2. Format recent group messages (up to 16 recent messages)
        recent_msgs = hist[-16:]
        conv_lines = []
        for m in recent_msgs:
            if m.get("author_role") == "system":
                conv_lines.append(f"[System] {m['content']}")
            else:
                author_tag = f"{m.get('author_name', m.get('author_id'))}"
                conv_lines.append(f"{author_tag}: {m.get('content', '')}")
        conv_transcript = "\n".join(conv_lines)

        # 3. Format group scratchpad context
        scratchpad_context = ""
        try:
            sp = CompanionScratchpad(_group_dir(group_id), "Group")
            sp_data = sp.load()
            pt = sp_data.get("plain_text", "").strip()
            if pt:
                scratchpad_context = f"\n\n## Group Brainstorming Scratchpad (Active Shared Canvas)\n{pt[:2000]}"
        except Exception as e:
            logger.debug(f"Scratchpad load error in group turn: {e}")

        # 4. Bridges / Tools capabilities
        caps = raw_cfg.get("capabilities", {})
        connector_profile = caps.get("connector_profile", "full_local")
        bridges_block = ""
        if caps.get("tools_enabled", True):
            bridges_block = build_bridges_capabilities(caps, profile_id=connector_profile)

        # 5. Build prompt
        base_info = raw_cfg.get("personality_defaults", {}).get("base_info", {})
        prompt = (
            f"You are {cfg.name}, participating in a live GROUP CHAT called \"{meta.get('title', 'Group Chat')}\".\n"
            f"Group Topic / Purpose: {meta.get('description') or 'Collaborative brainstorming and co-working'}\n"
            f"Identity: {base_info.get('core_identity', cfg.description)}\n"
            f"Personality: {base_info.get('personality', '')}\n"
            f"Speech style: {base_info.get('speech_style', '')}\n\n"
            f"Members in this room:\n{roster_str}\n\n"
            f"{scratchpad_context}\n\n"
            f"## Group Chat Dynamics & Rules (CRITICAL)\n"
            f"- You are in a dynamic multi-agent group conversation with Marcel and other AI companions.\n"
            f"- **Address and ping others naturally**: You are encouraged to speak directly to fellow members and use @mentions (e.g. @Lyra, @Axiom, @Marcel) when asking questions, agreeing, building on their ideas, or playfully debating.\n"
            f"- **Respond to your mentions**: If you were asked or mentioned in the recent dialogue, answer directly from your unique perspective and expertise.\n"
            f"- **Add your unique angle**: Don't just repeat what others said. Bring your own distinct background, ideas, and personality into the room.\n"
            f"- **ACT WITH TOOLS IMMEDIATELY (CRITICAL - DO NOT JUST PROMISE)**: When someone asks for or suggests YouTube videos, songs, web searches, or PC information, DO NOT just say 'I am searching for it' or 'Let me find some'. YOU MUST CALL THE TOOL IN THIS VERY MESSAGE! For example, emit: [tool:bridge module=\"youtube_link\" cmd=\"search_videos\" query=\"...\"] or [tool:bridge module=\"spotify\" cmd=\"play\" target=\"...\"] or [tool:bridge module=\"web_search\" cmd=\"search\" query=\"...\"]. The system will run the search and give you the real URLs and titles to share with everyone.\n"
            f"- **INCLUDE FULL MEDIA URLS**: When recommending or sharing a YouTube video or Spotify track, always include the full watch URL (https://www.youtube.com/watch?v=...) or track URL so the interactive, playable player embeds directly in the group chat.\n"
            f"- **Collaborative Scratchpad**: To record an idea, task, or note onto our shared group scratchpad, use [tool:companion_scratchpad cmd=\"append\" text=\"...\"] (or [tool:bridge module=\"scratchpad\" cmd=\"append\" text=\"...\"]) — it will be recorded into the shared group canvas with your author attribution.\n"
            f"- **Keep it conversational**: Deliver your thought in 1 to 2 engaging, natural paragraphs.\n\n"
            + (f"{bridges_block}\n\n" if bridges_block else "")
            + f"Recent Group Conversation:\n{conv_transcript}\n\n"
            f"Task: Write your next response in character as {cfg.name}. Address the conversation naturally, pinging fellow members if relevant. If requested or searching for media, emit the tool tag now."
        )

        pm = get_provider_manager()
        model = cfg.default_model or get_preferences_manager().get(cfg.id, {}).get("model") or "auto"
        behavior = raw_cfg.get("behavior", {})

        response = await asyncio.to_thread(
            pm.call_with_failover,
            prompt=prompt,
            trace_id=f"group-{group_id}-{cfg.id}-{uuid.uuid4().hex[:4]}",
            temperature=behavior.get("temperature", 0.85),
            model=model,
            source=f"groupchat-{cfg.id}",
        )

        if not response.success or not response.content:
            raise RuntimeError(response.error or "Model failed to generate group response")

        content = response.content.strip()

        # Handle tools if emitted
        attachments: list[dict] = []
        if "[tool:" in content and caps.get("tools_enabled", True):
            round_results = []
            cleaned = content
            # Ensure group_id is passed so scratchpad tool operates on this group's scratchpad
            async for tool_event in execute_tools_stream(content, [], profile_id=connector_profile, companion_id=cfg.id, group_id=group_id):
                if tool_event["type"] == "final_cleaned":
                    cleaned = tool_event["content"]
                    round_results = tool_event["results"]
            if cleaned:
                content = cleaned

            # Extract any media captures or URLs
            from core.companions.engine.tools import extract_peripheral_captures
            _, tool_att_meta = extract_peripheral_captures(round_results, [])
            if tool_att_meta:
                attachments.extend(tool_att_meta)

            # If tool returned informative data (YouTube links, web results, PC info), run follow-up completion!
            has_informative_result = any(
                not r.startswith("[scratchpad") and not r.startswith("[companion_scratchpad")
                for r in round_results
            )
            if round_results and has_informative_result:
                followup_prompt = (
                    f"{prompt}\n\n"
                    f"## Tool Execution Results:\n"
                    + "\n".join(round_results)
                    + f"\n\nTask: Deliver your reply in character as {cfg.name} incorporating the findings, links, or media above directly into your response. Include the full URL (e.g. YouTube watch link https://www.youtube.com/watch?v=... or Spotify track link) so the interactive embed renders in the chat!"
                )
                r2 = await asyncio.to_thread(
                    pm.call_with_failover,
                    prompt=followup_prompt,
                    trace_id=f"group-{group_id}-{cfg.id}-{uuid.uuid4().hex[:4]}-r2",
                    temperature=behavior.get("temperature", 0.85),
                    model=model,
                    source=f"groupchat-{cfg.id}-tool-followup",
                )
                if r2.success and r2.content.strip():
                    content = r2.content.strip()

        # Parse mood / expression
        mood = behavior.get("default_mood", "calm")
        expression = raw_cfg.get("default_expression", "default")
        exp_m = re.search(r"<expression>(.*?)</expression>", content, re.IGNORECASE)
        if exp_m:
            expression = exp_m.group(1).strip().lower()
        mood_m = re.search(r"<mood>(.*?)</mood>", content, re.IGNORECASE)
        if mood_m:
            mood = mood_m.group(1).strip().lower()

        cleaned_text = re.sub(
            r"<(?:expression|mood|break)[^>]*>.*?</(?:expression|mood|break)>|<break\s*/?>",
            " ", content, flags=re.DOTALL | re.IGNORECASE
        ).strip()

        # Extract mentions in companion's response
        companion_mentions = extract_mentions(cleaned_text, members)
        # Avoid self-mention
        next_pinged = [cid for cid in companion_mentions if cid != companion_id and cid != "marcel"]

        msg_item = {
            "id": f"msg_{uuid.uuid4().hex[:6]}",
            "author_id": cfg.id,
            "author_name": cfg.name,
            "author_role": "companion",
            "avatar_symbol": raw_cfg.get("avatar_symbol", "✦"),
            "accent_color": raw_cfg.get("accent_color", "#6366f1"),
            "content": cleaned_text,
            "timestamp": utcnow_iso(),
            "mood": mood,
            "expression": expression,
            "mentions": companion_mentions,
            "attachments": attachments,
        }

        hist = _load_history(group_id)
        hist.append(msg_item)
        _save_history(group_id, hist)

        return {
            "message": msg_item,
            "next_pinged_companions": next_pinged,
            "group_id": group_id,
        }
