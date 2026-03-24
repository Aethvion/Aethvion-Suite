# Final Plan — Aethvion Suite: The Unified Roadmap

> **Synthesised by:** GitHub Copilot (Coding Agent) — Round 1  
> **Source Plans:** Copilot_Plan.md · Antigravity_Plan.md · Claude_Plan.md  
> **Date:** 2026-03-24  
> **Codebase Version:** v10 (Experimental)  
>
> This document merges, de-duplicates, and prioritises every meaningful proposal from all three contributor plans. Where plans agreed, items were consolidated. Where plans diverged, the best-justified approach was chosen and noted. This document is intended to be the single source of truth for the Aethvion Suite improvement roadmap.

---

## How to Read This Document

| Label | Meaning |
|-------|---------|
| 🔴 **Critical** | Security issue or broken core feature — fix before anything else |
| 🟠 **High** | Significant improvement with broad, immediate impact |
| 🟡 **Medium** | Meaningful quality-of-life improvement |
| 🟢 **Low / Fun** | Nice-to-have, delight feature, or exploratory idea |

Items also carry a **source tag** showing which plan(s) raised them: `[C]` = Copilot, `[A]` = Antigravity, `[Cl]` = Claude.  
Items proposed by multiple sources are tagged with all relevant labels.

---

## Table of Contents

1. [Security & Hardening](#1-security--hardening)
2. [Core Architecture](#2-core-architecture)
3. [Local & Provider Model Layer](#3-local--provider-model-layer)
4. [Memory Tier](#4-memory-tier)
5. [Intelligence Firewall](#5-intelligence-firewall)
6. [The Factory — Agent System](#6-the-factory--agent-system)
7. [The Forge — Tool Generation](#7-the-forge--tool-generation)
8. [Web Dashboard UX](#8-web-dashboard-ux)
9. [Chat & Conversation](#9-chat--conversation)
10. [Code IDE App](#10-code-ide-app)
11. [Audio App](#11-audio-app)
12. [VTuber / Specter Engine](#12-vtuber--specter-engine)
13. [Photo App](#13-photo-app)
14. [Finance App](#14-finance-app)
15. [Arena — AI vs AI Battles](#15-arena--ai-vs-ai-battles)
16. [Games Tab](#16-games-tab)
17. [New App Ideas](#17-new-app-ideas)
18. [Developer Experience & Infrastructure](#18-developer-experience--infrastructure)
19. [Testing & Reliability](#19-testing--reliability)
20. [Fun, Personality & Polish](#20-fun-personality--polish)
21. [Priority Summary Table](#21-priority-summary-table)
22. [Implementation Roadmap](#22-implementation-roadmap)

---

## 1. Security & Hardening

### 1.1 🔴 Fix Wildcard CORS `[C][Cl]`
**File:** `core/interfaces/dashboard/server.py`  
`allow_origins=["*"]` is safe on pure localhost but becomes a real vulnerability the moment the server is exposed on a LAN or VPN.  
**Fix:** Read allowed origins from `aethvion.yaml`, default to `["http://localhost:8080"]`. Provide a `CORS_ORIGINS` env variable for easy override. The TODO comment is already there — do it.

### 1.2 🔴 Optional Dashboard Authentication `[C]`
The dashboard has no login gate. Anyone on the same network can read memory, run agents, and see API-key-adjacent data.  
**Fix:** Add an optional single-user PIN/password layer (session cookie, set in `.env`). If `DASHBOARD_PASSWORD` is unset, auth is skipped (dev mode). No user database needed.

### 1.3 🟠 Rate Limiting on API Routes `[C]`
No rate limiting exists on any FastAPI route. A runaway loop or bad request can hammer an external API and run up serious costs.  
**Fix:** Add `slowapi` (or a simple in-memory token bucket) to the FastAPI app. Sensible defaults: chat 30 req/min, forge 5 req/min. Expose limits in `aethvion.yaml`.

### 1.4 🟠 Secrets Scanning in Forge Output `[C]`
The Forge generates and registers Python code. A malicious prompt could embed API keys in generated tools.  
**Fix:** Run the Intelligence Firewall's scanner on generated tool source code before registration. Refuse registration if credentials are detected.

### 1.5 🟡 HTTPS / TLS Support `[C]`
For LAN or cloud deployments, plain HTTP exposes chat history and API tokens.  
**Fix:** Add a `--tls` flag that loads cert + key from `.env` and starts Uvicorn in SSL mode. Document self-signed cert generation in the Getting Started guide.

### 1.6 🟡 Audit Log Export `[C]`
Trace IDs exist per request but there's no way to search or export the audit log.  
**Fix:** Add an **Audit Log** sub-tab in the Usage page. Filter by date, provider, trace ID. Add CSV export.

---

## 2. Core Architecture

### 2.1 🟠 Streaming Responses `[C]`
Most responses return all at once. Streaming is partially implemented but not consistently used across providers.  
**Fix:** Wire SSE/WebSocket streaming end-to-end for all providers (Google, OpenAI, Anthropic, Grok, local GGUF). Render tokens as they arrive. This is the single biggest perceived-performance win available.

### 2.2 🟠 Circuit Breaker for Providers `[C]`
If a provider returns 5 errors in a row, the system keeps retrying instead of backing off.  
**Fix:** Implement a per-provider circuit breaker (closed → open → half-open). Expose health state in the dashboard header.

### 2.3 🟠 Request Queue with Priority Levels `[C]`
Long-running Forge/Factory tasks currently block the event loop.  
**Fix:** Async priority queue: `chat > memory_query > agent_task > forge_generation`. Background tasks run in a thread pool. Show queue depth in the status bar.

### 2.4 🟡 Plugin / Extension System `[C]`
New tools and agents are hard-coded. No user-extensible plugin surface exists.  
**Fix:** Define a simple `AethvionPlugin` interface. Anything in `core/plugins/` that implements it gets auto-discovered and registered on startup. Document with a sample plugin.

### 2.5 🟡 Preflight Checks on Startup `[C]`
The launcher does minimal checks and surfaces errors poorly (wrong Python version, missing API key, port in use).  
**Fix:** Pre-flight check system that prints a colour-coded summary (`✅ / ⚠️ / ❌`) before the server starts, with actionable messages on critical failures.

### 2.6 🟡 Frontend Error Handling Consistency `[Cl]`
Many API routes return `{"success": false, "detail": "..."}` but the frontend inconsistently reads `data.detail`, `data.error`, `data.message`, or the raw response. This makes error messages unreliable.  
**Fix:** Shared `apiPost()` helper with consistent error extraction and display used by all panels. Reduces debugging time significantly.

### 2.7 🟢 Hot-Reload Config Without Restart `[C]`
Changing `aethvion.yaml` or `providers.yaml` requires a full server restart.  
**Fix:** Add a `POST /api/config/reload` endpoint and a **Reload Config** button in Settings. Use `watchdog` for optional auto-reload on file change.

---

## 3. Local & Provider Model Layer

### 3.1 🔴 Local Model GPU Offload (CUDA) `[Cl]`
The system runs CPU-only despite an RTX 4090 being available. This is a **10–50× speed difference** for local models, making them practically unusable in their current state.  
**Fix:** Install CUDA Toolkit, then:
```
CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --force-reinstall
```
Document this as the first step in the Getting Started guide. This is low effort with enormous impact.

### 3.2 🟠 Ollama Integration `[C][A][Cl]`
All three plans independently identified this as high value. Ollama is the most popular local model runtime, supports GPU offload on all platforms, and exposes a simple REST API.  
**Fix:** Add an `OllamaProvider` targeting `http://localhost:11434`. Auto-detect running Ollama on startup. Show available Ollama models in the model selector alongside GGUF models.

### 3.3 🟠 Model Capability Tags `[C]`
The model selector shows names but not capabilities (vision, code, context window, cost tier).  
**Fix:** Enrich `suggested_models.json` with tags: `vision`, `code`, `long-context`, `cheap`, `reasoning`. Show tags as coloured badges in the model selector.

### 3.4 🟡 Smart Auto-Routing Explanation `[C]`
Auto-routing selects a provider but the logic is opaque.  
**Fix:** Return a `routing_reason` string (e.g., "Selected Gemini Flash — low complexity, cost-optimised") shown as a subtle annotation beneath the AI response.

### 3.5 🟡 Cost Budget Alerts `[C]`
No warning exists when API spend is high.  
**Fix:** Add `monthly_budget_usd` to `aethvion.yaml`. Dashboard banners at 80% and 100% of budget. Optional request blocking when over budget.

### 3.6 🟡 Provider Health Detail `[Cl]`
The status panel shows provider health but not which model is active, last latency, or failure counts.  
**Fix:** More detailed provider status card showing "last 10 calls: 9 OK, 1 failed (500 at 14:32)". Makes debugging far easier.

### 3.7 🟡 vLLM Integration `[C]`
For users with capable GPUs wanting high-throughput local inference.  
**Fix:** Add a `VLLMProvider` speaking to the vLLM OpenAI-compatible API. Configurable base URL in `providers.yaml`.

### 3.8 🟢 Provider Comparison Mode `[C]`
Send the same prompt to two providers simultaneously and compare.  
**Fix:** **Compare Mode** toggle in chat — split-pane showing Provider A vs B, with latency and token cost for each.

---

## 4. Memory Tier

### 4.1 🟠 Wire Memory Retrieval to Chat Context `[A][Cl][C]`
All three plans flag this as the most important memory fix. ChromaDB is set up and stores memories but is not meaningfully injected into chat responses. The memory panel is a browser, not a feature.  
**Fix:** Before every chat response, run a vector search for the top 3 most relevant past memories and prepend them as a concise "Relevant context:" block. Let the user toggle this per-thread. The infrastructure is already in place — it simply needs to be wired to the chat pipeline.

### 4.2 🟠 Memory Retrieval Quality `[C]`
Semantic search relies on default embeddings with no quality filtering.  
**Fix:** Allow the embedding model to be configured (e.g., swap `all-MiniLM-L6-v2` for `nomic-embed-text`). Add a relevance score threshold — results below it are filtered rather than returned with low confidence.

### 4.3 🟡 Memory Timeline View `[C]`
The memory tab shows a flat list. Episodic memories have timestamps but no chronological presentation.  
**Fix:** A **Timeline** view — a chronological strip (like a git log graph) showing memory clusters by day/week. Click a cluster to expand and search within it.

### 4.4 🟡 Memory Tagging and Namespaces `[C]`
All memories go into one pool with no separation between projects or topics.  
**Fix:** Add namespaces and tags to the memory schema. Users assign a namespace per conversation thread. Memory search can be scoped to a namespace.

### 4.5 🟡 Memory Importance Scoring `[C]`
A "hello" chat competes equally with a detailed architecture decision in retrieval.  
**Fix:** Add an importance score (1–10) computed at storage time by the LLM. High-importance memories retrieved with a boost; low-importance ones decay over time via a soft-delete threshold.

### 4.6 🟡 Manual Memory Editing `[C]`
Users can't edit or delete individual memories from the UI.  
**Fix:** Edit/delete buttons on each memory card. Confirm deletion with a modal. Allow direct text editing of the memory entry.

### 4.7 🟡 Memory Export / Import `[C]`
No way to back up or migrate memories.  
**Fix:** **Export All Memories** (JSON/CSV) and **Import Memories** buttons. Imported memories deduplicated via semantic similarity.

---

## 5. Intelligence Firewall

### 5.1 🔴 Complete the Firewall with Local Inference `[Cl]`
The firewall scanner (`core/security/firewall.py`) is a **placeholder**. It detects PII/credentials in a basic way but routes everything to the cloud with only a warning. This is architecturally important and currently not real.  
**Fix:** Load a small local model on startup specifically for firewall use (Llama 3.2 1B or Phi-4 mini — already installed). Run a quick yes/no classification: "Does this input contain harmful intent, sensitive credentials, or PII?" before any cloud call. No large model needed — 1B quantised is sufficient for classification.  
**Why now:** This is the highest-integrity gap in the whole system. Advertising a privacy firewall that doesn't work undermines the platform's core trust proposition.

---

## 6. The Factory — Agent System

### 6.1 🟠 Native Tool Calling API `[Cl]`
The current agent format (ACTION: JSON parsed with `raw_decode`) is fragile and produces "LLM returned malformed JSON" errors regularly. Gemini, OpenAI, and Anthropic all support native function/tool calling.  
**Fix:** Declare available tools as JSON schemas and use the provider's structured tool-call API where available. Eliminates the entire class of JSON parsing failures. Falls back to the current approach for providers that don't support it.

### 6.2 🟠 Agent Persistence and Resume `[C][Cl]`
Agents are transient. A long-running task interrupted by a restart has no way to continue.  
**Fix:** `persistent=True` flag on agent specs. Persistent agents serialise state to disk after each step. On restart, the orchestrator offers to resume incomplete tasks. Add a "Continue this task" button in the Agent Workspace UI — the `AgentState` file cache is already in place.

### 6.3 🟠 More Agent Tools `[Cl][A]`
The agent can read/write files, list directories, and run shell commands. Major missing tools:  
- `web_search` — search the web (Antigravity proposed full Playwright/Selenium browsing; a search API is a simpler starting point)  
- `read_url` — fetch and read a webpage  
- `ask_user` — pause mid-task to ask a clarifying question  
- `run_python` — execute a Python snippet and return the result (sandboxed)  
- `remember` / `recall` — write to and query the Memory Tier  
- `create_file_from_template` — scaffold boilerplate  

> **Note on Autonomous Web Browsing (Antigravity):** Full Playwright/Selenium browser automation is a valuable longer-term goal. `web_search` + `read_url` cover 80% of the research use cases at a fraction of the complexity. Playwright browsing should be added as a follow-on once the simpler tools are stable.

### 6.4 🟠 Deep Memory Integration for Agents `[A]`
Agents don't query past task memory before acting.  
**Fix:** Before an agent takes action, run a vector search for "similar past tasks" and inject successful strategies and past mistakes into the agent's context. Creates a genuinely self-improving loop over time.

### 6.5 🟡 Multi-Agent Coordination `[C][Cl]`
Agents can't communicate or split work.  
**Fix:** Simple **Agent Mesh** — agents post messages to a shared in-memory bus. Add a `delegate_to_agent(agent_name, task)` tool. Show inter-agent communication in the Workspace log.

Use case: "Architect" agent designs a system → "Critic" finds flaws → "Builder" implements. Or AI debate: two agents argue opposite sides, judged by a third.

### 6.6 🟡 Agent Step Display Order Fix `[Cl]`
Step cards render *before* the triggering message bubble in the history view. This makes the history confusing and hard to read.  
**Fix:** Correct the render order so the user's message appears first, followed by the agent's step cards.

### 6.7 🟡 Agent Templates Library `[C]`
Creating an agent requires knowing the Aethvion naming convention and spec format.  
**Fix:** Ship 10–15 pre-built agent templates (file organiser, web scraper, code reviewer, meeting summariser, etc.) accessible from a **Templates** button in the Agent Workspace tab.

### 6.8 🟡 Agent Import / Export `[C]`
Users can't share agent specs.  
**Fix:** **Export Agent Spec** (downloads JSON) and **Import Agent Spec** (upload, validate, register) buttons. Foundation for a community marketplace.

### 6.9 🟢 Agent Task Graph Visualisation `[C]`
Hard to see what an agent actually did.  
**Fix:** **Task Graph** in the Agent Workspace — a node/edge diagram of steps taken, tools called, and files touched. Use D3.js (consistent with existing knowledge graph visualisation).

---

## 7. The Forge — Tool Generation

### 7.1 🟠 TDD Loop — Auto-Generate and Run Unit Tests `[C][A]`
Both plans independently proposed this. Generated tools have no tests and fail silently.  
**Fix:** As part of tool registration (Phase 4), the LLM also generates a pytest test file. The test is run in an isolated subprocess; if it fails, the traceback is sent back to the LLM to fix the code before the tool is finalised. Store the test alongside the tool in the registry. Add a **Run Tests** button on each tool card.

### 7.2 🟠 Multi-Step Tool Decomposition `[C]`
The Forge works for simple tools but complex ones (multiple helper functions, external imports) often fail.  
**Fix:** Add a **decomposition phase** before code generation — the LLM writes a structured plan (function signatures + docstrings), then fills in implementations. Validate each function independently before assembly.

### 7.3 🟡 Tool Versioning `[C]`
Regenerating a tool overwrites the previous version.  
**Fix:** Version numbers on tool registrations. Keep the last N versions (configurable). Version history dropdown on each tool card with diff view.

### 7.4 🟡 Forge Dry Run / Preview Mode `[C]`
Users can't preview a tool before it's registered.  
**Fix:** **Preview** button that runs Phases 1–3 and shows generated code + security scan report without registering. Then **Register** or **Regenerate**.

### 7.5 🟢 Semantic Tool Discovery `[C]`
When a tool that already exists under a different name is requested, the Forge regenerates it.  
**Fix:** Before generating, search the registry using semantic similarity on the description. If a match above 0.8 cosine similarity is found, surface the existing tool and ask "Did you mean this one?"

---

## 8. Web Dashboard UX

### 8.1 🟠 Global Command Palette `[C]`
With 25+ tabs and features spread everywhere, finding things is difficult.  
**Fix:** `Ctrl+K` / `Cmd+K` command palette — floating modal with fuzzy search returning tabs, tools, agents, memory entries, and settings. Direct navigation on selection.

### 8.2 🟠 Dark / Light Theme Toggle `[C]`
The dashboard is dark-only.  
**Fix:** Theme toggle in the top nav. CSS custom-properties-based light theme. Save preference to `localStorage`.

### 8.3 🟡 Notification System `[C]`
No way for background tasks (agents, forge jobs) to alert the user when complete.  
**Fix:** 🔔 notification bell in the top nav. Background tasks post notifications on completion. Use browser `Notification` API for optional desktop notifications.

### 8.4 🟡 Customisable Tab Order and Pinning `[C]`
With 25+ tabs, navigation is unwieldy.  
**Fix:** Drag-to-reorder tabs. ★ pin icon to keep favourites always visible. Store in `preferences.json`.

### 8.5 🟡 Keyboard Navigation `[C]`
Most interactions require a mouse.  
**Fix:** Keyboard shortcuts for common actions (new thread, send message, switch tab). `?` shortcut reference modal.

### 8.6 🟡 Mobile-Responsive Layout `[C]`
Desktop-only.  
**Fix:** Responsive breakpoints at 768px. Hamburger menu for tab list on mobile. Chat interface is highest priority for mobile.

### 8.7 🟢 Customisable Dashboard Home `[C]`
The home screen is a static landing page.  
**Fix:** Customisable widget grid — recent chats, active agents, memory stats, system health, cost today, weather. Drag to rearrange.

---

## 9. Chat & Conversation

### 9.1 🟠 Message Editing and Regeneration `[C]`
Users can't edit a sent message or regenerate a response. This is a baseline expectation.  
**Fix:** **Edit** pencil icon on hover for user messages. Editing re-runs inference from that point and discards subsequent messages. **Regenerate** button on AI messages.

### 9.2 🟠 File and Image Attachments `[C]`
No way to attach files or images to a chat message.  
**Fix:** 📎 attachment button. For vision models (GPT-4o, Gemini 1.5, Claude 3), send the image as vision input. For non-vision models, extract and include text content from PDFs, `.txt`, `.md`, `.py` files. Show thumbnails in chat.

### 9.3 🟡 Memory Retrieval Toggle per Thread `[Cl]`
Memory retrieval (section 4.1) should be configurable per conversation.  
**Fix:** A toggle in the thread header to enable/disable "inject relevant memories." On by default for new threads; users can disable it for casual conversations.

### 9.4 🟡 Thread Search and Export `[Cl][C]`
Threads persist but there is no way to search across them or export them.  
**Fix:**  
- Global search across all thread content by keyword/topic  
- Export a thread as Markdown, PDF, or plain text  
- Archive old threads without deleting them  

### 9.5 🟡 Slash-Command Prompt Templates `[C]`
Users repeat the same prompt patterns (summarise, translate, explain code).  
**Fix:** `/` slash-command shortcut in the chat input. Typing `/summarise` expands to a full prompt template. 20 built-in templates; user-extensible.

### 9.6 🟡 Response Bookmarking `[C]`
Useful AI responses disappear into thread history.  
**Fix:** ⭐ bookmark icon on AI messages. Starred messages in a **Starred** sub-tab. Auto-save starred messages to Memory Tier (optional).

### 9.7 🟡 Conversation Branching `[C]`
No way to explore two different follow-up directions from the same message.  
**Fix:** **Branch** button at any assistant message. New thread forked from that point. Branches shown as a tree in the thread sidebar.

### 9.8 🟡 AI Persona Profiles `[C]`
No way to switch Misaka Cipher's personality.  
**Fix:** **Personas** feature — pre-configured system prompts (tutor, code reviewer, brainstorm partner, devil's advocate). Selectable from a dropdown in the thread header.

### 9.9 🟡 Voice Conversation Mode `[Cl]`
The audio tab has TTS and STT but they're disconnected from the chat pipeline.  
**Fix:** A **voice conversation mode** that runs continuously: STT → send to chat → response → TTS → play, as an automatic loop. Kokoro TTS is fast enough to stream sentence-by-sentence, keeping latency low.

---

## 10. Code IDE App

### 10.1 🟠 Git Integration `[C]`
The IDE shows a git branch in the status bar but supports no git operations.  
**Fix:** Basic git commands in the IDE: `status`, `diff`, `commit`, `log`, `checkout branch`. A **Source Control** panel (VS Code-style). Inline diff gutter markers in Monaco.

### 10.2 🟠 AI Change Diff View `[Cl]`
When the AI rewrites a file, the user just receives the new version. There is no way to see what changed before accepting.  
**Fix:** Side-by-side before/after diff view when the AI proposes file changes. **Accept** / **Reject** buttons before applying. Prevents accidental overwrites.

### 10.3 🟠 Multi-File AI Context `[C]`
The AI receives a flat file tree as context. Large projects overwhelm the context window.  
**Fix:** Smart context selection — AI gets the currently open file + files it imports (parsed via AST for Python/JS). Users manually pin additional files with a 📌 button.

### 10.4 🟡 Ghost Dev Agent `[A]`
The Code IDE has a chat interface but no proactive background analysis.  
**Fix:** Optional background "Dev Agent" that monitors the active editor. On save, it proactively analyses for bugs, runs linting, and generates inline suggestions or unit tests in a split pane — without being explicitly prompted.

> **Note:** Antigravity proposed this. It builds naturally on top of the existing Code IDE chat infrastructure and complements Claude's diff-view proposal (10.2). Both should be implemented together.

### 10.5 🟡 Hand-off to Agent `[Cl]`
The Code IDE copilot is separate from the main agent system.  
**Fix:** A **"Hand off to Agent"** button that sends the current file + a task description to the Agents tab. Makes the IDE and agent system complementary rather than isolated.

### 10.6 🟡 Terminal Persistence `[C]`
The terminal runs commands but doesn't maintain shell state.  
**Fix:** True persistent shell session (xterm.js). Multiple terminal tabs. AI can suggest shell commands with an Approve/Deny gate before execution.

### 10.7 🟢 Pair Programming Ghost Text `[C]`
**Fix:** The AI watches the file being edited and suggests the next logical code block as ghost text overlay, similar to GitHub Copilot inline suggestions. Triggered by 2-second idle.

---

## 11. Audio App

### 11.1 🟠 Effect Presets `[C]`
Effects exist but no preset system.  
**Fix:** Named presets for common effect chains (podcast cleanup, music mastering, voice-over). Save/load custom presets. 5–8 built-in presets shipped.

### 11.2 🟡 AI Transcript and Chapter Markers `[C]`
**Fix:** **AI Analyse** button after recording or importing. Transcribes via Whisper, then the LLM segments the transcript into chapters with titles. Chapter markers added to the timeline as cue points.

### 11.3 🟡 Export Format Options `[C]`
Limited export options.  
**Fix:** MP3, OGG, FLAC, and WAV export with configurable bitrate/quality. Use `pydub` or `ffmpeg` subprocess for conversion.

### 11.4 🟡 MIDI / Tempo Detection `[C]`
**Fix:** BPM detection on imported audio. Display tempo in timeline header. Snap clips to the detected beat grid.

### 11.5 🟢 AI Music Generation Integration `[C]`
**Fix:** **Generate Music** panel — text description ("upbeat lo-fi background track, 120 BPM") calls a local music generation model (MusicGen) or cloud API. Generated audio drops into a new track on the timeline.

---

## 12. VTuber / Specter Engine

### 12.1 🟠 AI Lip-Sync to TTS `[C][A][Cl]`
All three plans proposed this. The VTuber app and TTS system are both present but disconnected.  
**Fix:** Wire TTS audio output through a lip-sync analyser (phoneme extraction from audio waveform) to drive mouth animations in sync with speech. Misaka Cipher should speak her responses visually, not just audibly. This is one of the highest-cohesion improvements available.

### 12.2 🟠 Live Tracking Auto-Connect `[C]`
The Tracking (Synapse) module and Specter engine are separate and require manual steps to connect.  
**Fix:** **Connect Tracking** button in the Specter UI. Auto-discovers the running Synapse instance and subscribes to its stream. Face poses drive the character rig in real-time.

### 12.3 🟡 Desktop Pet Mode `[A]`
Antigravity proposed a compelling extension: run the VTuber as a transparent overlay on the host OS.  
**Execution:** Misaka (or any persona) sits on top of the taskbar, walks around the screen, or faces the active window. When an agent finishes a long-running task, the desktop pet waves and uses local TTS to notify the user.  
**Note:** This is the most ambitious VTuber expansion — implement lip-sync (12.1) and tracking (12.2) first as foundations.

### 12.4 🟡 Expression Trigger Presets `[C]`
**Fix:** Panel of expression buttons (happy, sad, surprised, thinking) that blend the character between pre-defined pose states. Useful for streaming without face tracking.

### 12.5 🟡 Background Scene Management `[C]`
**Fix:** Background layer with preset scenes (solid colour, gradient, chroma-key green, stock backgrounds). Upload custom background image or video loop.

---

## 13. Photo App

### 13.1 🟠 Layer Blend Modes `[C]`
Standard blend modes (Multiply, Screen, Overlay, etc.) are expected.  
**Fix:** 10 most common blend modes in the canvas compositor. Blend mode dropdown in the layer panel.

### 13.2 🟡 AI Inpainting `[C]`
**Fix:** Selection tool (lasso / rectangular marquee). With an area selected, **Fill with AI** sends the selection mask + surrounding context to an inpainting model (Stable Diffusion or DALL-E edit). Composites the result into the canvas.

### 13.3 🟡 Image Generation Gallery `[Cl]`
Images are generated one at a time with no history.  
**Fix:** Local gallery showing prompt → image pairs with the ability to re-run or iterate. Given API cost and generation time, this is a basic productivity feature.

### 13.4 🟡 Non-Destructive Adjustment Layers `[C]`
**Fix:** Adjustment layers (Brightness/Contrast, Hue/Saturation, Curves) that stack on pixel layers without modifying original data.

### 13.5 🟢 AI Style Transfer `[C]`
**Fix:** **Style Transfer** filter applying the visual style of a reference image or preset art style to the canvas using a lightweight neural style transfer model.

---

## 14. Finance App

### 14.1 🟠 Real Market Data Integration `[C]`
The Finance app appears to use placeholder or manual data.  
**Fix:** Integrate a free market data API (Alpha Vantage free tier or `yfinance`). Configurable refresh intervals. Live prices alongside portfolio holdings.

### 14.2 🟡 Budget Tracking and Categories `[C]`
**Fix:** Income/expense transaction entry with category tags. Monthly summary charts (pie: spending by category, bar: income vs expenses). CSV export.

### 14.3 🟡 AI Financial Advisor Chat `[C]`
**Fix:** Dedicated chat panel within Finance, context-aware of the user's portfolio and spending data. "Am I spending too much on dining?" gets grounded answers from actual tracked data.

### 14.4 🟡 Automated Finance Briefing `[A]`
Antigravity's cron workflow example: every morning, an agent fetches market data, summarises portfolio changes, and generates a TTS audio briefing that plays when the dashboard opens.  
**Fix:** Implement as a scheduled task using the cron infrastructure described in section 6 (see also section 18 below).

### 14.5 🟢 Net Worth Timeline `[C]`
**Fix:** Track portfolio value + cash over time. Line chart of net worth history. Milestone markers (first $1,000 saved, etc.).

---

## 15. Arena — AI vs AI Battles

### 15.1 🟠 ELO Leaderboard `[C][Cl]`
Arena battles produce winners but no persistent ranking exists. Both plans raised this.  
**Fix:** ELO rating system per provider/model. Track battles in `data/arena/history.json`. Leaderboard in the Arena tab with ratings, win/loss records, and average response quality.

### 15.2 🟡 Battle Categories `[C]`
All battles use a single format.  
**Fix:** Categories: **Reasoning** (logic puzzles), **Creativity** (story/poem), **Code** (generate a function), **Factual** (Q&A accuracy), **Speed** (first valid answer wins). Specialised judge prompt per category.

### 15.3 🟡 Human Judge Mode `[C]`
AI judging is fast but not always trustworthy.  
**Fix:** **Human Judge** option — both AI responses shown side-by-side without labels (blind evaluation). User picks the better answer. Contributes to the leaderboard.

### 15.4 🟢 Tournament Mode `[C]`
**Fix:** Round-robin or single-elimination tournament across all configured providers. Bracket visualisation. Fun for comparing newly added models.

---

## 16. Games Tab

### 16.1 🟠 AI Explains Its Moves (All Games) `[C]`
AI opponents don't explain why they made a move.  
**Fix:** **AI Commentary** toggle. After each AI move, a speech bubble shows its reasoning. Uses the active provider for real-time explanation.

### 16.2 🟡 Chess with AI Opponent `[C]`
Chess is the canonical AI game and notably missing.  
**Fix:** Integrate `chess.js` and `chessboard.js`. Difficulty levels: Easy (random legal moves), Medium (minimax depth 3), Hard (Stockfish WASM or LLM commentary). Track Elo across sessions.

### 16.3 🟡 AI Trivia Challenge `[C][Cl]`
**Fix:** Real-time trivia quiz where the LLM generates questions on-demand. Choose category and difficulty. Unlimited supply. Track high scores.

### 16.4 🟡 Story Builder / Collaborative Fiction `[C][Cl]`
Both plans proposed a collaborative story game.  
**Fix:** User writes a sentence, AI writes the next, repeat. Genre selectable (fantasy, sci-fi, horror). Save completed stories to Memory. At the end, the AI rates the story and optionally generates a cover image (ties into image generation).

### 16.5 🟡 "Are You Smarter Than AI?" — Expanded Modes `[Cl]`
The existing game is good; expand it.  
**Fix:** Team mode, subject packs, difficulty progression, streak bonuses.

### 16.6 🟡 Debate Arena Game `[C][Cl]`
**Fix:** Two AI providers debate a topic (one FOR, one AGAINST). User votes on the winner. Scores tracked per provider.

### 16.7 🟡 Persona Progression and Unlock System `[A]`
Antigravity proposed gamifying the whole platform experience.  
**Fix:** Earn "Sync Points" from agent task completions, mini-game wins, and milestones. Spend points to unlock new UI themes, TTS voice profiles, or system prompt personas. Creates a sense of investment in the local environment.

### 16.8 🟡 Persistent Game Profiles `[Cl]`
Scores are currently per-session.  
**Fix:** Persistent player profile saved to local JSON. All-time scores per game, win/loss record vs AI models, "most beaten model" stats.

### 16.9 🟢 Twenty Questions `[C]`
**Fix:** AI asks up to 20 yes/no questions to guess what the user is thinking. Chain-of-thought reasoning visible in an expandable panel. Confidence percentage after each answer.

### 16.10 🟢 Wordle Clone with AI Analysis `[C]`
**Fix:** Classic Wordle with AI providing a vocabulary hint after each guess. AI can also solve it optimally on request.

### 16.11 🟢 Dungeon Crawler (Text RPG) `[C]`
**Fix:** Text-based RPG where the LLM is game master, generating rooms, enemies, and items dynamically. Player stats (HP, attack, defence). Save/load game state to Memory. ASCII art dungeon maps.

### 16.12 🟢 Code Golf / Programming Puzzle `[Cl]`
Unique to Aethvion because it already has a code execution environment.  
**Fix:** AI generates a small programming challenge. Player writes code in a Monaco editor within the game. AI judge evaluates correctness and scores by brevity/elegance.

---

## 17. New App Ideas

### 17.1 🟠 Aethvion Notes — AI-Powered Notebook `[C]`
A Markdown note-taking app deeply integrated with the Memory Tier.  
- Rich Markdown editor with live preview  
- Notes auto-stored as high-importance memories  
- `[[wiki-link]]` style inter-note linking  
- AI answers questions based on your notes ("What did I write about project X?")  
- Backlinks panel  
- Export to PDF or HTML  

### 17.2 🟠 Knowledge Base / RAG Panel `[Cl]`
There is a KnowledgeGraph and ChromaDB but no UI for feeding documents into it.  
**Fix:** A dedicated panel where users can:  
- Upload PDFs, Markdown files, or paste text  
- Have them chunked and embedded into ChromaDB automatically  
- Optionally query this knowledge base before all chat responses  

This turns Aethvion into a personal knowledge assistant over the user's own documents — one of the highest-value local AI use cases.

### 17.3 🟡 Aethvion Tasks — AI Task Manager `[C]`
To-do / project management with AI organisation.  
- Tasks with due dates, priorities, and tags  
- AI auto-prioritises the backlog  
- Natural language task creation ("Remind me to call Alice tomorrow at 3pm")  
- Pomodoro timer  
- Click a task to spawn an agent to help complete it  

### 17.4 🟡 Aethvion Transcriber — Meeting Notes `[C]`
- Drop in audio (MP4, MP3, WAV) or record live  
- Transcribed via Whisper (local)  
- AI generates: summary, action items, key decisions, speaker labels  
- Export as Markdown meeting notes  
- Auto-saves summary to Memory Tier  

### 17.5 🟡 Scheduled Tasks and Automations `[Cl][A]`
Both plans proposed this. The system has a TaskQueue and orchestrator but everything is manually triggered.  
**Fix:** Simple cron-style scheduler. Define routines in the dashboard:  
- Daily briefing: summarise news or emails  
- Code review: check open PRs and summarise changes  
- Finance briefing: fetch market data, generate TTS summary  
- System health: check services and alert on anomalies  
Execution infrastructure is already present — the scheduler is the only missing piece.

### 17.6 🟢 Federated / Multiplayer Aethvion `[A]`
Antigravity proposed connecting instances between friends over a secure P2P or relayed connection. Send an agent to a friend's instance, have personas chat with each other, share files.  
**Note:** This is architecturally ambitious and should be considered a long-term goal rather than near-term work. Triage after core features are solid.

### 17.7 🟢 Aethvion Canvas — AI Whiteboard `[C]`
Infinite canvas for brainstorming. Sticky notes, drawing, arrows. Right-click any note → **Expand with AI** fills in related ideas as new sticky notes. AI can auto-cluster related notes.

### 17.8 🟢 Aethvion Flashcards — AI Spaced Repetition `[C]`
Paste any text → AI generates a flashcard deck. SM-2 spaced repetition scheduler. AI hint mode. Track retention stats per deck.

---

## 18. Developer Experience & Infrastructure

### 18.1 🟠 Docker / Docker Compose Support `[C]`
No Dockerfile exists. Setup is Windows-only.  
**Fix:** `Dockerfile` and `docker-compose.yml` for the core suite + optional apps. Multi-stage builds. Document in Getting Started.

### 18.2 🟠 Linux / macOS Launch Scripts `[C]`
Only `.bat` scripts exist.  
**Fix:** Equivalent `.sh` scripts for Linux and macOS. Auto-detect platform. Add a `Makefile` with common targets (`make start`, `make test`, `make lint`).

### 18.3 🟡 Development Server with Hot-Reload `[C]`
Developers restart the server after every code change.  
**Fix:** `--dev` flag runs Uvicorn with `--reload` watching `core/`. Also enable detailed error pages in dev mode.

### 18.4 🟡 Dependency Graph Visualisation `[C]`
With 181 Python files, understanding module dependencies is difficult.  
**Fix:** `python -m core.tools.dep_graph` command generating a dependency graph SVG using `pydeps`. Ship it in documentation.

### 18.5 🟡 Interactive API Documentation `[C]`
FastAPI ships Swagger docs for free but they may be disabled or not surfaced.  
**Fix:** Enable `/docs` and `/redoc` in dev mode. Link from the dashboard Settings tab.

### 18.6 🟢 VS Code DevContainer `[C]`
**Fix:** `.devcontainer/devcontainer.json` so developers using VS Code can open the repo in a fully configured container with Python, extensions, and env vars pre-configured.

---

## 19. Testing & Reliability

### 19.1 🟠 CI Pipeline `[C]`
No CI pipeline exists.  
**Fix:** GitHub Actions workflow (`.github/workflows/ci.yml`):  
- Runs `pytest core/tests/` on every push and PR  
- Lints with `ruff`  
- Checks types with `mypy` (incremental)  
- Runs on Python 3.10 and 3.11  

### 19.2 🟠 Provider Mock Layer for Tests `[C]`
Tests that call real providers are unreliable and cost money.  
**Fix:** `MockProvider` class returning deterministic canned responses. All tests default to `MockProvider`. Tests requiring real providers marked `@pytest.mark.live` and skipped in CI.

### 19.3 🟡 Test Coverage Reporting `[C]`
No coverage metrics exist.  
**Fix:** `pytest-cov` with HTML coverage reports. Gate CI on >60% coverage (increasing over time). Coverage badge in README.

### 19.4 🟡 Forge Tool Sandboxing `[C]`
Generated tools run with full process privileges.  
**Fix:** Execute Forge-generated tool validation in a subprocess with reduced privileges (no filesystem write access outside `tmp/`, no network). Use `subprocess` + `resource` module limits on Linux.

### 19.5 🟢 Chaos Testing Mode `[C]`
**Fix:** `--chaos` flag that randomly injects provider failures, memory errors, and latency. Verifies circuit-breaker and failover logic.

---

## 20. Fun, Personality & Polish

### 20.1 🟡 Misaka Cipher Animations `[C]`
The chibi sprite is static.  
**Fix:** Idle animations (breathing, blinking, occasional head-turn). "Thinking" animation during a response. Surprised expression on error. CSS sprite sheet animation.

### 20.2 🟡 Daily AI Briefing `[C][A]`
**Fix:** Opt-in daily briefing at a configured time. Misaka summarises: weather, top 3 memory items from yesterday, pending agent tasks, a random interesting fact. Delivered as dashboard notification and optionally spoken via TTS.

### 20.3 🟡 Package Manager Completion or Hiding `[Cl]`
The packages panel is flagged internally as unstable.  
**Fix:** Either complete it to a functional state, or hide it from the UI until it works. A half-working package manager that can break the environment is worse than no package manager. Don't ship broken features — fix or remove.

### 20.4 🟡 Discord Worker Logic `[Cl]`
`core/workers/discord_worker.py` has a TODO: "Implement actual 'should I reach out?' logic via orchestrator." The Discord integration has a settings panel but the decision logic is stubbed.  
**Fix:** Implement the reach-out decision logic using the orchestrator, or document it as explicitly not yet functional in the UI.

### 20.5 🟢 Seasonal / Holiday Themes `[C]`
**Fix:** `themes/` directory with CSS overrides for seasonal events. Auto-switch based on date or manually selectable.

### 20.6 🟢 Easter Eggs `[C]`
- Typing "konami" in the command palette triggers a brief fullscreen animation  
- Asking Misaka "what are you?" triggers a special lore-based response  
- Holding `Shift+Alt+M` plays a short jingle  
- A hidden "LEGENDARY" Arena difficulty pits 3 providers simultaneously  

### 20.7 🟢 AI Achievement System `[C]`
Hidden achievement badges for milestones: first conversation, first tool generated, first agent run, 100 messages sent, all providers configured, etc. Trophy modal accessible from the user avatar. Purely cosmetic and fun.

---

## 21. Priority Summary Table

| # | Item | Category | Priority | Sources |
|---|------|----------|----------|---------|
| 1.1 | Fix Wildcard CORS | Security | 🔴 Critical | C, Cl |
| 1.2 | Optional Dashboard Auth | Security | 🔴 Critical | C |
| 3.1 | Local GPU CUDA Offload | Providers | 🔴 Critical | Cl |
| 5.1 | Complete Intelligence Firewall | Security/AI | 🔴 Critical | Cl |
| 2.1 | Streaming Responses | Architecture | 🟠 High | C |
| 2.2 | Circuit Breaker | Architecture | 🟠 High | C |
| 3.2 | Ollama Integration | Providers | 🟠 High | C, A, Cl |
| 4.1 | Wire Memory Retrieval to Chat | Memory | 🟠 High | C, A, Cl |
| 6.1 | Agent Native Tool Calling | Factory | 🟠 High | Cl |
| 6.2 | Agent Persistence & Resume | Factory | 🟠 High | C, Cl |
| 6.3 | More Agent Tools | Factory | 🟠 High | Cl, A |
| 7.1 | Forge TDD Loop | Forge | 🟠 High | C, A |
| 8.1 | Global Command Palette | Dashboard | 🟠 High | C |
| 9.1 | Message Edit & Regenerate | Chat | 🟠 High | C |
| 9.2 | File/Image Attachments | Chat | 🟠 High | C |
| 10.1 | Git Integration in IDE | Code IDE | 🟠 High | C |
| 10.2 | AI Change Diff View | Code IDE | 🟠 High | Cl |
| 15.1 | Arena ELO Leaderboard | Arena | 🟠 High | C, Cl |
| 17.2 | Knowledge Base / RAG Panel | New App | 🟠 High | Cl |
| 18.1 | Docker Support | DevEx | 🟠 High | C |
| 18.2 | Linux/macOS Scripts | DevEx | 🟠 High | C |
| 19.1 | CI Pipeline | Testing | 🟠 High | C |
| 6.5 | Multi-Agent Coordination | Factory | 🟡 Medium | C, Cl |
| 9.9 | Voice Conversation Loop | Chat | 🟡 Medium | Cl |
| 10.4 | Ghost Dev Agent | Code IDE | 🟡 Medium | A |
| 12.1 | VTuber Lip-Sync | VTuber | 🟡 Medium | C, A, Cl |
| 16.1 | AI Explains Moves (Games) | Games | 🟡 Medium | C |
| 17.1 | Aethvion Notes App | New App | 🟡 Medium | C |
| 17.5 | Scheduled Tasks/Automations | Automation | 🟡 Medium | Cl, A |
| 20.3 | Fix or Hide Package Manager | Stability | 🟡 Medium | Cl |
| 20.4 | Discord Worker Logic | Stability | 🟡 Medium | Cl |
| 12.3 | Desktop Pet Mode | VTuber | 🟢 Low | A |
| 17.6 | Federated Aethvion Instances | Network | 🟢 Low | A |
| 20.6 | Easter Eggs | Fun | 🟢 Low | C |
| 20.7 | AI Achievement System | Fun | 🟢 Low | C |

---

## 22. Implementation Roadmap

### Phase 1 — Fix the Foundations (Week 1–2)
> Goal: Make the system secure, fast, and consistent for daily use.

1. **GPU CUDA offload** — 10–50× local model speed; low effort (one reinstall command)
2. **CORS fix** — unblocks safe LAN deployment; trivial change
3. **Optional dashboard auth** — unblocks real-world use
4. **Complete Intelligence Firewall** — highest-integrity gap; uses already-installed local models
5. **Wire memory retrieval to chat** — turns an unused system into a daily-use feature
6. **Streaming responses** — biggest perceived-performance win; makes the system feel fast
7. **Agent native tool calling** — eliminates a whole class of agent failures

### Phase 2 — Expand Core Capabilities (Week 3–4)
> Goal: Major feature gaps filled; platform feels complete for power users.

8. **Ollama integration** — dramatically expands local model access
9. **Agent persistence & resume** — makes long-running tasks practical
10. **More agent tools** (web_search, read_url, run_python, remember/recall)
11. **Forge TDD loop** — makes generated tools reliable
12. **Message edit & regenerate** — expected baseline chat feature
13. **File and image attachments**
14. **Linux/macOS scripts + Docker** — opens the project to non-Windows users

### Phase 3 — Polish & Productivity (Month 2)
> Goal: Quality-of-life wins that improve daily usage.

15. **Global command palette** (Ctrl+K)
16. **Git integration in Code IDE**
17. **AI change diff view** before applying edits
18. **Memory tagging, timeline, and importance scoring**
19. **Arena ELO leaderboard**
20. **CI pipeline + mock provider layer**
21. **Chat thread search and export**
22. **Knowledge Base / RAG Panel**
23. **Voice conversation loop**
24. **Fix or hide unstable Package Manager**
25. **Discord worker decision logic**

### Phase 4 — Expansion & Delight (Month 3+)
> Goal: New capabilities and the features that make Aethvion unique.

26. Multi-agent coordination (Agent Mesh)
27. VTuber lip-sync → desktop pet
28. Ghost Dev Agent in Code IDE
29. Scheduled tasks and automations
30. Aethvion Notes app
31. Persona progression / Sync Points
32. Games expansion (Chess, Trivia, Story Builder, Debate Arena)
33. Image generation gallery
34. Finance app real market data
35. Transcriber app
36. Easter eggs + Achievement system

### Long-Term Vision
- Federated Aethvion instances (Antigravity)
- Full autonomous web browsing with Playwright (Antigravity)
- Multimodal vision integration across all panels (Antigravity)
- Community agent/tool marketplace
- Mobile companion app

---

## Synthesis Notes

**Where all three plans agreed (highest confidence):**
- Ollama integration
- Memory retrieval must be wired to chat
- Agent persistence and more tools
- VTuber lip-sync
- Arena ELO leaderboard

**Key items only Claude identified (important gaps):**
- GPU CUDA offload being completely missing (critical; RTX 4090 wasted)
- Intelligence Firewall being a placeholder (architectural integrity issue)
- Package manager being unstable but still visible
- Agent step display ordering bug
- Discord worker being stubbed out

**Key items only Antigravity identified (creative expansions):**
- Desktop pet mode (compelling long-term VTuber feature)
- Persona progression / Sync Points gamification system
- Federated instances between friends
- Full autonomous web browsing with Playwright

**Correction to Antigravity's web browsing proposal:**
Antigravity proposed Playwright/Selenium as a *native tool* for all agents immediately. This is the right long-term direction but is high-complexity for early implementation. The plan above stages it: start with `web_search` + `read_url` (covers 80% of research use cases at far lower complexity), then add full Playwright browsing once the simpler tools are validated.

**Correction to Copilot's plan omissions:**
Copilot's plan did not explicitly call out the GPU offload issue or the Intelligence Firewall being non-functional. Claude's plan correctly identified these as the highest-priority unfixed items in the codebase. They have been elevated to **Critical** in this final plan.

---

*This final plan was created by synthesising Copilot_Plan.md, Antigravity_Plan.md, and Claude_Plan.md. All proposals were reviewed for accuracy against the v10 codebase. Items were de-duplicated, prioritised, and where plans disagreed, the best-justified approach was chosen with reasoning provided.*
