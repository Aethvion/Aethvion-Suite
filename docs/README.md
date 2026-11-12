# Aethvion Suite Documentation

**Note: This documentation was updated on 2026-11-12 to reflect the current Aethvion Suite architecture (git-derived versioning via `core/version.py`).**

---

## 📚 Documentation Structure

This documentation is organized into clear sections for users, contributors, and AI agents operating within the suite:

### 👥 Human Tier (`docs/human/`)
User-friendly guides for humans installing, configuring, and using the system.

- **[readme-overview.md](./human/readme-overview.md)** — System philosophy and architecture
  - The Five Pillars (AetherCore, Companions & Group Chats, Bridges & Realtime Incubator, Workspaces & Automate, Memory & AethvionDB)
  - Model Hub & Asset Library
  - Privacy-first routing and Intelligence Firewall
- **[getting-started.md](./human/getting-started.md)** — Practical guide for new users
  - Installation and setup (Windows one-click, manual venv, Docker headless)
  - API key & local GGUF/Ollama configuration
  - First session with a companion, Group Chats, and `/slash` commands
  - Using Code, Automate, Persistent Memory, and Connectors

### 🤖 AI Tier (`docs/ai/`)
Machine-readable specifications for AI agents and internal prompts operating within the system.

- **[system-spec.md](./ai/system-spec.md)** — Complete technical specification (directory map, data flows, 23 bridges, 10 providers, companions, Model Hub, Asset Library)
- **[agent-mission.md](./ai/agent-mission.md)** — Routing rules, cost-aware model selection, security constraints, and agent coordination
- **[assistant-tools.md](./ai/assistant-tools.md)** — Assistant tools, emotion IDs, and `[SwitchTab]` navigation reference
- **[dashboard-interface-context.md](./ai/dashboard-interface-context.md)** — Full dashboard tab & subtab reference
- **[evolution-logic.md](./ai/evolution-logic.md)** — Self-evolution via the Non-Destructive Evolution Protocol (Realtime Incubator), Multi-Agent Scratchpad, Visual Context Memory, and Companion Memory
- **[version-path.md](./ai/version-path.md)** — Automatic git-derived versioning (`core/version.py`)

### ⚙️ Subsystem Guides
- **[automate/overview.md](./automate/overview.md)** — Visual node-based workflow builder, engine v2 (branching, loops, retries, sub-workflows), Model Hub & Asset Library nodes, and standalone Python compiler
- **[aethviondb/overview.md](./aethviondb/overview.md)** — Structured personal knowledge base, semantic vector search, relationship graph, and dataset baking
- **[interactivedocs/index.html](./interactivedocs/index.html)** — Standalone interactive HTML reference

### 🗺️ Roadmaps (`docs/roadmap/`)
Active engineering plans and live changelogs:
- **[companions-plan.md](./roadmap/companions-plan.md)** — Server-side group chat conductor, companion inner state, relationships, and two-step tool architecture
- **[suite-evolution-plan.md](./roadmap/suite-evolution-plan.md)** — Model Hub, Asset Library, workflow engine v2, and Studio coworker hub

### 🧭 Project Mapper (`docs/projectmapper/`)
Documentation, setup guides, and multi-language token/security benchmarks for the companion MCP server [Aethvion Project Mapper](https://github.com/Aethvion/Aethvion-ProjectMapper).

---

## 🎯 Quick Navigation

| Goal | Where to look |
|---|---|
| Understand what Aethvion Suite is | [readme-overview.md](./human/readme-overview.md) |
| Install and run your first session | [getting-started.md](./human/getting-started.md) |
| Build visual AI & 3D workflows | [automate/overview.md](./automate/overview.md) |
| Build a structured knowledge graph | [aethviondb/overview.md](./aethviondb/overview.md) |
| Inspect technical architecture & paths | [system-spec.md](./ai/system-spec.md) |
| Understand self-evolving connectors | [evolution-logic.md](./ai/evolution-logic.md) |
| See active roadmap & shipped milestones | [suite-evolution-plan.md](./roadmap/suite-evolution-plan.md) |

---

## 🔄 Documentation Version History

- **2026-02-18:** Initial comprehensive documentation created (human tier + AI tier).
- **2026-04-19:** Updated to v15 (Companions, 6 Bridges, AetherCore, 35+ tabs).
- **2026-05-24:** Updated to v16 (Automate, AethvionDB, WorldSim, Code IDE).
- **2026-11-12:** Major update for current architecture:
  - Companions expanded with Group Chats (server-side `group_conductor.py`, natural pacing, `@mentions`, cross-chat retrieval), Multi-Agent Scratchpad, Visual Context Memory, Proactive Timers & Flow State, and inline YouTube/Spotify/Twitch embeds.
  - Bridges expanded to 23 native modules, Connector Access Profiles, `/slash` command autocomplete, and the **Realtime Incubator** (`dynamic_toolmaker` with Non-Destructive Evolution Protocol).
  - **Model Hub** (`core/modelhub/`) and **Asset Library** (`core/assets/`) integrated into Automate v2 (real branching, loops, retries, sub-workflows, 3D & image pipelines).
  - Providers expanded to 10 backends (added DeepSeek, Groq, Mistral, OpenRouter, Ollama).
  - Versioning switched to automatic git-derived `YYYY.MM.count (shorthash)`.
