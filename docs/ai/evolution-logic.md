AETHVION SUITE EVOLUTION & SELF-MODIFICATION LOGIC
=======================================================

PURPOSE: Safe, non-destructive protocols for capability extension, companion growth, and codebase maintenance.

1. REALTIME CONNECTOR EVOLUTION (Non-Destructive Evolution Protocol)
Subsystem: core/bridges/dynamic_manager.py + core/bridges/dynamic_toolmaker.py
Storage: data/bridges/dynamic/{tool_id}/
Protocol:
- Companions can propose and synthesize custom Python connectors at runtime via the Realtime Incubator (`/toolmaker`).
- Existing connectors are NEVER destructively overwritten in place when another companion or request upgrades them:
  - Changes create versioned revisions / candidate updates rather than clobbering active behavior.
  - Usage counts, companion feedback, and compatibility are tracked so proven connectors can be promoted to native `core/bridges/` modules cleanly.
- Safety rules:
  - Validate syntax and required interface before activation.
  - Preserve rollback capability to prior working versions.
  - Expose lifecycle, versions, and status in the Dashboard Connectors view (`library -> connectors`).

2. COMPANION MEMORY & GROUP COORDINATION
Subsystem: core/companions/ + core/memory/
Storage:
- 1-on-1 Companion Brain: data/companions/{companion_id}/
- Group Chats & Shared Scratchpads: data/companions/groups/{group_id}/
- Episodic & Knowledge Memory: ChromaDB + NetworkX knowledge graph + persistent_memory.json
Guidelines:
- Keep 1-on-1 personal scratchpads/memories distinct from shared group scratchpads (`core/companions/group_conductor.py` + `scratchpad_bridge.py`).
- Preserve companion persona definitions and user-curated memory entries across upgrades.

3. WORKSPACE & CODEBASE MODIFICATION RULES
- Canonical Paths: Always import paths from `core/utils/paths.py`. Never hardcode `data/modes/companions/` (companions moved to `data/companions/`, Code moved to `data/code/`).
- Versioning: Never hardcode version strings; `core/version.py` derives `YYYY.MM.count (shorthash)` from git.
- Verification: Run `pytest` after structural or behavioral changes and verify affected FastAPI routes.

LAST UPDATED: 2026-11-12
