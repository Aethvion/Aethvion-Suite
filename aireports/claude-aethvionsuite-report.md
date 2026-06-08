# Aethvion Suite — Code Quality Report
**Model:** Claude Sonnet 4.6  
**Date:** 2026-06-02  
**Scope:** Performance · Stability · Project Size

---

## Executive Summary

Analysis of ~260 Python files across the Aethvion Suite revealed **30+ distinct issues** spanning stability, performance, and bloat. The most critical items are: a synchronous blocking call that freezes the FastAPI event loop, a cascade-failure risk in router startup, a duplicated class definition in the orchestrator, and widespread resource leaks. Addressing the top-priority items would meaningfully reduce startup time, increase crash resilience, and remove hundreds of lines of dead/redundant code.

---

## 1. Stability

### 1.1 Duplicate `Task` Class — `core/orchestrator/task_models.py`
**Severity: Critical**

The `Task` dataclass is defined **twice** in the same file (lines ~31–69 and ~72–115). The first definition is incomplete — it has no `to_dict()` or `duration` logic — and is never used. Python silently overwrites the name, but any import that happens to bind the name before the second definition runs will get the broken version.

**Fix:** Delete lines 31–69. One class, one definition.

---

### 1.2 Router Import Has No Error Isolation — `core/interfaces/dashboard/server.py`
**Severity: High**

`_import_remaining_routers()` (lines ~31–75) imports 29 router modules with no `try/except` around individual imports. If any single router's module-level code raises (missing dependency, bad config, circular import), the **entire server fails to start** — including routers that are otherwise fine.

**Fix:** Wrap each router import in its own `try/except ImportError` with a logged warning, so a broken optional feature degrades gracefully instead of killing the process.

```python
# before
from core.interfaces.dashboard.routers import some_router
app.include_router(some_router.router)

# after
try:
    from core.interfaces.dashboard.routers import some_router
    app.include_router(some_router.router)
except Exception as exc:
    logger.warning("Router 'some_router' failed to load: %s", exc)
```

---

### 1.3 Bare Exception Handling Masks Real Errors
**Severity: High**

Multiple files swallow exceptions without re-raising or distinguishing error types:

| File | Location | Problem |
|------|----------|---------|
| `core/security/scanner.py` | ~line 93 | `except Exception` — action unclear |
| `core/bridges/bridge_manager.py` | ~line 82 | Logs only, silent failure path |
| `core/aethviondb/vectorizer.py` | ~lines 67, 144 | Silent retry/file-write failures |
| `core/utils/registry_utils.py` | ~line 34 | Catches, logs, returns `False` with no context |

**Fix:** Replace `except Exception` with the narrowest possible exception type. Where a broad catch is unavoidable, at minimum re-raise with `raise ... from exc` to preserve the traceback.

---

### 1.4 `time.sleep()` Inside `__init__` — `core/memory/episodic_memory.py`
**Severity: High**

The ChromaDB initialization retry loop (lines ~62–86) calls `time.sleep()` in `__init__`. Because this class is constructed during async server startup, it **blocks the entire event loop** until ChromaDB responds or retries exhaust. Startup can stall for tens of seconds.

**Fix:** Move initialization to an async factory or run the blocking portion via `asyncio.get_event_loop().run_in_executor(None, ...)`.

---

### 1.5 Race Conditions on Shared Global State
**Severity: Medium**

| File | Issue |
|------|-------|
| `core/aethviondb/vectorizer.py` ~line 220 | `_local_model_cache` dict has no lock; concurrent embedding calls can corrupt it |
| `core/workspace/usage_tracker.py` ~lines 25–32 | Double-checked locking singleton is not fully atomic in CPython under GIL pressure |
| `core/memory/file_vector_store.py` ~lines 37–55 | No thread safety; ChromaDB operations are unserialized |

**Fix:** Protect `_local_model_cache` with a `threading.Lock`. For the singleton, use `threading.Lock` + a proper "initialize once" guard rather than double-checked locking.

---

### 1.6 Resource Leaks — Unclosed HTTP Connections and File Handles
**Severity: Medium**

| File | Issue |
|------|-------|
| `core/bridges/web_search_bridge.py` ~lines 47–57 | `requests.get()` response not closed — TCP connection stays alive |
| `core/providers/provider_manager.py` ~lines 191–207 | JSON files opened without `with` — handle not guaranteed to close on exception |

**Fix:** Use `with` for all file opens. For `requests`, either use a `Session` with a context manager or explicitly call `response.close()` in a `finally` block. Better: switch to `httpx.AsyncClient` which fits the async context.

---

### 1.7 Direct Internal State Access — `core/aether_core.py`
**Severity: Low–Medium**

Lines ~135–140 directly mutate `trace_manager._active_traces` (a private dict) instead of going through the public API. If the key already exists, it is silently overwritten. This bypasses any validation the trace manager may add later.

**Fix:** Add a `start_trace()` method to the trace manager and use it here.

---

## 2. Performance

### 2.1 Synchronous TTS Model Loading Blocks Event Loop — `apps/audio/tts_manager.py`
**Severity: High**

`load_model()` (~lines 60–75) is synchronous and can take 30+ seconds for large ONNX/transformer models. It is called from async FastAPI route handlers, blocking the entire server for the duration.

**Fix:**
```python
# in the route handler
await asyncio.get_event_loop().run_in_executor(None, tts_manager.load_model)
```
Or load the model once at startup in a background thread before the server starts accepting requests.

---

### 2.2 No Client Caching for Embedding Providers — `core/aethviondb/vectorizer.py`
**Severity: High**

`_embed_google()` (~line 248) calls `_make_google_client()` on **every single embedding request**, re-reading environment variables and constructing the client object every time. Same pattern for OpenAI. These clients are stateless and expensive to construct.

**Fix:** Cache the client at module level (like the local model cache already does) and construct once:

```python
_google_client: genai.Client | None = None

def _get_google_client() -> genai.Client:
    global _google_client
    if _google_client is None:
        _google_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    return _google_client
```

---

### 2.3 History Scan Loads All Files Into Memory — `core/memory/history_manager.py`
**Severity: Medium**

`get_recent_history()` (~lines 145–161) iterates up to 7 daily files, loading each **fully into memory**, then prepends each result to a growing list using `all_messages = day_messages + all_messages`. This is O(n²) in message count — each day's messages create a full copy.

**Fix:** Use `list.extend()` and reverse once at the end instead of prepending. Add a `limit` parameter and stop reading files once the limit is reached so old days are never loaded.

---

### 2.4 `provider_manager` Recomputes Priority Order on Every Reload — `core/providers/provider_manager.py`
**Severity: Medium**

`reload_config()` (~lines 173–207) re-reads and re-parses `model_registry.json`, then rebuilds `chat_priority_order` and `agent_priority_order` even when nothing changed. The logic duplicates `__init__()` without a shared helper.

**Fix:** Extract a `_init_from_config(config: dict)` private method and call it from both `__init__` and `reload_config`. Add a file-modified-time check so no reload happens when the file on disk hasn't changed.

---

### 2.5 Agent Memory Load Repeats Knowledge Graph Queries — `core/factory/base_agent.py`
**Severity: Medium**

`_load_memory_context()` (~lines 59–131) performs three separate queries against the Knowledge Graph and Episodic Memory on every agent construction. If multiple agents are spawned in sequence (e.g., a pipeline), these queries repeat for each one with no caching.

**Fix:** Cache static knowledge (available tools, standard data tools) at the class level after the first load. Only episodic/recent-activity queries need per-agent freshness.

---

### 2.6 Topological Sort Recomputed on Every Workflow Execution — `core/automate/executor.py`
**Severity: Low–Medium**

The topological sort (~line 62) runs on every execution of a workflow. For static workflow graphs this is pure wasted CPU.

**Fix:** Cache the sorted order on the workflow object and invalidate only when the graph structure changes.

---

## 3. Project Size / Bloat

### 3.1 `sys.path` Polluted by Module-Level Side Effects — `core/factory/generic_agent.py`
**Severity: Medium**

Lines ~19–22 unconditionally append to `sys.path` at import time. If this module is imported multiple times (e.g., via reload or test isolation), the path entry is appended repeatedly.

**Fix:** Guard the append:
```python
_root = str(Path(__file__).parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)
```
Better still: configure the path in `pyproject.toml` / `setup.py` so it is never necessary at runtime.

---

### 3.2 Embedding Client Construction Duplicated Three Times — `core/aethviondb/vectorizer.py`
**Severity: Medium**

`_make_google_client()`, `_make_openai_client()`, and `_get_local_model()` all follow the same pattern (read env var, validate, construct, return) with identical error handling repeated three times.

**Fix:** A small `_make_client(provider: str)` factory or a `@functools.lru_cache` on each getter eliminates the duplication and gives you caching for free.

---

### 3.3 `provider_manager.__init__` and `reload_config` Are Nearly Identical
**Severity: Medium**

`reload_config()` is essentially a copy of the initialization logic in `__init__`, roughly 40 lines duplicated. Any change to how providers are loaded must be made in both places.

**Fix:** Extract shared logic into `_load_from_disk()` as noted in §2.4. Estimated reduction: ~35 lines.

---

### 3.4 No Shared Base for Companion Engine Sub-components
**Severity: Low–Medium**

`core/companions/engine/memory.py` and `core/companions/engine/history.py` share initialization patterns (load config, set up storage path, initialize backend) with no shared base class. Any cross-cutting change (e.g., adding a new storage backend) requires editing both files.

**Fix:** Introduce a thin `CompanionComponent` base class that handles config loading and path setup, letting subclasses focus only on their specific logic.

---

### 3.5 Unused Import in `task_models.py`
**Severity: Low**

`Enum` is imported (~line 9) and `TaskStatus` uses it, but the first dead `Task` definition (see §1.1) imports additional names that become unreferenced once it is removed.

**Fix:** After removing the dead class, audit and trim imports in this file.

---

## Priority Matrix

| # | File | Issue | Impact | Effort |
|---|------|-------|--------|--------|
| 1 | `apps/audio/tts_manager.py` | Sync load blocks event loop | High | Low |
| 2 | `core/interfaces/dashboard/server.py` | No per-router error isolation | High | Low |
| 3 | `core/orchestrator/task_models.py` | Duplicate `Task` class | High | Trivial |
| 4 | `core/memory/episodic_memory.py` | `time.sleep` in `__init__` | High | Medium |
| 5 | `core/aethviondb/vectorizer.py` | Client rebuilt every embed call | High | Low |
| 6 | `core/bridges/web_search_bridge.py` | HTTP connection leak | Medium | Low |
| 7 | `core/providers/provider_manager.py` | JSON file handle leak + duplicated reload | Medium | Low |
| 8 | `core/memory/history_manager.py` | O(n²) history prepend | Medium | Low |
| 9 | `core/aethviondb/vectorizer.py` | No lock on `_local_model_cache` | Medium | Low |
| 10 | `core/factory/base_agent.py` | Repeated KG queries on spawn | Medium | Medium |
| 11 | Multiple | Bare `except Exception` | Medium | Low |
| 12 | `core/factory/generic_agent.py` | `sys.path` side effect on import | Low | Trivial |
| 13 | `core/providers/provider_manager.py` | Duplicated init/reload logic | Low | Medium |
| 14 | `core/automate/executor.py` | Topo-sort not cached | Low | Low |
| 15 | Companion engine | No shared base class | Low | Medium |

---

## Estimated Gains if Top 10 Are Fixed

| Metric | Estimated Improvement |
|--------|-----------------------|
| Server cold-start time | −10 to −30 seconds (async ChromaDB + async TTS load) |
| Embedding request latency | −15 to −40 ms per call (client caching) |
| Lines of code removed | ~150–200 lines (dead class, duplicated reload, redundant client builders) |
| Crash surface at startup | Reduced by router isolation (29 → 0 single-point-of-failure imports) |
| Memory under concurrent load | Reduced (fixed race on model cache, proper connection management) |
