AETHVION SUITE - SYSTEM SPECIFICATION
Core architecture is consistent; companion configs, bridge modules, and tool implementations evolve during development sprints. Updated: 2026-04-19.

SYSTEM IDENTITY
Name: Aethvion Suite | Version: v1.4 | Language: Python 3.10+ | Purpose: Self-hosted local AI super-app with companions, agents, creative tools, and bridges — privacy-first, customizable, and self-evolving.
Primary AI companion: Misaka Cipher (misaka_cipher) | Other companions: Axiom (axiom), Lyra (lyra)

DIRECTORY STRUCTURE
main.py — entry point (Web mode: FastAPI + uvicorn; Test mode: --test flag)
core/ — core system modules
  core/aether_core.py — central AI gateway [SINGLE POINT OF ENTRY]; routing, failover, Intelligence Firewall, Trace IDs
  core/bridges/ — registry-driven system integrations
    core/bridges/registry.json — bridge module registry (6 active entries)
    core/bridges/bridge_manager.py — loads and manages active bridges; builds {bridges_block} capability string
    core/bridges/spotify_bridge.py — Spotify currently-playing data
    core/bridges/weather_bridge.py — weather conditions via external API
    core/bridges/system_bridge.py — CPU/GPU/RAM system stats
    core/bridges/media_sentinel.py — active media window detection
    core/bridges/screen_capture.py — on-demand screenshots
    core/bridges/webcam_capture.py — on-demand webcam images
  core/companions/ — companion engine and per-companion configs
    core/companions/companion_engine.py — main chat generator; handles chat_history, tool execution, memory updates, bridges_block and workspace_block injection, streaming, error handling
    core/companions/registry.py — companion registry; maps companion_id to config path
    core/companions/configs/ — per-companion JSON configurations
      core/companions/configs/misaka_cipher.json — Misaka Cipher personality, system prompt template, capabilities
      core/companions/configs/axiom.json — Axiom personality, system prompt template
      core/companions/configs/lyra.json — Lyra personality, system prompt template
      core/companions/configs/simple_companion.json — minimal companion template for companion creator
    core/companions/engine/ — companion engine submodules
      core/companions/engine/memory.py — CompanionMemory class; loads base_info.json + memory.json; XML tag extraction and synthesis; writes updated memory
      core/companions/engine/history.py — per-companion chat history management
      core/companions/engine/streaming.py — build_bridges_capabilities() — assembles {bridges_block} string from bridge_manager
      core/companions/engine/tools.py — companion tool definitions; tool dispatch for workspace and bridge tool calls
      core/companions/engine/workspace_utils.py — load_workspaces(companion_id), save_workspaces(companion_id), build_workspace_block(workspaces) — returns {workspace_block} string
  core/interfaces/ — interface layer
    core/interfaces/dashboard/ — web dashboard (FastAPI server + static files + 32 registered route handlers)
      core/interfaces/dashboard/server.py — FastAPI app; lifespan context manager; registers all routers
      core/interfaces/dashboard/static/ — HTML/CSS/JS frontend
        core/interfaces/dashboard/static/index.html — single-page app shell; panel-home is the main home panel
        core/interfaces/dashboard/static/partials/ — per-tab HTML partials (lazy-loaded)
        core/interfaces/dashboard/static/js/ — JavaScript modules (app-tabs.js, sidebar-manager.js, mode-*.js, view-*.js)
      core/interfaces/dashboard/*_routes.py — route handler files (32 registered routers total)
  core/memory/ — memory subsystems
    core/memory/episodic_memory.py — ChromaDB vector store for raw interactions
    core/memory/identity_manager.py — reads/writes companion base_info.json and memory.json; uses PERSONA_MISAKA* legacy constants (deprecated, still in use)
    core/memory/knowledge_graph.py — NetworkX-based concept relationship graph
    core/memory/persistent_memory.py — long-term knowledge topics (JSON)
    core/memory/summarization.py — Core Insights generation from episodic memories
  core/orchestrator/ — task execution and coordination
    core/orchestrator/agent_runner.py — AgentRunner class; ReAct-style loop; actions: write_file, read_file, list_dir, run_command, done; max 20 iterations; 2,054 lines
    core/orchestrator/agent_events.py — thread-safe in-memory SSE event store (per task_id)
    core/orchestrator/launcher.py — application launcher and service coordination
    core/orchestrator/persona_manager.py — system prompt builder for dashboard assistant (uses PERSONA_MISAKA for identity)
    core/orchestrator/summarization.py — wrapper for memory summarization calls
    core/orchestrator/task_queue.py — task queueing and dispatch for agent runners
  core/utils/ — utility modules
    core/utils/paths.py — canonical data path constants [SINGLE SOURCE OF TRUTH FOR PATHS]; import from here, never construct paths manually
    core/utils/logger.py — logging utilities
    core/utils/port_manager.py — dynamic port allocation and registration
  core/config/ — committed configuration (version-controlled)
    core/config/providers.yaml — provider configuration and failover order
    core/config/security.yaml — Intelligence Firewall rules (PII/credential patterns)
    core/config/model_defaults/ — suggested model configurations
apps/ — standalone application backends (run as separate services)
  apps/audio/ — TTS/STT manager and local model adapters
    apps/audio/models/ — Kokoro, XTTS-v2, Whisper adapters + base class + registry
    apps/audio/tts_manager.py — TTSManager singleton; model lifecycle, TTS generation, STT transcription, voice clone management
  apps/code/code_server.py — Code IDE FastAPI backend; FS ops, streaming execution (SSE), AI chat, thread persistence
  apps/finance/finance_server.py — Finance dashboard backend; holdings, market overview, per-ticker AI analysis
config/ — committed config files (top-level, version-controlled)
data/ — runtime data (never committed)
  data/modes/ — all tab-mode state and history
    data/modes/companions/ — companion persistent brain
      data/modes/companions/personas/{companion_id}/ — base_info.json (stable identity), memory.json (dynamic profile)
      data/modes/companions/knowledge/{companion_id}/ — knowledge graph data per companion
      data/modes/companions/memory/{companion_id}/ — episodic ChromaDB store per companion
    data/modes/chat/ — general chat history (daily JSON files)
    data/modes/agents/ — agent workspace thread history
    data/modes/agent_corp/ — agent corp task history
    data/modes/ai_conversations/ — AI conversation saves
    data/modes/advanced_ai_conversations/ — advanced AI conversation threads
    data/modes/workspaces/ — agent workspace file system
      data/modes/workspaces/outputs/ — agent-generated files
      data/modes/workspaces/tools/ — registered tools
      data/modes/workspaces/media/ — media files
      data/modes/workspaces/uploads/ — user uploads
      data/modes/workspaces/projects/ — per-workspace project state
      data/modes/workspaces/preferences.json — workspace preferences
    data/modes/schedule/ — scheduled task definitions
    data/modes/explained/ — explained AI conversation history
  data/apps/ — per-app runtime data (arena, audio, code, finance, games, photo, tracking, etc.)
  data/config/
    data/config/model_registry.json — active model registry (copied from core/config/ on first run)
    data/config/settings.json — user settings
  data/logs/
    data/logs/usage/ — AI API usage logs; YYYY-MM/usage_YYYY-MM-DD.json
    data/logs/notifications/ — notification history; YYYY-MM/YYYY-MM-DD.json
    data/logs/launcher.log — launcher log
    data/logs/crashlog.log — crash log
  data/system/ — lock file, ports registry
    data/system/aethvion.lock
    data/system/ports.json
  data/default_output/ — default AI output directory
    data/default_output/images/
    data/default_output/models/
    data/default_output/documents/
localmodels/ — user-downloaded model weights (never committed)
  localmodels/gguf/ — GGUF chat models (llama.cpp inference)
  localmodels/audio/ — TTS/STT/voice models
    localmodels/audio/kokoro/ — Kokoro TTS model weights
    localmodels/audio/xtts-v2/ — XTTS-v2 weights
    localmodels/audio/whisper/ — Whisper weights
    localmodels/audio/voices/ — voice cloning source WAVs (XTTS-v2)
  localmodels/3d/ — 3D model weights and pipelines
tests/ — test suite

DATA FLOW ARCHITECTURE
Entry point: main.py -> Web mode -> core/interfaces/dashboard/server.py (FastAPI + uvicorn at http://localhost:8080)
All AI requests -> core/aether_core.AetherCore.route_request() [SINGLE POINT OF ENTRY]
AetherCore -> core/security (Intelligence Firewall: PII detection, credential scanning, routing decision)
Routing: CLEAN -> external providers; FLAGGED PII -> LOCAL (when available) or warn; BLOCKED CREDS -> reject
External path -> provider selection + failover (Google AI priority 1 -> OpenAI priority 2 -> Grok priority 3) -> Response -> Trace Logging -> Return
Companion chat flow: POST /api/companions/{companion_id}/chat -> companion_engine.py::chat_response() -> load companion config -> build system prompt (inject {bridges_block} + {workspace_block}) -> convert chat_history to messages list -> AetherCore.route_request() -> LLM response -> stream to client -> memory update (XML tag extraction)
Agent workspace flow: Dashboard POSTs task -> task_queue creates task -> AgentRunner executes ReAct loop (read_file/write_file/list_dir/run_command/done actions) -> each step emitted to agent_events.py store -> client streams steps via SSE GET /api/tasks/{task_id}/events -> completed steps saved to data/modes/agents/
Memory flow: interaction occurs -> episodic_memory.py -> store in ChromaDB -> [periodic]: summarization.py generates Core Insights -> [companion]: memory.py extracts XML tags -> updates memory.json
Usage logging: any AI call -> provider logs token counts, costs, provider, model, source to data/logs/usage/YYYY-MM/usage_YYYY-MM-DD.json

COMPANION SYSTEM
Registry: core/companions/registry.py — maps companion_id to config file path; used by companion_engine and routes to resolve companions
Config structure (per-companion JSON): {name, companion_id, route_prefix, system_prompt (with {bridges_block} and {workspace_block} placeholders), personality_defaults {temperature, context_limit}, capabilities [], meta {}}
Engine entry: core/companions/companion_engine.py::chat_response(companion_id, message, chat_history, settings) -> generator (streaming)
Chat history format: [{role: "user"|"assistant", content: str}] — converted from raw history before LLM call
Bridges injection: build_bridges_capabilities() called on each request -> returns formatted string of active bridge states -> injected as {bridges_block} into system prompt
Workspace injection: build_workspace_block(workspaces) called on each request -> returns formatted workspace list -> injected as {workspace_block} into system prompt
Memory files: data/modes/companions/personas/{companion_id}/base_info.json (stable), memory.json (dynamic, updated via XML synthesis)
Memory module: CompanionMemory class in core/companions/engine/memory.py; _default_base_info stores defaults; write uses base_info key extraction to prevent nesting corruption
Active companions: misaka_cipher (route_prefix: /api/misaka), axiom (route_prefix: /api/axiom), lyra (route_prefix: /api/lyra)

BRIDGES SYSTEM
Registry file: core/bridges/registry.json — 6 active entries; fields per entry: {module (dotted path), name, description, enabled}
Active bridges: spotify (core.bridges.spotify_bridge), media_sentinel (core.bridges.media_sentinel), weather_link (core.bridges.weather_bridge), system_link (core.bridges.system_bridge), screen_capture (core.bridges.screen_capture), webcam_capture (core.bridges.webcam_capture)
Manager: core/bridges/bridge_manager.py — loads registry, imports enabled modules, polls each bridge, aggregates status strings
Output: {bridges_block} — formatted multi-line string injected into every companion system prompt; describes current state of each active bridge
Dashboard: Settings -> Bridges section; users can enable/disable bridges and enter credentials (e.g. Spotify client_id/client_secret stored as localStorage preferences with nexus.* key prefix — migration to bridges.* pending)

EXTERNAL API TOUCHPOINTS
Google AI | endpoint: https://generativelanguage.googleapis.com/v1beta | env: GOOGLE_AI_API_KEY | models: gemini-2.0-flash, gemini-1.5-pro-latest, imagen-3.0-generate-002 | priority: 1 (primary)
OpenAI | endpoint: https://api.openai.com/v1 | env: OPENAI_API_KEY | models: gpt-4o, gpt-4o-mini, dall-e-3 | priority: 2 (fallback)
xAI Grok | endpoint: https://api.x.ai/v1 | env: GROK_API_KEY | models: grok-3-mini-fast | priority: 3 (tertiary)
Anthropic | env: ANTHROPIC_API_KEY | optional: additional fallback provider
Spotify | env/prefs: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET | used by: core/bridges/spotify_bridge.py for currently-playing track data | optional
Weather | external weather API | used by: core/bridges/weather_bridge.py | optional
Yahoo Finance | library: yfinance | used by: apps/finance/finance_server.py for live price refresh and per-ticker metadata
Local filesystem: core/config/*.yaml, data/config/model_registry.json, data/config/settings.json, .env, data/modes/companions/ (ChromaDB + JSON), data/modes/workspaces/, data/logs/

MODEL REGISTRY
Runtime file: data/config/model_registry.json (copied from core/config/ on first run)
Template configs: core/config/model_defaults/suggested/
UI: Tabbed Model Registry in dashboard Settings; one tab per provider; active/hover states; status dots reflect provider active state
Structure: providers.[name].{active, priority, api_key_env, retries_per_step, models.[key].{id, capabilities, tier, input_cost_per_1m_tokens, output_cost_per_1m_tokens, notes, description}}, routing_strategy.{verification, generation, complex_architecture, image_generation, simple_chat}
Current routing: verification=flash, generation=flash, complex_architecture=pro, image_generation=imagen, simple_chat=flash

AGENT WORKSPACES
Runner: core/orchestrator/agent_runner.py — AgentRunner class; ReAct-style loop using <action> XML tags; supported actions: write_file, read_file, list_dir, run_command, done; max 20 iterations; working directory = selected workspace folder
Events: core/orchestrator/agent_events.py — thread-safe in-memory event store (per task_id); events pushed by runner and consumed by SSE endpoint
SSE endpoint: GET /api/tasks/{task_id}/events — streams agent step events in real-time; client uses EventSource
Task submission: POST /api/tasks with {workspace_id, thread_id, prompt, workspace_folder} -> task_queue -> agent_runner
History: completed threads saved to data/modes/agents/{workspace_id}/{thread_id}.json
Agent Corp: core/interfaces/dashboard/corp_routes.py — higher-level multi-agent coordination; data at data/modes/agent_corp/

MEMORY SYSTEM
Episodic memory (ChromaDB, per-companion): stored at data/modes/companions/memory/{companion_id}/; collection: episodic_memories; fields: {id, content, embedding, metadata: {trace_id, timestamp, type, provider, model, tags}}
Knowledge graph (NetworkX): node types: Domain, Tool, Agent, Concept, Insight; edge types: uses, spawned_by, related_to, derived_from; persistence: data/modes/companions/knowledge/graph.json
Core insights: triggered every N episodic memories; LLM summarization via AetherCore; format: {insight_id, content, source_memories, confidence, created_at}; stored at data/modes/companions/knowledge/insights.json
Persistent memory (knowledge hub): long-term curated topics in data/modes/companions/knowledge/persistent_memory.json; CRUD via dashboard Persistent Memory tab; injected into agent and companion context on retrieval
Social registry: data/modes/companions/knowledge/social.json; platform-ID-to-profile mapping for Discord and other platforms
Companion identity (identity_manager.py): stable base_info.json at PERSONA_MISAKA path (legacy constant, deprecated but still used by identity_manager.py and persona_manager.py); dynamic memory.json updated per-conversation via CompanionMemory synthesis

SCHEDULE SYSTEM
Manager: core/orchestrator/ or core/schedulers/ — manages recurring AI tasks; persists to data/modes/schedule/
API: core/interfaces/dashboard/schedule_routes.py — task CRUD (/api/schedule/tasks), manual runs (/run), deep-linking navigation support
State: draft (setup), active (scheduled), paused (suspended)
Notifications: integrated with notification hub; notifies user on task completion with result preview and deep-link target

NOTIFICATION SYSTEM
Infrastructure: real-time notification hub with persistent history (data/logs/notifications/); supports level-based alerting (info, success, warning, error)
Visibility filtering: granular category control via Settings -> Notifications; users toggle visibility per source without losing history
Deep-linking: notification "target" schema enables automatic dashboard navigation to specific tab and task result

TRACE MANAGEMENT
Format: MCTR-YYYYMMDDHHMMSS-UUID | Example: MCTR-20260418143022-a3f2c1b9
Lifecycle: start_trace() -> generate ID -> request processing -> log -> end_trace(status) -> persist metadata
Metadata fields: trace_id, start_time, end_time, status (completed|failed|blocked), request_type, provider, model, firewall_status (clean|flagged|blocked), routing_decision (external|local)

SECURITY FIREWALL RULES
File: core/config/security.yaml
PII detection: email, phone, credit card, SSN patterns (regex-based)
Credential detection: API keys ([A-Za-z0-9_-]{32,}), AWS (AKIA[0-9A-Z]{16}), passwords (password\s*[:=]\s*[^\s]+)
Routing: CLEAN -> EXTERNAL; FLAGGED PII -> LOCAL (when available) / WARNING (current); BLOCKED -> reject

CANONICAL PATH CONSTANTS (core/utils/paths.py)
DATA — project root / data
MODES — DATA / modes
COMPANIONS — MODES / companions
COMPANIONS_PERSONAS — COMPANIONS / personas
COMPANIONS_KNOWLEDGE — COMPANIONS / knowledge
COMPANIONS_MEMORY — COMPANIONS / memory
MODE_WORKSPACES — MODES / workspaces
WS_OUTPUTS, WS_TOOLS, WS_MEDIA, WS_UPLOADS, WS_PROJECTS — workspace subdirs
LOGS_USAGE — DATA / logs / usage
MODEL_REGISTRY — DATA / config / model_registry.json
SETTINGS — DATA / config / settings.json
PERSONA_MISAKA* — legacy constants (deprecated; still used by identity_manager.py and persona_manager.py; migrate when those files are updated)
APP_BRIDGES — DATA / apps / nexus (constant name APP_BRIDGES; underlying directory still /apps/nexus/)
Import from core.utils.paths; never construct paths manually.

LOCAL AUDIO MODELS
Location: apps/audio/models/ (adapters) + apps/audio/tts_manager.py (lifecycle manager)
Dashboard API: core/interfaces/dashboard/audio_models_routes.py — endpoints under /api/audio/local: load/unload, TTS (/tts), STT (/transcribe), voices (/voices), install pip packages
Supported models: Kokoro (TTS), XTTS-v2 (voice cloning, TTS), Whisper (faster-whisper STT)
Model weights: localmodels/audio/{kokoro,xtts-v2,whisper}/
Voice cloning: localmodels/audio/voices/ — upload WAV files, XTTS-v2 uses them as voice_samples
Tab: audio-models (Audio & Speech)

CONFIGURATION OVERRIDE PRIORITY
1. runtime parameters (highest), 2. environment variables (.env), 3. config files (config/*.yaml, data/config/settings.json), 4. system defaults (lowest)

AETHVION STANDARD COMPLIANCE
Naming: [Domain]_[Action]_[Object]
Valid domains: Data, Code, System, Network, Image, Text, Math, Finance, Security, Database, File
Valid actions: Create, Read, Update, Delete, Analyze, Generate, Transform, Validate
Invalid: snake_case without structure, CamelCase, lowercase, special characters

DEPENDENCIES
Core: python>=3.10, google-generativeai, openai, requests
Orchestration: pyyaml, python-dotenv, fastapi, uvicorn
Memory: chromadb, sentence-transformers, networkx
Utilities: rich, click
Full list: see pyproject.toml

ROUTE HANDLERS (registered in server.py)
32 routers registered: system, preferences, workspace, task, memory, registry, usage, arena, settings, photo, adv_aiconv, research_board, assistant, ollama, audio, corp, games, overlay, schedule, smarter_than_ai, three_d, agent_workspace, notification, explained, external_api (x2), persistent_memory, discord, logs, documentation, companion, companion_creator
All routes verified reachable; no orphaned route files.

DASHBOARD TAB SYSTEM
Tab registry: core/interfaces/dashboard/static/js/sidebar-manager.js — TABS array with id, label, icon, mode; 35 registered tabs
Sidebar profiles: named layouts saved to localStorage (sidebar_profiles_v1); 5 preset layouts (Professional, Creative, Researcher, Companion Hub, Full Suite) + Custom
Panel switching: ATB.switchTo(panelId) for app panels; switchDashboardTab(tabId) for sidebar tabs
SwitchTab tag: [SwitchTab: tab_id] in assistant response text triggers navigation; handled in assistant.js
Home panel: panel-home (suite-home tab)

SYSTEM STATUS MONITORING
AetherCore.get_status() returns: {initialized, providers: {[name]: {status, model}}, firewall: {active, rules_loaded}, active_traces}
Bridge status: bridge_manager returns per-bridge status strings; aggregated into {bridges_block}
Port registry: data/system/ports.json — dynamically assigned ports for standalone app services

LOGGING
Levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
Files: data/logs/ (main logs), data/logs/usage/ (AI usage), data/logs/notifications/ (notifications)
Format: %(asctime)s - %(name)s - %(levelname)s - %(message)s

KNOWN TECHNICAL DEBT (v4 audit)
agent_runner.py — 2,054 lines; tool-block parser and file-op executor should be extracted to shared core/tools/ modules
24 bare except: clauses across games_routes, three_d_routes, system_routes, workspace_routes, episodic_memory, others — should be except Exception: with logger.error() calls
PERSONA_MISAKA* constants in paths.py — deprecated; migrate identity_manager.py and persona_manager.py to dynamic paths then delete
nexus.* localStorage key prefix — should migrate to bridges.* (requires one-time migration step)

VERSION
Current: v1.4 (April 2026)
History: Sprint 1-3 (Foundation), v3-v8 (Apps ecosystem), v9 (Agent Workspaces + local models), v10 (Finance Dashboard), v11 (Nexus → Bridges rename + Companion Engine), v12 (Schedule + Notification Refactor), v13 (Companion Memory, Workspace Utils), v1.4 (Bridge cleanup, settings dynamic companion, workspace_utils finalized)
Breaking changes: v9 data paths migrated to data/ root; v11 core/nexus/ renamed to core/bridges/, nexus_core.py renamed to aether_core.py, all Python imports updated; v1.4 data paths moved to data/modes/

LAST UPDATED: 2026-04-19
MAINTAINED BY: Agentic Sprint Cycles
STABILITY: Core architecture stable; companion configs and bridge modules evolve with user needs
