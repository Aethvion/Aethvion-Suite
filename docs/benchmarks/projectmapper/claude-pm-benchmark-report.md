# Project Mapper — Benchmark Report
**Model:** Claude Sonnet 4.6  
**Date:** 2026-06-07  
**Scope:** Efficiency comparison — normal file-reading workflow vs Project Mapper API  
**Database:** AethvionMap (scan of Aethvion Suite itself)  
**DB State at test time:** 1,837 entities · 5,908 relations · 363 files (307 Python, 51 JS, 5 C#)

---

## What is being tested

Every time an AI assistant works on a codebase it needs to orient itself: find relevant classes, trace call chains, understand what would break if something changes. Currently this means reading files — often many of them, often redundantly. The Project Mapper stores a knowledge graph of the codebase (entities, inheritance, module imports, and — after this session's improvement — call-graph edges). This report measures whether querying the graph is faster, cheaper, and more accurate than reading files.

**No LLM enrichment was run on AethvionMap.** All summaries come from docstrings only. Context queries are excluded from the tests for this reason.

---

## Methodology

Each test runs in two modes:

**Normal (file-reading) workflow**  
Simulate what an AI assistant would do without the Project Mapper: use directory listings, grep, and file reads to find the answer. Record every tool call, count lines and characters consumed, derive token cost (1 token ≈ 4 characters). Assess result completeness.

**Project Mapper workflow**  
Use only PM API calls first, then read the minimum file set PM points to. Record API response sizes. Assess result completeness.

**Cross-reference**  
Run both methods against the same question and check if results agree. Note anything one method found that the other missed.

---

## Test 1 — Provider Discovery

**Question:** *"What AI providers does the system support, and where are they implemented?"*

This is a common orientation question when starting work in the providers subsystem.

### Normal workflow

| Step | Action | Lines | Chars | ~Tokens |
|------|--------|-------|-------|---------|
| 1 | `ls core/providers/` | — | 200 | 50 |
| 2 | Read `base_provider.py` (to understand interface) | 247 | 7,053 | 1,763 |
| 3 | Read first 60 lines of `provider_manager.py` (to find PROVIDER_CLASSES dict) | 60 | 2,400 | 600 |
| **Total** | 3 tool calls | **307** | **9,653** | **~2,413** |

**Result quality:** Found 10 providers from the `PROVIDER_CLASSES` dict in `provider_manager.py`. Got full interface from `base_provider.py` (5 abstract methods: generate, stream, generate_image, generate_speech, transcribe). No file paths for implementations — would need to read each one.

### PM workflow

| Step | Action | Response Chars | ~Tokens |
|------|--------|---------------|---------|
| 1 | `impact_query("BaseProvider", depth=1)` | 3,198 | 799 |
| **Total** | **1 API call** | **3,198** | **~799** |

**Result quality:** All 10 providers with name, implementation file path, and docstring summary (e.g., *"Google AI (Gemini) provider implementation. Primary provider for Aethvion Suite."*). No method signatures — to get those you still read `base_provider.py`.

### Cross-reference

Both methods found all 10 providers. Results are identical in completeness for the discovery question.  
PM advantage: file paths included without extra reads. Normal advantage: interface signatures available without extra reads.

### Conclusion — Test 1

| Metric | Normal | PM | Winner |
|--------|--------|----|--------|
| Tool calls | 3 | 1 | **PM** |
| Tokens consumed | ~2,413 | ~799 | **PM (3× less)** |
| Provider names found | 10 | 10 | Tie |
| File paths | No | Yes | **PM** |
| Method signatures | Yes | No | Normal |

**PM wins for pure discovery.** If you only need "which providers exist and where", PM is 3× cheaper. If you need the interface to implement something, you read `base_provider.py` either way.

---

## Test 2 — Call Chain Tracing

**Question:** *"How does a user chat message reach the AI provider?"*

A classic architectural question. Requires tracing from the HTTP endpoint through multiple orchestration layers to the provider call.

### Normal workflow

Minimum useful file set — you cannot answer this question without reading all of these:

| Step | File | Lines | Chars | ~Tokens | What it reveals |
|------|------|-------|-------|---------|-----------------|
| 1 | `server.py` | 342 | 15,069 | 3,767 | Entry point: `submit_task()` and WebSocket handler |
| 2 | `task_routes.py` | 583 | 22,288 | 5,572 | `TaskQueueManager.submit_task()` wired to route |
| 3 | `task_queue.py` | 1,174 | 53,789 | 13,447 | `TaskQueueManager → TaskWorker` |
| 4 | `agent_runner.py` | 1,264 | 59,030 | 14,757 | `AgentRunner → ProviderManager` |
| 5 | `provider_manager.py` | 863 | 40,602 | 10,150 | Provider call logic |
| **Total** | **5 files** | **4,226** | **190,778** | **~47,693** |

**Result quality:** After reading all 5 files: found `TaskQueueManager → TaskWorker → AgentRunner → ProviderManager`. Missed the parallel branch `AetherCore → ProviderManager` (would require also reading `aether_core.py`). Missed `CorpWorkerRunner` as another `AgentRunner` subclass that reaches providers.

### PM workflow

| Step | Action | Response Chars | ~Tokens | What it reveals |
|------|--------|---------------|---------|-----------------|
| 1 | `path_query("TaskQueueManager", "ProviderManager")` | 1,115 | 278 | Direct 3-hop path via `calls` edges |
| 2 | `impact_query("ProviderManager", depth=3)` | 2,591 | 647 | Full dependency tree: all 8 callers across 3 hops |
| **Total** | **2 API calls** | **3,706** | **~925** |

**Path query result — clean 3-hop calls chain:**
```
TaskQueueManager --calls--> TaskWorker --calls--> AgentRunner --calls--> ProviderManager
```

**Impact query result — complete caller tree:**
```
hop 1: AetherCore          (calls)
hop 1: AgentRunner         (calls)
hop 2: TaskWorker          (calls → calls)
hop 2: AethvionCLI         (calls → calls)
hop 2: CorpWorkerRunner    (calls → extends)   ← Normal method missed this
hop 3: TaskQueueManager    (calls → calls → calls)
hop 3: CorpManager         (calls → extends → calls)  ← Normal method missed this
```

### Cross-reference

Both methods found the primary path: `TaskQueueManager → TaskWorker → AgentRunner → ProviderManager`.  
PM additionally found: `AetherCore → ProviderManager`, `CorpWorkerRunner` (AgentRunner subclass also routing to providers), `CorpManager`. These were present in the codebase but would require reading `aether_core.py` and `corp_worker_runner.py` in the normal workflow — two more files, ~18,000 more chars, ~4,500 more tokens.

### Conclusion — Test 2

| Metric | Normal | PM | Winner |
|--------|--------|----|--------|
| Files read | 5 | 0 | **PM** |
| Tokens consumed | ~47,693 | ~925 | **PM (52× less)** |
| Primary chain found | Yes | Yes | Tie |
| Parallel branches found | No | Yes | **PM** |
| Actor count discovered | 5 | 8 | **PM** |

**PM wins decisively.** 52× fewer tokens and a more complete result. The calls graph surfaces branches that would require additional file reads in the normal workflow.

---

## Test 3 — Coding Task Simulation

**Prompt:** *"Add a `record_timeout` method to `BaseProvider` and all of its implementations."*

This tests a realistic engineering task: modifying a base class and propagating the change to all subclasses. The agent needs to know the full file list before touching anything.

### Normal workflow

Without PM, there are two approaches:

**Option A — Directory listing then selective reads:**  
`ls core/providers/` → see 12 files → read only `base_provider.py` to understand interface → write the method → update 10 implementation files  
Cost: `ls` (50 tokens) + `base_provider.py` (1,763 tokens) + 10 targeted edits = ~1,813 tokens of read overhead. Risk: the `ls` might miss providers in subdirectories or other modules that indirectly inherit.

**Option B — Defensive reading (what you'd actually do in a large unfamiliar codebase):**  
Read all 12 provider files to understand existing methods and avoid conflicts.

| Total files | Lines | Chars | Tokens |
|-------------|-------|-------|--------|
| 12 provider files | 3,796 | 152,812 | ~38,203 |

### PM workflow

| Step | Action | Chars | Tokens |
|------|--------|-------|--------|
| 1 | `impact_query("BaseProvider", depth=1)` | 3,198 | 799 |
| 2 | Read `base_provider.py` (to write the new method) | 7,053 | 1,763 |
| **Total** | **1 API call + 1 file** | **10,251** | **~2,562** |

PM response names all 10 implementation files with exact paths:
```
core/providers/mistral_provider.py
core/providers/deepseek_provider.py
core/providers/openrouter_provider.py
core/providers/openai_provider.py
core/providers/ollama_provider.py
core/providers/google_provider.py
core/providers/groq_provider.py
core/providers/grok_provider.py
core/providers/anthropic_provider.py
core/providers/local_provider.py
```

No need to read any implementation file before coding — you have the complete list, with exact paths, in a single call.

### Cross-reference

Both methods produce the exact same file list (10 implementations). Results are identical. PM advantage is purely in cost and confidence: instead of a directory listing that might miss non-obvious inheritance, PM traverses the actual `extends` graph.

### Conclusion — Test 3

| Metric | Normal (Option A) | Normal (Option B) | PM | Winner |
|--------|-------------------|-------------------|----|--------|
| Read tokens (overhead) | ~1,813 | ~38,203 | ~2,562 | **PM ≈ Option A** |
| Files found | 10 (ls) | 10 | 10 | Tie |
| Confidence (no missed files) | Medium | High | **High** | **PM** |
| Tokens if graph is deep | Same | Scales badly | Flat | **PM** |

**PM matches the cheapest normal approach in token cost while providing higher confidence** — the `extends` graph is exhaustive, not filesystem-bounded. As inheritance depth grows or if providers live in submodules, PM stays accurate while `ls` becomes unreliable.

---

## Test 4 — Cross-Domain Discovery

**Question:** *"How does a companion's identity affect AI model selection?"*

This crosses subsystem boundaries: companion config → orchestration → provider routing. It tests whether PM can navigate cross-domain connections that aren't in obvious proximity.

### Normal workflow

| Step | Action | Lines | Chars | ~Tokens | Found |
|------|--------|-------|-------|---------|-------|
| 1 | `grep -r "companion" core/` | — | — | ~200 | 15 files containing "companion" |
| 2 | Read `companion_engine.py` | 432 | 22,780 | 5,695 | **Line 19:** `from core.providers.provider_manager import get_provider_manager` → direct connection; **Line 70:** `model = preferences_manager.get(config.id, {}).get("model", config.default_model)` → model comes from per-companion preferences |
| 3 | Read `registry.py` | 110 | 3,988 | 997 | `CompanionConfig.default_model` field |
| **Total** | **3 steps** | **542** | **26,768** | **~6,892** |

**Result quality:** Confirmed the chain: `CompanionConfig.default_model` → `preferences_manager` (user override) → `get_provider_manager()` → `ProviderManager.model_to_provider_map` → provider selection. Found in 2 reads.

### PM workflow

| Step | Action | Chars | ~Tokens | Found |
|------|--------|-------|---------|-------|
| 1 | Entity listing (class type) | 2,900 | ~725 | 25 companion/identity related entities identified |
| 2 | `impact_query("CompanionEngine", depth=2)` | ~200 | ~50 | **0 callers** — connection missed |
| 3 | `path_query("CompanionEngine", "ProviderManager")` | 1,121 | ~280 | 4-hop path found **but via shared logger import** — not the real connection |
| **Fallback:** Read `companion_engine.py` | 432 | 22,780 | 5,695 | Same as normal step 2 |
| **Total** | **4 steps (including fallback)** | **27,001** | **~6,750** |

**Why PM missed the connection:** The call extractor captures `self.X = get_something()` patterns (self-attribute assignments). But `companion_engine.py` uses a local variable: `pm = get_provider_manager()` inside the method body — PM's static analysis does not track local variable types. This creates a gap in the `calls` graph for this pattern.

The path query returned a 4-hop path through `core.utils.logger` (a shared import) — this looks like a connection but is semantically meaningless. It is a false positive.

### Cross-reference

Normal method found the actual connection in 2 file reads. PM: the path query gave a misleading result, impact queries returned empty, and a file read was still needed. Both ended with the correct answer after reading `companion_engine.py`, but PM added overhead from the misleading path result.

### Conclusion — Test 4

| Metric | Normal | PM | Winner |
|--------|--------|----|--------|
| Tool calls to discovery | 3 | 4+ (including fallback) | **Normal** |
| Tokens consumed | ~6,892 | ~6,750 | Tie (PM adds API overhead that barely cancels) |
| Connection found correctly | Yes | No (missed, then fallback) | **Normal** |
| Path query accuracy | N/A | False positive via logger | **Normal** |

**Normal method wins.** Grep is more reliable than the PM path query for cross-domain discovery when the dependency uses the local variable pattern (`pm = factory()`). PM returns a misleading path and requires a file read anyway.

---

## Summary Table

| Test | Question type | Normal tokens | PM tokens | Savings | Winner | Accuracy |
|------|--------------|---------------|-----------|---------|--------|----------|
| T1 | Provider discovery | ~2,413 | ~799 | 3× | **PM** | Tie |
| T2 | Call chain tracing | ~47,693 | ~925 | **52×** | **PM** | **PM found more** |
| T3 | Coding task (subclass list) | ~1,813–38,203 | ~2,562 | Up to 15× | **PM** | Tie |
| T4 | Cross-domain dependency | ~6,892 | ~6,750 | ~1× | **Normal** | Normal more accurate |

---

## Key Findings

### Where PM is clearly superior

1. **Inheritance hierarchies are instant.** `impact_query("BaseProvider")` returns all 10 provider subclasses with file paths in one call. Normal alternative: grep or directory listing, with risk of missing non-obvious subclasses in subdirectories.

2. **Call chain traversal at depth.** After the `calls` relation extraction implemented in this session, `impact_query("ProviderManager", depth=3)` maps the entire dependency tree — 8 actors across 3 hops — in 925 tokens. Reading the same files manually costs 52× more and yields less complete results.

3. **Coding task scoping.** When you need to propagate a change through a class hierarchy, PM gives you the exhaustive list from the `extends` graph. No grep, no directory listing needed.

4. **Token efficiency scales with codebase size.** The PM responses stay roughly the same size regardless of how many files are involved. The normal method's cost scales linearly with file count.

### Where the normal method still wins

1. **Local variable dependency patterns.** The current call extractor only captures `self.X = get_something()` and `SomeClass(...)`. When code assigns dependencies to local variables (`pm = get_provider_manager()`), PM does not capture the relation. Grep + file read is faster and correct in these cases.

2. **Semantic/natural language queries.** Without LLM enrichment, `context_query` returns nothing. Grep is more useful for finding things by keyword when you don't know the entity name.

3. **Cross-domain discovery without known entity names.** When you don't know what you're looking for, `grep` is still the right first tool.

4. **First-time exploration of a totally unfamiliar subsystem.** Reading a file end-to-end gives you context that entity stubs don't: comments, data flow within functions, error handling patterns, config structure.

---

## Limitations Identified in the Current PM Build

| Limitation | Impact | Fix |
|------------|--------|-----|
| **Local variable call pattern not captured** — `pm = factory()` + `pm.method()` | Misses cross-module dependencies; false-positive paths via shared imports | Track local variable type annotations or extend `_CallExtractor` to follow local assignments |
| **Context query requires enrichment** — completely empty without LLM summaries | Entire query primitive unusable until enrichment runs | Run enrichment on stable submodules, or implement lightweight description generation from docstrings only |
| **Path query noise via shared dependencies** — `typing`, `logger`, `core.utils` create false shortest paths | Misleading results in T4; erodes trust in path query | Filter traversal to prefer `calls`/`extends` over `imports`/`contains` when both are available |
| **No function-level call tracking** — only class-level `calls` edges | Can't trace individual route handlers to their orchestrators | Extend extractor to top-level functions and method-level call edges |
| **Stub pollution** — `calls` stubs created for unresolved uppercase names | Minor DB noise from names like `WORKSPACE_ROOT` | Filter out ALL_CAPS names before creating stubs |

---

## Improvements Made During This Session

Prior to this session, the `AethvionMap` database had:
- **Relations:** `contains`, `imports`, `depends_on`, `extends` only
- **impact_query** on most classes: 0 results (no callers captured)
- **path_query**: found paths via shared imports — noise

After implementing static call extraction in `code_analyzer.py` and `ingestor.py`:
- **New relation type:** `calls` — extracted from method bodies via AST analysis
- **Relations total:** 3,136 → 5,908 (+2,772 calls edges)
- **Call extraction methods:** direct class instantiation, factory function heuristics (`get_X()` → `X`), self-attribute scanning across all methods (not just `__init__`)
- **impact_query("ProviderManager")** now returns 8 callers across 3 hops
- **path_query("TaskQueueManager", "ProviderManager")** returns a semantically clean 3-hop calls chain

---

## Recommendation

**Use PM as the first tool for any task involving:**
- Class hierarchy discovery (extends relationships)
- Impact analysis ("what breaks if I change X?")
- Call chain tracing between known entity names
- Building the file list before a multi-file edit

**Fall back to grep + file reads when:**
- You don't know the entity name (PM requires a name to query)
- The dependency uses local variable patterns (factory functions assigned to local vars)
- You need full function-body context, not just structure
- LLM enrichment has not been run (context queries are empty)

**Run enrichment on AethvionMap** to unlock `context_query` — this would add the ability to answer questions like *"what handles authentication?"* or *"where does streaming happen?"* by keyword, without needing to know the class name first. It would fundamentally change the cross-domain discovery story (Test 4's weak point).
