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
            "- TWITCH LIVE STREAMS & INLINE EMBEDS: You CAN check and show Twitch streams in the chat! Use [tool:bridge module=\"twitch_link\" cmd=\"get_channel\" channel=\"<login>\"] to check if a streamer is live, cmd=\"search_streams\" query=\"...\" to find live channels, or cmd=\"get_top_streams\" game=\"...\" for popular streams. Include the https://www.twitch.tv/<channel> URL in your reply — the chat UI renders an interactive Twitch card with an embedded live player. Only claim a streamer is live if the connector says so.",
            "- SPOTIFY EMBEDS & MEDIA CONTROLS: When the user asks you to play, search, pause, skip, or queue music on Spotify (e.g. 'play random rock', 'play Stay with Me by Miki Matsubara', 'pause music', 'what is playing?'), you MUST actually output the tool tag:",
            "    To play/search a song: [tool:bridge module=\"spotify\" cmd=\"play\" target=\"<song, artist, or genre>\"]",
            "    To check current track: [tool:bridge module=\"spotify\" cmd=\"get_current\"]",
            "    To pause playback: [tool:bridge module=\"spotify\" cmd=\"pause\"]",
            "    To skip to next: [tool:bridge module=\"spotify\" cmd=\"skip\"]",
            "    To go to previous: [tool:bridge module=\"spotify\" cmd=\"previous\"]",
            "    To queue a song: [tool:bridge module=\"spotify\" cmd=\"queue\" target=\"<song name>\"]",
            "  PLAYABLE SPOTIFY INLINE CARDS: When you play or recommend a song, album, or playlist, include its full Spotify link (e.g. https://open.spotify.com/track/...) in your reply — the chat UI automatically embeds a fully interactive, playable Spotify player card right inside your message bubble!",
            "- SHARED SCRATCHPAD & BRAINSTORMING CANVAS: You have a live co-working scratchpad/whiteboard shared with Marcel! When Marcel says 'write this down', 'add this to scratchpad/notes', or when you agree on an idea or mechanic, you MUST actually output the tool tag [tool:bridge module=\"scratchpad\" cmd=\"append\" text=\"<idea or mechanic>\" section=\"<Ideas | Mechanics | Notes>\"]. NEVER output a markdown code block pretending that you wrote it to the scratchpad—always execute the real tool tag so it actually writes to the file on disk! You can also read it anytime with [tool:bridge module=\"scratchpad\" cmd=\"read\"].",
            "- NEVER SIMULATE OR HALLUCINATE ACTIONS: Never pretend or tell the user 'I have sent the command', 'I am playing this now', or 'I added this to the scratchpad' in plain text, and NEVER output a fake markdown code block in place of an action without actually emitting the [tool:bridge ...] tag in that turn! If an action is requested, you MUST emit the real [tool:bridge ...] tag so the system executes it.",
            "- When you need a connector's data or action to answer, output the [tool:bridge ...] tag; the system will execute the connector and feed the live results back to you so you can write your response.",
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
