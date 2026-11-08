"""
core/bridges/visual_memory_bridge.py
Visual Context Memory Bridge Connector.
Allows companions to snapshot, index, recall, and compare visual layouts
(Unity projects, Blender 3D models, code architectures, UI designs) across days.
"""
from pathlib import Path
from typing import Any, Dict, Optional
from core.companions.engine.visual_memory import CompanionVisualMemory
from core.utils import get_logger

logger = get_logger(__name__)


def _get_visual_memory(args: Optional[Dict[str, Any]] = None) -> CompanionVisualMemory:
    cid = (args or {}).get("companion_id")
    if not cid:
        try:
            from core.companions.registry import CompanionRegistry
            comps = CompanionRegistry.list_companions()
            cid = comps[0].id if comps else "misakacipher"
        except Exception:
            cid = "misakacipher"

    try:
        from core.companions.registry import CompanionRegistry
        cfg = CompanionRegistry.get_companion(cid)
        if cfg:
            return CompanionVisualMemory(cfg.data_dir, cfg.name)
    except Exception:
        pass

    from core.utils.paths import COMPANIONS
    return CompanionVisualMemory(COMPANIONS / cid, cid.capitalize())


def remember_screen(args: Optional[Dict[str, Any]] = None) -> str:
    """
    Capture the active screen or monitor and store it as a long-term visual memory.
    Args:
        title (str): Title or label for what is on screen (e.g. 'Unity Main Level Hierarchy', 'Blender Cyber Katana Hilt').
        category (str): 'unity', 'blender', 'code', 'ui', 'reference', or 'general'.
        description / notes (str): What is visible, layout arrangement, components, or issues.
        key_elements (list/str): Important landmarks, objects, or UI panels.
        monitor (int): Monitor index (0=all, 1=primary, 2=secondary).
        image_path (str, optional): Path to existing screenshot/image if already taken.
    """
    if args is None:
        args = {}

    title = args.get("title") or args.get("name") or "Visual Snapshot"
    category = args.get("category") or "general"
    description = args.get("description") or args.get("notes") or args.get("details") or ""
    
    key_elems = args.get("key_elements") or args.get("elements") or []
    if isinstance(key_elems, str):
        key_elems = [e.strip() for e in key_elems.split(",") if e.strip()]

    monitor = 0
    if "monitor" in args:
        try:
            monitor = int(args["monitor"])
        except (ValueError, TypeError):
            monitor = 0

    img_path = args.get("image_path")
    vmem = _get_visual_memory(args)
    res = vmem.remember(
        title=title,
        category=category,
        description=description,
        key_elements=key_elems,
        image_path=img_path,
        monitor=monitor,
        source="bridge_connector"
    )

    if res.get("error"):
        return f"Visual Memory Error: {res['error']}"

    entry = res.get("memory", {})
    file_p = res.get("file_path", "")
    elems_str = f"\nKey Elements: {', '.join(entry.get('key_elements', []))}" if entry.get("key_elements") else ""
    desc_str = f"\nNotes: {entry.get('description')}" if entry.get("description") else ""

    return (
        f"Visual Memory Snapshot recorded successfully!\n"
        f"Title: {entry.get('title')}\n"
        f"Category: {entry.get('category').upper()}\n"
        f"Saved to: {file_p}\n"
        f"Resolution: {entry.get('width')}x{entry.get('height')}\n"
        f"Timestamp: {entry.get('human_time')}{elems_str}{desc_str}"
    )


def recall(args: Optional[Dict[str, Any]] = None) -> str:
    """
    Recall and search past visual memories by keyword or category.
    Args:
        query (str): Search keywords (e.g. 'unity level', 'blender model', 'katana').
        category (str): Optional category filter ('unity', 'blender', 'code', 'ui', etc.).
        limit (int): Maximum memories to return (default 4).
    """
    if args is None:
        args = {}

    query = args.get("query") or args.get("search") or args.get("terms") or ""
    category = args.get("category")
    limit = int(args.get("limit", 4))

    vmem = _get_visual_memory(args)
    results = vmem.search(query=query, category=category, limit=limit)

    if not results:
        loaded = vmem.load()
        total = loaded.get("total", 0)
        if total == 0:
            return "No visual memories recorded yet. Use 'remember_screen' to snapshot and remember visual layouts!"
        return f"No visual memories matching '{query}'. Total visual memories on file: {total}."

    lines = [f"Found {len(results)} matching visual context memories:"]
    for idx, m in enumerate(results, start=1):
        t = m.get("title", "Untitled")
        cat = m.get("category", "general").upper()
        ht = m.get("human_time", m.get("timestamp", ""))
        desc = m.get("description", "No description recorded.")
        elems = m.get("key_elements", [])
        elems_part = f" | Elements: {', '.join(elems)}" if elems else ""
        lines.append(f"{idx}. [{cat}] {t} ({ht}){elems_part}\n   Details: {desc}\n   File: {m.get('image_path')}")

    return "\n\n".join(lines)


def compare(args: Optional[Dict[str, Any]] = None) -> str:
    """
    Compare current screen layout with a past visual memory.
    Args:
        query (str): Keyword to match past memory (e.g. 'unity yesterday', 'blender model').
        memory_id (str, optional): Exact memory ID if known.
        monitor (int): Current monitor to capture (default 0).
    """
    if args is None:
        args = {}

    query = args.get("query") or args.get("title") or ""
    mem_id = args.get("memory_id")
    monitor = 0
    if "monitor" in args:
        try:
            monitor = int(args["monitor"])
        except (ValueError, TypeError):
            monitor = 0

    vmem = _get_visual_memory(args)
    res = vmem.compare(memory_id=mem_id, query=query, monitor=monitor)

    if res.get("error"):
        return f"Comparison Error: {res['error']}"

    ref = res.get("reference_memory", {})
    curr_path = res.get("current_image_path", "")
    ref_path = res.get("reference_image_path", "")

    elems = ref.get("key_elements", [])
    elems_part = f"\nPast Key Elements: {', '.join(elems)}" if elems else ""

    return (
        f"Visual Context Comparison ready!\n"
        f"Reference Past Memory: {ref.get('title')} ({ref.get('category').upper()})\n"
        f"Recorded on: {ref.get('human_time')}\n"
        f"Past Description: {ref.get('description')}{elems_part}\n"
        f"Past Reference Image: {ref_path}\n"
        f"Current Screen Captured: {curr_path}\n"
        f"Saved to: {curr_path}\n"
        f"Inspect the current screen and compare it with the reference layout described above."
    )


def list_memories(args: Optional[Dict[str, Any]] = None) -> str:
    """
    List stored visual memories.
    Optional args: category (str), limit (int).
    """
    if args is None:
        args = {}

    vmem = _get_visual_memory(args)
    loaded = vmem.load()
    memories = loaded.get("memories", [])
    if not memories:
        return "No visual memories recorded yet."

    cat = args.get("category")
    if cat:
        memories = [m for m in memories if m.get("category", "").lower() == cat.lower()]

    limit = int(args.get("limit", 6))
    memories = memories[:limit]

    lines = [f"Stored Visual Memories ({len(memories)} shown):"]
    for m in memories:
        lines.append(
            f"- [{m.get('category', 'general').upper()}] {m.get('title')} ({m.get('human_time')})\n"
            f"  ID: {m.get('id')} | File: {m.get('filename')}"
        )
    return "\n".join(lines)
