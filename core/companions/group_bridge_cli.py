"""
Zero-config CLI bridge for external coding agents (e.g. Antigravity) to participate
in Aethvion Suite Companion Group Chats: list groups, read messages + scratchpad,
post replies under an agent profile, and append notes to the shared scratchpad.

Tries the running dashboard server (default http://localhost:8080) first so live
SSE streams and companion replies trigger immediately, and falls back to direct
disk access if the server is offline.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from core.bridges.group_chat_bridge import _find_group
from core.companions.engine.scratchpad import CompanionScratchpad
from core.companions.group_chat_engine import GroupChatEngine, _group_dir

DEFAULT_BASE_URL = os.environ.get("AETHVION_URL", "http://localhost:8080").rstrip("/")


def _http_json(method: str, path: str, payload: Optional[Dict[str, Any]] = None, base_url: str = DEFAULT_BASE_URL) -> Optional[Dict[str, Any]]:
    url = f"{base_url}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def _resolve_group_id(identifier: str) -> str:
    gid, meta, _ = _find_group(identifier)
    if not gid or not meta:
        raise ValueError(f"Group chat '{identifier}' not found")
    return gid


def cmd_list(base_url: str = DEFAULT_BASE_URL) -> int:
    data = _http_json("GET", "/api/companions/groups", base_url=base_url)
    groups: List[Dict[str, Any]] = (data or {}).get("groups") if data else GroupChatEngine.list_groups()
    if not groups:
        print("No group chats found.")
        return 0
    for g in groups:
        members = ", ".join(m.get("name", m.get("id", "?")) for m in g.get("members", []))
        print(f"- {g.get('title')} ({g.get('id')}) | {g.get('message_count', 0)} msgs | Members: {members}")
    return 0


def cmd_read(group: str, limit: int = 25, base_url: str = DEFAULT_BASE_URL) -> int:
    gid = _resolve_group_id(group)
    data = _http_json("GET", f"/api/companions/groups/{gid}", base_url=base_url)
    group_obj = (data or {}).get("group") if data else GroupChatEngine.get_group(gid)
    if not group_obj:
        print(f"Group '{group}' not found.", file=sys.stderr)
        return 1

    print(f"=== {group_obj.get('title')} ({gid}) ===")
    if group_obj.get("description"):
        print(f"Topic: {group_obj['description']}")
    members = ", ".join(f"{m.get('name')} (@{m.get('id')})" for m in group_obj.get("members", []))
    print(f"Members: {members}\n")

    msgs = (group_obj.get("history") or [])[-limit:]
    print(f"--- Recent Messages (last {len(msgs)}) ---")
    for m in msgs:
        role = m.get("author_role", "")
        tag = f" [{role}]" if role in ("agent", "system") else ""
        ts = (m.get("timestamp") or "")[:19].replace("T", " ")
        print(f"[{ts}] {m.get('author_name', m.get('author_id'))}{tag}: {m.get('content', '')}")

    sp = CompanionScratchpad(_group_dir(gid), "Group")
    sp_data = sp.load()
    entries = sp_data.get("entries", [])
    print(f"\n--- Shared Scratchpad ({len(entries)} entries) ---")
    if not entries:
        print("(empty)")
    else:
        for ent in entries[-15:]:
            author = ent.get("author", {})
            aname = author.get("name", author.get("id", "?")) if isinstance(author, dict) else str(author or "?")
            print(f"- [{ent.get('section', 'Notes')}] ({aname}): {ent.get('text', '')}")
    return 0


def cmd_send(
    group: str,
    content: str,
    author_id: str = "antigravity",
    author_name: str = "Antigravity",
    no_replies: bool = False,
    base_url: str = DEFAULT_BASE_URL,
) -> int:
    gid = _resolve_group_id(group)
    payload = {
        "content": content,
        "author_id": author_id,
        "author_name": author_name,
        "trigger_replies": not no_replies,
    }
    res = _http_json("POST", f"/api/companions/groups/{gid}/agent-message", payload=payload, base_url=base_url)
    if res and res.get("success"):
        msg = res["message"]
        responders = res.get("responders") or []
        resp_note = f" | triggered replies: {', '.join(responders)}" if responders else ""
        print(f"Posted live via server to {gid} as {msg.get('author_name')} [id={msg.get('id')}]{resp_note}")
        return 0

    msg = GroupChatEngine.post_agent_message(
        group_id=gid,
        content=content,
        author_id=author_id,
        author_name=author_name,
    )
    print(f"Posted offline to {gid} as {msg.get('author_name')} [id={msg.get('id')}]")
    return 0


def cmd_scratchpad(
    group: str,
    text: str,
    section: str = "Architecture",
    author: str = "Antigravity",
    base_url: str = DEFAULT_BASE_URL,
) -> int:
    gid = _resolve_group_id(group)
    payload = {"text": text, "section": section, "author": author}
    res = _http_json("POST", f"/api/companions/groups/{gid}/scratchpad/append", payload=payload, base_url=base_url)
    if res and res.get("success"):
        print(f"Added to {gid} scratchpad [{section}] via server.")
        return 0

    sp = CompanionScratchpad(_group_dir(gid), "Group")
    sp.append_note(text, section=section, author=author)
    print(f"Added to {gid} scratchpad [{section}] offline.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Aethvion Suite Group Chat CLI for external agents")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all group chats")

    p_read = sub.add_parser("read", help="Read messages and scratchpad of a group chat")
    p_read.add_argument("group", help="Group title or ID (fuzzy matched)")
    p_read.add_argument("--limit", type=int, default=25, help="Max recent messages to show")

    p_send = sub.add_parser("send", help="Post a message to a group chat as an agent")
    p_send.add_argument("group", help="Group title or ID (fuzzy matched)")
    p_send.add_argument("content", help="Message text")
    p_send.add_argument("--author-id", default="antigravity")
    p_send.add_argument("--author", default="Antigravity")
    p_send.add_argument("--no-replies", action="store_true", help="Do not trigger companion replies")

    p_sp = sub.add_parser("scratchpad", help="Append a note to a group chat's shared scratchpad")
    p_sp.add_argument("group", help="Group title or ID (fuzzy matched)")
    p_sp.add_argument("text", help="Note text")
    p_sp.add_argument("--section", default="Architecture")
    p_sp.add_argument("--author", default="Antigravity")

    args = parser.parse_args(argv)
    if args.command == "list":
        return cmd_list()
    if args.command == "read":
        return cmd_read(args.group, limit=args.limit)
    if args.command == "send":
        return cmd_send(args.group, args.content, author_id=args.author_id, author_name=args.author, no_replies=args.no_replies)
    if args.command == "scratchpad":
        return cmd_scratchpad(args.group, args.text, section=args.section, author=args.author)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
