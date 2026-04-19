"""
core/companions/engine/tools.py
════════════════════════════════
Tool execution — file operations + bridge module dispatch.
Shared by ALL companions; workspaces gate file permissions per companion instance.
"""
from __future__ import annotations
import asyncio
import json
import re
from pathlib import Path
from typing import Any, AsyncGenerator
from core.utils.logger import get_logger

logger = get_logger(__name__)


# ── Workspace helpers ─────────────────────────────────────────────────────────

def validate_path(target: str, workspaces: list[dict], permission: str) -> tuple[bool, str]:
    """Return (allowed, reason_string)."""
    tp = Path(target).resolve()
    for ws in workspaces:
        if permission not in ws.get("permissions", []):
            continue
        ws_path = Path(ws["path"]).resolve()
        try:
            tp.relative_to(ws_path)
            if not ws.get("recursive", True) and tp.parent != ws_path:
                return False, (
                    f"Non-recursive workspace '{ws['label']}' — subdirectories not allowed."
                )
            return True, "OK"
        except ValueError:
            continue
    return False, f"'{target}' is not inside any workspace with '{permission}' permission."





# ── Tool tag parsing ──────────────────────────────────────────────────────────

def parse_tool_blocks(text: str) -> list[tuple[int, int, str]]:
    """Return list of (start, end, raw_block) for every [tool:...] block in text."""
    blocks: list[tuple[int, int, str]] = []
    idx = text.find("[tool:")
    while idx != -1:
        depth = 0
        end_idx = len(text)
        for i in range(idx, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    end_idx = i + 1
                    break
        blocks.append((idx, end_idx, text[idx:end_idx]))
        idx = text.find("[tool:", end_idx)
    return blocks


def parse_attrs(attr_str: str) -> dict[str, str]:
    """Parse key="value" / key='value' / key=value attribute string."""
    attrs: dict[str, str] = {}
    pos = 0
    while pos < len(attr_str):
        m = re.search(r"(\w+)=", attr_str[pos:])
        if not m:
            break
        key = m.group(1)
        pos += m.end()
        if pos < len(attr_str) and attr_str[pos] in ('"', "'"):
            q = attr_str[pos]
            pos += 1
            end = attr_str.find(q, pos)
            if end == -1:
                end = len(attr_str)
            val = attr_str[pos:end]
            pos = end + 1
        else:
            end = attr_str.find(" ", pos)
            if end == -1:
                end = len(attr_str)
            val = attr_str[pos:end]
            pos = end + 1
        val = val.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")
        if key not in ("path", "dir", "directory", "folder"):
            val = val.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
        attrs[key] = val.strip()
    return attrs


# ── Single-tool execution (sync, runs in thread) ──────────────────────────────

def _execute_one(tool_name: str, attrs: dict[str, str], workspaces: list[dict]) -> str:
    """Execute a single tool call synchronously. Called via asyncio.to_thread."""
    try:
        if tool_name == "read_file":
            path = attrs.get("path", "")
            ok, reason = validate_path(path, workspaces, "read")
            if not ok:
                return f"[read_file ERROR] {reason}"
            p = Path(path)
            if not p.exists():
                return f"[read_file ERROR] File not found: {path}"
            if p.stat().st_size > 500_000:
                return f"[read_file ERROR] File too large (>500KB): {path}"
            return f"[read_file: {path}]\n{p.read_text(encoding='utf-8', errors='replace')[:8000]}"

        if tool_name == "write_file":
            path = attrs.get("path", "")
            content = attrs.get("content", "")
            ok, reason = validate_path(path, workspaces, "write")
            if not ok:
                return f"[write_file ERROR] {reason}"
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"[write_file OK] Written {len(content)} chars to {path}"

        if tool_name == "list_files":
            path = attrs.get("path", "")
            ok, reason = validate_path(path, workspaces, "read")
            if not ok:
                return f"[list_files ERROR] {reason}"
            p = Path(path)
            if not p.is_dir():
                return f"[list_files ERROR] Not a directory: {path}"
            items = sorted(p.iterdir())[:50]
            listing = "\n".join(
                f"{'[DIR] ' if i.is_dir() else '[FILE]'} {i.name}" for i in items
            )
            return f"[list_files: {path}]\n{listing}"

        if tool_name == "search_files":
            query = attrs.get("query", "")
            search_path = attrs.get("path", "")
            ok, reason = validate_path(search_path, workspaces, "read")
            if not ok:
                return f"[search_files ERROR] {reason}"
            p = Path(search_path)
            matches: list[str] = []
            for file in p.rglob("*"):
                if file.is_file() and len(matches) < 20:
                    try:
                        text = file.read_text(encoding="utf-8", errors="ignore")
                        if query.lower() in text.lower():
                            lines = [
                                f"  L{i + 1}: {line.strip()}"
                                for i, line in enumerate(text.splitlines())
                                if query.lower() in line.lower()
                            ][:3]
                            matches.append(f"{file}:\n" + "\n".join(lines))
                    except Exception:
                        pass
            if matches:
                return f"[search_files '{query}' in {search_path}]\n" + "\n\n".join(matches)
            return f"[search_files] No matches for '{query}' in {search_path}"

        # bridge explicit: [tool:bridge module="..." cmd="..."]
        if tool_name == "bridge":
            from core.bridge import bridge_manager
            module_id = attrs.get("module", "")
            cmd = attrs.get("cmd", "")
            args = {k: v for k, v in attrs.items() if k not in ("module", "cmd")}
            result = bridge_manager.call_module(module_id, cmd, args)
            return f"[bridge:{module_id}.{cmd}] {result}"

        # bridge auto-route: tool_name matches a registered module id
        try:
            from core.bridge import bridge_manager
            registry = bridge_manager.get_registry()
            mod = next((m for m in registry.get("modules", []) if m["id"] == tool_name), None)
            if mod:
                cmd = attrs.get("cmd", "")
                if not cmd and mod.get("available_commands"):
                    cmd = next(iter(mod["available_commands"]))
                args = {k: v for k, v in attrs.items() if k != "cmd"}
                result = bridge_manager.call_module(tool_name, cmd, args)
                return f"[{tool_name}:{cmd}] {result}"
        except Exception:
            pass

        return f"[{tool_name} ERROR] Unknown tool"
    except Exception as e:
        logger.error(f"Tool error ({tool_name}): {e}", exc_info=True)
        return f"[{tool_name} ERROR] {e}"


# ── Async streaming tool executor ─────────────────────────────────────────────

async def execute_tools_stream(
    content: str,
    workspaces: list[dict],
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Parse all [tool:...] blocks from content and execute them.

    Yields:
        {"type": "tool_start", "tool": name, "args": attrs}
        {"type": "final_cleaned", "content": cleaned_str, "results": list[str]}
    """
    blocks = parse_tool_blocks(content)
    results: list[str] = []
    cleaned = content

    for start, end, raw in reversed(blocks):
        inner = raw[6:-1].strip() if raw.endswith("]") else raw[6:].strip()
        parts = inner.split(None, 1)
        if not parts:
            continue
        tool_name = parts[0].lower()
        attrs = parse_attrs(parts[1] if len(parts) > 1 else "")

        yield {"type": "tool_start", "tool": tool_name, "args": attrs}
        result = await asyncio.to_thread(_execute_one, tool_name, attrs, workspaces)
        results.append(result)
        cleaned = cleaned.replace(raw, "")

    cleaned = cleaned.strip()
    for suffix in ['\\n}"]', '\n}"]', '}"]']:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()

    yield {"type": "final_cleaned", "content": cleaned, "results": results}


# ── Peripheral (screenshot / webcam) capture hook ────────────────────────────

def extract_peripheral_captures(
    tool_results: list[str],
    current_captures: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Scan tool results for screenshot/webcam paths.
    Returns (updated_current_captures, attachment_metadata_list).
    """
    attachments: list[dict] = []
    captures = list(current_captures)

    for res in tool_results:
        if ("Screenshot captured successfully" in res or "Webcam image captured successfully" in res) and "Saved to: " in res:
            try:
                path_line = next(line for line in res.splitlines() if "Saved to: " in line)
                media_path = path_line.replace("Saved to: ", "").strip()
                p = Path(media_path)
                if not p.exists():
                    continue
                img_bytes = p.read_bytes()
                mime_type = "image/png" if media_path.lower().endswith(".png") else "image/jpeg"
                tag = "webcam" if "webcam" in media_path else "screenshot"
                # Keep only latest of each type per turn
                captures = [c for c in captures if c.get("peripheral_type") != tag]
                captures.append({
                    "data": img_bytes,
                    "mime_type": mime_type,
                    "is_peripheral_capture": True,
                    "peripheral_type": tag,
                })
                attachments.append({
                    "filename": p.name,
                    "url": f"/api/workspace/files/content?path={media_path}",
                    "is_image": True,
                    "mime_type": mime_type,
                    "path": str(media_path),
                    "is_peripheral_capture": True,
                })
            except Exception as e:
                logger.error(f"Peripheral capture extraction failed: {e}")

    return captures, attachments
