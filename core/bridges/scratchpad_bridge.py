"""
core/bridges/scratchpad_bridge.py
Shared Brainstorming Scratchpad & Whiteboard Connector.
Allows companions and users to read, append, update, and manage
their collaborative markdown scratchpad.
"""
from typing import Optional, Dict, Any
from core.companions.engine.scratchpad import CompanionScratchpad
from core.utils import get_logger

logger = get_logger(__name__)


def _get_scratchpad(args: Optional[Dict[str, Any]] = None) -> CompanionScratchpad:
    cid = (args or {}).get("companion_id")
    if not cid:
        try:
            from core.companions.registry import CompanionRegistry
            comps = CompanionRegistry.get_all()
            cid = next(iter(comps.keys()), "misakacipher") if comps else "misakacipher"
        except Exception:
            cid = "misakacipher"

    try:
        from core.companions.registry import CompanionRegistry
        cfg = CompanionRegistry.get(cid)
        if cfg:
            return CompanionScratchpad(cfg.data_dir, cfg.name)
    except Exception:
        pass

    from core.utils.paths import COMPANIONS
    return CompanionScratchpad(COMPANIONS / cid, cid.capitalize())


def read(args: Optional[Dict[str, Any]] = None) -> str:
    """Read the current shared scratchpad. Optional arg: 'section' (str)."""
    if args is None:
        args = {}
    sp = _get_scratchpad(args)
    data = sp.load()
    content = data.get("content", "")
    section = args.get("section")

    if section and section.strip():
        sec_lower = section.strip().lower()
        lines = content.split("\n")
        in_section = False
        sec_lines = []
        for line in lines:
            line_s = line.strip()
            if line_s.startswith("## ") or line_s.startswith("### "):
                if sec_lower in line_s.lower():
                    in_section = True
                    sec_lines.append(line)
                    continue
                elif in_section:
                    break
            elif in_section:
                sec_lines.append(line)

        if sec_lines:
            return "\n".join(sec_lines).strip()
        return f"Section '{section}' not found on scratchpad. Available sections: {', '.join(data.get('sections', []))}"

    return content.strip() or "(Scratchpad is currently empty)"


def append(args: Optional[Dict[str, Any]] = None) -> str:
    """
    Append a note, idea, or task to the scratchpad.
    Args: 'text' or 'note' (str, required), optional 'section' (str, e.g. 'Ideas', 'Mechanics', 'Notes').
    """
    if args is None:
        args = {}
    text = args.get("text") or args.get("note") or args.get("query") or args.get("task") or ""
    if not text.strip():
        return "Please provide 'text' to add to the scratchpad."

    section = args.get("section")
    sp = _get_scratchpad(args)
    res = sp.append_note(text, section=section)
    return res.get("message", f"Added note: '{text}'")


def write(args: Optional[Dict[str, Any]] = None) -> str:
    """Overwrite the scratchpad content. Args: 'content' (str, required)."""
    if args is None:
        args = {}
    content = args.get("content")
    if content is None:
        return "Please provide 'content' to write to the scratchpad."
    sp = _get_scratchpad(args)
    sp.save(content)
    return "Scratchpad content updated successfully."


def list_sections(args: Optional[Dict[str, Any]] = None) -> str:
    """List available heading sections in the scratchpad."""
    sp = _get_scratchpad(args)
    sections = sp.get_sections()
    if not sections:
        return "No sections defined yet on the scratchpad."
    return "Scratchpad sections:\n" + "\n".join(f"- {s}" for s in sections)


def clear(args: Optional[Dict[str, Any]] = None) -> str:
    """Reset scratchpad to default template."""
    sp = _get_scratchpad(args)
    sp.clear(reset_template=True)
    return "Reset scratchpad to default template."
