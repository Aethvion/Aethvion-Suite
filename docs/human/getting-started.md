# Getting Started with Aethvion Suite

**Updated**: 2026-11-12

---

## What is Aethvion Suite?

Aethvion Suite is a local-first AI platform combining multi-provider chat, AI Companions with 1-on-1 and Group Chat capabilities, 23 native Connectors plus a self-evolving Realtime Incubator, an AI Code workspace, a visual Automate node workflow engine, a Model Hub, a unified Asset Library, and AethvionDB for structured workspace memory.

Versions are derived dynamically from git history (`YYYY.MM.count (shorthash)` via `core/version.py`).

---

## Prerequisites & Setup

- **Python 3.10+**
- **Git** (used for version derivation and repository workflows)
- **LLM Backend** (at least one):
  - **Local**: [Ollama](https://ollama.com/) (`http://localhost:11434`) or local GGUF models managed via the **Model Hub** (`local-models` / `llama-cpp-python`).
  - **Cloud APIs**: Configured in **Model Hub -> API Providers** or environment variables across supported providers (`anthropic`, `deepseek`, `google`, `grok`, `groq`, `mistral`, `openai`, `openrouter`).

### Install & Launch

```bash
git clone <repo-url>
cd Aethvion-Suite
pip install -r requirements.txt
python main.py
```

Open the web dashboard at `http://localhost:8000` (check **System -> Ports** if configured on another port).

---

## Core Workflows

### 1. Chat & Companions
- **Direct Chat (`chat`)**: Multi-provider streaming conversations with model switching and attachments.
- **Companions**: Persistent AI personas (e.g., `misaka-cipher` and custom personas created in **Companion Creator**) with their own memory, voice, avatar, and expression states.
  - Brain state is stored per companion under `data/companions/{companion_id}/`.
  - **Companion Memory (`companion-memory`)**: Inspect and manage companion memory and scratchpad entries.
- **Group Chats**: Multi-companion rooms coordinated server-side by `core/companions/group_conductor.py` and `core/companions/group_chat_engine.py`, with shared scratchpads and tool/connector access stored under `data/companions/groups/{group_id}/`.

### 2. Connectors (`library -> connectors`)
Aethvion Suite includes **23 native connector modules** registered in `core/bridges/registry.json` (covering screen capture, OCR, visual memory, window focus, clipboard, git, processes, media, system info, webcam, tasks, scratchpad, timers, flow state, web search, webpage reader, YouTube, Twitch, Reddit, weather, Spotify, group chat, and `dynamic_toolmaker`).

- **Realtime Incubator**: Companions can create and safely evolve custom Python connectors at runtime under `data/bridges/dynamic/{tool_id}/` using the Non-Destructive Evolution Protocol (`core/bridges/dynamic_manager.py`).
- **Connector Profiles**: Manage connector presets and active scopes from the **Connectors** tab.

### 3. Code (`code`)
Interactive coding workspace with project context, file editing, and multi-model assistance.

### 4. Automate (`automate`) & Asset Pipeline
- **Automate**: Node-based workflow builder supporting multi-model chains, branching, loops, retries, and sub-workflows.
- **Model Hub (`model-hub`)**: Manage `local-models`, `image-models`, `audio-models`, `api-providers`, and `3d-models` (`core/modelhub/`).
- **Asset Library (`workspace -> asset-library`)**: Unified gallery and storage for generated images, audio, and 3D assets (`core/assets/`).

### 5. AethvionDB (`aethviondb`)
Structured graph and knowledge workspace (`data/aethviondb/<name>/`) with Explorer, Distiller, Graph, Import, and Tools tabs for organizing entities, sections, and relationships.

---

## Dashboard Navigation

The sidebar organizes views into pinned core tools and 8 collapsible categories (`core/interfaces/dashboard/static/js/sidebar-manager.js`):

- **Pinned / Core**: `suite-home`, `chat`, `code`, `automate`, `aethviondb`, companions (e.g. `misaka-cipher`), `companion-creator`, `companion-memory`, `settings`
- **Workspace**: `agent-corp`, `schedule`, `asset-library`, `photo`, `audio`, `3d-gen`
- **Research**: `advaiconv`, `researchboard`, `arena`, `aiconv`, `explained`
- **Memory**: `memory`, `persistent-memory`, `sched-overview`
- **Storage**: `output`, `screenshots`, `camera`, `uploads`
- **Model Hub**: `local-models`, `image-models`, `audio-models`, `api-providers`, `3d-models`
- **Library**: `voice-library`, `connectors`
- **System**: `logs`, `documentation`, `usage`, `status`, `ports`
- **Experimental**: `physics-lab`, `stats-lab`, `chembio-lab`, `worldsim`, `project-mapper`, `decision-trace`, `lexmap`, `supplymind`, `clinicaltrace`

---

## Running Tests

```bash
pytest
```

---

## Next Reading

- [Architecture Overview](readme-overview.md)
- [Documentation Index](../README.md)
- [AethvionDB Overview](../aethviondb/overview.md)
- [Automate Overview](../automate/overview.md)
