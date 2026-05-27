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

from . import (
    actions, aethviondb, ai, data, globals as global_nodes,
    inputs_outputs, integrations, logic, media, memory, triggers,
)

# ── Handler registry ──────────────────────────────────────────────────────────

_REGISTRY: dict[str, Callable] = {

    # Triggers ─────────────────────────────────────────────────────────────────
    "trigger.app_event":  triggers.trigger_app_event,
    "trigger.file_watch": triggers.trigger_file_watch,
    "trigger.manual":     triggers.trigger_manual,
    "trigger.schedule":   triggers.trigger_schedule,
    "trigger.webhook":    triggers.trigger_webhook,

    # Logic ────────────────────────────────────────────────────────────────────
    "logic.delay":     logic.logic_delay,
    "logic.if":        logic.logic_if,
    "logic.loop":      logic.logic_loop,
    "logic.merge":     logic.logic_merge,
    "logic.repeat":    logic.logic_repeat,
    "logic.switch":    logic.logic_switch,
    "logic.try_catch": logic.logic_try_catch,

    # Global — public workflow parameters ─────────────────────────────────────
    "global.text":      global_nodes.global_text,
    "global.number":    global_nodes.global_number,
    "global.toggle":    global_nodes.global_toggle,
    "global.database":  global_nodes.global_database,
    "global.snapshot":  global_nodes.global_snapshot,

    # Data ─────────────────────────────────────────────────────────────────────
    "data.csv_parse":     data.data_csv_parse,
    "data.extract_json":  data.data_extract_json,
    "data.filter":        data.data_filter,
    "data.format_text":   data.data_format_text,
    "data.list_item":     data.data_list_item,
    "data.merge_objects": data.data_merge_objects,
    "data.parse_json":    data.data_parse_json,
    "data.regex":         data.data_regex,
    "data.set_variable":  data.data_set_variable,
    "data.split_text":    data.data_split_text,
    "data.template":      data.data_template,
    "data.type_convert":  data.data_type_convert,
    "transform.combine":  data.transform_combine,

    # Actions ──────────────────────────────────────────────────────────────────
    "action.camera_capture": media.action_camera_capture,
    "action.clipboard":      actions.action_clipboard,
    "action.file_list":      actions.action_file_list,
    "action.file_read":      actions.action_file_read,
    "action.file_write":     actions.action_file_write,
    "action.http":           actions.action_http,
    "action.log":            actions.action_log,
    "action.notify":         actions.action_notify,
    "action.ocr":            media.action_ocr,
    "action.run_agent":      actions.action_run_agent,
    "action.run_command":    actions.action_run_command,
    "action.run_script":     actions.action_run_script,
    "action.screenshot":     media.action_screenshot,
    "action.web_scrape":     actions.action_web_scrape,

    # AI ───────────────────────────────────────────────────────────────────────
    "ai.analyze_image":   media.ai_analyze_image,
    "ai.any":             ai.ai_model,
    "ai.classify":        ai.ai_classify,
    "ai.extract_data":    ai.ai_extract_data,
    "ai.generate_image":  media.ai_generate_image,
    "ai.google":          ai.ai_model,
    "ai.speech_to_text":  media.ai_speech_to_text,
    "ai.summarize":       ai.ai_summarize,
    "ai.text_to_speech":  media.ai_text_to_speech,

    # Memory ───────────────────────────────────────────────────────────────────
    "memory.retrieve":        memory.memory_retrieve,
    "memory.search_semantic": memory.memory_search_semantic,
    "memory.store":           memory.memory_store,

    # Inputs ───────────────────────────────────────────────────────────────────
    "input.file":   inputs_outputs.input_file,
    "input.list":   inputs_outputs.input_list,
    "input.number": inputs_outputs.input_number,
    "input.text":   inputs_outputs.input_text,

    # Outputs ──────────────────────────────────────────────────────────────────
    "output.clipboard": inputs_outputs.output_clipboard,
    "output.display":   inputs_outputs.output_display,
    "output.file":      inputs_outputs.output_file,

    # AethvionDB — search ───────────────────────────────────────────────────────
    "aethviondb.search":                    aethviondb.aethviondb_search,
    "aethviondb.semantic_search":           aethviondb.aethviondb_semantic_search,
    "aethviondb.snapshot_search":           aethviondb.aethviondb_snapshot_search,
    "aethviondb.snapshot_semantic_search":  aethviondb.aethviondb_snapshot_semantic_search,
    # AethvionDB — database ─────────────────────────────────────────────────────
    "aethviondb.create_database":    aethviondb.aethviondb_create_database,
    "aethviondb.get_stats":          aethviondb.aethviondb_get_stats,
    # AethvionDB — entity CRUD ──────────────────────────────────────────────────
    "aethviondb.list_entities":      aethviondb.aethviondb_list_entities,
    "aethviondb.get_entity":         aethviondb.aethviondb_get_entity,
    "aethviondb.create_entity":      aethviondb.aethviondb_create_entity,
    "aethviondb.update_entity":      aethviondb.aethviondb_update_entity,
    "aethviondb.delete_entity":      aethviondb.aethviondb_delete_entity,
    # AethvionDB — AI operations ────────────────────────────────────────────────
    "aethviondb.distill":            aethviondb.aethviondb_distill,
    "aethviondb.expand_entity":      aethviondb.aethviondb_expand_entity,
    "aethviondb.deepen_entity":      aethviondb.aethviondb_deepen_entity,
    # AethvionDB — snapshots ────────────────────────────────────────────────────
    "aethviondb.create_snapshot":    aethviondb.aethviondb_create_snapshot,
    "aethviondb.list_snapshots":     aethviondb.aethviondb_list_snapshots,
    # AethvionDB — maintenance ──────────────────────────────────────────────────
    "aethviondb.validate":           aethviondb.aethviondb_validate,
    "aethviondb.generate_vectors":   aethviondb.aethviondb_generate_vectors,
    "companion.ask":              integrations.companion_ask,
    "integration.discord":  integrations.integration_discord,
    "integration.email":    integrations.integration_email,
    "integration.slack":    integrations.integration_slack,

}


def get_handler(node_type: str) -> Callable | None:
    """Return the handler for *node_type*, or None if unregistered."""
    return _REGISTRY.get(node_type)


def registered_types() -> list[str]:
    """Return all registered node type strings (useful for debugging)."""
    return sorted(_REGISTRY.keys())
