"""
core/companions/engine/streaming.py
Stream-time text utilities shared by all companions.
"""
from __future__ import annotations
from typing import Optional


def build_bridges_capabilities(capabilities: dict | None = None, profile_id: Optional[str] = None) -> str:
    """
    Read the live bridge/connector registry and return a formatted capabilities block
    suitable for injection into a companion's system prompt, filtered by global state
    and the active Connector Profile.
    """
    if capabilities is None:
        capabilities = {}
    eff_profile = profile_id or capabilities.get("connector_profile") or "full_local"
    try:
        from core.bridges import bridge_manager
        registry = bridge_manager.get_registry()
        modules = registry.get("modules", [])
        if not modules:
            return ""
        lines = [
            "CONNECTOR / BRIDGE CAPABILITIES — LIVE REAL-TIME TOOLS:",
            "You have direct access to the user's PC, desktop environment, and external services via the Aethvion Connectors listed below.",
            "When the user asks a question or makes a request that can be answered by any of these connectors "
            "(e.g. what is currently open on their PC, active window, screen content/OCR, clipboard, git status/diff, GPU/processes, hardware telemetry, media playing, weather, web search, webpage URLs, YouTube videos, Reddit, or reminders/tasks), "
            "you MUST call the connector by outputting its tool tag:",
            '  [tool:bridge module="<module_id>" cmd="<command>" <optional_arg>="<value>"]',
            "CRITICAL RULES FOR CONNECTOR CALLS:",
            "- NEVER say you do not have access to the user's computer, OS, or real-time data if a connector below provides it. Emit the [tool:bridge ...] tag instead!",
            "- When you need a connector's data to answer, output ONLY the [tool:bridge ...] tag (you may chain multiple tags if needed) and stop; the system will immediately execute the connector(s) and feed the live results back to you so you can write your final response.",
            ""
        ]
        visible = False
        for mod in modules:
            mod_id = mod.get("id", "?")

            # Check global enabled state + Connector Profile permission
            allowed, _ = bridge_manager.is_module_allowed(mod_id, eff_profile)
            if not allowed:
                continue

            # Skip modules gated behind a capability the companion doesn't have
            gate = mod.get("capability_gate")
            if gate and capabilities and not capabilities.get(gate, True):
                continue

            mod_name = mod.get("name", mod_id)
            mod_desc = mod.get("description", "")
            requires_auth = mod.get("requires_auth", False)
            is_authorized = mod.get("is_authorized", True)
            commands = mod.get("available_commands", {})
            auth_note = ""
            if requires_auth and not is_authorized:
                auth_note = " [NOT AUTHORIZED — do NOT attempt to call this module]"
            elif requires_auth:
                auth_note = " [authorized]"
            lines.append(f"  Module: {mod_id} ({mod_name}){auth_note} — {mod_desc}")
            for cmd, desc in commands.items():
                lines.append(f'    → [tool:bridge module="{mod_id}" cmd="{cmd}"] — {desc}')
            visible = True
        if not visible:
            return ""
        lines.append('  Example (check open windows/apps): [tool:bridge module="window_focus" cmd="get_active_window"]')
        lines.append('  Example (capture screenshot): [tool:bridge module="screen_capture" cmd="take_screenshot"]')
        return "\n".join(lines)
    except Exception:
        return ""
