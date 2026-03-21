<div align="center">

# Aethvion Suite

**A self-hosted AI platform — chat, agents, tools, and apps, all running locally**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-experimental-orange.svg)](https://github.com/Aethvion/Aethvion-Suite)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[📚 Documentation](/core/documentation/) · [🚀 Getting Started](/core/documentation/human/getting-started.md) · [💬 Discussions](https://github.com/Aethvion/Aethvion-Suite/discussions)

<img width="124px" src="https://raw.githubusercontent.com/Aethvion/Aethvion-Suite/refs/heads/main/core/interfaces/dashboard/static/misakacipher/chibi1/misakacipher_chibi_tablet.png">

*Connect cloud providers or run local GGUF models. Control everything from a 25+ tab dashboard, an AI-powered code IDE, or a terminal CLI — your platform, your rules.*

**Current version: v9.0.0**

⚠️ **EXPERIMENTAL — EARLY DEVELOPMENT** · Actively being built. Expect rough edges and partially-implemented features.

</div>

---

## 🖼️ Showcase

<div align="center">

<img src="assets/showcase/AethvionSuite_HomeScreen.png" alt="Aethvion Suite Home Screen" width="100%">

</div>

<br>

<div align="center">

| | |
|:---:|:---:|
| <img src="assets/showcase/MisakaCipher_Chat.png" alt="Misaka Cipher Chat Interface" width="100%"> | <img src="assets/showcase/AethvionSuite_Photo.png" alt="Aethvion Suite Photo App" width="100%"> |
| **Misaka Cipher** · Multi-provider AI chat with threads, auto-routing, and context modes | **Aethvion Photo** · AI image generation and precision layer-based editing system |
| <img src="assets/showcase/AethvionSuite_Audio.png" alt="Aethvion Suite Audio App" width="100%"> | <img src="assets/showcase/AethvionSuite_Code.png" alt="Aethvion Suite Code IDE" width="100%"> |
| **Aethvion Audio** · Professional multi-track timeline editor with live waveforms and effects | **Aethvion Code IDE** · Monaco-based IDE with AI copilot and code execution |
| <img src="assets/showcase/AethvionSuite_LocalModels.png" alt="Aethvion Suite Local Models" width="100%"> | <img src="assets/showcase/AethvionSuite_DriveInfo.png" alt="Aethvion Suite Drive Info" width="100%"> |
| **Direct Local Inference** · Run GGUF models (Mistral, LLaMA) directly on your hardware | **Aethvion Drive Info** · Recursive system storage analysis and visualization |

<br>

<img src="assets/showcase/MisakaCipher_UsagePage.png" alt="Aethvion Suite Usage Page" width="100%">

**Usage & Cost Tracking** · Token usage, cost estimates, and granular per-query breakdowns

</div>

---

## 🎯 What Is Aethvion Suite?

Aethvion Suite is a **self-hosted AI assistant platform** that connects to cloud providers (Google Gemini, OpenAI, xAI Grok, Anthropic Claude) and local GGUF models via llama-cpp-python. It gives you a structured environment for running chat threads, generating tools, spawning agents, and interacting with a growing set of integrated apps — all from a server you own and control.

There are **two main components** to the ecosystem:

### 1. Aethvion Suite Core
The central intelligence hub and management platform. It provides the dashboard, API orchestration, and foundational AI services.

| Interface | Description |
|-----------|-------------|
| **Web Dashboard** | 25+ tab control center — chat, agents, tools, memory, games |
| **Core Terminal** | CLI mode for headless use, scripting, and developer queries |

### 2. Standalone Integrated Applications
Professional-grade tools built on the Aethvion core. Each app runs as a standalone server but integrates seamlessly into the main dashboard.

| App | Role | Default Port |
|-----|------|--------------|
| **Aethvion Code IDE** | VS Code-powered IDE with AI chat and execution | 8083 |
| **Aethvion VTuber** | 2D character rigging and animation engine | 8081 |
| **Aethvion Audio** | Multi-track timeline editor and effects processor | 8081* |
| **Aethvion Photo** | Layer-based image generation and editor | 8081* |
| **Aethvion Tracking** | AI-powered facial motion capture bridge with HUD | 8081* |
| **Aethvion Drive Info** | Interactive disk space and storage analyzer | 8084 |
| **Aethvion Finance** | Personal financial tracking, portfolio, and AI market analysis | 8081* |
| **Aethvion Hardware Info** | System hardware information and monitoring | 8081* |

*\* Note: Apps sharing port 8081 will automatically negotiate the next available port (8082, etc.) if multiple are running simultaneously.*

The AI core features **Misaka Cipher**, backed by four subsystems:

| Component | Role | Status |
|-----------|------|--------|
| **Nexus Core** | Single entry point — routes all requests, manages trace IDs | ✅ Stable |
| **The Factory** | Spawns transient worker agents for complex tasks | 🧪 Works for basic tasks |
| **The Forge** | Generates Python tools autonomously | 🧪 Works for simple tools |
| **Memory Tier** | ChromaDB episodic memory + knowledge graph | ✅ Storage stable, retrieval improving |

**Cloud Providers:** Google AI (Gemini) · OpenAI (GPT-4o) · xAI (Grok) · Anthropic (Claude)
**Local Models:** GGUF via llama-cpp-python (Mistral, LLaMA, Phi, and others)
**Intelligence Firewall:** PII/credential scanning before any external API call — blocks sensitive data from leaving.

---

## 🚀 Quick Start

```bash
# Clone and install
git clone https://github.com/Aethvion/Aethvion-Suite.git
cd Aethvion-Suite
pip install -e ".[memory]"

# Configure providers
copy .env.example .env
# Edit .env — add any of: GOOGLE_AI_API_KEY / OPENAI_API_KEY / GROK_API_KEY / ANTHROPIC_API_KEY
# Leave them blank to use only local models
```

**One-click (Windows):** Each application includes a dedicated launcher script. Double-click the `.bat` file to automatically create the virtual environment, install dependencies, and open the app.

| Application | Launcher | Default URL |
|-------------|----------|-------------|
| **Suite Dashboard** | `Start_Aethvion_Suite.bat` | http://localhost:8080 |
| **Code IDE** | `apps/code/Start_Code.bat` | http://localhost:8083 |
| **VTuber Engine** | `apps/vtuber/Start_VTuber.bat` | http://localhost:8081 |
| **Audio Editor** | `apps/audio/Start_Audio.bat` | http://localhost:8081* |
| **Photo Editor** | `apps/photo/Start_Photo.bat` | http://localhost:8081* |
| **Finance Hub** | `apps/finance/Start_Finance.bat` | http://localhost:8081* |
| **Drive Info** | `apps/driveinfo/Start_DriveInfo.bat` | http://localhost:8084 |
| **Tracking Bridge**| `apps/tracking/Start_Tracking.bat` | http://localhost:8081* |
| **Hardware Info** | `apps/hardwareinfo/Start_HardwareInfo.bat` | http://localhost:8081* |

**Manual:**
```bash
python -m core.main           # web dashboard
python -m core.main --cli     # interactive CLI
python -m core.main --test    # run verification tests
python apps/code/code_server.py    # Code IDE standalone
```

---

## ✅ What Works Right Now

### 💬 Chat & Threads
- Multi-provider chat (Google, OpenAI, Grok, Anthropic) with automatic failover
- Local GGUF model inference via llama-cpp-python — no cloud required
- Persistent conversation threads with configurable context modes (none / smart / full)
- Per-message model selection or **auto-routing** (LLM picks the best model from your enabled pool)
- Collapsible, flush-edge chat UI with persistent layout state memory

### 🤖 Agent Workspaces
- **Agent Workspaces tab**: Create named workspaces, each with their own thread history
- **Agent threads**: Start tasks from a workspace — the agent runner executes them step-by-step in a chosen folder
- **ReAct-style execution loop**: Agent reads files, writes files, lists directories, and runs shell commands to complete tasks
- **Real-time SSE streaming**: Each agent action and result streams live to the dashboard via Server-Sent Events
- **Step history**: Previous runs are saved and re-rendered when revisiting a thread; actions and results displayed inline
- Folder browser for selecting a workspace directory on the server filesystem

### ⚒️ Tool Forge
- AI can generate Python tools and register them for reuse
- Generated tools are saved locally and available in subsequent sessions

### 🧠 Memory
- Episodic memory stored in ChromaDB (vector search)
- Every conversation stored as a task JSON with model, routing, and usage metadata

### 💻 Code IDE
- Full Monaco editor (VS Code engine) with syntax highlighting for 30+ languages
- AI copilot: chat, explain, fix, complete, refactor — all with streaming responses
- **Chat thread system** — create, rename, switch, and delete threads per workspace; threads persist between sessions
- **File creation from chat** — the AI uses `### FILE:` markers; files are written to disk automatically
- **Python-exec blocks** — AI outputs Python code for file operations; executed server-side with Approve/Deny security toggle
- Code execution: Python, Node.js, Bash/Shell — output streams live to the built-in terminal via SSE
- **Ctrl+P fuzzy file finder palette** — quickly open any file with substring and character-sequence scoring
- **Status bar** — shows git branch, language, cursor position, and dirty-state indicator
- **AI Project Notes panel** — saved per-workspace and auto-injected into every AI system prompt
- Apply/Copy buttons on AI chat code blocks; collapsed file write cards with expand-on-click
- **AI continuation loop** — automatically chains follow-up calls so large tasks don't get cut off mid-response
- File context menu: Move to…, Duplicate, Delete, Open in Explorer actions
- Usage logging compatible with the dashboard Usage tab (logged under `data/ai/logs/usage/`)
- Persistent workspace state — remembers open tabs, last workspace, and recent projects per folder
- Project context injection — the AI receives your workspace file structure on every request
- Native OS folder picker for workspace selection
- Resizable 3-panel layout: file tree · Monaco editor · AI chat

### 🎙️ Audio Interaction (Core)
- Built-in Text-to-speech (TTS) and speech-to-text (STT) support within the dashboard and chat.
- **Misaka TTS voice UI** — select voice profiles directly from the chat interface.
- **Local TTS/STT routing** — routes to local audio models when loaded, falls back to browser/API.
- Configurable voice profiles and audio processing settings.

### 🔊 Local Audio Models
- **Audio Models tab** in the dashboard for managing local TTS and STT models.
- **Kokoro** (TTS) — lightweight, fast local text-to-speech model.
- **XTTS-v2** (Coqui TTS) — high-quality TTS with voice cloning support; cloned voice WAVs stored under `localmodels/audio/voices/`.
- **Whisper** (faster-whisper) — accurate local speech-to-text transcription.
- Model lifecycle management: load/unload models, generate TTS, transcribe audio, manage cloned voices, and install pip packages via the dashboard.
- Models stored under `localmodels/audio/`; GGUF chat models under `localmodels/gguf/`.

### 🎵 Aethvion Audio (Standalone)
- Full multi-track timeline editor with per-track volume, solo, and pan.
- Professional waveform visualization with gradient rendering and real-time effects.
- Format conversion and effects pipeline (Normalization, Gain, Pitch, Speed).

### 🎮 Games
- Built-in games: Logic Quest, Blackjack, Sudoku, Word Search, Checkers (vs AI)
- Leaderboard to track scores across sessions

### 🎭 VTuber & 📊 Tracking
- **Aethvion VTuber:** Visualization and animation engine — rigging, real-time deformation, preview/live modes
- **Aethvion Tracking:** Motion tracking via WebSocket at port 8082, streams parameters directly to the VTuber viewer
- **Revamped Tracking UI** with a live HUD overlay, real-time telemetry readout, and FPS counter
- Live mode auto-discovers the tracking server; browser connects directly with auto-reconnect

### 🔌 Nexus Module
- Peripheral plugin hub — screen capture, webcam, Spotify, weather, system info
- Registry-driven architecture for adding new integrations

### 📊 Dashboard Tabs (25+)

| Tab | Status | Notes |
|-----|--------|-------|
| Chat | ✅ Working | Threads, context, model selection, auto-routing |
| Image | ✅ Working | Imagen 3 / DALL-E 3 image generation |
| Audio | ✅ Working | Text-to-speech and speech-to-text; Misaka TTS voice selection |
| Arena | ✅ Working | Side-by-side model comparison with enhanced leaderboard |
| AI Conversations | ✅ Working | Two-party model conversation with history persistence, human participant, pause/inject, share/export |
| Advanced AI Conversation | ✅ Working | Multi-persona conversation threads |
| Leaderboards | ✅ Working | Game scores and rankings |
| Logic Quest | 🎮 Game | AI-powered logic puzzles |
| Blackjack | 🎮 Game | Classic card game |
| Sudoku | 🎮 Game | Sudoku puzzles |
| Word Search | 🎮 Game | Word search puzzles |
| Checkers (vs AI) | 🎮 Game | Checkers against an AI opponent |
| Misaka Cipher | ✅ Working | Main hub: output files, screenshots, camera, uploads |
| Agent Workspaces | ✅ Working | Create workspaces, run multi-step agent tasks with real-time SSE streaming |
| Tools | ✅ Working | View registered tools and agents |
| Packages | 🧪 Experimental | Package install with safety scoring — unstable |
| Memory | ✅ Working | Browse task history and episodic memory |
| Misaka Memory | ✅ Working | Dedicated episodic memory browser |
| Audio Models | ✅ Working | Manage local TTS/STT models (Kokoro, XTTS-v2, Whisper) |
| Aethvion VTuber | ✅ Working | Character animation and visualization engine |
| Aethvion Tracking | ✅ Working | Motion tracking module with HUD and telemetry |
| Aethvion Code | ✅ Working | AI-powered IDE (standalone app, port 8083) |
| Logs | ✅ Working | Live log stream |
| Documentation | ✅ Working | In-dashboard documentation viewer |
| Usage | ✅ Working | Token usage, cost tracking, Local/API filters, and granular queries |
| Status | ✅ Working | System and provider health |
| Port Manager | ✅ Working | View and manage active service ports |
| Settings | ✅ Working | Tabbed Model Registry, routing profiles, Discord, assistant, environment config, self-update |

---

## ⚠️ Known Limitations

- **Autonomous long-running tasks:** Agent execution works for single well-defined tasks, not multi-step plans over hours or days.
- **Memory integration:** Memory is stored reliably but not yet deeply wired into agent decision-making.
- **Tool forge reliability:** Simple tools generate fine; anything requiring external libraries or complex multi-file output can be unreliable.
- **Ollama / vLLM:** Not yet supported. Local inference uses llama-cpp-python (GGUF files) directly.
- **Production hardening:** This is a personal/research project, not audited or hardened for production deployments.

---

## 📁 Directory Structure

```
Aethvion-Suite/
├── Start_Aethvion_Suite.bat     # One-click install + launch (main dashboard)
├── pyproject.toml               # All dependencies + project metadata
│
├── core/                        # Shared AI core — used by all apps and the dashboard
│   ├── main.py                  # Entry point (web / CLI / test modes)
│   ├── nexus_core.py            # Central orchestration hub
│   ├── config/                  # Configuration files (YAML/JSON)
│   │   ├── suggested_apimodels.json      # Suggested cloud model configs
│   │   ├── suggested_localmodels.json    # Suggested GGUF model configs
│   │   └── suggested_localaudiomodels.json # Suggested local audio model configs
│   ├── factory/                 # Agent spawning engine
│   ├── forge/                   # Tool generation pipeline
│   ├── memory/                  # Episodic memory + knowledge graph (ChromaDB)
│   │   └── agent_workspace_manager.py   # Agent workspace and thread state manager
│   ├── nexus/                   # Nexus manager (peripheral plugin system)
│   ├── orchestrator/            # Master orchestrator + task queue
│   │   ├── agent_events.py      # Thread-safe per-task SSE event store
│   │   └── agent_runner.py      # ReAct-style multi-step agent execution loop
│   ├── providers/               # Google / OpenAI / Grok / Anthropic / Local adapters
│   ├── security/                # Intelligence Firewall
│   ├── utils/                   # Shared utilities
│   │   └── paths.py             # Canonical data path constants (single source of truth)
│   ├── workers/                 # Background workers
│   ├── workspace/               # Usage tracker, package manager
│   └── interfaces/
│       ├── dashboard/           # Web dashboard (FastAPI + static files)
│       │   ├── agent_workspace_routes.py  # Agent workspace + browse API
│       │   ├── audio_models_routes.py     # Local TTS/STT model management API
│       │   └── task_routes.py             # Task submission + SSE streaming endpoint
│       └── cli_modules/         # CLI module implementations
│
├── apps/                        # Standalone apps — each has its own server + launcher
│   ├── audio/                   # Audio processing (TTS / STT)
│   │   ├── models/              # Local audio model adapters (Kokoro, XTTS-v2, Whisper)
│   │   └── tts_manager.py       # TTS model lifecycle manager
│   ├── code/                    # Code IDE — Monaco editor + AI copilot (port 8083)
│   │   ├── Start_Code.bat       # One-click launcher
│   │   ├── code_server.py       # FastAPI backend — FS, execution, AI, threads, usage
│   │   └── viewer/              # Frontend: Monaco editor, file tree, AI chat
│   ├── driveinfo/               # System storage and drive info
│   ├── finance/                 # Finance tracking + AI market analysis
│   ├── hardwareinfo/            # System hardware information
│   ├── photo/                   # AI-powered photo editing
│   ├── tracking/                # Motion tracking — WebSocket server (port 8082)
│   └── vtuber/                  # VTuber engine — character animation (port 8081)
│
├── data/                        # Runtime data — never committed
│   ├── apps/                    # Per-app runtime data (arena, audio, code, finance, …)
│   ├── config/                  # Runtime config (model_registry.json, settings.json)
│   ├── history/                 # Persistent conversation history
│   │   ├── chat/                # Standard Misaka chat sessions
│   │   ├── ai_conversations/    # AI Conversations saves (JSON per conversation)
│   │   └── agents/              # Agent workspace thread history
│   ├── logs/                    # Usage logs (YYYY-MM/usage_YYYY-MM-DD.json) + system logs
│   ├── system/                  # Lock file, launcher log, ports registry
│   ├── vault/                   # Persistent brain (personas, knowledge graph, episodic)
│   └── workspaces/              # Output files, uploads, tools, projects, preferences
│
├── localmodels/                 # Model files — never committed
│   ├── gguf/                    # GGUF chat models (llama.cpp)
│   └── audio/                   # TTS / STT / voice models
│       └── voices/              # Voice cloning source WAVs (XTTS-v2)
│
├── tools/                       # Tool registry (standard + AI-generated)
├── tests/                       # Test suite
└── assets/                      # Static assets (character sprites, showcase images)
```

---

## 🗺️ Roadmap

### ✅ Done
- Multi-provider chat with failover and auto-routing
- Local GGUF model support via llama-cpp-python
- Persistent threads and task memory
- Tool forge and agent spawning
- Intelligence Firewall (PII/credential scan)
- Web dashboard with 25+ tabs
- API usage tracking with cost estimates (Local/API filters)
- LLM Arena with enhanced leaderboard, system prompt pass-through
- Image Studio (Imagen 3, DALL-E 3)
- Advanced AI Conversation (multi-persona)
- Routing profiles with configurable model pools
- Discord integration (bot worker, message mirroring, dashboard controls)
- Audio tab (TTS and STT) with local TTS routing and Misaka voice selection
- Local Audio Models: Kokoro (TTS), XTTS-v2 (voice cloning), Whisper (STT)
- Tabbed Model Registry UI with suggested model configs and registry support
- Games suite with leaderboards
- Aethvion VTuber and Tracking (WebSocket bridge, live mode, HUD + telemetry)
- Nexus peripheral module with refresh button
- Documentation viewer, Port Manager, and in-dashboard assistant
- **Code IDE** — Monaco editor, AI copilot, file creation, streaming execution, persistent workspace, chat threads, Ctrl+P palette, status bar, Project Notes, python-exec blocks, continuation loop
- **AI Conversations** — human participant, pause/inject, continue conversation, shareable links, participant personality, history persistence
- **Agent Workspaces** — create workspaces and threads, ReAct-style agent runner, real-time SSE step streaming, step history
- Self-update via dashboard (Settings → Version Control)
- Centralized data path management (`core/utils/paths.py`)
- Aethvion Hardware Info app
- Finance: AI market analysis and per-ticker detail panel with live data

### 🔄 In Progress / Near-Term
- Improved agent reliability for multi-step goals
- Better memory integration in decision making
- Tool forge validation and reliability improvements
- Ollama integration for local model management UI
- Code IDE: diff view, multi-file refactor, git integration

### 🌟 Long-Term Vision
- Reliable autonomous multi-step goal execution
- Self-improving architecture (system modifies itself based on usage)
- True infinite sessions with human-in-the-loop checkpoints

---

## 🤝 Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
git clone https://github.com/Aethvion/Aethvion-Suite.git
cd Aethvion-Suite
pip install -e ".[memory]"
cp .env.example .env   # Windows: copy .env.example .env
```

---

## 📝 License

[MIT License](LICENSE)

---

## 🔗 Links

- **Docs:** [/core/documentation/](/core/documentation/)
- **Issues:** [GitHub Issues](https://github.com/Aethvion/Aethvion-Suite/issues)
- **Discussions:** [GitHub Discussions](https://github.com/Aethvion/Aethvion-Suite/discussions)

---

<div align="center">

*An experimental AI platform — building toward something real, one sprint at a time.*

[⭐ Star on GitHub](https://github.com/Aethvion/Aethvion-Suite)

</div>
