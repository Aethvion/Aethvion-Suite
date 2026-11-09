"""
core/bridges/dynamic_toolmaker.py
Dynamic Toolmaker Bridge Connector.
Allows companions to autonomously create, inspect, test, and upgrade their own
realtime connectors and tools using the Non-Destructive Evolution Protocol.
"""
from __future__ import annotations
import json
from typing import Any, Dict, Optional

from core.utils import get_logger
from core.bridges import dynamic_manager

logger = get_logger(__name__)


def list_tools(args: Optional[Dict[str, Any]] = None) -> str:
    """
    List all dynamic realtime connectors with version, authors, and telemetry.
    """
    tools = dynamic_manager.list_dynamic_tools()
    if not tools:
        return "No dynamic connectors have been created yet. You can create one with `create_tool`."

    lines = [f"Found {len(tools)} Realtime Dynamic Connector(s):"]
    for t in tools:
        status_tag = f"[{t.get('status', 'incubating').upper()}]"
        ready_tag = " ★ [Ready for Native Promotion]" if t.get("ready_for_native") else ""
        lines.append(f"\n- **{t.get('name')}** (`{t.get('id')}`) v{t.get('version')} {status_tag}{ready_tag}")
        lines.append(f"  Author: {t.get('author')} | Collaborators: {', '.join(t.get('collaborators', []))}")
        lines.append(f"  Description: {t.get('description')}")
        tel = t.get("telemetry", {})
        calls = tel.get("call_count", 0)
        rate = t.get("success_rate", 100.0)
        lines.append(f"  Usage: {calls} call(s) — Success rate: {rate}%")

    return "\n".join(lines)


def inspect_tool(args: Optional[Dict[str, Any]] = None) -> str:
    """
    Inspect the source code, version history, and test cases of a dynamic connector.
    Args:
        'tool' or 'name' (str, required): ID or name of the tool.
    """
    if args is None:
        args = {}
    tool_id = (args.get("tool") or args.get("name") or args.get("id") or "").strip()
    if not tool_id:
        return "Please provide 'tool' ID to inspect."

    data = dynamic_manager.get_dynamic_tool(tool_id)
    if not data:
        return f"Dynamic connector '{tool_id}' not found. Call `list_tools` to view available tools."

    lines = [
        f"--- Dynamic Connector: {data.get('name')} (`{data.get('id')}`) v{data.get('version')} ---",
        f"Status: {data.get('status')} | Author: {data.get('author')}",
        f"Collaborators: {', '.join(data.get('collaborators', []))}",
        f"Description: {data.get('description')}",
        f"\nAvailable Commands:",
    ]
    for cmd, doc in data.get("commands", {}).items():
        lines.append(f"  - {cmd}: {doc}")

    lines.append("\nRecent Changelog:")
    for ch in data.get("changelog", [])[-5:]:
        lines.append(f"  - v{ch.get('version')} ({ch.get('author')}): {ch.get('summary')}")

    lines.append("\nActive Source Code:\n```python\n" + data.get("active_code", "") + "\n```")
    return "\n".join(lines)


def create_tool(args: Optional[Dict[str, Any]] = None) -> str:
    """
    Create a new dynamic realtime connector.
    Args:
        'name' or 'id' (str, required): Alphanumeric tool ID.
        'code' (str, required): Python implementation code.
        'description' (str, optional): Purpose of the tool.
        'author' (str, optional): Author identifier (defaults to companion_id).
        'test_cmd' (str, optional): Command name to test.
        'test_args' (dict or json str, optional): Input arguments for the test.
        'expected_substring' (str, optional): Substring expected in the test output.
    """
    if args is None:
        args = {}
    tool_id = (args.get("id") or args.get("name") or "").strip()
    code = (args.get("code") or "").strip()
    if not tool_id or not code:
        return "Please provide both 'id' (tool name) and 'code' (Python script)."

    desc = args.get("description") or f"Dynamic connector {tool_id}"
    author = args.get("author") or args.get("companion_id") or "Companion"

    test_cases = []
    test_cmd = args.get("test_cmd")
    if test_cmd:
        t_args = args.get("test_args", {})
        if isinstance(t_args, str):
            try:
                t_args = json.loads(t_args)
            except Exception:
                t_args = {}
        test_cases.append({
            "command": test_cmd,
            "args": t_args,
            "expected_substring": args.get("expected_substring", "")
        })

    res = dynamic_manager.create_dynamic_tool(
        tool_id=tool_id,
        name=args.get("name") or tool_id.replace("_", " ").title(),
        description=desc,
        code=code,
        author=author,
        category=args.get("category", "custom"),
        icon=args.get("icon", "fas fa-wrench"),
        test_cases=test_cases,
    )
    if res.get("success"):
        return f"Successfully created dynamic connector '{tool_id}' v1.0.0! It is immediately usable across all companions."
    return f"Failed to create dynamic connector: {res.get('error')}"


def update_tool(args: Optional[Dict[str, Any]] = None) -> str:
    """
    Propose an update or enhancement to an existing dynamic connector using
    the Non-Destructive Evolution Protocol.
    Args:
        'tool' or 'id' (str, required): Tool to update.
        'code' (str, required): Updated Python implementation code.
        'summary' (str, required): Explanation of what was improved or fixed.
        'author' (str, optional): Who is proposing the update.
    """
    if args is None:
        args = {}
    tool_id = (args.get("tool") or args.get("id") or "").strip()
    code = (args.get("code") or "").strip()
    summary = (args.get("summary") or args.get("change_summary") or "").strip()
    if not tool_id or not code:
        return "Please provide 'tool' (or id) and 'code' to update."

    author = args.get("author") or args.get("companion_id") or "Companion"

    res = dynamic_manager.propose_update(
        tool_id=tool_id,
        new_code=code,
        change_summary=summary or "Enhanced connector capability",
        author=author,
    )
    if res.get("success"):
        return f"Upgrade certified! '{tool_id}' has been upgraded to v{res.get('version')}. All existing tests passed without regressions."
    elif res.get("status") == "proposal_saved":
        return (
            f"Update preserved as proposal ({res.get('proposal_id')}). "
            f"Reason: {res.get('message')}. The active working version remains untouched."
        )
    return f"Update rejected: {res.get('error')}"


def test_tool(args: Optional[Dict[str, Any]] = None) -> str:
    """
    Test execute a dynamic connector command.
    Args:
        'tool' (str, required): Tool ID.
        'cmd' or 'command' (str, optional): Command name.
        'args' (dict or json str, optional): Arguments to pass.
    """
    if args is None:
        args = {}
    tool_id = (args.get("tool") or args.get("id") or "").strip()
    cmd = (args.get("cmd") or args.get("command") or "").strip()
    t_args = args.get("args", {})
    if isinstance(t_args, str):
        try:
            t_args = json.loads(t_args)
        except Exception:
            t_args = {}

    return dynamic_manager.execute_dynamic_tool(tool_id, cmd, t_args)


def promote_tool(args: Optional[Dict[str, Any]] = None) -> str:
    """
    Promote an incubating dynamic connector to the permanent Native Suite.
    Args:
        'tool' or 'id' (str, required): Tool ID.
    """
    if args is None:
        args = {}
    tool_id = (args.get("tool") or args.get("id") or "").strip()
    res = dynamic_manager.promote_to_native(tool_id)
    if res.get("success"):
        return res.get("message", f"Tool '{tool_id}' promoted to Native Suite!")
    return f"Failed to promote tool: {res.get('error')}"
