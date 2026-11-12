AETHVION SUITE SYSTEM SPECIFICATION (AI-OPTIMIZED)
==================================================

ARCHITECTURE OVERVIEW
Pattern: Event-driven, modular microkernel with Security Firewall, Multi-Provider LLM Routing, Companion & Group Chat Engine, Model Hub, Asset Library, Automate Workflow Engine, AethvionDB, and Self-Evolving Connectors
Core Entry Point: main.py -> core/interfaces/dashboard/server.py (FastAPI + Uvicorn)
Versioning: Git-derived YYYY.MM.count (shorthash) via core/version.py (no manual version numbers)
Runtime Environment: Python 3.10+, Windows/Linux/macOS, Local-First

KEY SUBSYSTEMS & MODULES
- core/orchestrator/aether_core.py — Central LLM router, provider failover, security firewall enforcement, trace management
- core/providers/ — 10 LLM provider adapters: anthropic_provider, deepseek_provider, google_provider, grok_provider, groq_provider, local_provider, mistral_provider, ollama_provider, openai_provider, openrouter_provider
- core/companions/ — Companion & Group Chat subsystem:
  - companion_engine.py, companion_routes.py, companion_creator_routes.py, registry.py
  - group_chat_engine.py, group_chat_routes.py, group_conductor.py (server-side turn orchestration, shared scratchpad, tool/connector execution)
- core/bridges/ — 23 native connector modules (registered in core/bridges/registry.json) + Realtime Incubator:
  - bridge_manager.py, dynamic_manager.py (Non-Destructive Evolution Protocol), dynamic_toolmaker.py
  - Native bridges: screen_capture, screen_ocr_bridge, visual_memory_bridge, window_focus_bridge, clipboard_bridge, git_bridge, process_bridge, media_sentinel, system_bridge, webcam_capture, tasks_bridge, scratchpad_bridge, companion_timer_bridge, flow_state_bridge, web_search_bridge, webpage_bridge, youtube_bridge, twitch_bridge, reddit_bridge, weather_bridge, spotify_bridge, group_chat_bridge, dynamic_toolmaker
- core/modelhub/ — Unified Model Hub (hub.py, registry.py, adapters.py, capabilities.py, glb.py, templating.py, modelhub_routes.py) for chat, image, audio, and 3D models
- core/assets/ — Unified Asset Library (store.py, values.py, asset_routes.py) for generated images, audio, and 3D assets
- core/automate/ — Visual node workflow engine (engine v2 with multi-model chains, branching, loops, retries, sub-workflows)
- core/aethviondb/ — Structured entity/section/relation graph databases (data/aethviondb/<name>/)
- core/memory/ — Episodic memory (ChromaDB), NetworkX knowledge graph, persistent memory, core insights
- core/security/ — Security firewall (core/config/security.yaml)
- core/utils/paths.py — Canonical filesystem path constants (always import from here; never construct paths manually)

LLM PROVIDERS (10)
Cloud: Anthropic, DeepSeek, Google AI, xAI Grok, Groq, Mistral, OpenAI, OpenRouter
Local: Ollama (http://localhost:11434), Local GGUF (llama-cpp-python via local_provider.py)
Config: data/config/model_registry.json (templates in core/config/model_defaults/suggested/)

CANONICAL DATA PATHS (core/utils/paths.py)
DATA               -> data/
COMPANIONS         -> data/companions/           (top-level; per-companion brain data)
COMPANION_GROUPS   -> data/companions/groups/    (group chat histories & shared scratchpads)
BRIDGES_DATA       -> data/bridges/
DYNAMIC_CONNECTORS -> data/bridges/dynamic/      (Realtime Incubator dynamic connectors)
AETHVIONDB         -> data/aethviondb/
CODE               -> data/code/                 (Code IDE workspaces, threads, blueprints)
MODES              -> data/modes/                (chat, agent_corp, ai_conversations, advanced_ai_conversations, explained, workspaces, schedule, worldsim)
CONFIG             -> data/config/               (model_registry.json, settings.json)
LOGS               -> data/logs/                 (main logs, usage/, notifications/)
SYSTEM             -> data/system/               (ports.json, etc.)
LOCAL_MODELS       -> localmodels/               (gguf/, audio/, audio/voices/, 3d/, image/)

CONNECTOR PROTOCOL (BRIDGES + REALTIME INCUBATOR)
Native Registry: core/bridges/registry.json (23 modules)
Bridge Routes: /api/bridges/... (screen_capture, ocr, visual_memory, window, clipboard, git, processes, media, system, webcam, remind, scratchpad, timer, vibe, search, read_url, youtube, twitch, reddit, weather, spotify, groupchat, toolmaker)
Realtime Incubator:
- Companions create/evolve dynamic connectors via dynamic_toolmaker.py
- Managed by core/bridges/dynamic_manager.py using the Non-Destructive Evolution Protocol (versioned snapshots, usage/feedback tracking, safe rollback)
- Stored under data/bridges/dynamic/{tool_id}/

DASHBOARD TAB SYSTEM
Registry: core/interfaces/dashboard/static/js/sidebar-manager.js
8 Categories:
- workspace: agent-corp, schedule, asset-library, photo, audio, 3d-gen
- research: advaiconv, researchboard, arena, aiconv, explained
- memory: memory, persistent-memory, sched-overview
- storage: output, screenshots, camera, uploads
- model-hub: local-models, image-models, audio-models, api-providers, 3d-models
- library: voice-library, connectors
- system: logs, documentation, usage, status, ports
- experimental: physics-lab, stats-lab, chembio-lab, worldsim, project-mapper, decision-trace, lexmap, supplymind, clinicaltrace
Core / Pinned: suite-home, chat, code, automate, aethviondb, companions (e.g. misaka-cipher), companion-creator, companion-memory, settings

TRACE & SECURITY
Trace ID Format: MCTR-YYYYMMDDHHMMSS-UUID
Security Rules: core/config/security.yaml (PII & credential regex scanning; CLEAN -> external, FLAGGED PII -> local/warning, BLOCKED -> reject)

LAST UPDATED: 2026-11-12
