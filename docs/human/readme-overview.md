# Aethvion Suite — System Overview

**Note: This documentation was updated on 2026-11-12 to reflect the current Aethvion Suite architecture.**

---

## The Vibe: Not Just Another Chat Wrapper

Aethvion Suite is a self-hosted AI platform and R&D environment built for people who want a deeply personal, capable AI system without paying a subscription or surrendering their data to someone else's cloud. It runs locally on your machine, routes across the cloud or local models you choose, and expands its own capabilities as you work with it.

Think of it as five tightly integrated systems in one dashboard:
- **A companion & multi-agent platform** — persistent AI personalities in 1-on-1 chats and server-conducted group chats with shared scratchpads, visual memory, and cross-chat recall
- **An autonomous code & agent engine** — workers that read files, patch code, run shell commands, and coordinate on shared tasks
- **A multi-model automation layer** — visual node-based workflow builder (`Automate`) wired into a unified `Model Hub` and `Asset Library`
- **A structured knowledge layer** — `AethvionDB` entity/vector graph plus multi-tier companion and persistent memory
- **A creative & research suite** — image generation, 3D asset pipelines, local TTS/STT/voice cloning, LLM Arena, and Research Board

---

## Core Architecture: The Five Pillars

### 1. **AetherCore** — The AI Gateway
The single point of entry for AI routing, cost tracking, and privacy enforcement (`core/aether_core.py`).

**Key Features:**
- **10 Provider Backends:** Google AI (Gemini), OpenAI, Anthropic (Claude), xAI (Grok), DeepSeek, Groq, Mistral, OpenRouter, Ollama, and Local GGUF (`llama-cpp-python`)
- **Automatic Failover:** Priority-ordered provider queue with automatic session failover when a provider rate-limits or goes offline
- **Intelligence Firewall:** Pre-scans outbound prompts for PII and credentials before data leaves the machine, blocking or routing sensitive requests locally
- **Traceability:** Every call receives a unique Trace ID and logs token/cost usage

---

### 2. **Companions & Group Chats** — Persistent AI Coworkers
Companions are the primary human-facing layer (`core/companions/`). Each companion has a JSON personality config, evolving memory, visual expressions, and access to live tools.

**Built-in Companions & Creator:**
- **Misaka Cipher**, **Axiom**, **Lyra**, plus any custom companions built in **Companion Creator** (e.g., *Ruiko Saten*)

**Key Companion Capabilities:**
- **1-on-1 & Group Chats:** Multi-companion rooms driven by a server-side conductor (`core/companions/group_conductor.py`) with natural human pacing, `@mentions`, `[pass]` silence, and emoji reactions (`[react:👍]`)
- **Cross-Chat Recall:** Companions in 1-on-1 chat automatically detect references to group chats (or search them via the `group_chat` bridge) so ideas brainstormed in a group can be implemented 1-on-1
- **Multi-Agent Scratchpad Ledger:** Thread-safe shared Markdown/JSON whiteboard with author-colored pills and hover attribution (`core/companions/engine/scratchpad.py`) — available in both 1-on-1 and Group Chats
- **Visual Context Memory:** Companions snapshot, index, and compare screenshots of Unity scenes, Blender models, code, or UI layouts across sessions (`core/companions/engine/visual_memory.py`)
- **Proactive Flow State & Self-Timers:** Companions can schedule follow-up timers (`companion_timer`) and adapt check-ins to your active work context (`flow_state`)
- **Inline Media Embeds:** Sharing YouTube, Spotify, or Twitch URLs renders interactive playable cards directly inside chat bubbles

**Data paths:**
- Companion data: `data/companions/{companion_id}/` (`base_info.json`, `memory.json`, `history/`, `scratchpad.md`, `visual_memory/`)
- Group chats: `data/companions/groups/{group_id}/` (`meta.json`, `history.json`, `scratchpad.md`)

---

### 3. **Bridges, Connector Profiles & Realtime Incubator** — Real-World Tools
Bridges (`core/bridges/`) connect companions and `/slash` commands to your desktop environment and external services.

- **23 Native Connectors:**
  - *System & Desktop:* `screen_capture`, `screen_ocr`, `visual_memory`, `window_focus`, `clipboard_link`, `git_link`, `process_watcher`, `media_sentinel`, `system_link`, `webcam_capture`
  - *Co-Working & Memory:* `companion_tasks`, `scratchpad`, `companion_timer`, `flow_state`, `group_chat`, `dynamic_toolmaker`
  - *Web & Media:* `web_search`, `webpage_reader`, `youtube_link`, `twitch_link`, `reddit`, `weather_link`, `spotify`
- **Connector Access Profiles:** Fine-grained permission presets (`full_local`, `cloud_safe`, `ambient_observer`, `sandboxed`, or custom profiles) control which connectors a companion or chat session may invoke
- **Realtime Incubator (`dynamic_toolmaker`):** Companions can write, test, and upgrade their own Python connectors on the fly under the **Non-Destructive Evolution Protocol** (AST safety checks, backward-compatibility test verification, automatic rollback on error, and 1-click promotion to Native Suite from **Library → Connectors → Realtime Incubator**)

---

### 4. **Code, Agent Corp, Automate, Model Hub & Asset Library** — Autonomous Execution & Pipelines
- **Code (`apps/code/`)**: Workspace-scoped AI coding IDE with file tools, shell execution, SSE streaming, and project memory
- **Agent Corp (`core/orchestrator/corp_manager.py`)**: Multi-worker agent teams with specialized roles, shared task board, and cost tracking
- **Automate (`core/automate/`)**: Visual node-based workflow builder (~90 node types) with parallel DAG execution, real conditional branching, loops, retries, sub-workflows, and compilation to zero-dependency standalone Python bundles
- **Model Hub (`core/modelhub/`)**: Unified capability-based registry (`text.generate`, `image.generate`, `mesh.generate`, `mesh.texture`, `audio.tts`, etc.) so any workflow node can swap between local servers, CLI tools (like Blender), or cloud APIs via JSON config
- **Asset Library (`core/assets/`)**: Permanent typed asset store (images, 3D meshes, audio, documents) with full lineage tracking (which workflow, run, node, and model produced what)

---

### 5. **Memory & AethvionDB** — Knowledge Persistence
A multi-layered cognitive system ensuring context carries forward across sessions:
1. **Companion Memory:** Per-companion `base_info.json` + `memory.json` updated via `<memory_update>` XML extraction and LLM synthesis
2. **Visual Context Memory:** Persistent screenshot snapshots and visual diffs per companion
3. **Persistent Memory:** Curated long-term knowledge topics (`core/memory/persistent_memory.py`)
4. **Episodic Memory & Core Insights:** ChromaDB semantic interaction store (`core/memory/episodic_memory.py`) + periodic summarization (`core/memory/summarization.py`)
5. **AethvionDB (`core/aethviondb/`):** Multi-database structured entity & relationship graph with semantic vector search, AI distillation, interactive graph explorer, and snapshot baking

---

## The Dashboard: Everything in One Place

The web dashboard (`http://localhost:8080`) uses a drill-down sidebar organized into top-level modes (`Home`, `Chat`, `Code`, `Automate`, `AethvionDB`, Companions) and 8 collapsible categories:

| Category | Tabs |
|---|---|
| **Workspace** | Agent Corp, Schedule, Assets & Models, Photo, Audio, 3D Workspace |
| **Research** | Adv. AI Conv., Directors (Research Board), Arena, AI Conv., Explained |
| **Memory** | Memory, Persistent, Scheduled |
| **Storage** | Output, Gallery, Camera, Uploads |
| **Model Hub** | Text & Chat, Image Models, Audio & Speech, API Providers, 3D Models |
| **Library** | Voice Library, Connectors (Native · Realtime Incubator · Profiles) |
| **System** | Logs, Docs, Usage, Status, Ports |
| **Experimental** | Physics & Math, Data & Stats, Chem & Bio, WorldSim, Project Mapper, DecisionTrace, LexMap, SupplyMind, ClinicalTrace |
