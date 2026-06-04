"""
core/automate/nodes/ui.py
Execution handlers for ui.* interactive interface nodes.
"""
from __future__ import annotations

from typing import Any


def ui_button(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Trigger node corresponding to a button click in custom interfaces."""
    return {}


def ui_input_text(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Retrieve text input value, checking ctx._vars first (seeded from API call)."""
    p       = node.get("properties", {})
    nid     = node.get("id", "")
    name    = str(p.get("name", nid)).strip() or nid
    default = str(p.get("value", ""))

    val             = str(ctx._vars.get(name, default))
    ctx._vars[name] = val
    return {"out": val}


def ui_input_number(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Retrieve numeric input value."""
    p       = node.get("properties", {})
    nid     = node.get("id", "")
    name    = str(p.get("name", nid)).strip() or nid
    default = p.get("value", 0)

    raw = ctx._vars.get(name, default)
    try:
        val = float(raw)
    except (ValueError, TypeError):
        val = 0.0

    ctx._vars[name] = val
    return {"out": val}


def ui_input_toggle(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Retrieve boolean toggle value."""
    p       = node.get("properties", {})
    nid     = node.get("id", "")
    name    = str(p.get("name", nid)).strip() or nid
    default = p.get("value", False)

    raw = ctx._vars.get(name, default)
    if isinstance(raw, str):
        val = raw.lower() in ("true", "1", "yes")
    else:
        val = bool(raw)

    ctx._vars[name] = val
    return {"out": val}


def ui_display_text(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Pass input text to the UI display card."""
    return {"_display": inputs.get("in", "")}


def ui_display_image(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Pass input image URL/base64 to the UI image container."""
    return {"_display_image": inputs.get("in", "")}
