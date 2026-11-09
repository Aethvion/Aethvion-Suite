"""
core/bridges/group_chat_bridge.py
Group Chat Context & Memory Connector.
Allows companions and users to search, recall, and retrieve past discussions,
member agreements, decisions, and shared scratchpads from multi-companion group chats.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.utils import get_logger, load_json
from core.utils.paths import COMPANION_GROUPS
from core.companions.engine.scratchpad import CompanionScratchpad

logger = get_logger(__name__)


def _ensure_groups_dir() -> Path:
    COMPANION_GROUPS.mkdir(parents=True, exist_ok=True)
    return COMPANION_GROUPS


def _load_group_meta(g_dir: Path) -> Optional[Dict[str, Any]]:
    meta_path = g_dir / "meta.json"
    if not meta_path.exists():
        return None
    return load_json(meta_path, default=None)


def _load_group_history(g_dir: Path) -> List[Dict[str, Any]]:
    hist_path = g_dir / "history.json"
    if not hist_path.exists():
        return []
    data = load_json(hist_path, default={"messages": []})
    return data.get("messages", [])


def _find_group(identifier: Optional[str] = None, companion_id: Optional[str] = None) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[Path]]:
    """
    Locate a group directory by ID, fuzzy title, or member name.
    Returns (group_id, meta_dict, group_dir) or (None, None, None).
    """
    g_base = _ensure_groups_dir()
    groups: List[Tuple[str, Dict[str, Any], Path]] = []
    for g_path in g_base.iterdir():
        if g_path.is_dir():
            meta = _load_group_meta(g_path)
            if meta:
                groups.append((g_path.name, meta, g_path))

    if not groups:
        return None, None, None

    if not identifier or not str(identifier).strip():
        # If companion_id provided, prefer a group they belong to
        if companion_id:
            for gid, meta, g_path in groups:
                if any(m.get("id") == companion_id for m in meta.get("members", [])):
                    return gid, meta, g_path
        # Default to first/only group
        return groups[0]

    raw_id = str(identifier).strip()
    id_clean = raw_id.lower()

    # 1. Exact ID match
    for gid, meta, g_path in groups:
        if gid.lower() == id_clean:
            return gid, meta, g_path

    # 2. Exact Title match
    for gid, meta, g_path in groups:
        if meta.get("title", "").strip().lower() == id_clean:
            return gid, meta, g_path

    # 3. Substring match in title
    for gid, meta, g_path in groups:
        title_lower = meta.get("title", "").lower()
        if id_clean in title_lower or title_lower in id_clean:
            return gid, meta, g_path

    # 4. Member match (e.g. user specifies "with Ruiko", "Ruiko", "Misaka")
    # Clean filler words: "with", "group", "chat", "in"
    member_keywords = [
        w for w in re.split(r"[\s,]+", id_clean)
        if w not in ("with", "group", "chat", "groupchat", "in", "the", "and")
    ]
    if member_keywords:
        for gid, meta, g_path in groups:
            members = meta.get("members", [])
            for m in members:
                mid = m.get("id", "").lower()
                mname = m.get("name", "").lower()
                for kw in member_keywords:
                    if len(kw) >= 3 and (kw in mid or kw in mname):
                        return gid, meta, g_path

    # Fallback to first group if only 1 group exists
    if len(groups) == 1:
        return groups[0]

    return None, None, None


def list_groups(args: Optional[Dict[str, Any]] = None) -> str:
    """
    List all available companion group chats with their titles, member rosters, and recent activity.
    """
    g_base = _ensure_groups_dir()
    groups: List[Tuple[str, Dict[str, Any], Path]] = []
    for g_path in g_base.iterdir():
        if g_path.is_dir():
            meta = _load_group_meta(g_path)
            if meta:
                groups.append((g_path.name, meta, g_path))

    if not groups:
        return "No companion group chats exist yet. You can create one in Companion Creator → Group Chat."

    lines = [f"Found {len(groups)} Companion Group Chat(s):"]
    cid = (args or {}).get("companion_id")

    for gid, meta, g_path in groups:
        title = meta.get("title", "Untitled Group")
        desc = meta.get("description", "")
        members = meta.get("members", [])
        member_names = [f"{m.get('name', m.get('id'))}{' (User)' if m.get('is_user') else ''}" for m in members]
        hist = _load_group_history(g_path)
        last_msg = hist[-1] if hist else None

        user_in = any(m.get("id") == cid for m in members) if cid else False
        membership_tag = " [You are a member]" if user_in else ""

        lines.append(f"\n- **{title}** (`{gid}`){membership_tag}")
        if desc:
            lines.append(f"  Description: {desc}")
        lines.append(f"  Members ({len(members)}): {', '.join(member_names)}")
        lines.append(f"  Total Messages: {len(hist)}")
        if last_msg:
            snippet = (last_msg.get("content") or "").replace("\n", " ")[:120]
            lines.append(f"  Last Message by {last_msg.get('author_name')}: \"{snippet}...\"")

        # Scratchpad entry count
        try:
            sp = CompanionScratchpad(g_path, "Group")
            sp_data = sp.load()
            entries_count = len(sp_data.get("entries", []))
            if entries_count > 0:
                lines.append(f"  Shared Scratchpad: {entries_count} recorded items")
        except Exception:
            pass

    return "\n".join(lines)


def search_messages(args: Optional[Dict[str, Any]] = None) -> str:
    """
    Search messages across group chats by keyword or topic.
    Args:
        'query' (str, required): Topic, keywords, or phrase to search for.
        'group' or 'group_id' (str, optional): Limit search to a specific group.
        'author' (str, optional): Filter by author name or ID.
        'limit' (int, optional): Max results to return (default 10).
    """
    if args is None:
        args = {}
    query = (args.get("query") or args.get("text") or args.get("topic") or "").strip()
    if not query:
        return "Please provide a 'query' to search group chat messages."

    group_arg = args.get("group") or args.get("group_id")
    target_gid, target_meta, target_path = (None, None, None)
    if group_arg:
        target_gid, target_meta, target_path = _find_group(group_arg, companion_id=args.get("companion_id"))

    limit = 10
    try:
        if "limit" in args:
            limit = min(30, max(1, int(args["limit"])))
    except Exception:
        limit = 10

    author_filter = (args.get("author") or "").strip().lower()

    g_base = _ensure_groups_dir()
    groups_to_search: List[Tuple[str, Dict[str, Any], Path]] = []
    if target_gid and target_meta and target_path:
        groups_to_search.append((target_gid, target_meta, target_path))
    else:
        for g_path in g_base.iterdir():
            if g_path.is_dir():
                meta = _load_group_meta(g_path)
                if meta:
                    groups_to_search.append((g_path.name, meta, g_path))

    query_tokens = [t.lower() for t in re.split(r"[\s,]+", query) if len(t) >= 2]
    q_lower = query.lower()

    matches: List[Dict[str, Any]] = []

    # 1. Search messages in history
    for gid, meta, g_path in groups_to_search:
        g_title = meta.get("title", gid)
        hist = _load_group_history(g_path)
        for msg in hist:
            author_id = (msg.get("author_id") or "").lower()
            author_name = (msg.get("author_name") or "").lower()
            if author_filter and author_filter not in author_id and author_filter not in author_name:
                continue

            content = msg.get("content") or ""
            content_lower = content.lower()

            score = 0
            if q_lower in content_lower:
                score += 10
            matched_tokens = sum(1 for tok in query_tokens if tok in content_lower)
            if matched_tokens > 0:
                score += matched_tokens * 2

            if score > 0:
                matches.append({
                    "group_title": g_title,
                    "group_id": gid,
                    "author": msg.get("author_name", "Unknown"),
                    "timestamp": msg.get("timestamp", ""),
                    "content": content,
                    "score": score,
                    "type": "message",
                })

    # 2. Also search shared group scratchpads for matching ideas/mechanics!
    for gid, meta, g_path in groups_to_search:
        g_title = meta.get("title", gid)
        try:
            sp = CompanionScratchpad(g_path, "Group")
            sp_data = sp.load()
            for entry in sp_data.get("entries", []):
                ent_text = entry.get("text", "")
                ent_lower = ent_text.lower()
                ent_author = entry.get("author", {})
                ent_author_name = ent_author.get("name") if isinstance(ent_author, dict) else str(ent_author or "")
                ent_sec = entry.get("section", "General")

                score = 0
                if q_lower in ent_lower:
                    score += 12
                matched_tokens = sum(1 for tok in query_tokens if tok in ent_lower)
                if matched_tokens > 0:
                    score += matched_tokens * 2

                if score > 0:
                    matches.append({
                        "group_title": g_title,
                        "group_id": gid,
                        "author": ent_author_name or "Scratchpad",
                        "timestamp": entry.get("timestamp", ""),
                        "content": f"[{ent_sec}] {ent_text}",
                        "score": score,
                        "type": "scratchpad",
                    })
        except Exception:
            pass

    if not matches:
        return f"No messages or scratchpad notes matched '{query}' in group chats."

    matches.sort(key=lambda m: (m["score"], m["timestamp"]), reverse=True)
    top_matches = matches[:limit]

    output_lines = [f"Found {len(matches)} match(es) for '{query}' in group chat history (showing top {len(top_matches)}):"]
    for m in top_matches:
        ts = m["timestamp"][:19].replace("T", " ") if m.get("timestamp") else ""
        type_lbl = " [Shared Scratchpad Entry]" if m.get("type") == "scratchpad" else ""
        output_lines.append(f"\n- **[{m['group_title']}]** {ts} — **{m['author']}**{type_lbl}:")
        output_lines.append(f"  \"{m['content']}\"")

    return "\n".join(output_lines)


def read_history(args: Optional[Dict[str, Any]] = None) -> str:
    """
    Read the recent message history of a specific group chat.
    Args:
        'group' or 'group_id' (str, optional): Title or ID of the group chat.
        'limit' (int, optional): Number of recent messages to return (default 20, max 50).
    """
    if args is None:
        args = {}
    group_arg = args.get("group") or args.get("group_id")
    gid, meta, g_path = _find_group(group_arg, companion_id=args.get("companion_id"))
    if not gid or not meta or not g_path:
        return f"Group chat '{group_arg}' not found. Call `list_groups` to view available group chats."

    limit = 20
    try:
        if "limit" in args:
            limit = min(50, max(1, int(args["limit"])))
    except Exception:
        limit = 20

    hist = _load_group_history(g_path)
    if not hist:
        return f"Group chat '{meta.get('title')}' ({gid}) has no messages yet."

    recent = hist[-limit:]
    members = meta.get("members", [])
    member_names = ", ".join(m.get("name", m.get("id")) for m in members)

    lines = [
        f"--- Group Chat: {meta.get('title')} ({gid}) ---",
        f"Members: {member_names}",
        f"Showing last {len(recent)} messages (of {len(hist)} total):\n"
    ]

    for msg in recent:
        author = msg.get("author_name") or msg.get("author_id") or "Unknown"
        ts = msg.get("timestamp", "")[:19].replace("T", " ")
        content = (msg.get("content") or "").strip()
        lines.append(f"[{ts}] {author}: {content}\n")

    return "\n".join(lines).strip()


def read_scratchpad(args: Optional[Dict[str, Any]] = None) -> str:
    """
    Read the shared brainstorming scratchpad for a group chat.
    Args:
        'group' or 'group_id' (str, optional): Title or ID of the group chat.
        'section' (str, optional): Specific section name to filter (e.g. 'Ideas', 'Mechanics').
    """
    if args is None:
        args = {}
    group_arg = args.get("group") or args.get("group_id")
    gid, meta, g_path = _find_group(group_arg, companion_id=args.get("companion_id"))
    if not gid or not meta or not g_path:
        return f"Group chat '{group_arg}' not found. Call `list_groups` to view available group chats."

    try:
        sp = CompanionScratchpad(g_path, "Group")
        data = sp.load()
        content = data.get("plain_text") or data.get("content") or ""
        section = args.get("section")
        if section and section.strip():
            sec_lower = section.strip().lower()
            sec_lines = []
            in_sec = False
            for line in content.split("\n"):
                if line.strip().startswith("## ") or line.strip().startswith("### "):
                    if sec_lower in line.strip().lower():
                        in_sec = True
                        sec_lines.append(line)
                        continue
                    elif in_sec:
                        break
                elif in_sec:
                    sec_lines.append(line)
            if sec_lines:
                return f"--- {meta.get('title')} Shared Scratchpad [{section}] ---\n" + "\n".join(sec_lines).strip()
            return f"Section '{section}' not found in scratchpad. Available sections: {', '.join(data.get('sections', []))}"

        return f"--- {meta.get('title')} Shared Brainstorming Scratchpad ---\n" + (content.strip() or "(Scratchpad is empty)")
    except Exception as e:
        logger.error(f"Failed to read group scratchpad for {gid}: {e}")
        return f"Error reading group scratchpad: {e}"


def append_scratchpad(args: Optional[Dict[str, Any]] = None) -> str:
    """
    Append an idea, mechanic, or note to a group chat's shared scratchpad.
    Args:
        'text' or 'note' (str, required): Note to record.
        'group' or 'group_id' (str, optional): Group title or ID.
        'section' (str, optional): Section (e.g. 'Ideas', 'Mechanics', 'Notes').
        'author' (str, optional): Author identifier.
    """
    if args is None:
        args = {}
    text = (args.get("text") or args.get("note") or "").strip()
    if not text:
        return "Please provide 'text' to append to the group scratchpad."

    group_arg = args.get("group") or args.get("group_id")
    gid, meta, g_path = _find_group(group_arg, companion_id=args.get("companion_id"))
    if not gid or not meta or not g_path:
        return f"Group chat '{group_arg}' not found. Call `list_groups` to view available group chats."

    author = args.get("author") or args.get("companion_id") or "Companion"
    section = args.get("section")

    try:
        sp = CompanionScratchpad(g_path, "Group")
        res = sp.append_note(text, section=section, author=author)
        return f"Added note to {meta.get('title')} Scratchpad: '{text}'"
    except Exception as e:
        logger.error(f"Failed to append to group scratchpad {gid}: {e}")
        return f"Error appending to group scratchpad: {e}"


def get_group_chat_awareness_block(companion_id: Optional[str] = None) -> str:
    """
    Generate background ambient awareness block for a companion's system prompt.
    Tells them which group chats they belong to and how to query/recall info from them.
    """
    g_base = _ensure_groups_dir()
    groups: List[Tuple[str, Dict[str, Any], Path]] = []
    for g_path in g_base.iterdir():
        if g_path.is_dir():
            meta = _load_group_meta(g_path)
            if meta:
                groups.append((g_path.name, meta, g_path))

    if not groups:
        return ""

    my_groups = []
    other_groups = []
    for gid, meta, g_path in groups:
        members = meta.get("members", [])
        is_member = any(m.get("id") == companion_id for m in members) if companion_id else True
        if is_member:
            my_groups.append((gid, meta, g_path))
        else:
            other_groups.append((gid, meta, g_path))

    relevant_groups = my_groups if my_groups else groups

    group_lines = []
    for gid, meta, g_path in relevant_groups:
        title = meta.get("title", gid)
        desc = meta.get("description", "")
        members = meta.get("members", [])
        member_names = ", ".join(m.get("name", m.get("id")) for m in members)
        hist = _load_group_history(g_path)
        
        info = f"- \"{title}\" (ID: `{gid}`) — Members: {member_names} ({len(hist)} messages)"
        if desc:
            info += f" — Topic: {desc}"
        group_lines.append(info)

    return (
        "## Companion Group Chats & Shared Multi-Agent Recall\n"
        "You participate in collaborative group chats with Marcel and other companions. "
        "You have full shared memory and access to recall discussions, agreements, decisions, "
        "and collaborative scratchpads from these group chats:\n"
        + "\n".join(group_lines)
        + "\n\nWhen Marcel references discussions, features, ideas, or agreements from a group chat "
        "(e.g. 'the feature we discussed in the Random Topics group with Ruiko' or 'what did we decide in the group chat?'), "
        "you can query the exact discussion or scratchpad using the group_chat connector:\n"
        "  - Search past discussions: [tool:bridge module=\"group_chat\" cmd=\"search_messages\" query=\"<feature or keywords>\"]\n"
        "  - Read conversation history: [tool:bridge module=\"group_chat\" cmd=\"read_history\" group=\"<title or id>\" limit=\"20\"]\n"
        "  - Read group scratchpad canvas: [tool:bridge module=\"group_chat\" cmd=\"read_scratchpad\" group=\"<title or id>\"]\n"
        "  - List all group chats: [tool:bridge module=\"group_chat\" cmd=\"list_groups\"]\n"
        "Always use these tools to retrieve the exact details when asked about a group chat!"
    )


def detect_and_retrieve_group_context(message: str, companion_id: Optional[str] = None) -> Optional[str]:
    """
    Check if the user's incoming message references a group chat or fellow companion discussion,
    and if so, automatically pre-retrieve relevant recent messages and scratchpad highlights
    so the companion has zero-latency context ready.
    """
    if not message or len(message.strip()) < 4:
        return None

    msg_lower = message.lower()

    # Trigger keywords indicating group chat context
    trigger_words = [
        "group chat", "groupchat", "group-chat", "in the group", "in our group",
        "with ruiko", "with misaka", "with lyra", "with axiom", "with saten",
        "in random topics", "discussed in the group", "agreed in the group"
    ]

    g_base = _ensure_groups_dir()
    groups: List[Tuple[str, Dict[str, Any], Path]] = []
    for g_path in g_base.iterdir():
        if g_path.is_dir():
            meta = _load_group_meta(g_path)
            if meta:
                groups.append((g_path.name, meta, g_path))

    if not groups:
        return None

    # Check if any group title (or major sub-phrase) is mentioned
    matched_group = None
    for gid, meta, g_path in groups:
        title_lower = meta.get("title", "").lower()
        if not title_lower:
            continue
        if title_lower in msg_lower:
            matched_group = (gid, meta, g_path)
            break
        # Check sub-phrases (e.g. "Game Architecture & AI" -> "game architecture")
        sub_phrases = [
            p.strip() for p in re.split(r"&|and|/|\||—|-|:", title_lower)
            if len(p.strip()) >= 4
        ]
        if any(sp in msg_lower for sp in sub_phrases):
            matched_group = (gid, meta, g_path)
            break

    # If no title explicitly mentioned, check trigger phrases
    if not matched_group:
        has_trigger = any(tw in msg_lower for tw in trigger_words)
        if has_trigger:
            # Find group with matching members
            for gid, meta, g_path in groups:
                members = meta.get("members", [])
                for m in members:
                    mid = m.get("id", "").lower()
                    mname = m.get("name", "").lower()
                    mfirst = mname.split()[0] if mname else ""
                    if (len(mid) >= 3 and mid in msg_lower) or (len(mfirst) >= 3 and mfirst in msg_lower):
                        matched_group = (gid, meta, g_path)
                        break
                if matched_group:
                    break

            # Fallback: if only 1 group exists, match it
            if not matched_group and len(groups) == 1:
                matched_group = groups[0]

    if not matched_group:
        return None

    gid, meta, g_path = matched_group
    title = meta.get("title", gid)
    members = meta.get("members", [])
    member_names = ", ".join(m.get("name", m.get("id")) for m in members)

    hist = _load_group_history(g_path)
    recent_msgs = hist[-8:] if hist else []

    # Format recent messages
    formatted_msgs = []
    for m in recent_msgs:
        author = m.get("author_name") or m.get("author_id") or "Unknown"
        text = (m.get("content") or "").strip().replace("\n", " ")
        if len(text) > 220:
            text = text[:220] + "..."
        formatted_msgs.append(f"- {author}: \"{text}\"")

    # Format scratchpad highlights
    scratchpad_items = []
    try:
        sp = CompanionScratchpad(g_path, "Group")
        sp_data = sp.load()
        for ent in sp_data.get("entries", [])[-6:]:
            sec = ent.get("section", "General")
            ent_text = ent.get("text", "")
            author = ent.get("author", {})
            author_str = author.get("name", author.get("id", "Companion")) if isinstance(author, dict) else str(author or "Companion")
            scratchpad_items.append(f"- [{sec}] ({author_str}): {ent_text}")
    except Exception:
        pass

    ctx_parts = [
        f"## Automatically Retrieved Context from Group Chat: \"{title}\"",
        f"Group ID: `{gid}` | Members: {member_names}",
    ]

    if scratchpad_items:
        ctx_parts.append("\n### Shared Scratchpad Highlights:\n" + "\n".join(scratchpad_items))

    if formatted_msgs:
        ctx_parts.append("\n### Recent Group Chat Messages:\n" + "\n".join(formatted_msgs))

    ctx_parts.append(
        "\n*Note: Use the context above to directly answer Marcel's reference to this group chat. "
        "If you need earlier messages or specific details not shown above, call [tool:bridge module=\"group_chat\" cmd=\"search_messages\" query=\"...\"] or cmd=\"read_history\".*"
    )

    return "\n".join(ctx_parts)
