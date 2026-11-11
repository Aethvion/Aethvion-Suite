# Aethvion Suite — Evolution Plan

**Started:** 2026-11-11
**Goal:** turn the Suite from a collection of AI tabs into (1) a workflow system where *any* model
— text, image, 3D, audio, or a custom tool — can be chained with any other, and (2) a hub where one
person works alongside many agents on real projects (first use case: game development).

This document is the plan *and* the change log. Each phase lists what was found, what is decided,
and what has actually shipped. Status markers: ✅ shipped · 🟡 partly shipped · ⬜ planned.

---

## 1. Audit — where the Suite stands today

### What is strong

| Area | State |
|---|---|
| **Automate** (`core/automate/`) | Solid node editor: ~90 node types defined as JSON (`core/config/automate/nodes/`), parallel DAG executor, SSE streaming, triggers, compile-to-standalone. Adding a node is two small steps. |
| **Providers** (`core/providers/`) | 10 chat providers behind `call_with_failover()`; any chat model can be picked per node. |
| **Image / 3D / Audio tabs** | Each has a working generation backend (local Diffusers, SD WebUI, Imagen, DALL·E; TRELLIS/TripoSR worker processes; Kokoro/XTTS/Whisper). |
| **Agent Corp** (`core/orchestrator/corp_manager.py`) | Multi-worker teams with roles, a per-worker model, task board, shared log, cost tracking. |
| **AethvionDB, memory, companions** | Mature and already exposed as nodes. |

### What blocks the goal

1. **Models are siloed by tab.** Text models go through `ProviderManager`; image generation lives
   inside `photo_routes.py`; 3D lives inside `three_d_routes.py`; audio inside `tts_manager`. There
   is no single place that says "these are all the models I have and what each can do". The
   `ai.generate_image` node could only call Google Imagen. There was **no 3D node at all**.
2. **No way to plug in a new model without writing Python.** A new 3D or texture model (local
   server, hosted API, or a command-line tool such as Blender) needed a new route file plus a new
   node handler.
3. **Wires only really carry text.** Images travelled as temp-file paths or base64 strings; there
   was no notion of "this is a mesh", no stable storage, no record of which model produced what
   from what. Generated files ended up in the OS temp folder.
4. **The executor could not branch or loop for real.**
   - `logic.if` / `logic.switch` set the untaken port to `None`, but the nodes behind it **still
     ran** (with empty input).
   - `logic.loop` only emits the first list item.
   - Graphs must be acyclic, so "generate → verify → retry if bad" was not expressible.
   - No sub-workflows, no cancel, no run history.
5. **Nothing can check non-text output.** A verification step for a 3D model needs facts about the
   mesh (triangle count, UVs, textures) and a model that judges against criteria.
6. **Agents and workflows don't share anything.** Agent Corp workers write files to their own
   workspace; workflows write to temp; the Image/3D tabs keep their own histories. There is no
   shared project space or asset library — the things a "coworker hub" is built on.

---

## 2. Target architecture

```
                      ┌───────────────────────────────────────────┐
                      │                 STUDIO (hub)              │  Phase 3
                      │ projects · team of agents · board · feed  │
                      └───────────────┬───────────────────────────┘
                 uses workflows as tools │ reads/writes assets
        ┌──────────────────────────────▼──────────────┐
        │            AUTOMATE (workflow engine)        │  Phase 1–2
        │ branching · sub-workflows · loops · retries  │
        └───────┬──────────────────────────┬───────────┘
   invokes any model                 stores every output
        ┌───────▼────────┐          ┌──────▼───────────┐
        │   MODEL HUB    │          │  ASSET LIBRARY   │  Phase 1
        │ one registry:  │          │ typed files +    │
        │ capability →   │          │ lineage (who     │
        │ endpoints      │          │ made what from   │
        │                │          │ what)            │
        └───────┬────────┘          └──────────────────┘
   adapters: llm · suite-image · suite-3d · http · command
```

### Design rules

- **Capability, not provider.** A node asks for a *capability* (`mesh.generate`, `mesh.texture`,
  `image.generate`, `text.generate`, …). Any endpoint that declares the capability can serve it, so
  swapping the model behind a step is a dropdown change.
- **Plugging in a model is configuration.** A JSON file (or a form in the UI) describing an HTTP
  API or a command line is enough. No Python required.
- **Everything a model produces is an asset.** Assets are files with a kind, stored permanently,
  with lineage: workflow, run, node, endpoint, parent assets.
- **Existing features keep working.** The old tabs, nodes, saved workflows and the compiler are
  left intact; new capabilities are added beside them and old nodes are upgraded in place only
  where the behaviour is a strict superset.

---

## 3. Phases

### Phase 1 — Model Hub, Asset Library, engine v2  (this change set)

| # | Item | Status |
|---|---|---|
| 1.1 | `core/assets/` — asset store with kinds, lineage, tags, REST API | see §4 |
| 1.2 | `core/modelhub/` — capability registry + adapters (`llm`, `suite-image`, `suite-3d`, `http`, `command`) | see §4 |
| 1.3 | Custom endpoints as JSON in `data/config/model_endpoints/`, templates shipped in `core/config/model_endpoints/` | see §4 |
| 1.4 | Executor: real branch pruning, cancel, run ids, run history | see §4 |
| 1.5 | New nodes: 3D generate / texture, universal *Run Model*, mesh inspect, AI verify (quality gate), asset save/load/export, sub-workflow, for-each, retry-until | see §4 |
| 1.6 | `ai.generate_image` upgraded to use any image endpoint | see §4 |
| 1.7 | Example workflows for game-dev pipelines | see §4 |
| 1.8 | Dashboard: Assets + Model Hub tab; asset previews inside Automate | see §4 |

### Phase 2 — Workflow depth  ⬜

- **Human-in-the-loop node** (`flow.approval`): pause a run, show the candidate asset(s), continue
  on approve / branch on reject. Needs a pending-approvals inbox in the UI.
- **Resumable runs**: persist node outputs as a run proceeds so a failed 20-minute pipeline can be
  resumed from the failed node instead of restarted.
- **GPU scheduling**: local image/3D/LLM models compete for one GPU. Add a resource lock per
  endpoint (`"exclusive": "gpu"`) so the executor serialises heavy local steps and unloads models
  between them.
- **Typed ports in the editor**: colour ports by kind (text / image / mesh / audio) and refuse
  incompatible connections.
- **Mesh rendering**: ship a `mesh.render` endpoint (Blender headless turntable) so vision models
  can judge a 3D model from pictures, not only from stats and textures.
- **Compiler support** for the new nodes (standalone bundles currently cover the original node set
  only).
- **Batch runs / parameter sweeps**: run one workflow over a table of inputs and compare results
  side by side (same prompt, three 3D models).

### Phase 3 — Studio: the coworker hub  ⬜

The Suite already has the pieces (Agent Corp, agents, companions, schedule, workflows). Studio
joins them around a **project**:

- **Project** = a folder on disk (e.g. a Unity/Unreal/Godot repo) + brief + asset library scope +
  team + board.
- **Team**: agents with a role, a model, and a tool set. Roles for game dev out of the box: concept
  artist, 3D artist, technical artist, gameplay programmer, writer, QA, producer.
- **Workflows as tools**: any saved workflow with `global.*` inputs and `flow.return` outputs is
  callable by an agent ("make a prop from this description"). This is the bridge between the two
  halves of the Suite and is the first thing to build in this phase.
- **Shared board + feed**: built on the existing Corp task board; adds asset attachments, review
  states (draft → needs review → approved), and a single activity feed across agents and workflow
  runs.
- **Review queue**: everything agents produce lands in one inbox for the human to approve, reject
  with a comment, or send back.
- **Project memory**: one AethvionDB database per project (design doc, art bible, naming rules) that
  every agent and workflow reads.
- **Engine bridges**: export nodes/tools for Unity, Unreal and Godot (import settings, folder
  conventions, `.meta` generation), plus Blender for conversion and LODs.

### Phase 4 — Polish and reach  ⬜

- Workflow marketplace/import of shared pipelines, endpoint packs for popular model servers.
- Cost and time budgets per run and per project.
- Scheduled production (nightly asset batches, automated playtest summaries).

---

## 4. Change log

### 2026-11-11 — Phase 1 shipped (uncommitted at time of writing)

**New packages**
- `core/assets/` — `store.py` (asset records, lineage, export), `values.py` (turn any wire value into
  bytes/path), `asset_routes.py` (`/api/assets`). Files live in `data/assets/`.
- `core/modelhub/` — `capabilities.py`, `registry.py` (built-in discovery + custom endpoints in
  `data/config/model_endpoints/*.json`), `adapters.py` (`llm`, `suite-image`, `suite-3d`, `demo`,
  `http` incl. job polling, `command`), `hub.py` (`hub.invoke()`), `glb.py` (GLB/OBJ inspection,
  no dependencies), `templating.py`, `modelhub_routes.py` (`/api/modelhub`),
  `scripts/blender_*.py`. Endpoint templates in `core/config/model_endpoints/`.

**Executor (`core/automate/executor.py`)**
- Nodes with no live data input are skipped ("branch not taken" / "an upstream node failed").
  Opt out per workflow: `"settings": {"prune_dead_branches": false}`. **Behaviour change** for old
  workflows that relied on untaken branches still running with empty input.
- Run ids, cancel, `returns`, sub-workflow nesting (max depth 8).
- Routes: run history in `data/automate/runs/`, `POST /runs/{id}/cancel`, `GET /workflows/{id}/runs`,
  `GET /runs/{id}`, `GET /workflow-options`; SSE now starts with a `run_started` event.

**New nodes** (definitions in `core/config/automate/nodes/`, handlers in `core/automate/nodes/`)
- Models: `model.run`, `model3d.generate`, `model3d.texture`, `mesh.inspect`, `quality.verify`
- Assets: `asset.save`, `asset.load`, `asset.export`
- Flow: `flow.input`, `flow.return`, `flow.subworkflow`, `flow.for_each`, `flow.retry_until`
- `ai.generate_image` now accepts any image endpoint and outputs an `image` asset;
  `ai.analyze_image` and `action.ocr` accept assets.

**Examples** (Automate → Examples): 3D Prop Pipeline, …with AI Review, Make Prop (sub-workflow),
3D Prop: Retry Until Pass, Batch Props (For Each). They default to the `demo:*` placeholder
endpoints so they run with no model installed.

**Dashboard**: new *Assets & Models* tab (Workspace category); Automate shows asset previews on
nodes and in Results; the Run button becomes Stop while a run is active.

**Tests**: `tests/test_workflow_engine_v2.py` (23 tests, offline).

### 2026-11-11 (later) — 3D workers made to work, Image node, symbol repair

Found while running the 3D Prop Pipeline against freshly installed Trellis-2 and TripoSR:

- **Trellis-2 would not load.** The installer's attention patch wrote the two characters `\n`
  instead of line breaks and replaced every `else:` in `full_attn.py`, leaving files that do not
  parse. Replaced by `core/interfaces/dashboard/trellis_patches.py` (anchored edits, compiles the
  result before writing, idempotent). Existing installs are repaired automatically the next time
  the worker starts.
- **Trellis-2 export crashed** (`MeshExtractResult has no attribute apply_transform`): the worker
  rotated the wrong object and base64-encoded a mesh object instead of GLB bytes. Fixed in
  `templates/tsr_server_template.py`.
- **Trellis-2 texture baking is unavailable on this machine.** It needs `diff_gaussian_rasterization`
  (built from the mip-splatting repo), which the installer never installs. The worker now falls
  back to a simplified mesh with per-vertex colours instead of failing. `nvdiffrast` was missing
  too and has been installed into the Trellis venv by hand.
- **TripoSR would not load** (`No module named 'torchmcubes'`): the C++/CUDA extension failed to
  build, but the install was still marked complete. The worker now uses a scikit-image
  marching-cubes fallback (CPU; axis order and face orientation checked against a known shape).
- **Worker start-up** (`three_d_routes.py`): generation now waits for the model to finish loading
  instead of returning "HTTP 503"; a worker stuck in the failed state is replaced on the next
  attempt or Launch click; installed `run_server.py` files are refreshed from the templates on
  start; errors show the actual cause and the log path. Both local models need an image — a
  prompt-only request now says so.
- **Engine:** a step whose required input never arrived (upstream failed) is skipped instead of
  reporting a second error (`NodeSkipped`).
- **New node `input.image`** ("Image", Inputs): pick a file or paste an asset id; imports once and
  reuses it. New example *Image to 3D Model*.
- **Corrupted symbols** (`â€”`, `â€¦`, `â†’` …): 1,483 sequences in 13 files were UTF-8 that had
  been re-saved as Windows-1252. Repaired in place; this predates this work (present in `HEAD`).

Verified live: *Image to 3D Model* with Trellis-2 (38 s including model load, 12.5k triangles,
vertex colours) and TripoSR (19 s) on the RTX 4090. 26 tests pass.

**Not verified / not done**
- Real 3D generation is verified (see the entry above). No real image, texturing or chat model
  was called: the API keys in the test environment are invalid, so `suite-image` and `llm` are
  exercised only up to their error handling and `quality.verify` is tested with a stubbed reviewer.
- There is still no real texturing endpoint (`mesh.texture`); only the demo placeholder.
- Trellis-2 textured export needs `diff_gaussian_rasterization` built into its venv
  (mip-splatting `submodules/diff-gaussian-rasterization`, `pip install --no-build-isolation`);
  the installer does not do this yet.
- The Blender scripts and the hosted-API template are untested (Blender is not installed; the
  hosted template uses placeholder URLs).
- `docs/modelhub/overview.md` (endpoint file reference, linked from the UI) is not written yet.
- `docs/automate/overview.md` does not yet list the new nodes.
- The standalone compiler does not support the new nodes.
