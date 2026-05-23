"""
core/automate/nodes/triggers.py
════════════════════════════════
Handler functions for all trigger.* node types.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def trigger_manual(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    # Fires the downstream chain without carrying data.
    # Returning None on "trigger" means _gather_inputs skips the value,
    # so downstream nodes don't receive spurious data from the trigger port.
    return {"trigger": None}


def trigger_schedule(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    # "trigger" fires the chain; "data" carries the ISO timestamp of execution.
    return {"trigger": None, "data": datetime.now().isoformat()}


def trigger_webhook(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    body = inputs.get("body", {})
    return {"out": body, "body": body}
