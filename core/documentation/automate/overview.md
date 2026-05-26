# Automate — Visual Workflow Builder

**Last Updated:** 2026-05-26

Automate is Aethvion Suite's node-based workflow builder. You connect nodes on a visual canvas to create automation pipelines — no code required. Workflows run locally on your machine, with AI, file system, web, and data operations all available as drag-and-drop nodes.

---

## What You Can Build

- Scrape a web page, summarize it with AI, and display the result
- Watch a folder for new files and classify or process them automatically
- Fetch data from an API, filter and transform it, and write the result to a file
- Extract structured data (names, dates, emails) from any pasted text
- Run any AI model with a custom prompt and pipe its output to another node
- Build multi-step pipelines where each node's output feeds the next

---

## The Canvas

Open **Automate** in the sidebar. The canvas is a free-form space where you place and connect nodes.

### Navigation

| Action | How |
|---|---|
| Pan | Middle-click drag, or hold Space + left-click drag |
| Zoom | Scroll wheel |
| Select node | Left-click |
| Multi-select | Shift + click, or drag a selection box on empty canvas |
| Move node | Drag from the node body |
| Reset view | Toolbar → Home icon (or press H) |
| Fit to screen | Toolbar → Fit icon |

### Connecting Nodes

Every node has **input ports** (left side) and **output ports** (right side). Drag from an output port to an input port to wire them together. The port tooltip shows you the port name, direction, and what kind of data it carries.

To delete a connection: click it to select it, then press Delete.

### Trigger Highlighting

Click any **trigger node** on the canvas to highlight which nodes it will activate. Nodes in its chain glow blue; everything outside dims to gray. This makes it easy to see exactly what will run when that trigger fires.

---

## Workflows

### Creating a Workflow

Click **New** in the toolbar. Give it a name — the name appears in the toolbar and is used to save the file.

### Saving

Click **Save** (or Ctrl+S). Workflows are stored locally as JSON files in `data/automate/`.

### Loading

Your saved workflows appear in the sidebar panel on the left side of the canvas. Click one to load it.

### Exporting

Click **Export** to download the workflow as a `.json` file you can share or back up.

### Deleting

Click **Delete** in the toolbar. This permanently removes the workflow file.

---

## Running a Workflow

### Run Button

The **Run** button executes the workflow. Next to it is a **trigger selector** (defaults to "All").

- **All** — runs every trigger in the workflow sequentially, one after another
- **Select a specific trigger** — runs only that trigger's chain

When you run, the execution panel opens on the right showing real-time progress: each node lights up as it runs, turns green on success, or red on failure.

### Real-Time Streaming

Execution events are streamed live via SSE (Server-Sent Events). You see each node's status change the moment it happens — no waiting for the full run to complete.

### What Gets Executed

When a trigger fires, the engine computes its **reachable nodes** using a three-phase algorithm:

1. **Forward** — every node directly downstream from the trigger
2. **Other territory** — nodes owned by *other* triggers (so parallel chains don't bleed into each other)
3. **Backward** — upstream data suppliers (input nodes, variables) that feed into the active chain, stopping at other triggers' boundaries

This means:
- `input.text` and `data.variable` nodes don't need to be connected to the trigger directly — the engine finds them automatically via backward traversal
- Two triggers in the same workflow can each have their own input nodes without interfering with each other

---

## Node Categories

### Triggers

Every workflow needs at least one trigger — it's the starting point for execution.

| Node | What It Does |
|---|---|
| `trigger.manual` | Fires when you click Run in the UI |
| `trigger.schedule` | Fires on a cron schedule; outputs an ISO timestamp via `data` port |
| `trigger.webhook` | Fires when an HTTP POST arrives at its endpoint; passes the request body |
| `trigger.app_event` | Fires when an internal Aethvion event occurs (companion message, agent completion, etc.) |
| `trigger.file_watch` | Fires when a watched file or folder changes; outputs the path and event type |

All triggers emit a `trigger` output port that carries `null` — it signals graph reachability without injecting data into downstream nodes.

---

### Inputs

Source nodes that supply values. They have no input ports — they're the start of a data chain.

| Node | Output | Notes |
|---|---|---|
| `input.text` | `out` (string) | Paste or type static text; can be edited inline |
| `input.number` | `out` (number) | Numeric constant |
| `input.list` | `out` (list) | Comma-separated values become a JSON array |
| `input.file` | `out` (string), `name`, `path`, `size` | Reads a file from disk; path set in properties |

---

### Outputs

Sink nodes that display or store results.

| Node | Input | Notes |
|---|---|---|
| `output.display` | `in` | Shows the value in the execution panel results |
| `output.file` | `in` | Writes the value to a file; path set in properties |
| `output.clipboard` | `in` | Copies the value to the system clipboard |

---

### AI

AI nodes call the configured model via the AetherCore gateway (supports all configured providers with automatic failover).

| Node | Key Inputs | Key Outputs | Notes |
|---|---|---|---|
| `ai.any` | `in`, `model`, `system_prompt` | `out`, `error` | General-purpose prompt; pick any model |
| `ai.google` | `in`, `model`, `system_prompt` | `out`, `error` | Same as `ai.any` but scoped to Google models |
| `ai.summarize` | `in`, `model` | `out`, `error` | Focused summarizer; style (paragraph/bullets/headline/TL;DR) and length set in properties |
| `ai.classify` | `in`, `model` | `label`, `reasoning`, `all`, `error` | Classifies text into one of the configured categories; returns label + one-sentence reasoning |
| `ai.extract_data` | `in`, `model` | `out`, `error` | Extracts structured fields from text; fields defined as `name: description` lines in properties |
| `ai.analyze_image` | `image`, `model` | `out`, `error` | Describes or answers questions about an image |
| `ai.generate_image` | `in`, `model` | `image`, `url`, `error` | Generates an image from a text prompt |
| `ai.speech_to_text` | `audio`, `model` | `out`, `error` | Transcribes audio to text (Whisper) |
| `ai.text_to_speech` | `in`, `model` | `audio`, `error` | Synthesises speech from text (Kokoro/XTTS) |

**Prompt prefix/suffix:** The `ai.any` and `ai.google` nodes support `prompt_prefix` and `prompt_suffix` ports — text prepended/appended to the main input before it reaches the model.

---

### Logic

Flow-control nodes that branch, loop, delay, or catch errors.

| Node | Inputs | Outputs | Notes |
|---|---|---|---|
| `logic.if` | `in` | `true`, `false` | Evaluates a Python expression (e.g. `len(value) > 100`); routes value to the matching port |
| `logic.switch` | `in` | `case_1`…`case_4`, `default` | Routes value to the port matching a configured string |
| `logic.delay` | `in` | `trigger` | Waits N milliseconds (max 10 s), then passes `in` through as `trigger` |
| `logic.loop` | `in` (list) | `item`, `done` | Emits the first item from a list; `done` carries the full list |
| `logic.repeat` | `in` | `out` (list), `count` | Repeats the input value N times into a list |
| `logic.merge` | `a`, `b`, `c`, `d` | `out`, `source` | First-non-null mode: passes the first arriving value; All mode: collects all into an object |
| `logic.try_catch` | `in`, `error_in` | `try`, `catch`, `always` | Routes to `catch` if `error_in` is non-empty; `always` fires regardless |

---

### Data

Nodes for transforming, parsing, and managing data.

| Node | Notes |
|---|---|
| `data.variable` | Named workflow-scoped variable; reads the stored value on execution |
| `data.set_variable` | Stores a value into a named workflow variable |
| `data.template` | Mustache-style template: `{{variable_name}}` replaced with values |
| `data.format_text` | Format a string using Python `.format()` with named ports |
| `data.regex` | Apply a regex to the input; outputs match, groups, or replaced string |
| `data.split_text` | Split text by delimiter into a list |
| `data.parse_json` | Parse a JSON string into an object |
| `data.extract_json` | Extract a value from a JSON path (e.g. `items[0].name`) |
| `data.csv_parse` | Parse CSV text into a list of row objects |
| `data.filter` | Filter a list by a Python expression (`item.get('city') == 'New York'`) |
| `data.list_item` | Get the Nth item from a list |
| `data.merge_objects` | Merge two JSON objects into one |
| `data.type_convert` | Convert between string, number, boolean, list |
| `transform.combine` | Concatenate multiple inputs into one string |

---

### Actions

Nodes that interact with the file system, network, clipboard, or system shell.

| Node | Notes |
|---|---|
| `action.file_read` | Read a file from disk |
| `action.file_write` | Write text to a file |
| `action.file_list` | List files in a directory |
| `action.http` | Make an HTTP request (GET/POST/etc.); returns status, body, headers |
| `action.web_scrape` | Fetch and extract readable text from a URL |
| `action.run_command` | Execute a shell command; returns stdout, stderr, exit code |
| `action.run_script` | Run a Python snippet inline |
| `action.run_agent` | Dispatch a task to an Aethvion agent |
| `action.clipboard` | Read from or write to the system clipboard |
| `action.log` | Write a message to the Aethvion log |
| `action.notify` | Send a system desktop notification |
| `action.screenshot` | Capture the screen; outputs an image |
| `action.ocr` | Extract text from an image using OCR |
| `action.camera_capture` | Capture a frame from the webcam |

---

### Memory

Read and write to Aethvion's persistent memory system.

| Node | Notes |
|---|---|
| `memory.store` | Write a value to a named memory key |
| `memory.retrieve` | Read a value by key |
| `memory.search_semantic` | Find memory entries semantically similar to the query |

---

### AethvionDB

Nodes that query the AethvionDB knowledge database.

| Node | Inputs | Outputs | Notes |
|---|---|---|---|
| `aethviondb.search` | `query`, `db` | `out`, `count`, `error` | Keyword/name search against a live database |
| `aethviondb.semantic_search` | `query`, `db` | `out`, `count`, `error` | Vector similarity search against a live database |
| `aethviondb.snapshot_search` | `query`, `bake` | `out`, `count`, `error` | Keyword search against a baked snapshot file |
| `aethviondb.snapshot_semantic_search` | `query`, `bake` | `out`, `count`, `error` | Semantic search against a baked snapshot |

---

### Integrations

Connect to external services and companions.

| Node | Notes |
|---|---|
| `companion.ask` | Send a message to a companion and receive its response |
| `integration.discord` | Post a message to a Discord webhook |
| `integration.slack` | Post a message to a Slack webhook |
| `integration.email` | Send an email |

---

## Example Workflows

Six example workflows ship with Automate and are accessible from the **Examples** button in the sidebar panel. They demonstrate common patterns and serve as starting points.

| Example | Pattern |
|---|---|
| **Web to Summary** | `trigger.manual → action.web_scrape → ai.summarize → output.display` |
| **Data Extractor** | `trigger.manual + input.text → ai.extract_data → output.display` |
| **AI Prompt Tester** | `trigger.manual + input.text → ai.any → output.display` |
| **File Classifier** | `trigger.manual + input.file → ai.classify → output.display` |
| **Scheduled Web Brief** | `trigger.schedule → action.web_scrape → ai.summarize → action.notify` |
| **CSV Data Pipeline** | `trigger.manual + input.file → data.csv_parse → data.filter → output.display` |

Loading an example creates a copy in your workspace — the originals are never modified.

---

## Compiling a Workflow

Click **Compile** in the toolbar. This generates a self-contained `run.py` bundle (plus a `run.bat` launcher on Windows) that runs your workflow without the Aethvion Suite dashboard.

The compiled bundle embeds:
- Your workflow JSON (node graph + connections)
- A standalone `WorkflowExecutor` class with the full three-phase reachability algorithm
- All node handlers (copied verbatim from the live implementation)
- A `run()` entry point that executes the workflow and prints results

The compiled file reads API keys from the same `.env` in the project root. It does not include keys directly.

**When to compile:**
- Deploy a workflow to a server or scheduled job
- Share a workflow as a standalone script
- Run a workflow without launching the full dashboard

---

## Execution Model (Technical)

### Graph Traversal

The executor uses **Kahn's algorithm** (BFS topological sort) to determine node execution order. Nodes with no upstream dependencies run first; downstream nodes run after all their inputs are ready.

### Reachability — Three-Phase Algorithm

When a single trigger fires, the engine determines which nodes to execute:

**Phase 1 — Forward BFS from the active trigger**
Finds every node the trigger can directly reach by following connection edges forward.

**Phase 2 — Forward BFS from all other (inactive) triggers**
Builds an "other territory" set — nodes exclusively owned by sibling trigger chains.

**Phase 3 — Backward BFS from the Phase 1 set**
Pulls in upstream source nodes (input.text, data.variable, etc.) that feed into the active chain. The backward walk is blocked if it would cross into other territory or reach another trigger node.

This correctly handles:
- Source nodes that aren't connected to the trigger (input.text feeding a scraper)
- Two triggers with their own private input nodes
- Two triggers that share a downstream node (each fires only its own upstream branch)

### `__trigger__` Port Convention

Connections from trigger output ports use `targetPort: "__trigger__"`. This establishes graph reachability without injecting a data value — trigger nodes return `{"trigger": None}` and the executor skips `None` values when gathering inputs. Downstream nodes receive data only from actual data connections, not from the trigger signal itself.

### Event Streaming

The `/run-stream` endpoint (POST) returns a `text/event-stream` (SSE) response. Each line is a JSON event:

```json
{"type": "node_status", "node_id": "n1", "status": "running"}
{"type": "node_status", "node_id": "n1", "status": "done", "outputs": {...}}
{"type": "log", "level": "info", "msg": "✓ Scrape Page", "ts": "14:22:01.345"}
{"type": "done", "result": {"ok": true, ...}}
```

The executor runs in a thread (`asyncio.to_thread`) and bridges events to the async event loop via `loop.call_soon_threadsafe(queue.put_nowait, event)`.

---

## Adding New Nodes (Developer Reference)

Adding a new node type is a two-step process:

**Step 1** — Register the node definition in `core/automate/automate_routes.py` inside `_NODE_TYPES`. This dict controls what appears in the "Add Node" panel.

**Step 2** — Add the handler function to the correct category file in `core/automate/nodes/` (e.g., `ai.py`, `logic.py`, `actions.py`), then register it in `core/automate/nodes/__init__.py` in the `_REGISTRY` dict.

Handler signature:
```python
def my_node_handler(node: dict, inputs: dict, ctx: WorkflowExecutor) -> dict:
    p = node.get("properties", {})
    # ... do work ...
    return {"out": result, "error": ""}
```

- `node` — the full node dict including `id`, `type`, `label`, `properties`
- `inputs` — gathered port values from upstream connections
- `ctx` — the `WorkflowExecutor` instance; use `ctx._info()`, `ctx._warn()`, `ctx._error()` for logging; `ctx._vars` for workflow-scoped variables
- Return a dict mapping output port names to values; return `None` for a port to exclude it from downstream inputs

The `executor.py` file itself never needs to change when adding new nodes.

---

## File Locations

| Path | Contents |
|---|---|
| `core/automate/` | Executor, compiler, routes |
| `core/automate/nodes/` | Node handler implementations (one file per category) |
| `core/automate/examples/` | Bundled example workflow JSON files |
| `data/automate/` | User-created workflow JSON files |
| `core/interfaces/dashboard/static/js/mode-automate.js` | Frontend canvas, node rendering, SSE streaming client |
| `core/interfaces/dashboard/static/css/automate.css` | Canvas and node styles |
| `core/interfaces/dashboard/static/partials/automate.html` | Toolbar and panel HTML |
