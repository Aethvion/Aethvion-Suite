# Dashboard Interface Context

This document maps the Aethvion Suite Dashboard UI (`core/interfaces/dashboard/`) for AI assistants and developers.

---

## Navigation Architecture

Registered in `core/interfaces/dashboard/static/js/sidebar-manager.js`.
Tab switching is handled by `switchDashboardTab(tabId)` or `[SwitchTab: tab_id]` tags in assistant responses.

### Pinned / Core Tabs
- `suite-home` — Suite Home landing overview (`panel-home`)
- `chat` — Multi-provider LLM Chat
- `code` — Code IDE & agentic coding workspace
- `automate` — Visual node workflow builder
- `aethviondb` — Structured knowledge & graph workspace
- Companions — Dynamic companion tabs (e.g. `misaka-cipher`), plus `companion-creator` and `companion-memory` (Companions view also hosts 1-on-1 chat and **Group Chats**)
- `settings` — Global settings & sidebar profile customization

### Sidebar Categories (8)
1. **Workspace (`workspace`)**: `agent-corp`, `schedule`, `asset-library`, `photo`, `audio`, `3d-gen`
2. **Research (`research`)**: `advaiconv`, `researchboard`, `arena`, `aiconv`, `explained`
3. **Memory (`memory`)**: `memory`, `persistent-memory`, `sched-overview`
4. **Storage (`storage`)**: `output`, `screenshots`, `camera`, `uploads`
5. **Model Hub (`model-hub`)**: `local-models`, `image-models`, `audio-models`, `api-providers`, `3d-models`
6. **Library (`library`)**: `voice-library`, `connectors` (Native Connectors, Realtime Incubator, Profiles)
7. **System (`system`)**: `logs`, `documentation`, `usage`, `status`, `ports`
8. **Experimental (`experimental`)**: `physics-lab`, `stats-lab`, `chembio-lab`, `worldsim`, `project-mapper`, `decision-trace`, `lexmap`, `supplymind`, `clinicaltrace`

---

## Key UI Subsystems
- **Connectors (`connectors`)**: Displays the 23 native bridges (`core/bridges/registry.json`), the **Realtime Incubator** for dynamic connectors (`core/bridges/dynamic_manager.py`), and connector profiles.
- **Model Hub (`model-hub`)**: Unified model management for local GGUF, image, audio, 3D, and cloud API providers (`core/modelhub/`).
- **Asset Library (`asset-library`)**: Unified gallery and metadata store for generated media (`core/assets/`).
- **Companions & Group Chat**: Supports 1-on-1 companion conversations and multi-companion Group Chats (`core/companions/group_conductor.py`) with shared scratchpads and connector execution.

**Last Updated**: 2026-11-12
