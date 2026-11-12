AGENT SYSTEM MISSION & GUARDRAILS
==================================

IDENTITY: You are operating inside Aethvion Suite, a local-first AI platform with multi-provider routing, AI Companions & Group Chats, 23 native Connectors + Realtime Incubator, Model Hub, Asset Library, Automate workflows, Code IDE, and AethvionDB.

CORE PRINCIPLES
1. Security First: Never bypass `core/security/` firewall rules or expose API keys, credentials, or PII.
2. Canonical Paths: Always import filesystem paths from `core/utils/paths.py` (`DATA`, `COMPANIONS`, `COMPANION_GROUPS`, `BRIDGES_DATA`, `DYNAMIC_CONNECTORS`, `CODE`, `AETHVIONDB`, `MODES`, `CONFIG`, `LOGS`).
3. Multi-Provider Resilience: Route through `AetherCore` (`core/orchestrator/aether_core.py`) across the 10 configured providers (`anthropic`, `deepseek`, `google`, `grok`, `groq`, `local`, `mistral`, `ollama`, `openai`, `openrouter`) and Model Hub (`core/modelhub/`).
4. Non-Destructive Connector Evolution: Dynamic connectors created via `dynamic_toolmaker.py` live under `data/bridges/dynamic/{tool_id}/` and must follow `core/bridges/dynamic_manager.py` versioning/rollback rules.
5. Git-Derived Versioning: Never invent or hardcode version numbers; `core/version.py` computes `YYYY.MM.count (shorthash)` from git.
6. Test Verification: Run `pytest` after modifying `core/` or `apps/` logic.

BOUNDARIES
- Allowed: Creating/updating companions, dynamic connectors, Automate workflows, AethvionDB entries, Code workspace files, and verified bug fixes/features.
- Prohibited: Disabling firewall rules, leaking secrets into logs/responses, bypassing `core/utils/paths.py`, or running destructive `rm`/reset operations without explicit user confirmation.

LAST UPDATED: 2026-11-12
