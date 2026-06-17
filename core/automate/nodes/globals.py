"""
core/automate/nodes/globals.py
Handlers for Global (public-variable) workflow nodes.

Global nodes are the *public interface* of a compiled workflow.  Every
global.* node:
  • Exposes its configured value as a named API parameter when the
    workflow is called programmatically or run from a compiled bundle.
  • Falls back to the node's default value when no injected value is
    present.
  • Writes the resolved value back into ctx._vars so template/format
    nodes can reference it by name.

All global nodes share the same ctx._vars injection pattern:
    1. Check ctx._vars[name]   (injected at runtime by API caller)
    2. Fall back to node's 'value' property
    3. Write resolved value back to ctx._vars[name]
    4. Return {"out": value}
"""
from __future__ import annotations

from typing import Any



# global.text

def global_text(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Expose a text string as a named workflow parameter."""
    p       = node.get("properties", {})
    name    = str(p.get("name",  "text")).strip() or "text"
    default = str(p.get("value", ""))

    val             = str(ctx._vars.get(name, default))
    ctx._vars[name] = val
    return {"out": val}


# global.number

def global_number(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Expose a numeric value as a named workflow parameter."""
    p       = node.get("properties", {})
    name    = str(p.get("name",  "number")).strip() or "number"
    default = p.get("value", 0)

    raw = ctx._vars.get(name, default)
    try:
        s   = str(raw)
        val = float(s) if "." in s else int(s)
    except (ValueError, TypeError):
        val = 0

    ctx._vars[name] = val
    return {"out": val}


# global.toggle

def global_toggle(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Expose a boolean flag as a named workflow parameter."""
    p       = node.get("properties", {})
    name    = str(p.get("name",  "flag")).strip() or "flag"
    default = p.get("value", False)

    raw = ctx._vars.get(name, default)
    if isinstance(raw, str):
        val = raw.lower() in ("true", "1", "yes")
    else:
        val = bool(raw)

    ctx._vars[name] = val
    return {"out": val}


# global.database

def global_database(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Expose an AethvionDB database name as a named workflow parameter.

    Connect the *out* port to the *database* input port of any
    AethvionDB node to drive all of them from one place.
    """
    p       = node.get("properties", {})
    name    = str(p.get("name",  "database")).strip() or "database"
    default = str(p.get("value", "default"))

    val             = str(ctx._vars.get(name, default)) or "default"
    ctx._vars[name] = val
    return {"out": val}


# global.snapshot

def global_snapshot(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Expose an AethvionDB snapshot name as a named workflow parameter.

    Connect the *out* port to the *snapshot* input port of any
    AethvionDB snapshot node.
    """
    p       = node.get("properties", {})
    name    = str(p.get("name",  "snapshot")).strip() or "snapshot"
    default = str(p.get("value", ""))

    val             = str(ctx._vars.get(name, default))
    ctx._vars[name] = val
    return {"out": val}
