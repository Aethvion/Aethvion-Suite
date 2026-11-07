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
            "CONNECTOR / BRIDGE CAPABILITIES — ON-DEMAND REAL-TIME TOOLS:",
            "You have access to the user's PC, desktop environment, and external services via the Aethvion Connectors listed below.",
            "When the user asks a question or makes a request that requires live data from any of these connectors "
            "(e.g. asking what is open on their PC, checking their screen/OCR, clipboard, git status/diff, GPU/processes, hardware telemetry, media playing, weather, web search, webpage URLs, YouTube videos, Reddit, or reminders/tasks), "
            "call the connector by outputting its tool tag:",
            '  [tool:bridge module="<module_id>" cmd="<command>" <optional_arg>="<value>"]',
            "RULES FOR CONNECTOR USAGE:",
            "- ON-DEMAND ONLY: These connectors are capabilities you CAN use when relevant or requested—do NOT call them or bring up PC telemetry/open apps in normal conversation when the user hasn't asked about them.",
            "- NEVER CLAIM LACK OF ACCESS: When the user DOES ask about their PC, open windows, screen, clipboard, git, or live info, never say you lack access—emit the matching [tool:bridge ...] tag instead!",
            "- FILTER OUTPUT NATURALLY: When a connector returns data, focus only on what is relevant to the user's question rather than reciting every background process, tab, or hardware metric.",
            "- YOUTUBE RECOMMENDATIONS & INLINE EMBEDS: You CAN show and embed YouTube videos directly in the chat! When the user asks for a YouTube video, song, or recommendation, call [tool:bridge module=\"youtube_link\" cmd=\"search_videos\" query=\"<search terms>\"] to get real YouTube watch URLs, and include the full https://www.youtube.com/watch?v=... URL in your reply — the chat UI automatically renders an interactive YouTube video card and playable embed right inside your message bubble!",
            "- When you need a connector's data to answer, output ONLY the [tool:bridge ...] tag and stop; the system will execute the connector and feed the live results back to you so you can write your response.",
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
