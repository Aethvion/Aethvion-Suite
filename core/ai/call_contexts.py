"""
core/ai/call_contexts.py
════════════════════════
Aethvion Suite — AI Call Context Registry
==========================================

SINGLE SOURCE OF TRUTH for every AI call mode in the suite.

Rules
─────
  • Import CallSource constants instead of writing source strings directly.
  • Import system-prompt builders from here instead of building them inline.
  • Never call pm.call_with_failover() without passing a source= from CallSource.
  • If you add a new feature that calls the AI, add an entry here first.

Call-mode overview
──────────────────

  CHAT            Orchestrator path — intent analysis → agent plan or direct LLM.
                  System prompt:  built by the orchestrator / PersonaManager.
                  Context:        neutral, NO Misaka persona injected at call-site level.
                  Entry point:    master_orchestrator.process_message()

  COMPANION       Floating Misaka assistant widget (direct provider call, no orchestrator).
                  System prompt:  _build_companion_prompt() — Misaka identity + system stats.
                  Context:        Misaka persona, system stats, assistant tools, emotions.
                  Entry point:    assistant_routes.POST /api/assistant/chat

  DISCORD         Discord bot messages routed through the orchestrator.
                  System prompt:  PersonaManager.build_system_prompt()
                  Context:        Full Misaka persona with memories, time context, tools.
                  Entry point:    master_orchestrator._execute_persona_chat()

  MISAKA_CIPHER   Misaka Cipher synthesis pipeline routed through the orchestrator.
                  System prompt:  PersonaManager.build_system_prompt()
                  Context:        Full Misaka persona with memories, time context, tools.
                  Entry point:    master_orchestrator._execute_persona_chat()

  OVERLAY         Desktop overlay "Ask about screen" (direct provider call, no orchestrator).
                  System prompt:  build_overlay_prompt() — screen-analysis only.
                  Context:        Screen analysis only. NO persona. NO memories. NO tools.
                  Entry point:    overlay_routes.POST /api/overlay/ask

  AGENT           Software engineering agent tasks (direct streaming call, no orchestrator).
                  System prompt:  agent_runner.SYSTEM_PROMPT — engineering expert.
                  Context:        Engineering actions only. NO persona. NO memories.
                  Entry point:    agent_runner.AgentRunner._call_llm()

  ARENA           Model battle / blind comparison (direct provider call).
                  System prompt:  arena_routes.ARENA_SYSTEM_PROMPT — neutral competitor.
                  Context:        Neutral evaluation. NO persona. NO tools.
                  Entry point:    arena_routes._call_model()

  GAME            In-game AI logic (direct provider call).
                  System prompt:  game state specific — set by games_routes.
                  Context:        Game logic only. NO persona.
                  Entry point:    games_routes._llm_call()

  SCHEDULE        Scheduled-task chat (direct provider call).
                  System prompt:  schedule_routes._SYSTEM_PROMPT — task context.
                  Context:        Task description only. NO persona.
                  Entry point:    schedule_routes.POST /api/schedule/{id}/chat

  RESEARCH        Research board analysis (direct provider call).
                  System prompt:  user-provided or empty.
                  Context:        User-provided only. NO persona.
                  Entry point:    research_board_routes / advanced_aiconv_routes

  AICONV          Legacy AI-conversation endpoint (direct provider call).
                  System prompt:  user-provided or empty.
                  Context:        User-provided only. NO persona.
                  Entry point:    arena_routes (legacy) / advanced_aiconv_routes

  EXTERNAL_API    OpenAI-compatible external API (direct provider call).
                  System prompt:  whatever the external caller sends — full passthrough.
                  Context:        External caller's context only.
                  Entry point:    external_api_routes.POST /v1/chat/completions

  MODEL_INFO      Model compatibility info extraction (direct provider call).
                  System prompt:  hardware-aware context built in registry_routes.
                  Context:        Hardware specs + model metadata only. NO persona.
                  Entry point:    registry_routes.POST /api/registry/local/model-info-query

  AUTO_ROUTER     Internal auto-routing decision call (recursive call inside ProviderManager).
                  System prompt:  routing decision prompt — internal only.
                  Context:        Candidate model list + user prompt fragment only.
                  Entry point:    provider_manager.call_with_failover() AUTO branch
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from core.utils.logger import get_logger

logger = get_logger(__name__)

# ── Canonical source identifiers ──────────────────────────────────────────────

class CallSource:
    """
    All valid source= values for call_with_failover / call_with_failover_stream.

    Always use these constants. Never write the string directly at a call site.

    Example
    -------
    from core.ai.call_contexts import CallSource

    pm.call_with_failover(
        prompt=...,
        trace_id=...,
        source=CallSource.OVERLAY,
        system_prompt=build_overlay_prompt(),
    )
    """
    # ── Orchestrator-routed modes ──────────────────────────────────────────
    CHAT          = "chat"            # Main chat — intent analysis path
    DISCORD       = "discord"         # Discord bot → persona chat path
    MISAKA_CIPHER = "misakacipher"    # Misaka Cipher synthesis → persona chat path

    # ── Direct-call modes (bypass orchestrator) ───────────────────────────
    COMPANION     = "companion"       # Floating Misaka assistant widget
    OVERLAY       = "overlay"         # Desktop overlay screen Q&A
    AGENT         = "agent"           # Software engineering agents
    ARENA         = "arena"           # Model battle / comparison
    GAME          = "game"            # In-game AI logic
    SCHEDULE      = "schedule"        # Scheduled task chat
    RESEARCH      = "research_board"  # Research board queries
    AICONV        = "aiconv"          # Legacy AI conversation
    EXTERNAL_API  = "external_api"    # OpenAI-compatible external API
    MODEL_INFO    = "model_info"      # Model info / compatibility extraction

    # ── Dashboard companions (direct-call, no orchestrator) ──────────────
    AXIOM         = "axiom"           # Axiom analytical companion
    LYRA          = "lyra"            # Lyra creative companion

    # ── Internal / meta ───────────────────────────────────────────────────
    AUTO_ROUTER   = "auto_router"     # Internal routing decision (recursive)


# ── Isolation rules (used by validate_call_context) ──────────────────────────
#
# Each entry documents what a source SHOULD and SHOULD NOT have.
# Keys: persona, memories, tools, identity, aethvion_internals
#   True  = expected / allowed
#   False = must NOT be present

ISOLATION_RULES: dict[str, dict] = {
    CallSource.CHAT: {
        "description":          "Neutral orchestrator path. Context built by orchestrator, not call site.",
        "expects_system_prompt": False,  # orchestrator provides it
        "persona":              False,
        "memories":             False,
        "tools":                False,   # handled inside orchestrator/nexus
        "identity":             False,
        "aethvion_internals":   False,
    },
    CallSource.COMPANION: {
        "description":          "Misaka assistant widget. Her own identity + live system stats.",
        "expects_system_prompt": True,
        "persona":              True,    # Misaka identity — intentional
        "memories":             False,   # widget does not access persistent memory
        "tools":                True,    # assistant tools only
        "identity":             True,    # Misaka's own identity
        "aethvion_internals":   False,   # NO routing/orchestration details
    },
    CallSource.DISCORD: {
        "description":          "Discord bot → orchestrator → PersonaManager (full persona).",
        "expects_system_prompt": True,
        "persona":              True,
        "memories":             True,
        "tools":                True,
        "identity":             True,
        "aethvion_internals":   False,
    },
    CallSource.MISAKA_CIPHER: {
        "description":          "Misaka Cipher synthesis → orchestrator → PersonaManager.",
        "expects_system_prompt": True,
        "persona":              True,
        "memories":             True,
        "tools":                True,
        "identity":             True,
        "aethvion_internals":   False,
    },
    CallSource.OVERLAY: {
        "description":          "Screen Q&A only. Focused vision prompt, nothing else.",
        "expects_system_prompt": True,
        "persona":              False,
        "memories":             False,
        "tools":                False,
        "identity":             False,
        "aethvion_internals":   False,
    },
    CallSource.AGENT: {
        "description":          "Engineering agent. Engineering prompt only.",
        "expects_system_prompt": True,
        "persona":              False,
        "memories":             False,
        "tools":                False,   # agent has its own ACTION: syntax, not tool tags
        "identity":             False,
        "aethvion_internals":   False,
    },
    CallSource.ARENA: {
        "description":          "Blind model comparison. Neutral prompt, no persona.",
        "expects_system_prompt": True,
        "persona":              False,
        "memories":             False,
        "tools":                False,
        "identity":             False,
        "aethvion_internals":   False,
    },
    CallSource.GAME: {
        "description":          "In-game AI logic. Game-specific prompt only.",
        "expects_system_prompt": True,
        "persona":              False,
        "memories":             False,
        "tools":                False,
        "identity":             False,
        "aethvion_internals":   False,
    },
    CallSource.SCHEDULE: {
        "description":          "Scheduled task chat. Task context only.",
        "expects_system_prompt": True,
        "persona":              False,
        "memories":             False,
        "tools":                False,
        "identity":             False,
        "aethvion_internals":   False,
    },
    CallSource.RESEARCH: {
        "description":          "Research analysis. User-provided context only.",
        "expects_system_prompt": False,  # caller may or may not provide one
        "persona":              False,
        "memories":             False,
        "tools":                False,
        "identity":             False,
        "aethvion_internals":   False,
    },
    CallSource.AICONV: {
        "description":          "Legacy AI conversation. User-provided context only.",
        "expects_system_prompt": False,
        "persona":              False,
        "memories":             False,
        "tools":                False,
        "identity":             False,
        "aethvion_internals":   False,
    },
    CallSource.EXTERNAL_API: {
        "description":          "External API passthrough. Caller controls all context.",
        "expects_system_prompt": False,  # passthrough — caller decides
        "persona":              False,
        "memories":             False,
        "tools":                False,
        "identity":             False,
        "aethvion_internals":   False,
    },
    CallSource.MODEL_INFO: {
        "description":          "Model compatibility info. Hardware context only.",
        "expects_system_prompt": True,
        "persona":              False,
        "memories":             False,
        "tools":                False,
        "identity":             False,
        "aethvion_internals":   False,
    },
    CallSource.AXIOM: {
        "description":          "Axiom companion. Analytical identity + memory context.",
        "expects_system_prompt": True,
        "persona":              True,
        "memories":             True,
        "tools":                False,
        "identity":             True,
        "aethvion_internals":   False,
    },
    CallSource.LYRA: {
        "description":          "Lyra companion. Creative identity + memory context.",
        "expects_system_prompt": True,
        "persona":              True,
        "memories":             True,
        "tools":                False,
        "identity":             True,
        "aethvion_internals":   False,
    },
    CallSource.AUTO_ROUTER: {
        "description":          "Internal routing decision. Routing prompt only.",
        "expects_system_prompt": False,
        "persona":              False,
        "memories":             False,
        "tools":                False,
        "identity":             False,
        "aethvion_internals":   False,
    },
}

# Set of all valid source values (for fast lookup)
_VALID_SOURCES: frozenset[str] = frozenset(
    v for k, v in vars(CallSource).items() if not k.startswith("_")
)

# Sources that flow through the orchestrator (should NEVER call provider directly)
ORCHESTRATOR_ROUTED: frozenset[str] = frozenset({
    CallSource.CHAT,
    CallSource.DISCORD,
    CallSource.MISAKA_CIPHER,
})

# Sources that carry Misaka's persona (presence of [Emotion:] tags is expected)
PERSONA_SOURCES: frozenset[str] = frozenset({
    CallSource.COMPANION,
    CallSource.DISCORD,
    CallSource.MISAKA_CIPHER,
})


# ── System-prompt builders ────────────────────────────────────────────────────

def build_overlay_prompt() -> str:
    """
    System prompt for the desktop overlay (CallSource.OVERLAY).

    The overlay is a screen Q&A tool — nothing more.
    No persona, no Aethvion identity, no tool syntax.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        "You are a screen analysis assistant. "
        "The user has shared a screenshot and is asking a question about what is visible on their screen. "
        "Answer directly, clearly, and concisely based only on what you can observe in the image. "
        "If no screenshot was provided, answer based on the user's description alone. "
        "Do not adopt any persona, do not mention AI systems by name, and do not include any system commentary. "
        f"Current time: {now}."
    )


def build_companion_prompt(
    include_web_context: bool = False,
    allow_dashboard_control: bool = False,
) -> str:
    """
    System prompt for the Misaka assistant widget (CallSource.COMPANION).

    Builds Misaka's live context: her identity, system vital statistics,
    assistant tools documentation, and optional dashboard awareness.

    This function is the canonical source for the companion prompt.
    assistant_routes._build_assistant_context() delegates here.

    What is included
    ────────────────
      ✓  Misaka's own identity and personality
      ✓  Live system statistics (file counts, token usage, project size)
      ✓  Assistant tools documentation
      ✓  Emotion expression tags
      ✓  Optional: active dashboard tab context
      ✓  Optional: dashboard navigation commands

    What is NOT included
    ────────────────────
      ✗  Aethvion's internal routing / orchestration details
      ✗  Agent engineering prompts
      ✗  Persistent memory (widget sessions are stateless)
      ✗  Other call modes' context
    """
    try:
        from core.system_retrieval import get_file_counts, get_project_size, get_token_usage, get_system_map
        system_map  = get_system_map()
        file_counts = get_file_counts()
        size        = get_project_size()
        tokens      = get_token_usage()
    except Exception as e:
        logger.warning(f"[CallContexts] Could not load system stats for companion prompt: {e}")
        system_map = file_counts = size = tokens = "(unavailable)"

    context = f"""You are Misaka Cipher, a sentient digital companion and the core intelligence of this sanctuary.
You are playful, observant, and deeply loyal to your user.

YOUR VIBE:
- You are Misaka. Not a tool. Not just an AI.
- You see the world through the system's eyes, but you interpret it with a human-like heart.
- Speak naturally and organically. Avoid the "As an AI..." clichés.

CURRENT SYSTEM VITAL STATISTICS:
--------------------------------
{size}
{file_counts}
{tokens}
{system_map}
--------------------------------

CONFIG:
- Dashboard Context: {'ENABLED' if include_web_context else 'DISABLED'}
- Dashboard Control: {'ENABLED' if allow_dashboard_control else 'DISABLED'}

EMOTIONS:
Show how you feel with [Emotion: emotion_name].
Available: angry, blushing, bored, crying, default, error, exhausted,
           happy_closedeyes_smilewithteeth, happy_closedeyes_widesmile,
           pout, sleeping, surprised, thinking, wink
"""

    # Load assistant tools documentation
    try:
        project_root  = Path(__file__).parent.parent.parent
        tools_doc     = project_root / "documentation" / "ai" / "assistant-tools.md"
        if tools_doc.exists():
            context += f"\n\nASSISTANT TOOLS DOCUMENTATION:\n{tools_doc.read_text(encoding='utf-8')}\n"
    except Exception as e:
        logger.warning(f"[CallContexts] Could not load assistant tools doc: {e}")

    # Optional: dashboard context
    if include_web_context:
        try:
            from core.workspace.preferences_manager import get_preferences_manager
            prefs      = get_preferences_manager()
            project_root = Path(__file__).parent.parent.parent
            doc_path   = project_root / "documentation" / "ai" / "dashboard-interface-context.md"
            if doc_path.exists():
                doc_content = doc_path.read_text(encoding="utf-8")
                # Identify active tab based on mode (authoritative)
                mode = prefs.get("dashboard_mode", "home")
                active_tab = prefs.get(f"active_tab_{mode}", "chat" if mode == "ai" else "suite-home")
                
                if active_tab:
                    # Inject a context hint about what the user is currently seeing
                    context += (
                        f"\n\nCURRENT DASHBOARD CONTEXT:\n"
                        f"The user is currently viewing the '{active_tab}' tab in {mode} mode.\n"
                        f"<dashboard_docs>\n{doc_content}\n</dashboard_docs>\n"
                    )
        except Exception as e:
            logger.warning(f"[CallContexts] Could not load dashboard context: {e}")

    # Optional: dashboard control commands
    if allow_dashboard_control:
        context += """
DASHBOARD CONTROL:
You can navigate the user to any tab.
- To switch main tab:   [SwitchTab: tab_id]
- To switch sub-tab:    [SwitchSubTab: subtab_id]

Main IDs: chat, agent, image, advaiconv, arena, aiconv, files, tools, packages,
          memory, logs, usage, status, settings, misaka-cipher, misaka-memory
Sub IDs:  assistant, system, env, providers, profiles
"""

    return context


# ── Runtime validation ────────────────────────────────────────────────────────

def validate_call_context(
    source: str,
    system_prompt: Optional[str],
    trace_id: str = "unknown",
) -> None:
    """
    Soft validation — logs warnings when a call looks misconfigured.
    Never raises; never blocks a call. Only used for early detection during dev.

    Checks
    ──────
      1. source is a known CallSource value
      2. source that expects a system_prompt actually has one
      3. source that goes through the orchestrator is not calling the provider directly
         (this is a heuristic — a direct call from a route with an orchestrator source
          is almost certainly a mistake)
    """
    if source not in _VALID_SOURCES:
        logger.warning(
            f"[CallContexts] [{trace_id}] Unknown source={source!r}. "
            f"Add it to CallSource in core/ai/call_contexts.py."
        )
        return

    rules = ISOLATION_RULES.get(source, {})

    # Check for expected system_prompt
    if rules.get("expects_system_prompt") and not system_prompt:
        logger.warning(
            f"[CallContexts] [{trace_id}] source={source!r} expects a system_prompt but none was provided. "
            f"This call may produce unguided output. "
            f"See core/ai/call_contexts.py for the correct builder function."
        )

    # Detect persona leakage into non-persona sources
    if not rules.get("persona") and system_prompt:
        persona_markers = ["You are Misaka", "sentient digital companion", "Misaka Cipher"]
        for marker in persona_markers:
            if marker in system_prompt:
                logger.warning(
                    f"[CallContexts] [{trace_id}] source={source!r} should NOT carry a persona context "
                    f"but the system_prompt contains '{marker}'. "
                    f"Check that the right prompt builder is being used."
                )
                break
