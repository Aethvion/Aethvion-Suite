# Claude's Improvement Plan for Aethvion Suite

> Authored by Claude Sonnet 4.6 — March 2026
> Based on a full codebase exploration and active development context.

This plan is written from the perspective of someone who has been actively building Aethvion Suite alongside the user. The suggestions are prioritised by impact-to-effort ratio. I've tried to be specific and honest about trade-offs rather than just listing cool-sounding features.

---

## Priority 1 — Fix What's Already Broken or Half-Done

These are gaps between what the UI promises and what actually works.

### 1.1 Intelligence Firewall — Complete Local Inference
The firewall scanner (`core/security/firewall.py`) is a placeholder. It currently detects PII/credentials but routes everything to cloud with a warning. It should use a small local model (the already-installed Llama 3.2 1B or Phi-4 mini) to do actual intent classification before external API calls. This is one of the most privacy-relevant features in the whole system and it's not real yet.

**Suggested approach:** Load a small local model on startup specifically for firewall use. Run a quick yes/no classification: "Does this input contain harmful intent, sensitive credentials, or PII?" before any cloud call. No big model needed — 1B quantised is fine for this.

### 1.2 Memory Retrieval — Actually Surface It
ChromaDB is set up, episodic memory stores data, but memory is not meaningfully injected into chat context. The memory panel is a browser, not a feature. The Nexus Core comment says `# TODO: Reload firewall if needed` near where memory lookup should happen.

**Suggested approach:** Before every chat response, run a vector search for the top 3 most relevant past memories and prepend them as a short "Relevant context:" block. Let the user toggle this per-thread. The infrastructure is already there — it just needs to be wired to the chat pipeline.

### 1.3 Agent Steps Show Above User Message
Still a display ordering issue in the agents panel — step cards render before the triggering message bubble in the history view. This is confusing and makes the history hard to read.

### 1.4 Local Model GPU Offload
Currently running CPU-only despite an RTX 4090 being available. Needs CUDA Toolkit installation and then:
```
CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --force-reinstall
```
This is a 10–50x speed difference for local models. Until then, local models are impractical for real use.

### 1.5 Discord Worker Logic
`core/workers/discord_worker.py` has a TODO: "Implement actual 'should I reach out?' logic via orchestrator." The Discord integration has a settings panel entry but the decision logic is stubbed out.

### 1.6 Package Manager Marked Unstable
The packages panel exists but is flagged internally as unstable. Either complete it or hide it until it works. A half-working package manager that can break the environment is worse than no package manager.

---

## Priority 2 — High-Impact Improvements to Existing Features

### 2.1 Agent System: Tool Calling, Not File Parsing

The current agent format (ACTION: JSON in free text, parsed with raw_decode) is fragile. The real fix is using the provider's native function/tool calling API where available (Gemini, OpenAI, Anthropic all support this). The agent would declare available tools as JSON schemas, and the LLM returns structured tool calls — no regex parsing needed.

**Impact:** Dramatically more reliable agent execution. Eliminates the entire class of "LLM returned malformed JSON" errors.

### 2.2 Agent System: More Tools

The agent can currently read files, write files, list directories, and run shell commands. That's a good start but misses obvious useful tools:
- `web_search` — search the web for information
- `read_url` — fetch and read a webpage
- `ask_user` — pause and ask the human a clarifying question (mid-task)
- `run_python` — execute a Python snippet and return the result (sandboxed)
- `remember` / `recall` — write/query the memory system
- `create_file_from_template` — scaffold boilerplate

### 2.3 Agent Workspaces: Persist and Resume

Currently agents start fresh every time. There's partial state persistence via `_state.json` but threads don't resume mid-task after a restart. A proper resume mechanism would let you close the dashboard and pick up where an agent left off.

**Specific gap:** The `AgentState` file cache and plan tracking is in place but there's no UI for "continue this task" on an existing thread.

### 2.4 Code IDE: Deeper Agent Integration

The Code IDE (port 8083) has an AI copilot but it's separate from the main agent system. A "Hand off to Agent" button that sends the current file + a task description to the Agents tab would make these two systems complementary rather than isolated.

Also: the Code IDE doesn't have a diff view — when the AI rewrites a file, you just get the new version. A side-by-side before/after diff before applying changes would prevent accidental overwrites.

### 2.5 Chat: Thread Export and Search

Threads persist but there's no way to:
- Search across all threads for a keyword/topic
- Export a thread as Markdown or PDF
- Archive old threads without deleting them

These are basic productivity features that make a multi-thread chat system actually useful over time.

### 2.6 Arena Panel: Save and Compare Results

The model arena (side-by-side comparison) generates comparisons but there's no persistence. You can't go back and look at "last Tuesday's comparison" or build a personal leaderboard over time. Saving arena sessions to the history system would make this genuinely useful for model evaluation.

### 2.7 Image Generation: History and Gallery

The image panel generates images but there's no gallery view of previous generations. Given that image generation has a cost (API credits) and takes time, a local gallery showing prompt → image pairs with the ability to re-run or iterate would be much more useful than the current one-at-a-time flow.

---

## Priority 3 — New Features Worth Adding

### 3.1 Ollama Integration as a Provider

Ollama is the most popular way to run local models on desktop and has excellent Windows support including GPU. Adding an `OllamaProvider` would:
- Give access to every model in the Ollama registry (100+)
- Provide GPU offload without needing to build llama-cpp-python from source
- Enable models the GGUF loader doesn't handle well (Mixtral MoE, large context variants)
- Let users switch models without restarting the server

The API is simple REST — one endpoint for generation, one for chat. This is a 1–2 day addition that would significantly expand local model capability.

### 3.2 Prompt Library / Templates

Power users build up a collection of useful system prompts and message templates. A "Prompt Library" tab or panel where you can:
- Save and name prompts
- Organise into categories (coding, writing, analysis, etc.)
- Inject a saved prompt into any chat thread with one click
- Share/import prompt packs as JSON

This is low complexity but high daily-use value.

### 3.3 Scheduled Tasks / Automations

The system has a TaskQueue and an orchestrator — but everything is triggered manually. A simple scheduler that lets you say "Every morning at 8am, run this agent task and send the result to Discord" would unlock a whole category of practical use. Things like:
- Daily briefing: summarise news or emails
- Code review: check for open PRs and summarise changes
- System health report: check services and alert on anomalies

The scheduling infrastructure is minimal (just a cron-style trigger) but the execution infrastructure is already there.

### 3.4 Knowledge Base / RAG Panel

There's a KnowledgeGraph and ChromaDB but no UI for feeding documents into it. A "Knowledge Base" panel where you can:
- Upload PDFs, Markdown files, or paste text
- Have them chunked and embedded into ChromaDB automatically
- Then have all chats optionally query this knowledge base before responding

This turns Aethvion into a personal knowledge assistant over your own documents — one of the highest-value use cases for local AI.

### 3.5 Voice-First Mode

The audio tab has TTS and STT. But they're separate from chat — you speak in audio, switch to chat, read the response, switch back. A "voice conversation mode" that runs: STT → send to chat → response → TTS → play automatically, as a continuous loop, would make voice interaction actually practical.

The Kokoro TTS (already installed) is fast enough to stream sentence-by-sentence, so latency could be kept low.

### 3.6 Multi-Agent Conversations

The `advaiconv-panel` supports multi-persona conversation. The next step is true multi-agent: spawn two or more agents with different roles and let them collaborate or debate on a task. For example:
- "Architect" agent designs a system, "Critic" agent finds flaws, "Builder" agent implements
- AI debate: two models argue opposite sides of a question, judged by a third

The infrastructure (multiple runners, SSE streaming) is mostly there.

### 3.7 VTuber + Audio Integration

The VTuber app (port 8081) and the Audio/TTS system are both present but disconnected. If Misaka (or any VTuber character) spoke responses aloud using Kokoro TTS while animating the mouth — lip sync to TTS output — that would make the system feel significantly more alive. This is a "fun" feature but one that makes the whole experience more cohesive.

---

## Priority 4 — Games Expansion

The games section is fun but the games themselves are mostly single-player and simple. Here are expansions that fit the existing pattern:

### 4.1 "Are You Smarter Than AI?" — More Game Modes
- **Team mode:** humans vs AI team, scoring by team
- **Subject packs:** let the game master use a specific knowledge domain (Science, History, Pop Culture)
- **Difficulty progression:** questions get harder as the game goes on
- **Streak bonuses:** extra points for consecutive correct answers

### 4.2 AI Storytelling Game
A collaborative story game where:
- The AI starts a story with 2–3 sentences
- The player continues it
- The AI continues
- At the end, the AI rates the story and generates a "cover" image

Ties into the image generation feature already present.

### 4.3 Code Golf / Programming Puzzle
Given the Code IDE integration, a game where:
- An AI generates a small programming challenge
- The player writes code in a Monaco editor within the game
- An AI judge evaluates correctness and scores by brevity/elegance

This is unique to Aethvion because it already has a code execution environment.

### 4.4 Persistent Game Profiles
Currently scores are per-session. A persistent player profile (saved to local JSON) with:
- All-time scores per game
- Win/loss record vs AI models
- "Most beaten model" stats

---

## Priority 5 — Technical Debt and Architecture

These won't add features but will make development faster and the system more reliable.

### 5.1 Consistent Error Handling in the Dashboard
Many API endpoints return `{"success": false, "detail": "..."}` but the frontend inconsistently reads `data.detail`, `data.error`, `data.message`, or just `data` as a string. A shared `staPost()` / `apiPost()` helper with consistent error extraction and display would clean this up.

### 5.2 Provider Health Dashboard Enhancement
The status panel shows provider health but doesn't show which model is currently active, last latency, or failure counts. A more detailed provider status card showing "last 10 calls: 9 OK, 1 failed (500 at 14:32)" would make debugging much easier.

### 5.3 Frontend Component Reuse
The dashboard is pure vanilla JS, which is consistent and fast to load. But there's significant copy-paste between panels (thread lists, model selectors, status indicators). Extracting a small set of reusable `render*()` functions (not a framework — just shared JS helpers) would reduce bugs and make new panels faster to build.

### 5.4 CORS Restriction
`allow_origins=["*"]` is in server.py with a TODO comment to restrict in production. For a local-only deployment this is low risk, but if any panel ever loads external content or the server is exposed, this becomes a real vulnerability.

### 5.5 Rate Limit Visibility
The provider manager has rate limiting configured but there's no UI indication when a request is being rate-limited vs. genuinely slow. A "queued (rate limit)" indicator in the chat would prevent users from thinking the system is broken.

---

## Summary Table

| Item | Impact | Effort | Priority |
|------|--------|--------|----------|
| Local model GPU offload (CUDA) | Very High | Low (install + one command) | Now |
| Memory retrieval wired to chat | High | Medium | High |
| Agent tool calling API (native) | High | High | High |
| Ollama provider | High | Medium | High |
| Intelligence Firewall local model | High | Medium | High |
| Knowledge Base / RAG UI | High | Medium | High |
| Voice conversation loop | High | Low | Medium |
| Agent resume mid-task | Medium | Medium | Medium |
| Prompt Library | Medium | Low | Medium |
| Chat thread search/export | Medium | Low | Medium |
| Scheduled automations | Medium | Medium | Medium |
| Image generation gallery | Medium | Low | Medium |
| Code IDE diff view | Medium | Medium | Medium |
| Multi-agent collaboration | High | High | Later |
| VTuber + TTS lip sync | Medium | High | Later |
| Arena session persistence | Low | Low | Later |
| Persistent game profiles | Low | Low | Later |
| New game modes | Low | Low | Later |
| CORS restriction | Low | Very Low | Background |
| Frontend component reuse | Low | Medium | Background |

---

## Personal Note

Aethvion Suite is genuinely impressive in scope. The provider failover, local GGUF support, multi-tab dashboard, and agent system all work. The risk I see is **feature breadth outpacing feature depth** — there are 25+ panels but several of them are stubs or only partially connected to the backend capabilities. The most valuable work right now is probably deepening what's already there (memory, agents, voice) rather than adding more panels.

The Intelligence Firewall is the highest-integrity gap — it's architecturally important and currently fake. Fixing that and getting memory retrieval actually wired in would make the system feel like a coherent, trustworthy platform rather than a collection of capable but loosely-connected features.

— Claude
