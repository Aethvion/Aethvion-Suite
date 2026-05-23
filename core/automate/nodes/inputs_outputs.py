"""
core/automate/nodes/inputs_outputs.py
══════════════════════════════════════
Handler functions for input.* and output.* node types.
"""
from __future__ import annotations

from typing import Any


def input_text(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p = node.get("properties", {})
    return {"out": str(p.get("value", ""))}


def input_number(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p = node.get("properties", {})
    try:
        return {"out": float(p.get("value", 0))}
    except (ValueError, TypeError):
        return {"out": 0.0}


def output_display(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    # "_display" prefix is used by the executor summary to skip this port
    # when building the log preview, but the frontend reads it for the display node.
    return {"_display": inputs.get("in", "")}
