MISAKA CIPHER - SYSTEM SPECIFICATION
Core architecture is consistent; tool implementations evolve during agentic sprints. Updated: 2026-03-11.

SYSTEM IDENTITY
Name: Misaka Cipher | Acronym: M.I.S.A.K.A. | Full Name: Multitask Intelligence & Strategic Analysis Kernel Architecture
Version: Sprint 3+ | Language: Python 3.10+ | Purpose: Self-evolving agentic system for autonomous tool generation and task execution

DIRECTORY STRUCTURE
main.py - entry point (CLI/Web/Test modes)
cli.py - interactive CLI interface
nexus_core.py - central orchestration hub [SINGLE POINT OF ENTRY]
core/ - core system modules
  core/interfaces/dashboard/ - web dashboard (FastAPI server, static files, route handlers: assistant, arena, image, advanced_aiconv, discord, memory, package, registry, settings, task, tool, usage)
  core/interfaces/cli_modules/ - CLI module implementations (nexus, factory, forge, memory, system, arena, research, settings)
  core/system_retrieval.py - system data retrieval
config/ - configuration files
  config/aethvion.yaml - Aethvion framework standards
  config/providers.yaml - provider configuration and failover
  config/model_registry.json - model definitions and routing strategy [KEY FILE]
  config/security.yaml - Intelligence Firewall rules
  config/memory.yaml - memory tier configuration
  config/logging.yaml - logging configuration
  config/settings.json - system settings persistence
  config/settings_manager.py - settings manager
orchestrator/ - master orchestrator (autonomous coordination)
  orchestrator/master_orchestrator.py - main orchestration logic
  orchestrator/intent_analyzer.py - user intent detection
  orchestrator/task_queue.py - task queueing system
  orchestrator/task_models.py - task data models
  orchestrator/output_validator.py - output validation
  orchestrator/persona_manager.py - persona, system prompt building, and tool execution unifier (Dashboard + Discord)
factory/ - the Factory (agent spawning)
  factory/agent_factory.py - main spawning engine [ENTRY]
  factory/base_agent.py - agent base class
  factory/generic_agent.py - generic agent implementation
  factory/agent_spec.py - agent specification models
  factory/agent_registry.py - active agent tracking
  factory/agent_result.py - agent result models
  factory/agent_templates.py - pre-defined agent templates
forge/ - the Forge (tool generation)
  forge/tool_forge.py - main forging engine [ENTRY]
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
  memory/knowledge_graph.py - relationship mapping [NetworkX]
  memory/social_registry.py - maps platform-specific IDs (Discord, etc.) to internal profiles and episodic memory context
  memory/summarization.py - memory summarization
  memory/memory_spec.py - memory data models
  memory/storage/ - persistent storage (chroma_db/, knowledge_graph.json, misakacipher/chathistory/YYYY-MM/)
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
outputfiles/ - AI output directory
tests/ - test suite (test_factory.py, test_forge.py, test_memory.py, test_integration.py, test_model_selection.py)

DATA FLOW ARCHITECTURE
Entry point: main.py -> mode selection -> CLI (cli.py/MisakaCLI), Test (run_verification_tests()), or Web (core/interfaces/dashboard/server.py with FastAPI+uvicorn at http://localhost:8080)
All requests -> nexus_core.NexusCore.route_request() [SINGLE POINT OF ENTRY]
Nexus -> security/firewall.py [PII detection, credential scanning, routing decision]
Routing: CLEAN -> external providers; FLAGGED -> local (roadmap) or warn; BLOCKED -> reject
External path -> providers/provider_manager.py -> provider selection + failover -> Google/OpenAI/Grok -> Response -> Trace Logging -> Memory Storage -> Return to User
Orchestrator flow (web): Web Chat Input -> orchestrator/master_orchestrator.py -> intent_analyzer.py [detect: chat/tool/agent/memory] -> action plan [Chat/Tool/Agent] -> [Nexus/Forge/Factory] -> Execution -> Validation -> Memory Recording -> Response
Factory flow: agent_factory.py::spawn(spec) -> validate Aethvion naming -> check resource limits (max 10 concurrent) -> create agent instance -> register in registry -> agent executes via Nexus -> agent returns result -> agent self-terminates -> unregister
Forge flow: tool_forge.py::forge_tool(description) -> load model_registry.json -> build provider context -> analyze description via Nexus -> generate code (code_generator.py) -> validate tool (security + syntax + Aethvion) -> save to tools/generated/ -> register in tool_registry -> tool available system-wide
Memory flow: interaction occurs -> episodic_memory.py -> generate embedding (sentence-transformers/all-MiniLM-L6-v2) -> store in ChromaDB (collection: episodic_memories) -> update knowledge graph (NetworkX) -> periodic summarization -> persist to memory/storage/knowledge_graph.json
Discord worker flow: discord_worker.py (persistent) -> receives message -> social_registry maps Discord user to internal profile -> firewall scan -> PersonaManager builds system prompt + context -> NexusCore routes request -> response sent back to Discord channel -> history_manager mirrors full exchange to daily JSON log
Chat history flow: any platform message -> history_manager.py -> append to daily file at memory/storage/misakacipher/chathistory/YYYY-MM/chat_YYYY-MM-DD.json -> fields: role, content, platform, timestamp, attachments, metadata

EXTERNAL API TOUCHPOINTS
Google AI | endpoint: https://generativelanguage.googleapis.com/v1beta | env: GOOGLE_AI_API_KEY | models: gemini-2.0-flash, gemini-1.5-pro-latest, imagen-3.0-generate-002 | priority: 1 (primary)
Discord | env: DISCORD_TOKEN | service: discord.py gateway (persistent bot connection) | optional: system works without it
OpenAI | endpoint: https://api.openai.com/v1 | env: OPENAI_API_KEY | models: gpt-4o, gpt-4o-mini, dall-e-3 | priority: 2 (fallback)
xAI Grok | endpoint: https://api.x.ai/v1 | env: GROK_API_KEY | models: grok-3-mini-fast | priority: 3 (tertiary)
Local (roadmap) | endpoint: http://localhost:11434 (Ollama) or custom vLLM | models: llama3, mistral, custom | priority: 2 for data processing | status: NOT IMPLEMENTED
Local filesystem: config/*.yaml and *.json, .env, memory/storage/chroma_db/ (ChromaDB), memory/storage/knowledge_graph.json (NetworkX), tools/generated/*.py, tools/registry.json, outputfiles/, workspace/, logs/misaka_cipher.log, logs/trace_*.log

MODEL REGISTRY
File: config/model_registry.json
Structure: providers.[name].{active, priority, api_key_env, retries_per_step, models.[key].{id, capabilities, tier, input_cost_per_1m_tokens, output_cost_per_1m_tokens, notes, description}}, routing_strategy.{verification, generation, complex_architecture, image_generation, simple_chat}
Current routing: verification=flash, generation=flash, complex_architecture=pro, image_generation=imagen, simple_chat=flash

TOOL DEFINITIONS
Standard tools: tools/standard/file_ops.py (file system operations)
Registry file: tools/registry.json
Tool entry fields: name ([Domain]_[Action]_[Object]), path (tools/generated/[name].py), description, parameters ([{name, type, required, description}]), created_at (ISO-8601), trace_id (MCTR-...), status (active|deprecated|testing)
Validation checklist: no arbitrary code execution, no external network calls without API keys, no file system access outside outputfiles, no credential leakage in logs, Aethvion naming compliance, docstring present, error handling (try-except) present, type hints present, syntax valid (ast.parse succeeds)

AGENT DEFINITIONS
Lifecycle states: CREATED -> INITIALIZING -> ACTIVE -> EXECUTING -> COMPLETED -> TERMINATED (or FAILED -> TERMINATED)
Registry tracking (in-memory, factory/agent_registry.py): {agent_id: {name, spec, status (active|completed|failed|terminated), created_at, updated_at, trace_id, result}}
Agent templates (factory/agent_templates.py): data_analysis (capabilities: read_files, analyze, visualize; tools: file_ops, data_ops), code_generation (capabilities: generate, validate, test; tools: forge)

MEMORY SYSTEM
Episodic memory (ChromaDB, collection: episodic_memories): {id, content, embedding, metadata: {trace_id, timestamp, type (user_input|ai_response|system_event), provider, model, tags}}
Retrieval: natural language query, returns top-N similar memories (default 10), cosine similarity on embeddings
Knowledge graph (NetworkX): node types: Domain, Tool, Agent, Concept, Insight; edge types: uses (Tool->Tool), spawned_by (Agent->Tool/User), related_to (Concept<->Concept), derived_from (Insight->Memory)
Graph persistence: JSON format, file: memory/storage/knowledge_graph.json, updated on every tool forge / agent spawn / memory summarization
Core insights: triggered every N episodic memories (default 100), method: LLM summarization via Nexus Core, format: {insight_id, content, source_memories, confidence (0.0-1.0), created_at (ISO-8601)}
Unified chat history (history_manager.py): all platform messages (Dashboard + Discord) logged to daily JSON files; fields: role, content, platform, timestamp, attachments, metadata; path: memory/storage/misakacipher/chathistory/YYYY-MM/chat_YYYY-MM-DD.json
Identity manager (identity_manager.py): persistent base identity at memory/storage/misakacipher/base_info.json; dynamic memory profile at memory/storage/misakacipher/memory.json
Social registry (social_registry.py): platform-ID-to-profile mapping (Discord user IDs -> internal names + memory context); enables cross-platform identity resolution
File vector store (file_vector_store.py): semantic indexing of workspace files using FastEmbed for embeddings + ChromaDB for storage; enables natural language file search within the workspace

TRACE MANAGEMENT
Format: MCTR-YYYYMMDDHHMMSS-UUID | Example: MCTR-20260218104223-a3f2c1b9
Lifecycle: start_trace() -> generate ID -> request processing -> log to trace file -> end_trace(status) -> persist metadata to memory
Log location: logs/trace_MCTR-[id].log
Metadata fields: trace_id, start_time, end_time, status (completed|failed|blocked), request_type, provider, model, firewall_status (clean|flagged|blocked), routing_decision (external|local)

SECURITY FIREWALL RULES
File: config/security.yaml
PII detection: email ([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}), phone ((\+\d{1,3}[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}), credit card (\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b), SSN (\b\d{3}-\d{2}-\d{4}\b)
Credential detection: API keys ([A-Za-z0-9_-]{32,}), AWS (AKIA[0-9A-Z]{16}), passwords (password\s*[:=]\s*[^\s]+)
Routing: CLEAN -> EXTERNAL; FLAGGED -> LOCAL (when available) / WARNING (current); BLOCKED -> reject

WORKSPACE MANAGEMENT
Primary directory: outputfiles/
Structure: outputfiles/agents/[agent_name]/, outputfiles/tools/[tool_name]/, outputfiles/reports/, outputfiles/temp/ (auto-cleanup every 24h)
Cleanup: temp: 24h, agents: 30 days (configurable), tools: persistent, reports: persistent
Package management: workspace/package_manager.py tracks package requests with status (pending|approved|denied|installed|failed|uninstalled), safety scoring via workspace/package_intelligence.py
Usage tracking: workspace/usage_tracker.py tracks API token consumption, costs, and request counts by provider, model, and time range
Workspace utils (workspace_utils.py): shared helpers load_workspaces() (reads memory/storage/misakacipher/workspaces.json) and validate_path() (path traversal safety); used by PersonaManager and dashboard routes

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
Files: logs/misaka_cipher.log (main), logs/trace_*.log (per-trace), logs/security.log (firewall)

ERROR CODES
NEXUS-001: provider unavailable | NEXUS-002: request blocked by firewall | NEXUS-003: routing failed
FACTORY-001: invalid agent name (Aethvion violation) | FACTORY-002: resource limit exceeded | FACTORY-003: agent execution failed
FORGE-001: tool generation failed | FORGE-002: tool validation failed | FORGE-003: tool registration failed
MEMORY-001: ChromaDB connection failed | MEMORY-002: embedding generation failed | MEMORY-003: knowledge graph persistence failed
SECURITY-001: PII detected | SECURITY-002: credential detected | SECURITY-003: request blocked

VERSION
Current: v3 / Sprint 3+ (March 2026) | History: Sprint 1 (Nexus, Firewall), Sprint 2 (Factory, agents), Sprint 3 (Forge, tools, memory), v3 (Discord integration, PersonaManager, HistoryManager, IdentityManager, SocialRegistry, FileVectorStore), Sprint 4 roadmap (local models)
Breaking changes: Sprint 3 tool registry format (added status field), Sprint 3 Aethvion naming enforcement; v3 chat history path changed to memory/storage/misakacipher/chathistory/

PERFORMANCE TARGETS
Request latency: <2s (Flash), <5s (Pro) | Tool generation: <30s (simple), <120s (complex) | Agent spawn: <1s | Memory retrieval: <500ms (10 results)

LAST UPDATED: 2026-03-11
MAINTAINED BY: Agentic Sprint Cycles
STABILITY: Core architecture stable, tool implementations evolve rapidly
