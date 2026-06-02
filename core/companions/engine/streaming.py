"""
core/companions/engine/streaming.py
═════════════════════════════════════
Stream-time text utilities shared by all companions.
"""
from __future__ import annotations
import re





def build_bridges_capabilities(capabilities: dict | None = None) -> str:
    """
    Read the live bridge registry and return a formatted capabilities block
    suitable for injection into a companion's system prompt.

    Args:
        capabilities: The companion's capabilities dict.  Modules whose
                      ``capability_gate`` key names a capability that is not
                      enabled (falsy) in this dict are excluded from the block.
                      Pass None / omit to include all authorised modules.

    Returns empty string if bridge is unavailable or has no visible modules.
    """
    if capabilities is None:
        capabilities = {}
    try:
        from core.bridges import bridge_manager
        registry = bridge_manager.get_registry()
        modules = registry.get("modules", [])
        if not modules:
            return ""
        lines = [
            'BRIDGE CAPABILITIES — use [tool:bridge module="<id>" cmd="<command>" ...] syntax:'
        ]
        visible = False
        for mod in modules:
            # Skip modules gated behind a capability the companion doesn't have
            gate = mod.get("capability_gate")
            if gate and not capabilities.get(gate):
                continue

            mod_id = mod.get("id", "?")
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

