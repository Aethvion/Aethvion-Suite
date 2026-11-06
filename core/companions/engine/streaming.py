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
            'CONNECTOR / BRIDGE CAPABILITIES — use [tool:bridge module="<id>" cmd="<command>" ...] syntax:'
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
            if gate and not capabilities.get(gate, True):
                continue

            mod_name = mod.get("name", mod_id)
            requires_auth = mod.get("requires_auth", False)
            is_authorized = mod.get("is_authorized", True)
            commands = mod.get("available_commands", {})
            auth_note = ""
            if requires_auth and not is_authorized:
                auth_note = " [NOT AUTHORIZED — do NOT attempt to call this module]"
            elif requires_auth:
                auth_note = " [authorized]"
            lines.append(f"  Module: {mod_id} ({mod_name}){auth_note}")
            for cmd, desc in commands.items():
                lines.append(f'    → cmd="{cmd}" — {desc}')
            visible = True
        if not visible:
            return ""
        lines.append('  Example: [tool:bridge module="screen_capture" cmd="take_screenshot"]')
        return "\n".join(lines)
    except Exception:
        return ""
