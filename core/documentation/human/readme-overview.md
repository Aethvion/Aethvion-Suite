# Aethvion Suite - System Overview

**Note: This documentation was updated on 2026-04-19 to reflect the current Aethvion Suite (v1.4) state.**

---

## The Vibe: This Is Not Just an AI App

Aethvion Suite is a self-hosted AI super-app built for people who want a deeply personal, capable AI system without paying a subscription or sending their data to someone else's cloud. It runs entirely on your machine, connects to the AI providers you choose, and grows smarter the more you use it.

Think of it as three things at once:
- **A companion platform** — AI personalities that remember you, your projects, and your preferences
- **An agent engine** — autonomous AI workers that can read files, write code, run commands, and complete multi-step tasks
- **A creative suite** — image generation, 3D models, audio, research, and more, unified in one dashboard

### What Makes It Different?

**🧠 Companions with Real Memory**
Misaka Cipher, Axiom, and Lyra are not just chat modes — they are distinct AI personalities, each with their own memory profile that grows over time. They remember facts about you, adapt to your preferences, and can call on system tools and bridges mid-conversation. The more you talk with them, the more personal and useful they become.

**🔄 Self-Evolution at the Core**
The system doesn't just execute tasks — it solves them through iterative ReAct loops. Agents can read files, write code, run commands, and document their findings as persistent knowledge that future agents and companions can access.

**🔌 Bridges — Real-World Connections**
Companions know what's playing on your Spotify, what the weather is like, what's happening on your system, and what your camera sees — because bridges inject live context directly into their prompts. No manual pasting required.

**🛡️ Privacy by Default**
Everything runs locally. AetherCore's Intelligence Firewall scans every request before it leaves your machine. Sensitive data stays on-device. You choose which providers to trust and when.

---

## Core Architecture: The Five Pillars

### 1. **AetherCore** — The AI Gateway
The single point of entry for every AI request in the system. Every companion message, every agent step, every image generation call routes through AetherCore.

**Key Features:**
- Unified provider abstraction (Google Gemini, OpenAI, xAI Grok, Anthropic, local GGUF)
- Automatic failover between providers (Google → OpenAI → Grok)
- Trace ID generation for complete auditability
- Intelligence Firewall: PII and credential scanning before any external call
- Smart routing based on task complexity and sensitivity

**File:** `core/aether_core.py`

---

### 2. **Companions** — Persistent AI Personalities
The primary user-facing layer. Each companion has a distinct personality, a memory profile that grows with every conversation, and access to tools and bridges.

**Active Companions:**
| Companion | Personality | Strengths |
|---|---|---|
| **Misaka Cipher** | Warm, loyal, direct | General use, memory, creativity |
| **Axiom** | Analytical, precise | Logic, research, structured reasoning |
| **Lyra** | Expressive, creative | Art, writing, creative projects |

**How Companion Memory Works:**
Each conversation is analyzed for `<memory>` XML tags. These are synthesized into a dynamic memory profile (`memory.json`) stored alongside a stable identity file (`base_info.json`). The memory profile is injected into every future conversation, making companions progressively more personalized over time.

**Data paths:**
- Identity: `data/modes/companions/personas/{companion_id}/base_info.json`
- Memory: `data/modes/companions/personas/{companion_id}/memory.json`
- Episodic: `data/modes/companions/memory/{companion_id}/`

**Engine:** `core/companions/companion_engine.py`

---

### 3. **Bridges** — Live System Connections
Bridges connect companions to real-world data sources. Every companion's system prompt is injected with a `{bridges_block}` showing the current state of all active bridges, so companions can reference live data naturally in conversation.

**Active Bridges:**
| Bridge | What It Provides |
|---|---|
| **Spotify** | Currently playing track, artist, playlist |
| **Weather** | Current conditions, temperature, forecast |
| **System** | CPU/GPU/RAM usage, running processes |
| **Media Sentinel** | Active media windows and playback state |
| **Screen Capture** | Screenshots on demand |
| **Webcam Capture** | Webcam images on demand |

**Registry:** `core/bridges/registry.json`
**Manager:** `core/bridges/bridge_manager.py`

---

### 4. **Agents & Workspaces** — Autonomous Execution
Two modes of agent execution, from single tasks to complex multi-agent workflows:

**Agent Workspaces (Agents tab)**
- Single agents performing multi-step ReAct loops
- Actions: `read_file`, `write_file`, `list_dir`, `run_command`, `done`
- Real-time streaming via SSE — watch every step as it happens
- Working directory = selected workspace folder
- Max 20 iterations per task

**Agent Corp (Agent Corp tab)**
- Multi-agent coordination for complex, parallel objectives
- Higher-level orchestration than individual agent tasks

**Schedule (Schedule tab)**
- Cron-based recurring AI tasks
- Completion notifications with deep-linking to results
- Background execution with persistent history

**Runner:** `core/orchestrator/agent_runner.py`

---

### 5. **Memory Tier** — Knowledge Persistence
A multi-layered cognitive system ensuring everything the suite learns today is available tomorrow.

**Layers (fastest to slowest retrieval):**
1. **Companion Memory** — per-companion dynamic profile (base_info.json + memory.json)
2. **Persistent Memory** — curated long-term facts and topics (Knowledge Hub)
3. **Core Insights** — recursive summarization of interactions into behavioral patterns
4. **Episodic Memory** — raw interaction logs with semantic embeddings (ChromaDB)
5. **Knowledge Graph** — NetworkX-based mapping of tools, agents, and concepts

---

## The Dashboard: Everything in One Place

Aethvion Suite is organized into a configurable sidebar. Every tab can be shown or hidden, grouped into folders, and saved as named layout profiles — so your dashboard only shows what you actually use.

**Default folder layout:**

| Folder | Tabs |
|---|---|
| Workspace | Chat, Agents, Agent Corp, Schedule, Photo, Audio, 3D Workspace |
| Research | Adv. AI Conv., Research Board, Arena, AI Conv., Explained |
| Companions | Misaka Cipher, Axiom, Lyra, Create Companion |
| Entertainment | Games Center |
| Memory | Memory, Companion Memory, Persistent Memory, Schedule Overview |
| Storage | Output, Gallery, Camera, Uploads |
| Model Hub | Text & Chat Models, Image Models, Audio & Speech, 3D Models, API Providers |
| System | Logs, Docs, Usage, Status, Ports |

**Built-in games:** Checkers (vs Aethvion AI), Are You Smarter Than AI?, Sudoku, Blackjack, Word Search, Logic Quest

**Creative tools:** AI image generation, 3D asset generation, AI photo studio, Kokoro TTS, XTTS-v2 voice cloning, Whisper STT

**Research tools:** Research Board (multi-director AI debate), Advanced AI Conversations (structured multi-agent lab), LLM Arena (model comparison)

---

## Technical Foundation

### Stack
- **Language:** Python 3.10+
- **Web Framework:** FastAPI + uvicorn (`http://localhost:8080`)
- **Vector DB:** ChromaDB (companion episodic memory)
- **Graph Engine:** NetworkX (knowledge relationships)
- **Persistence:** JSON-based storage (`data/` directory via `core/utils/paths.py`)
- **Frontend:** Vanilla JS with partial loader, sidebar profile system, SSE streaming

### AI Provider Support
| Provider | Models | Role |
|---|---|---|
| Google AI | Gemini 2.0 Flash, Gemini 1.5 Pro, Imagen 3 | Primary |
| OpenAI | GPT-4o, GPT-4o-mini, DALL-E 3 | Fallback |
| xAI | Grok-3 Mini Fast | Tertiary |
| Anthropic | Claude | Optional |
| Local GGUF | llama-cpp-python | Zero-cost bulk tasks |
| Local Audio | Kokoro, XTTS-v2, Whisper | TTS/STT/voice cloning |

### Security Features
- Intelligence Firewall pre-scans all requests (PII + credential regex detection)
- Flagged data routed to local processing or user-warned before external call
- No external data leakage on blocked requests
- Complete audit trail with Trace IDs on every request

---

## The Infinite Session Goal

Traditional AI handles discrete, bounded tasks. Aethvion Suite aims higher.

**Simple example:**
```
User: "Analyze this Python project for performance bottlenecks"
→ Agent reads all .py files
→ AetherCore routes analysis to appropriate model
→ Agent writes findings to workspace
→ Companion summarizes results in chat
→ Key findings stored in Persistent Memory for future reference
Result: Actionable report, all steps traceable
```

**Ambitious example:**
```
User: "Build me a portfolio website for my photography"
→ Lyra companion discusses aesthetic and structure
→ Agent Corp spawns frontend + content agents in parallel
→ Photo bridge provides sample images on demand
→ Schedule sets up a weekly "refresh portfolio" task
→ Persistent Memory stores project decisions for continuity
Result: Complete website, with ongoing automation built in
```

---

## Getting Started

Ready to dive in? Check out [getting-started.md](./getting-started.md) for:
- Installation and setup
- API key configuration
- First conversation with a companion
- Example use cases
- Best practices

---

## Philosophy

Aethvion Suite is built on a simple idea: **your AI should work for you, not the other way around.** It runs on your hardware, stores your data locally, respects your privacy, and becomes more useful over time — not because the cloud got smarter, but because you taught it what matters to you.

The goal is not to replace human creativity or judgment. It's to remove the friction between an idea and the result.

---

**Last Updated:** 2026-04-19

**Need technical details?** → [AI Documentation](/core/documentation/ai/)

**Questions?** → Check the root [README.md](../../README.md) for community and support
