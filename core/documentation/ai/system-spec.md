AETHVION SUITE - SYSTEM SPECIFICATION
Core architecture is consistent; tool implementations evolve during agentic sprints. Updated: 2026-03-30.

SYSTEM IDENTITY
Name: Aethvion Suite | Acronym: M.I.S.A.K.A. | Full Name: Multitask Intelligence & Strategic Analysis Kernel Architecture
Version: v11 | Language: Python 3.10+ | Purpose: Self-evolving agentic research and execution engine with multi-tiered memory and integrated app ecosystem

DIRECTORY STRUCTURE
main.py - entry point (CLI/Web/Test modes)
cli.py - interactive CLI interface
nexus_core.py - central orchestration hub [SINGLE POINT OF ENTRY]
core/ - core system modules
  core/interfaces/dashboard/ - web dashboard (FastAPI server, static files, route handlers: assistant, arena, audio_models, image, advanced_aiconv, agent_workspace, discord, memory, package, registry, settings, task, tool, usage)
  core/interfaces/cli_modules/ - CLI module implementations (nexus, factory, forge, memory, system, arena, research, settings)
  core/system_retrieval.py - system data retrieval
config/ - configuration files (committed, version-controlled)
  config/aethvion.yaml - Aethvion framework standards
  config/providers.yaml - provider configuration and failover
  config/security.yaml - Intelligence Firewall rules
  config/memory.yaml - memory tier configuration
  config/logging.yaml - logging configuration
  config/settings_manager.py - settings manager
  config/suggested_apimodels.json - suggested cloud model configurations for Model Registry UI
  config/suggested_localmodels.json - suggested GGUF model configurations for Local Models UI
  config/suggested_localaudiomodels.json - suggested local audio model configurations (Kokoro, XTTS-v2, Whisper)
orchestrator/ - master orchestrator (autonomous coordination)
  orchestrator/master_orchestrator.py - main orchestration logic
  orchestrator/intent_analyzer.py - user intent detection
  orchestrator/task_queue.py - task queueing system (supports agent workspace tasks)
  orchestrator/task_models.py - task data models
  orchestrator/output_validator.py - output validation
  orchestrator/persona_manager.py - persona, system prompt building, and tool execution unifier (Dashboard + Discord)
  orchestrator/agent_events.py - thread-safe per-task SSE event store for real-time streaming
  orchestrator/agent_runner.py - ReAct-style multi-step agent execution loop (max 20 iterations); actions: write_file, read_file, list_dir, run_command, done
factory/ - the Factory (agent spawning)
  factory/agent_factory.py - main spawning engine [ENTRY]
  factory/base_agent.py - agent base class
  factory/generic_agent.py - generic agent implementation
  factory/agent_spec.py - agent specification models
  factory/agent_registry.py - active agent tracking
  factory/agent_result.py - agent result models
  factory/agent_templates.py - pre-defined agent templates
forge/ - Legacy Forge (static tool generation)
  forge/tool_forge.py - tool generation engine (deprecated in favor of Agentic Skill execution)
  forge/code_generator.py - Python code generation
  forge/tool_validator.py - validation and security checking
  forge/tool_registry.py - tool registration system
  forge/tool_spec.py - tool specification models
  forge/validators/tool_validator.py - tool validation logic
memory/ - the Memory Tier (knowledge persistence)
  memory/episodic_memory.py - vector-based interaction storage [ChromaDB]
  memory/file_vector_store.py - semantic indexing and search for workspace files [FastEmbed + ChromaDB]
  memory/history_manager.py - unified chat history across platforms (Dashboard + Discord); daily JSON files
  memory/identity_manager.py - persistent system identity (base_info.json) and dynamic memory profile (memory.json)
  memory/persistent_memory.py - Persistent Memory (long-term knowledge topics stored in JSON) [DASHBOARD KNOWLEDGE HUB]
  memory/knowledge_graph.py - relationship mapping [NetworkX]
  memory/social_registry.py - maps platform-specific IDs (Discord, etc.) to internal profiles and episodic memory context
  memory/summarization.py - memory summarization [Core Insights generation]
  memory/memory_spec.py - memory data models
  memory/agent_workspace_manager.py - agent workspace and thread state manager; CRUD for workspaces and threads; used by task queue for agent context injection
providers/ - provider abstraction layer
  providers/provider_manager.py - provider coordination and failover
  providers/base_provider.py - provider interface
  providers/google_provider.py - Google AI (Gemini)
  providers/openai_provider.py - OpenAI (GPT)
  providers/grok_provider.py - xAI (Grok)
security/ - Intelligence Firewall
  security/firewall.py - main firewall coordination
  security/scanner.py - content scanning (PII/credentials)
  security/router.py - routing decision logic
tools/ - tool registry
  tools/standard/ - core system tools (file_ops.py)
  tools/generated/ - AI-generated tools [DYNAMIC]
  tools/register_standard_tools.py - standard tool registration
workers/ - background workers
  workers/discord_worker.py - persistent Discord bot service; inbound scanning, outbound polling, message mirroring to unified history, proactive conversations
  workers/package_installer.py - async package installation worker
workspace/ - workspace management
  workspace/workspace_manager.py - file system operations
  workspace/workspace_utils.py - shared workspace helpers: load_workspaces(), validate_path()
  workspace/package_manager.py - package request and approval management
  workspace/package_intelligence.py - package analysis and safety scoring
  workspace/usage_tracker.py - API usage and cost tracking
  workspace/preferences_manager.py - user preferences persistence
utils/ - utility modules
  utils/logger.py - logging utilities
  utils/trace_manager.py - trace ID management
  utils/validators.py - input validation
  utils/paths.py - canonical data path constants (single source of truth); import instead of constructing paths manually
apps/ - standalone application modules
  apps/audio/models/ - local audio model adapters: kokoro.py (Kokoro TTS), xtts.py (XTTS-v2 with voice cloning), whisper_model.py (faster-whisper STT)
  apps/audio/models/base.py - LocalAudioModel base class, Voice/TTS/STT result dataclasses
  apps/audio/models/registry.py - available audio model registry
  apps/audio/tts_manager.py - TTSManager singleton; manages model lifecycle (load/unload), TTS generation, STT transcription, voice clone management
  apps/code/code_server.py - Code IDE FastAPI backend; FS ops, streaming execution (SSE), AI chat, thread persistence, usage logging
  apps/finance/finance_server.py - Finance app backend; holdings, market overview, per-ticker AI analysis (/api/market/overview, /api/holding/stats/{ticker}, /api/holding/analyze/{ticker})
data/ - runtime data (never committed)
  data/apps/ - per-app runtime data (arena, audio, code, driveinfo, finance, games, hardwareinfo, nexus, photo, tracking, vtuber)
  data/config/ - runtime config (model_registry.json, settings.json)
  data/history/ - persistent conversation history
    data/history/chat/ - standard Misaka persona chat sessions (daily JSON files)
    data/history/ai_conversations/ - AI Conversations saves (id, name, topic, participants, messageHistory, stats, created/updated timestamps)
    data/history/advanced/ - advanced AI conversation threads
    data/history/agents/ - agent workspace thread history
  data/logs/usage/ - AI API usage logs; YYYY-MM/usage_YYYY-MM-DD.json; suite-standard format shared by dashboard and Code IDE
  data/logs/system/ - system, launcher, and app logs
  data/system/ - lock file, launcher log, ports registry
  data/vault/ - persistent brain (personas, knowledge graph, episodic memory, search)
    data/vault/personas/misakacipher/ - base_info.json (identity), memory.json (dynamic profile), threads/
    data/vault/knowledge/ - graph.json (NetworkX), social.json (social registry), insights.json, persistent_memory.json (long-term knowledge topics)
  data/workspaces/ - outputs, uploads, tools, media, projects, preferences.json, packages.json, files.json
localmodels/ - user-downloaded model weights (never committed)
  localmodels/gguf/ - GGUF chat models (llama.cpp inference)
  localmodels/audio/ - TTS/STT/voice models
    localmodels/audio/kokoro/ - Kokoro TTS model weights
    localmodels/audio/xtts-v2/ - XTTS-v2 model weights
    localmodels/audio/whisper/ - Whisper model weights
    localmodels/audio/voices/ - voice cloning source WAVs (XTTS-v2)
tests/ - test suite (test_factory.py, test_forge.py, test_memory.py, test_integration.py, test_model_selection.py)

DATA FLOW ARCHITECTURE
Entry point: main.py -> mode selection -> CLI (cli.py/AethvionCLI), Test (run_verification_tests()), or Web (core/interfaces/dashboard/server.py with FastAPI+uvicorn at http://localhost:8080)
All requests -> nexus_core.NexusCore.route_request() [SINGLE POINT OF ENTRY]
Nexus -> security/firewall.py [PII detection, credential scanning, routing decision]
Routing: CLEAN -> external providers; FLAGGED -> local (roadmap) or warn; BLOCKED -> reject
External path -> providers/provider_manager.py -> provider selection + failover -> Google/OpenAI/Grok -> Response -> Trace Logging -> Memory Storage -> Return to User
Orchestrator flow (web): Web Chat Input -> orchestrator/master_orchestrator.py -> intent_analyzer.py [detect: chat/agent/memory/app] -> action plan [Chat/Agent/App] -> [Nexus/Factory/Workspace] -> Execution -> Validation -> Memory Recording -> Response
Factory flow: agent_factory.py::spawn(spec) -> validate Aethvion naming -> check resource limits (max 10 concurrent) -> create agent instance -> register in registry -> [LEGACY path]: agent executes via Nexus; [MODERN path]: agent assigned to Workspace Thread -> [AgentRunner] executes ReAct loop -> self-terminates -> unregister
Agent workspace flow: Dashboard POSTs task to /api/tasks -> task_queue creates task with workspace context -> AgentWorkspaceManager injects workspace folder path -> AgentRunner executes ReAct loop (read_file/write_file/list_dir/run_command/done actions) -> each step emitted to agent_events.py store -> client streams steps via SSE GET /api/tasks/{task_id}/events -> completed steps saved to data/history/agents/{workspace_id}/{thread_id}.json
Forge flow (Legacy): tool_forge.py::forge_tool(description) -> code_generator.py -> tool_validator.py -> save to data/workspaces/tools/generated/ -> register in tools/registry.json; Tools in this directory are available system-wide but static.
Memory flow: interaction occurs -> episodic_memory.py -> store in ChromaDB -> [Periodic Job]: summarization.py generates Core Insights -> [User/AI]: persistent_memory.py manages long-term topics -> [System]: update knowledge graph (NetworkX)
Discord worker flow: discord_worker.py (persistent) -> receives message -> social_registry maps Discord user to internal profile -> firewall scan -> PersonaManager builds system prompt + context -> NexusCore routes request -> response sent back to Discord channel -> history_manager mirrors full exchange to daily JSON log
Chat history flow: any platform message -> history_manager.py -> append to daily file at data/history/chat/YYYY-MM/chat_YYYY-MM-DD.json -> fields: role, content, platform, timestamp, attachments, metadata; used by the Misaka persona
AI Conversation save flow: conversation stop or turn end -> arena_routes.py saves to data/history/ai_conversations/{id}.json -> fields: id, name, topic, participants, messageHistory, stats, created_at, updated_at
Local audio flow: client requests TTS/STT -> audio_models_routes.py -> TTSManager.get_model(model_id) -> load model if not cached -> generate TTS or transcribe STT -> return result; voice cloning reads source WAV from localmodels/audio/voices/
Usage logging flow: any AI call (dashboard or Code IDE) -> provider logs token counts, costs, provider, model, source to data/logs/usage/YYYY-MM/usage_YYYY-MM-DD.json

EXTERNAL API TOUCHPOINTS
Google AI | endpoint: https://generativelanguage.googleapis.com/v1beta | env: GOOGLE_AI_API_KEY | models: gemini-2.0-flash, gemini-1.5-pro-latest, imagen-3.0-generate-002 | priority: 1 (primary)
Discord | env: DISCORD_TOKEN | service: discord.py gateway (persistent bot connection) | optional: system works without it
OpenAI | endpoint: https://api.openai.com/v1 | env: OPENAI_API_KEY | models: gpt-4o, gpt-4o-mini, dall-e-3 | priority: 2 (fallback)
xAI Grok | endpoint: https://api.x.ai/v1 | env: GROK_API_KEY | models: grok-3-mini-fast | priority: 3 (tertiary)
Anthropic | env: ANTHROPIC_API_KEY | optional: additional fallback provider
Yahoo Finance | library: yfinance | used by: apps/finance/finance_server.py for live price refresh and per-ticker metadata
Local (roadmap) | endpoint: http://localhost:11434 (Ollama) or custom vLLM | models: llama3, mistral, custom | priority: 2 for data processing | status: NOT IMPLEMENTED
Local filesystem: core/config/*.yaml, data/config/model_registry.json, data/config/settings.json, .env, data/vault/episodic/ (ChromaDB), data/vault/knowledge/graph.json (NetworkX), tools/generated/*.py, tools/registry.json, data/workspaces/outputs/, data/logs/

MODEL REGISTRY
Runtime file: data/config/model_registry.json (copied from config/ on first run)
Template configs: core/config/suggested_apimodels.json, core/config/suggested_localmodels.json, core/config/suggested_localaudiomodels.json
UI: Tabbed Model Registry in dashboard Settings; one tab per provider; active/hover states; status dots reflect provider active state
Structure: providers.[name].{active, priority, api_key_env, retries_per_step, models.[key].{id, capabilities, tier, input_cost_per_1m_tokens, output_cost_per_1m_tokens, notes, description}}, routing_strategy.{verification, generation, complex_architecture, image_generation, simple_chat}
Current routing: verification=flash, generation=flash, complex_architecture=pro, image_generation=imagen, simple_chat=flash
Local audio models: registered separately in audio_models_routes.py; stored in localmodels/audio/

TOOL DEFINITIONS
Standard tools: tools/standard/file_ops.py (file system operations)
Registry file: tools/registry.json
Tool entry fields: name ([Domain]_[Action]_[Object]), path (tools/generated/[name].py), description, parameters ([{name, type, required, description}]), created_at (ISO-8601), trace_id (MCTR-...), status (active|deprecated|testing)
Validation checklist: no arbitrary code execution, no external network calls without API keys, no file system access outside outputfiles, no credential leakage in logs, Aethvion naming compliance, docstring present, error handling (try-except) present, type hints present, syntax valid (ast.parse succeeds)

AGENT DEFINITIONS
Factory agent lifecycle states: CREATED -> INITIALIZING -> ACTIVE -> EXECUTING -> COMPLETED -> TERMINATED (or FAILED -> TERMINATED)
Registry tracking (in-memory, factory/agent_registry.py): {agent_id: {name, spec, status (active|completed|failed|terminated), created_at, updated_at, trace_id, result}}
Agent templates (factory/agent_templates.py): data_analysis (capabilities: read_files, analyze, visualize; tools: file_ops, data_ops), code_generation (capabilities: generate, validate, test; tools: forge)

AGENT WORKSPACES (dashboard Agents tab)
Manager: core/memory/agent_workspace_manager.py - CRUD for named workspaces and threads; persists to data/history/agents/
API: core/interfaces/dashboard/agent_workspace_routes.py - REST endpoints (/api/agents): list/create/update/delete workspaces and threads; /api/agents/browse for server-side folder browsing
Runner: core/orchestrator/agent_runner.py - AgentRunner class; ReAct-style loop using <action> XML tags; supported actions: write_file, read_file, list_dir, run_command, done; max 20 iterations; working directory = selected workspace folder
Events: core/orchestrator/agent_events.py - thread-safe in-memory event store (per task_id); events pushed by runner and consumed by SSE endpoint
SSE endpoint: GET /api/tasks/{task_id}/events - streams agent step events (action, result, status, error) in real-time; client uses EventSource
Task submission: POST /api/tasks with {workspace_id, thread_id, prompt, workspace_folder} -> task_queue creates task -> sets agent context -> triggers agent runner

MEMORY SYSTEM
Episodic memory (ChromaDB, collection: episodic_memories): {id, content, embedding, metadata: {trace_id, timestamp, type (user_input|ai_response|system_event), provider, model, tags}}
Retrieval: natural language query, returns top-N similar memories (default 10), cosine similarity on embeddings
Knowledge graph (NetworkX): node types: Domain, Tool, Agent, Concept, Insight; edge types: uses (Tool->Tool), spawned_by (Agent->Tool/User), related_to (Concept<->Concept), derived_from (Insight->Memory)
Graph persistence: JSON format, file: data/vault/knowledge/graph.json, updated on every tool forge / agent spawn / memory summarization
Core insights: triggered every N episodic memories (default 100), method: LLM summarization via Nexus Core, format: {insight_id, content, source_memories, confidence (0.0-1.0), created_at (ISO-8601)}
Unified chat history (history_manager.py): all platform messages (Dashboard + Discord) logged to daily JSON files; fields: role, content, platform, timestamp, attachments, metadata; path: data/history/chat/YYYY-MM/chat_YYYY-MM-DD.json; consumed by Misaka persona
AI Conversation history (arena_routes.py): saves/loads full conversation state at data/history/ai_conversations/{id}.json; supports CRUD (list, save, load, delete, rename); fields: id, name, topic, participants, messageHistory, stats, created_at, updated_at
Identity manager (identity_manager.py): persistent base identity at data/vault/personas/misakacipher/base_info.json; dynamic memory profile at data/vault/personas/misakacipher/memory.json
Social registry (social_registry.py): platform-ID-to-profile mapping (Discord user IDs -> internal names + memory context); persisted to data/vault/knowledge/social.json; enables cross-platform identity resolution
File vector store (file_vector_store.py): semantic indexing of workspace files using FastEmbed for embeddings + ChromaDB for storage; enables natural language file search within the workspace

MISAKA PERSONA TRACE MANAGEMENT
Format: MCTR-YYYYMMDDHHMMSS-UUID | Example: MCTR-20260218104223-a3f2c1b9
Lifecycle: start_trace() -> generate ID -> request processing -> log to trace file -> end_trace(status) -> persist metadata to memory
Log location: data/logs/system/aethvion.log (trace details inline) or logs/trace_MCTR-[id].log
Metadata fields: trace_id, start_time, end_time, status (completed|failed|blocked), request_type, provider, model, firewall_status (clean|flagged|blocked), routing_decision (external|local)

SECURITY FIREWALL RULES
File: config/security.yaml
PII detection: email ([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}), phone ((\+\d{1,3}[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}), credit card (\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b), SSN (\b\d{3}-\d{2}-\d{4}\b)
Credential detection: API keys ([A-Za-z0-9_-]{32,}), AWS (AKIA[0-9A-Z]{16}), passwords (password\s*[:=]\s*[^\s]+)
Routing: CLEAN -> EXTERNAL; FLAGGED -> LOCAL (when available) / WARNING (current); BLOCKED -> reject

WORKSPACE MANAGEMENT
Canonical paths: core/utils/paths.py - single source of truth for all data directory/file locations; import from here instead of constructing paths manually
Primary output directory: data/workspaces/outputs/
Structure: data/workspaces/outputs/ (AI output files), data/workspaces/tools/ (registered tools), data/workspaces/media/ (media files), data/workspaces/uploads/ (user uploads), data/workspaces/projects/ (per-workspace project state)
Package management: workspace/package_manager.py tracks package requests with status (pending|approved|denied|installed|failed|uninstalled), safety scoring via workspace/package_intelligence.py
Usage tracking: workspace/usage_tracker.py tracks API token consumption, costs, and request counts by provider, model, and time range; compatible log format shared between dashboard and Code IDE
Workspace utils (workspace_utils.py): shared helpers load_workspaces() and validate_path() (path traversal safety); used by PersonaManager and dashboard routes

LOCAL AUDIO MODELS
Location: apps/audio/models/ (adapters) + apps/audio/tts_manager.py (lifecycle manager)
Dashboard API: core/interfaces/dashboard/audio_models_routes.py - endpoints under /api/audio/local: load/unload models, generate TTS (/tts), transcribe STT (/transcribe), list/upload/delete voices (/voices), install pip packages
Supported models: Kokoro (TTS, kokoro package), XTTS-v2 (Coqui TTS with voice cloning, TTS package), Whisper (faster-whisper STT)
Model weights location: localmodels/audio/{kokoro,xtts-v2,whisper}/
Voice cloning: cloned voice WAV files stored at localmodels/audio/voices/; XTTS-v2 reads these for voice_samples
Dependencies: optional per-model (kokoro, faster-whisper, TTS); install via pip or via dashboard package installer
Dashboard tab: Audio Models - shows loaded/unloaded state, model info cards, TTS test input, STT transcription, voice management

CONFIGURATION OVERRIDE PRIORITY
1. runtime parameters (highest), 2. environment variables (.env), 3. config files (config/*.yaml, config/*.json, config/settings.json), 4. system defaults (lowest)

AETHVION STANDARD COMPLIANCE
Naming: [Domain]_[Action]_[Object]
Valid domains: Data, Code, System, Network, Image, Text, Math, Finance, Security, Database, File
Valid actions: Create, Read, Update, Delete, Analyze, Generate, Transform, Validate
Valid objects: singular nouns (File, CSV, JSON, Image, Report, etc.)
Invalid: snake_case without structure (my_tool_123), CamelCase (MyToolName), lowercase (mytool), special characters (My-Tool!)

DEPENDENCIES
Core: python>=3.10, google-generativeai, openai, requests
Orchestration: pyyaml, python-dotenv
Memory: chromadb, sentence-transformers, networkx
Web: fastapi, uvicorn, websockets
Utilities: rich, click
Full list: see requirements.txt

TESTING
Test files: tests/test_factory.py, tests/test_forge.py, tests/test_memory.py, tests/test_integration.py, tests/test_model_selection.py
Run: python main.py --test (verification), pytest tests/ (full suite), pytest tests/test_forge.py -v (specific module)

SYSTEM STATUS MONITORING
nexus.get_status() returns: {initialized, providers: {[name]: {status, model}}, firewall: {active, rules_loaded}, active_traces}
factory.get_status() returns: {active_agents, max_concurrent, total_spawned, total_completed, total_failed}
forge.get_status() returns: {total_tools, standard_tools, generated_tools, validation_rate, tools_dir}

LOGGING
File: config/logging.yaml | Levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
Rotation: max 10MB, 5 backups, format: %(asctime)s - %(name)s - %(levelname)s - %(message)s
Files: data/logs/system/ (main app log), logs/trace_*.log (per-trace), logs/security.log (firewall), data/logs/usage/YYYY-MM/usage_YYYY-MM-DD.json (AI usage, shared format between dashboard and Code IDE)

ERROR CODES
NEXUS-001: provider unavailable | NEXUS-002: request blocked by firewall | NEXUS-003: routing failed
FACTORY-001: invalid agent name (Aethvion violation) | FACTORY-002: resource limit exceeded | FACTORY-003: agent execution failed
FORGE-001: tool generation failed | FORGE-002: tool validation failed | FORGE-003: tool registration failed
MEMORY-001: ChromaDB connection failed | MEMORY-002: embedding generation failed | MEMORY-003: knowledge graph persistence failed
SECURITY-001: PII detected | SECURITY-002: credential detected | SECURITY-003: request blocked

VERSION
CurrVersion: Current: v10 (March 2026) | History: Sprint 1-3 (Foundation), v3-v8 (Apps), v9 (Agent Workspaces, local models, Finance AI, Tracking HUD), v10 (Centralized Versioning, Financial Analyst Dashboard, Tracking Terminal Redesign)
Breaking changes: v9 data paths migrated to data/ root (centralised via core/utils/paths.py); history moved from memory/storage/ to data/history/; vault data moved to data/vault/; localmodels paths changed from LocalModels/ to localmodels/gguf/ and localmodels/audio/; v11 rebranding to Aethvion Suite.

PERFORMANCE TARGETS
Request latency: <2s (Flash), <5s (Pro) | Tool generation: <30s (simple), <120s (complex) | Agent spawn: <1s | Memory retrieval: <500ms (10 results) | Agent runner step: depends on action (file I/O <100ms, shell command variable)

LAST UPDATED: 2026-03-31
MAINTAINED BY: Agentic Sprint Cycles
STABILITY: Core architecture stable, tool implementations evolve rapidly
