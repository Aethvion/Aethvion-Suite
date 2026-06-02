"""
core/automate/nodes/triggers.py
Handler functions for all trigger.* node types.
"""
from __future__ import annotations

from typing import Any

from core.utils import utcnow_iso


def trigger_manual(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    # Fires the downstream chain without carrying data.
    # Returning None on "trigger" means _gather_inputs skips the value,
    # so downstream nodes don't receive spurious data from the trigger port.
    return {"trigger": None}


def trigger_schedule(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    # "trigger" fires the chain; "data" carries the ISO timestamp of execution.
    return {"trigger": None, "data": utcnow_iso()}


def trigger_webhook(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    body = inputs.get("body", {})
    return {"out": body, "body": body}


def trigger_app_event(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """
    Fires when an internal Aethvion event occurs (companion message, agent
    completion, memory write, etc.).  The event type and payload are injected
    into inputs by the scheduler service; this handler just surfaces them.
    """
    p          = node.get("properties", {})
    event_type = str(inputs.get("event_type") or p.get("event_type", "")).strip()
    source     = str(inputs.get("source", "")).strip()
    data       = inputs.get("data")
    return {
        "trigger":     None,
        "event_type":  event_type,
        "source":      source,
        "data":        data,
    }


def trigger_file_watch(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """
    In the executor, file_watch behaves like a manual trigger — it fires the
    downstream chain with the configured path and the event type that woke it.
    The actual file-system polling/inotify is handled by the scheduler service;
    this handler just surfaces whatever event info was injected into inputs.
    """
    p          = node.get("properties", {})
    watch_path = str(inputs.get("path") or p.get("path", "")).strip()
    event      = str(inputs.get("event", "modified"))   # injected by scheduler
    return {
        "trigger": None,
        "path":    watch_path,
        "event":   event,
    }
