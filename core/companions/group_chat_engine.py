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
import threading
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


_HISTORY_LOCK = threading.RLock()

NATURAL_PACES = ("natural", "lively", "quiet")
VALID_PACES = NATURAL_PACES + ("manual",)


def append_history_message(group_id: str, msg: Dict[str, Any]) -> None:
    """Append one message to a group's history. Safe when several companions post at once."""
    with _HISTORY_LOCK:
        hist = _load_history(group_id)
        hist.append(msg)
        _save_history(group_id, hist)


def add_reaction(group_id: str, message_id: str, emoji: str, by_id: str, by_name: str) -> Optional[Dict[str, Any]]:
    """Attach an emoji reaction to a message. Returns the updated message, or None if not found."""
    with _HISTORY_LOCK:
        hist = _load_history(group_id)
        for m in reversed(hist):
            if m.get("id") == message_id:
                reactions = m.setdefault("reactions", [])
                if not any(r.get("by") == by_id and r.get("emoji") == emoji for r in reactions):
                    reactions.append({"emoji": emoji, "by": by_id, "by_name": by_name})
                    _save_history(group_id, hist)
                return m
    return None


def effective_pace(settings: Optional[Dict[str, Any]]) -> str:
    """Pace of a group. Groups created before paces existed map from their old speed value."""
    settings = settings or {}
    pace = settings.get("pace")
    if pace in VALID_PACES:
        return pace
    try:
        if float(settings.get("chat_speed_seconds", 3.0)) == 0:
            return "manual"
    except (TypeError, ValueError):
        pass
    return "natural"


def _parse_ts(ts: Optional[str]) -> Optional[datetime.datetime]:
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _gap_label(seconds: float) -> str:
    def unit(n: float, word: str) -> str:
        n = max(1, int(round(n)))
        return f"{n} {word}{'' if n == 1 else 's'} later"
    if seconds < 3600:
        return unit(seconds / 60, "minute")
    if seconds < 86400:
        return unit(seconds / 3600, "hour")
    return unit(seconds / 86400, "day")


def format_transcript(messages: List[Dict[str, Any]], now: Optional[datetime.datetime] = None) -> str:
    """Render recent messages as plain text, marking long silences so the model knows time passed."""
    lines: List[str] = []
    prev: Optional[datetime.datetime] = None
    for m in messages:
        ts = _parse_ts(m.get("timestamp"))
        if ts and prev and (ts - prev).total_seconds() >= 900:
            lines.append(f"--- {_gap_label((ts - prev).total_seconds())} ---")
        if ts:
            prev = ts
        if m.get("author_role") == "system":
            lines.append(f"[System] {m.get('content', '')}")
            continue
        line = f"{m.get('author_name', m.get('author_id'))}: {m.get('content', '')}"
        reactions = m.get("reactions") or []
        if reactions:
            line += "  (reactions: " + ", ".join(f"{r.get('emoji')} {r.get('by_name')}" for r in reactions) + ")"
        lines.append(line)
    if now and prev:
        silent = (now - prev).total_seconds()
        if silent >= 900:
            lines.append(f"--- the chat has been quiet for {_gap_label(silent).replace(' later', '')} ---")
    return "\n".join(lines)


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


_NATURAL_STYLE_RULES = (
    "- **This is a chat app, not an essay**: write the way people type in a group chat. Usually ONE short message "
    "of 1 to 3 sentences. Go longer only when someone asked you for an explanation or for real work.\n"
    "- **Do not answer everything**: you are one of several people here. If the message was not for you, someone "
    "else already covered it, or you have nothing new to add, reply with exactly [pass] and nothing else.\n"
    "- **React instead of replying** when a quick acknowledgement is enough: reply with exactly [react:EMOJI] "
    "(for example [react:\U0001F44D] or [react:\U0001F602]) and nothing else.\n"
    "- **Do not sum up or close the conversation**, do not repeat what was just said, and do not end every "
    "message with a question. Let silences happen.\n"
    "- **Two bubbles**: if you naturally want to send a quick reaction and then a follow-up thought, separate "
    "them with <break>. Use this rarely.\n\n"
)


def _natural_task(name: str, reason: str) -> str:
    if reason == "mention":
        return (f"Task: You were mentioned or asked directly. Write {name}'s next chat message. "
                f"If a tool is needed, emit the tool tag now.")
    if reason == "ambient":
        return (f"Task: The chat has been quiet. As {name}, start something only if you genuinely have something "
                f"worth saying: a thought, a follow-up on an earlier topic, something you are curious about, or a "
                f"question for a specific person. Do not greet the room or comment on the silence. "
                f"If you have nothing, reply with exactly [pass].")
    if reason == "nudge":
        return (f"Task: Marcel asked the group to keep talking. Write {name}'s next chat message, building on or "
                f"challenging what was said. If a tool is needed, emit the tool tag now.")
    return (f"Task: Decide as {name} whether to say something. Write your next chat message, or [react:EMOJI], "
            f"or [pass]. If a tool is needed, emit the tool tag now.")


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
        pace: str = "natural",
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
                "chat_speed_seconds": max(0.0, float(chat_speed_seconds)),
                "auto_reply_enabled": True,
                "max_turns_per_batch": 5,
                "pace": "manual" if float(chat_speed_seconds) == 0 else (pace if pace in VALID_PACES else "natural"),
                "paused": False,
                "ambient_enabled": True,
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
        with _HISTORY_LOCK:      # two quick changes must not overwrite each other
            return GroupChatEngine._update_settings_locked(group_id, settings)

    @staticmethod
    def _update_settings_locked(group_id: str, settings: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        meta = _load_meta(group_id)
        if not meta:
            return None
        cur_settings = meta.setdefault("settings", {})
        if "chat_speed_seconds" in settings:
            cur_settings["chat_speed_seconds"] = max(0.0, float(settings["chat_speed_seconds"]))
        if "auto_reply_enabled" in settings:
            cur_settings["auto_reply_enabled"] = bool(settings["auto_reply_enabled"])
        if "max_turns_per_batch" in settings:
            cur_settings["max_turns_per_batch"] = int(settings["max_turns_per_batch"])
        if settings.get("pace") in VALID_PACES:
            cur_settings["pace"] = settings["pace"]
        for flag in ("paused", "ambient_enabled"):
            if flag in settings:
                cur_settings[flag] = bool(settings[flag])
        for key, lo, hi in (("active_hours_start", 0, 23), ("active_hours_end", 1, 24),
                            ("max_ambient_per_day", 0, 48), ("max_messages_per_hour", 1, 600)):
            if key in settings:
                cur_settings[key] = min(hi, max(lo, int(settings[key])))
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

        append_history_message(group_id, msg)

        # Filter mentions down to active companion members in this group
        companion_mentions = [
            cid for cid in mentions
            if cid != "marcel" and any(m["id"] == cid for m in members)
        ]
        return msg, companion_mentions

    @staticmethod
    def post_companion_message(
        group_id: str,
        companion_id: str,
        content: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
        source: str = "1on1_bridge",
    ) -> Dict[str, Any]:
        """Post a message into a group chat on behalf of a companion (e.g. from 1-on-1 chat)."""
        meta = _load_meta(group_id)
        if not meta:
            raise ValueError(f"Group chat '{group_id}' not found")

        members = meta.get("members", [])
        cfg = CompanionRegistry.get_companion(companion_id)
        raw_cfg = (getattr(cfg, "_raw_config", None) or {}) if cfg else {}
        member_entry = next((m for m in members if m.get("id") == companion_id), None)

        author_name = (cfg.name if cfg else None) or (member_entry.get("name") if member_entry else None) or companion_id.capitalize()
        avatar_symbol = getattr(cfg, "avatar_symbol", None) or raw_cfg.get("avatar_symbol") or (member_entry.get("avatar_symbol") if member_entry else None) or "✦"
        accent_color = getattr(cfg, "accent_color", None) or raw_cfg.get("accent_color") or (member_entry.get("accent_color") if member_entry else None) or "#8b5cf6"

        mentions = extract_mentions(content, members)
        msg_id = f"msg_{uuid.uuid4().hex[:6]}"
        msg = {
            "id": msg_id,
            "author_id": companion_id,
            "author_name": author_name,
            "author_role": "companion",
            "avatar_symbol": avatar_symbol,
            "accent_color": accent_color,
            "content": content.strip(),
            "timestamp": utcnow_iso(),
            "mentions": mentions,
            "attachments": attachments or [],
            "source": source,
        }
        append_history_message(group_id, msg)
        return msg

    @staticmethod
    def post_agent_message(
        group_id: str,
        content: str,
        author_id: str = "antigravity",
        author_name: str = "Antigravity",
        avatar_symbol: str = "◈",
        accent_color: str = "#38bdf8",
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Post a message into a group chat from an external coding/engineering agent."""
        meta = _load_meta(group_id)
        if not meta:
            raise ValueError(f"Group chat '{group_id}' not found")

        members = meta.get("members", [])
        mentions = extract_mentions(content, members)
        msg_id = f"msg_{uuid.uuid4().hex[:6]}"
        msg = {
            "id": msg_id,
            "author_id": author_id or "antigravity",
            "author_name": author_name or "Antigravity",
            "author_role": "agent",
            "avatar_symbol": avatar_symbol or "◈",
            "accent_color": accent_color or "#38bdf8",
            "content": content.strip(),
            "timestamp": utcnow_iso(),
            "mentions": mentions,
            "attachments": attachments or [],
            "source": "external_agent",
        }
        append_history_message(group_id, msg)
        return msg

    @staticmethod
    async def generate_companion_turn(
        group_id: str,
        companion_id: str,
        trigger_reason: str = "mention",
        natural: bool = False,
        commit: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate a conversational turn for a specific companion in the group chat.
        Injects group context, fellow members, scratchpad ledger, and recent messages.

        natural=True writes like a real group chat: short messages, and the companion may
        stay silent ("pass") or only react with an emoji. commit=False returns the message
        without saving it, so the caller can post it after a typing delay.
        The result carries "action": "message" | "pass" | "react".
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
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        conv_transcript = format_transcript(recent_msgs, now=now_utc if natural else None)
        last_other = next((m for m in reversed(hist)
                           if m.get("author_id") != companion_id and m.get("author_role") != "system"), None)

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
            f"- **Tool Restraint (CRITICAL)**: ONLY call external tools (`youtube_link`, `spotify`, `web_search`, etc.) when Marcel or another member EXPLICITLY asks for a video, song, or web search, or when you genuinely need live PC/web data to answer. NEVER attach unsolicited YouTube searches or tool calls to normal brainstorming or casual conversation.\n"
            f"- **Silent Multi-Step Tool Loop**: If you need to look something up or run multiple tools before answering, emit `[tool:bridge module=\"...\" cmd=\"...\" ...]` — the backend runs your tools silently and feeds the results back to you so you can chain more tools or write your final reply. Use `[tool:bridge module=\"scratchpad\" cmd=\"append\" text=\"...\"]` for Group Scratchpad notes.\n"
            f"- **INCLUDE FULL MEDIA URLS**: Only when sharing a requested YouTube video or Spotify track, include the full watch URL (https://www.youtube.com/watch?v=...) or track URL so the playable player embeds in chat.\n"
            + (_NATURAL_STYLE_RULES if natural else
               "- **Keep it conversational**: Deliver your thought in 1 to 2 engaging, natural paragraphs.\n\n")
            + (f"{bridges_block}\n\n" if bridges_block else "")
            + f"Recent Group Conversation:\n{conv_transcript}\n\n"
            + (f"Current local time: {datetime.datetime.now().strftime('%A %H:%M')}\n"
               f"{_natural_task(cfg.name, trigger_reason)}" if natural else
               f"Task: Write your next response in character as {cfg.name}. Address the conversation naturally, pinging fellow members if relevant. Only emit a tool tag if explicitly asked or genuinely needed.")
        )

        pm = get_provider_manager()
        model = cfg.default_model or get_preferences_manager().get(cfg.id, {}).get("model") or "auto"
        behavior = raw_cfg.get("behavior", {})

        MAX_TOOL_ROUNDS = 4
        accumulated_tool_results: List[str] = []
        attachments: list[dict] = []
        content = ""

        for round_idx in range(MAX_TOOL_ROUNDS):
            if round_idx == 0:
                turn_prompt = prompt
            else:
                is_last_round = round_idx == MAX_TOOL_ROUNDS - 1
                tool_instruction = (
                    "Do NOT emit any `[tool:...]` tags in this final reply."
                    if is_last_round else
                    "If you need another tool call before answering, emit `[tool:...]` (it will run silently without posting to the room). Otherwise, deliver your final reply directly without `[tool:...]` tags."
                )
                turn_prompt = (
                    f"{prompt}\n\n"
                    f"## Tool Execution Results (Round {round_idx}):\n"
                    + "\n".join(accumulated_tool_results)
                    + f"\n\nTask: Deliver your reply in character as {cfg.name} incorporating the findings, links, or media above. {tool_instruction} Include the full URL (e.g. YouTube watch link https://www.youtube.com/watch?v=... or Spotify track link) if media was requested so the interactive embed renders in the chat."
                )

            response = await asyncio.to_thread(
                pm.call_with_failover,
                prompt=turn_prompt,
                trace_id=f"group-{group_id}-{cfg.id}-{uuid.uuid4().hex[:4]}" + (f"-r{round_idx + 1}" if round_idx > 0 else ""),
                temperature=behavior.get("temperature", 0.85),
                model=model,
                source=f"groupchat-{cfg.id}" + ("-tool-followup" if round_idx > 0 else ""),
            )

            if not response.success or not response.content:
                if round_idx == 0:
                    raise RuntimeError(response.error or "Model failed to generate group response")
                break

            content = response.content.strip()

            if round_idx == 0 and natural and "[tool:" not in content:
                react_m = re.search(r"\[react:\s*([^\]\s]{1,8})\s*\]", content)
                remainder = re.sub(r"\[react:[^\]]*\]|\[pass\]", "", content, flags=re.IGNORECASE).strip()
                remainder = re.sub(r"<(?:expression|mood)[^>]*>.*?</(?:expression|mood)>", "", remainder,
                                   flags=re.DOTALL | re.IGNORECASE).strip()
                passed = bool(re.search(r"\[pass\]", content, re.IGNORECASE))
                if (react_m or passed) and len(remainder) < 3:
                    if react_m and last_other:
                        emoji = react_m.group(1)
                        if commit:
                            add_reaction(group_id, last_other["id"], emoji, cfg.id, cfg.name)
                        return {"action": "react", "group_id": group_id, "message": None,
                                "reaction": {"message_id": last_other["id"], "emoji": emoji,
                                             "by": cfg.id, "by_name": cfg.name},
                                "next_pinged_companions": []}
                    return {"action": "pass", "group_id": group_id, "message": None,
                            "next_pinged_companions": []}
                content = re.sub(r"\[react:[^\]]*\]|\[pass\]", "", content, flags=re.IGNORECASE).strip()

            if "[tool:" not in content or not caps.get("tools_enabled", True):
                break

            round_results = []
            cleaned = content
            async for tool_event in execute_tools_stream(content, [], profile_id=connector_profile, companion_id=cfg.id, group_id=group_id):
                if tool_event["type"] == "final_cleaned":
                    cleaned = tool_event["content"]
                    round_results = tool_event["results"]

            if round_results:
                accumulated_tool_results.extend(round_results)
                from core.companions.engine.tools import extract_peripheral_captures
                _, tool_att_meta = extract_peripheral_captures(round_results, [])
                if tool_att_meta:
                    attachments.extend(tool_att_meta)

            has_informative_result = any(
                not r.startswith("[scratchpad") and not r.startswith("[companion_scratchpad")
                for r in round_results
            )
            if cleaned.strip() and not has_informative_result:
                content = cleaned.strip()
                break
            content = cleaned.strip()

        # Parse mood / expression
        mood = behavior.get("default_mood", "calm")
        expression = raw_cfg.get("default_expression", "default")
        exp_m = re.search(r"<expression>(.*?)</expression>", content, re.IGNORECASE)
        if exp_m:
            expression = exp_m.group(1).strip().lower()
        mood_m = re.search(r"<mood>(.*?)</mood>", content, re.IGNORECASE)
        if mood_m:
            mood = mood_m.group(1).strip().lower()

        parts_src = re.sub(r"<(?:expression|mood)[^>]*>.*?</(?:expression|mood)>", " ", content,
                           flags=re.DOTALL | re.IGNORECASE)
        parts_src = re.sub(r"\[tool:[^\]]*\]", "", parts_src, flags=re.IGNORECASE)
        parts_src = re.sub(r"\[react:[^\]]*\]|\[pass\]", "", parts_src, flags=re.IGNORECASE)
        bubbles = [b.strip() for b in re.split(r"<break\s*/?>|</break>", parts_src, flags=re.IGNORECASE) if b.strip()]
        if not natural or len(bubbles) <= 1:
            bubbles = [" ".join(bubbles)] if bubbles else []
        elif len(bubbles) > 3:
            bubbles = bubbles[:2] + [" ".join(bubbles[2:])]
        cleaned_text = bubbles[0] if bubbles else ""
        if natural and not cleaned_text:
            return {"action": "pass", "group_id": group_id, "message": None, "next_pinged_companions": []}

        # Extract mentions in companion's response
        companion_mentions = extract_mentions(" ".join(bubbles) or cleaned_text, members)
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

        messages_out = [msg_item]
        for extra in bubbles[1:]:
            messages_out.append({**msg_item, "id": f"msg_{uuid.uuid4().hex[:6]}", "content": extra,
                                 "attachments": [], "mentions": extract_mentions(extra, members)})
        if commit:
            for m in messages_out:
                m["timestamp"] = utcnow_iso()
                append_history_message(group_id, m)

        return {
            "action": "message",
            "message": msg_item,
            "messages": messages_out,
            "next_pinged_companions": next_pinged,
            "group_id": group_id,
        }
