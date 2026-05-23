"""
core/automate/nodes/__init__.py
════════════════════════════════
Node handler registry for the Automate workflow executor.

Each entry maps a node type string to a handler function with signature:
    (node: dict, inputs: dict, ctx: WorkflowExecutor) -> dict

To add a new node type:
  1. Add its definition to _NODE_TYPES in automate_routes.py
  2. Add the handler function to the appropriate category file in this package
  3. Register it in _REGISTRY below — one line, alphabetically within its group
"""
from __future__ import annotations

from typing import Callable

from . import actions, ai, data, inputs_outputs, logic, memory, triggers

# ── Handler registry ──────────────────────────────────────────────────────────

_REGISTRY: dict[str, Callable] = {

    # Triggers ─────────────────────────────────────────────────────────────────
    "trigger.manual":   triggers.trigger_manual,
    "trigger.schedule": triggers.trigger_schedule,
    "trigger.webhook":  triggers.trigger_webhook,

    # Logic ────────────────────────────────────────────────────────────────────
    "logic.delay":     logic.logic_delay,
    "logic.if":        logic.logic_if,
    "logic.loop":      logic.logic_loop,
    "logic.merge":     logic.logic_merge,
    "logic.switch":    logic.logic_switch,
    "logic.try_catch": logic.logic_try_catch,

    # Data ─────────────────────────────────────────────────────────────────────
    "data.extract_json":  data.data_extract_json,
    "data.filter":        data.data_filter,
    "data.format_text":   data.data_format_text,
    "data.parse_json":    data.data_parse_json,
    "data.regex":         data.data_regex,
    "data.set_variable":  data.data_set_variable,
    "data.split_text":    data.data_split_text,
    "data.template":      data.data_template,
    "data.type_convert":  data.data_type_convert,
    "transform.combine":  data.transform_combine,

    # Actions ──────────────────────────────────────────────────────────────────
    "action.clipboard":  actions.action_clipboard,
    "action.file_read":  actions.action_file_read,
    "action.file_write": actions.action_file_write,
    "action.http":       actions.action_http,
    "action.log":        actions.action_log,
    "action.notify":     actions.action_notify,
    "action.run_script": actions.action_run_script,

    # AI ───────────────────────────────────────────────────────────────────────
    "ai.any":          ai.ai_model,
    "ai.classify":     ai.ai_classify,
    "ai.extract_data": ai.ai_extract_data,
    "ai.google":       ai.ai_model,
    "ai.summarize":    ai.ai_summarize,

    # Memory ───────────────────────────────────────────────────────────────────
    "memory.retrieve": memory.memory_retrieve,
    "memory.store":    memory.memory_store,

    # Inputs ───────────────────────────────────────────────────────────────────
    "input.file":   inputs_outputs.input_file,
    "input.list":   inputs_outputs.input_list,
    "input.number": inputs_outputs.input_number,
    "input.text":   inputs_outputs.input_text,

    # Outputs ──────────────────────────────────────────────────────────────────
    "output.clipboard": inputs_outputs.output_clipboard,
    "output.display":   inputs_outputs.output_display,
    "output.file":      inputs_outputs.output_file,

    # Data (Sprint 3) ──────────────────────────────────────────────────────────
    "data.list_item":     data.data_list_item,
    "data.merge_objects": data.data_merge_objects,

}


def get_handler(node_type: str) -> Callable | None:
    """Return the handler for *node_type*, or None if unregistered."""
    return _REGISTRY.get(node_type)


def registered_types() -> list[str]:
    """Return all registered node type strings (useful for debugging)."""
    return sorted(_REGISTRY.keys())
