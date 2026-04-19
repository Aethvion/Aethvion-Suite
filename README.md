<div align="center">

# Aethvion Suite

**Your private AI super-app — companions, agents, creative tools & more, all self-hosted**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)

[Documentation](https://github.com/Aethvion/Aethvion-Suite/tree/main/core/documentation) · [Quick Start Guide](https://github.com/Aethvion/Aethvion-Suite/blob/main/core/documentation/human/getting-started.md) · [Discussions](https://github.com/Aethvion/Aethvion-Suite/discussions)

</div>

<br>

**Aethvion Suite** is a powerful, self-hosted AI platform combining the best cloud models (Gemini, GPT-4o, Claude, Grok) with fast local GGUF models — all in one unified, privacy-first dashboard.

Run intelligent agents on your own code and files, chat with persistent AI companions who actually remember you, generate images and audio, research any topic with a multi-expert board, play AI-powered games, and automate recurring tasks. Everything runs on **your machine**, under **your control**.

Whether you're a developer, creator, researcher, or just want a powerful personal AI setup, Aethvion Suite gives you a unified workspace that adapts to how *you* want to use it.

**Current version: v15**

### ✨ Key Highlights

- **AI Companions** — Persistent characters with memory, moods, tools, and workspace access; they remember who you are across every session
- **Hybrid Intelligence** — Seamlessly mix cloud APIs (Gemini, GPT-4o, Claude, Grok) and local GGUF models with smart auto-routing and failover
- **Powerful Agents** — Multi-step ReAct agents with file access, shell execution, and real-time streaming output
- **Agent Corp** — Create multi-worker AI organizations with specialized roles; assign complex projects and watch them collaborate
- **Research Board** — Generate structured expert perspectives on any topic; debate mode lets experts argue across multiple rounds
- **Creative Studio** — Image generation (DALL-E 3, Imagen 3, Stable Diffusion), Audio (TTS/STT with voice cloning), and 3D asset generation
- **Bridges** — Live connections between companions and your environment: Spotify, weather, system stats, screen capture, webcam, and more
- **Privacy First** — Intelligence Firewall scans and blocks sensitive data before it leaves your machine; all data stored locally
- **One-Click Windows Launcher** — `Start_Aethvion_Suite.bat` handles venv creation, dependency installation, and launch

---

## Screenshots

<div align="center">
<img src="assets/showcase/AethvionSuite_HomeScreen.png" alt="Aethvion Suite Home Screen" width="100%">
</div>

<br>

<div align="center">

| | |
|:---:|:---:|
| <img src="assets/showcase/AethvionSuite_Agent.png" alt="Agents" width="100%"> | <img src="assets/showcase/AethvionSuite_AgentCorp.png" alt="Agent Corp" width="100%"> |
| **Agent Workspace** · Multi-step ReAct agent runner with real-time SSE event streaming | **Agent Corp** · Manage and collaborate with multiple persistent specialized agents |
| <img src="assets/showcase/AethvionSuite_MisakaCipher.png" alt="Misaka Cipher Chat Interface" width="100%"> | <img src="assets/showcase/AethvionSuite_Photo.png" alt="Aethvion Suite Photo App" width="100%"> |
| **Companions** · Persistent AI characters with memory, moods, tools, and workspace access | **Aethvion Photo** · AI image generation with DALL-E 3, Imagen 3, and local Stable Diffusion |
| <img src="assets/showcase/AethvionSuite_Audio.png" alt="Aethvion Suite Audio App" width="100%"> | <img src="assets/showcase/AethvionSuite_Code.png" alt="Aethvion Suite Code IDE" width="100%"> |
| **Aethvion Audio** · Local TTS (Kokoro, XTTS-v2) and STT (Whisper) with voice cloning | **Aethvion Code IDE** · Monaco-based IDE with AI copilot and code execution |
| <img src="assets/showcase/AethvionSuite_LocalModels.png" alt="Aethvion Suite Local Models" width="100%"> | <img src="assets/showcase/AethvionSuite_UsagePage.png" alt="Aethvion Suite Usage Page" width="100%"> |
| **Local Models** · Browse, download, and run GGUF models and Ollama models locally | **Usage & Cost Tracking** · Token usage, cost estimates, and per-provider breakdowns |

</div>

---

## What Is Aethvion Suite?

Aethvion Suite is a **self-hosted AI platform** built around three core ideas: **local** (your data, your models, your hardware), **personal** (companions that know you, a dashboard that adapts to you), and **unified** (every AI workflow in one place, and those workflows talk to each other).

### Core Components

| Component | Role | Status |
|---|---|---|
| **AetherCore** | Central AI gateway — routes all requests, manages failover, Intelligence Firewall | Stable |
| **Companion Engine** | Persistent AI companions with memory, moods, tools, and workspace access | Stable |
| **Agent Runner** | ReAct-style multi-step task execution with file I/O and shell commands | Stable |
| **Bridges** | Registry-driven integrations: Spotify, weather, system stats, screen, webcam | Stable |
| **Memory Tier** | Episodic memory (ChromaDB) + knowledge graph + persistent memory + identity | Stable |
| **Schedule Manager** | Cron-based recurring AI task automation with notifications | Stable |
| **Provider Manager** | Multi-provider routing with automatic failover across all AI calls | Stable |

**Cloud Providers:** Google AI (Gemini 2.0 Flash, 1.5 Pro, Imagen 3) · OpenAI (GPT-4o, DALL-E 3) · xAI (Grok) · Anthropic (Claude)
**Local Models:** GGUF via llama-cpp-python · Ollama integration · Kokoro TTS · XTTS-v2 (voice cloning) · Whisper STT
**Intelligence Firewall:** PII/credential scanning before any external API call — sensitive data never leaves your machine.

### Companions

Four distinct AI companions, each with a unique personality, capability set, and persistent memory:

| Companion | Personality | Capabilities |
|---|---|---|
| **Misaka Cipher** | Adaptive, curious, playful | Tools, workspace access, web search, bridges, memory |
| **Axiom** | Analytical, precise, stoic | Tools, workspace access, bridges, memory |
| **Lyra** | Empathetic, creative, warm | Bridges, memory |
| **Nova** | Minimalist, calm, observant | Memory |

Every companion has persistent `base_info.json` (evolving identity) and `memory.json` (dynamic observations about you). Companions learn your preferences across sessions.

### Bridges

Live connections between companions and your environment, called mid-conversation:

| Bridge | What it does |
|---|---|
| `spotify_bridge` | Control Spotify — play, pause, skip, get current track |
| `weather_bridge` | Real-time weather for any location |
| `media_sentinel` | What's currently playing on Windows (any app) |
| `system_bridge` | Live CPU, RAM, and disk usage |
| `screen_capture` | Take a screenshot and share it with the companion |
| `webcam_capture` | Capture a webcam image |

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/Aethvion/Aethvion-Suite.git
cd Aethvion-Suite
pip install -e ".[memory]"

# Configure providers (at least one required)
copy .env.example .env
# Edit .env — add any of: GOOGLE_AI_API_KEY / OPENAI_API_KEY / GROK_API_KEY / ANTHROPIC_API_KEY
# Leave blank to use only local models
```

**One-click (Windows):** Double-click `Start_Aethvion_Suite.bat` — it creates the venv, installs dependencies, and opens the dashboard automatically.

| Application | Launcher | Default URL |
|---|---|---|
| **Suite Dashboard** | `Start_Aethvion_Suite.bat` | http://localhost:8080 |
| **Code IDE** | `apps/code/Start_Code.bat` | http://localhost:8083 |
| **VTuber Engine** | `apps/vtuber/Start_VTuber.bat` | http://localhost:8081 |
| **Audio Editor** | `apps/audio/Start_Audio.bat` | http://localhost:8081* |
| **Photo Editor** | `apps/photo/Start_Photo.bat` | http://localhost:8081* |
| **Finance Hub** | `apps/finance/Start_Finance.bat` | http://localhost:8081* |
| **Drive Info** | `apps/driveinfo/Start_DriveInfo.bat` | http://localhost:8084 |
| **Tracking Bridge** | `apps/tracking/Start_Tracking.bat` | http://localhost:8081* |
| **Hardware Info** | `apps/hardwareinfo/Start_HardwareInfo.bat` | http://localhost:8081* |

*\* Apps sharing port 8081 auto-negotiate the next available port if multiple are running.*

**Manual:**
```bash
python -m core.main           # web dashboard at http://localhost:8080
python -m core.main --cli     # interactive CLI
python -m core.main --test    # run verification tests
```

---

## What's In The Suite

### Companions & Chat
- **Four companions** (Misaka Cipher, Axiom, Lyra, Nova) — each with distinct personality, memory, and capability profile
- Per-session and long-term memory — companions remember preferences, past conversations, and observations about you
- Bridges integration — companions can check weather, control Spotify, read system stats, and more, mid-conversation
- Workspace access — companions can read, write, and search files in permitted directories
- Floating overlay companion (Misaka) — accessible system-wide via hotkey (Ctrl+Shift+Space)

### Research & Analysis
- **Research Board** — simulate a board of experts; each gives a structured perspective; optional live debate mode where experts argue across multiple rounds
- **AI Explained** — generate richly formatted HTML deep-dives on any topic, with persistent threads
- **Model Arena** — blind benchmark: run the same prompt across multiple models simultaneously and rate results
- **Advanced Lab** — structured multi-persona conversations with custom participant profiles

### Agents & Automation
- **Agent Workspaces** — create named workspaces; agents run multi-step ReAct loops (read/write/list/run_command); each step streams live to the dashboard
- **Agent Corp** — build multi-worker AI organizations; assign complex projects across specialized roles
- **Task Scheduler** — cron-based recurring AI tasks; completion triggers notifications with direct links to results
- **Task Queue** — submit, cancel, and monitor background AI tasks with persistent state

### Creative Tools
- **Image generation** — DALL-E 3, Imagen 3, Stable Diffusion WebUI, ComfyUI
- **Audio Studio** — local TTS (Kokoro, XTTS-v2 with voice cloning), STT (Whisper), and a full multi-track timeline editor
- **3D Generation** — text-to-3D and image-to-3D (Trellis 2, TripoSR)
- **Local Model Hub** — browse, download, and manage GGUF models and audio models locally

### Games
- Checkers, Blackjack, Sudoku, Word Search, Logic Quest — all with AI opponents or generation
- **Are You Smarter Than AI?** — gameshow-format trivia: AI Game Master generates questions, you and an AI opponent compete, the GM judges in real time

### System & Integrations
- **External API** — OpenAI-compatible `/v1/chat/completions` endpoint; use Aethvion as a backend for other apps
- **Discord Bot** — connect your Discord server; full bi-directional messaging with companions
- **Usage & Cost Tracking** — token counts, cost estimates, per-provider and per-day breakdowns
- **Persistent Memory** — long-term topic-based knowledge hub; manually curate facts that every companion and agent can retrieve
- **Notification System** — real-time alerts with persistent history, category filtering, and deep-link navigation
- **Port Manager, Logs Viewer, System Status** — full operational visibility

---

## Directory Structure

```
Aethvion-Suite/
├── Start_Aethvion_Suite.bat        # One-click install + launch (Windows)
├── pyproject.toml                  # All dependencies + project metadata
│
├── core/                           # Shared AI core — used by all apps and the dashboard
│   ├── main.py                     # Entry point (web / CLI / test modes)
│   ├── aether_core.py              # Central AI gateway (AetherCore) — routing, failover, firewall
│   ├── bridges/                    # Companion integration layer
│   │   ├── bridge_manager.py       # Registry-driven module loader and dispatcher
│   │   ├── registry.json           # Active bridge module registry
│   │   ├── spotify_bridge.py       # Spotify playback control
│   │   ├── weather_bridge.py       # Real-time weather data
│   │   ├── system_bridge.py        # CPU / RAM / disk telemetry
│   │   ├── media_sentinel.py       # Windows SMTC media info
│   │   ├── screen_capture.py       # Screenshot capture
│   │   └── webcam_capture.py       # Webcam image capture
│   ├── companions/                 # Companion system
│   │   ├── companion_engine.py     # Main chat generator — history, tools, memory, streaming
│   │   ├── companion_routes.py     # FastAPI routes for all companion endpoints
│   │   ├── registry.py             # Companion config loader (CompanionConfig)
│   │   ├── configs/                # Per-companion JSON configs
│   │   │   ├── misaka_cipher.json  # Misaka Cipher — adaptive, tool-enabled
│   │   │   ├── axiom.json          # Axiom — analytical, precise
│   │   │   ├── lyra.json           # Lyra — empathetic, creative
│   │   │   └── simple_companion.json # Nova — minimalist
│   │   └── engine/                 # Shared companion subsystems
│   │       ├── memory.py           # base_info.json + memory.json — init, load, XML update, synthesis
│   │       ├── history.py          # Per-companion conversation history
│   │       ├── streaming.py        # build_bridges_capabilities() — prompt injection helper
│   │       └── tools.py            # Tool block parsing, execution, workspace validation
│   ├── config/                     # Configuration files (version-controlled)
│   │   ├── providers.yaml          # Provider priority and failover config
│   │   ├── security.yaml           # Intelligence Firewall rules
│   │   ├── settings_manager.py     # Settings singleton
│   │   ├── suggested_apimodels.json
│   │   └── suggested_localmodels.json
│   ├── factory/                    # Agent spawning engine (legacy factory pattern)
│   ├── memory/                     # Memory tier
│   │   ├── episodic_memory.py      # Vector-based interaction storage (ChromaDB)
│   │   ├── identity_manager.py     # System identity and Misaka persona management
│   │   ├── knowledge_graph.py      # Entity-relationship graph (NetworkX)
│   │   ├── persistent_memory.py    # Long-term topic-based knowledge hub
│   │   ├── social_registry.py      # Cross-platform user identity mapping
│   │   ├── summarization.py        # Memory consolidation and core insights
│   │   └── file_vector_store.py    # Semantic file indexing (FastEmbed + ChromaDB)
│   ├── orchestrator/               # Task orchestration
│   │   ├── agent_runner.py         # ReAct-style multi-step agent execution loop
│   │   ├── task_queue.py           # Task submission, cancellation, state management
│   │   ├── persona_manager.py      # System prompt building and persona routing
│   │   └── schedule_manager.py     # Cron-based recurring task scheduler
│   ├── providers/                  # AI provider abstraction layer
│   │   ├── provider_manager.py     # Multi-provider routing with failover
│   │   ├── google_provider.py      # Google AI (Gemini, Imagen)
│   │   ├── openai_provider.py      # OpenAI (GPT-4o, DALL-E 3)
│   │   ├── grok_provider.py        # xAI (Grok)
│   │   └── anthropic_provider.py   # Anthropic (Claude)
│   ├── security/                   # Intelligence Firewall
│   │   ├── firewall.py             # Pre-flight PII/credential scanning
│   │   └── scanner.py              # Regex-based content scanning
│   ├── workers/                    # Background workers
│   │   ├── discord_worker.py       # Persistent Discord bot service
│   │   └── package_installer.py    # Async pip package installation
│   ├── workspace/                  # Workspace utilities
│   │   ├── workspace_utils.py      # load_workspaces(), validate_path(), build_workspace_block()
│   │   └── preferences_manager.py  # User preference persistence
│   ├── utils/                      # Shared utilities
│   │   └── paths.py                # Canonical data path constants (single source of truth)
│   └── interfaces/
│       ├── dashboard/              # Web dashboard (FastAPI + static files)
│       │   ├── server.py           # FastAPI app — 32 routers registered
│       │   └── *_routes.py         # Feature route modules (agents, arena, companions, games, …)
│       └── cli_modules/            # CLI module implementations
│
├── apps/                           # Standalone apps — each has its own server + launcher
│   ├── audio/                      # Audio processing (TTS/STT)
│   │   ├── models/                 # Local audio model adapters (Kokoro, XTTS-v2, Whisper)
│   │   └── tts_manager.py          # TTS/STT lifecycle manager
│   ├── code/                       # Monaco-based Code IDE (port 8083)
│   ├── driveinfo/                  # System storage and drive info
│   ├── finance/                    # Finance tracking + AI market analysis
│   ├── hardwareinfo/               # System hardware information
│   ├── photo/                      # AI-powered photo editing
│   ├── tracking/                   # Motion tracking WebSocket server (port 8082)
│   └── vtuber/                     # VTuber character animation engine (port 8081)
│
├── data/                           # Runtime data — never committed
│   ├── companions/                 # Per-companion persistent data
│   │   └── {companion_id}/         # base_info.json, memory.json, history/, uploads/
│   ├── config/                     # Runtime config (model_registry.json, settings.json)
│   ├── modes/                      # Per-mode data (workspaces, agents, schedules)
│   ├── logs/                       # Usage logs + system logs
│   └── workspaces/                 # Output files, uploads, media, projects
│
├── localmodels/                    # Model files — never committed
│   ├── gguf/                       # GGUF chat models (llama.cpp)
│   └── audio/                      # TTS/STT/voice models + voice cloning WAVs
│
└── assets/                         # Static assets (showcase images, character sprites)
```

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
git clone https://github.com/Aethvion/Aethvion-Suite.git
cd Aethvion-Suite
pip install -e ".[memory]"
cp .env.example .env   # Windows: copy .env.example .env
```

---

## License

[AGPL-3.0 License](LICENSE)

---

## Links

- **Docs:** [/core/documentation/](/core/documentation/)
- **Issues:** [GitHub Issues](https://github.com/Aethvion/Aethvion-Suite/issues)
- **Discussions:** [GitHub Discussions](https://github.com/Aethvion/Aethvion-Suite/discussions)

---

<div align="center">

*A local-first AI super-app — private, personal, and always yours.*

[Star on GitHub](https://github.com/Aethvion/Aethvion-Suite)

</div>
