# AethvionDB — Structured Knowledge Database

**Last Updated:** 2026-05-29

AethvionDB is Aethvion Suite's local knowledge database. It stores information as structured entities — people, places, events, concepts, organizations, and more — in a format designed for AI consumption, semantic search, and relationship mapping. You can build knowledge bases about anything: a fictional universe, historical research, a technical domain, personal notes, or a project knowledge hub.

---

## What AethvionDB Is For

- Build a structured, searchable database on any topic
- Let AI extract and organize knowledge from raw text automatically
- Query and graph-view the relationships between entities
- Export your database for use in RAG pipelines, LLM prompts, or external tools
- Search semantically — find entities by meaning, not just by keyword
- Use your database inside Automate workflows as a live knowledge source

---

## Core Concepts

### Entities

Every piece of knowledge in AethvionDB is an **entity** — a single subject with a canonical name, a type, and structured sections.

**Entity types:**

| Type | Examples |
|---|---|
| `person` | Albert Einstein, Sherlock Holmes, Misaka Cipher |
| `place` | London, Hogwarts, the Andromeda Galaxy |
| `event` | World War II, the Fall of Constantinople |
| `concept` | Quantum entanglement, narrative tension |
| `organization` | NASA, Stark Industries |
| `artifact` | The Mona Lisa, the One Ring |
| `creature` | Dragon, Homo sapiens |
| `substance` | Water, kryptonite |
| `process` | Photosynthesis, gradient descent |
| `phenomenon` | Northern Lights, the Big Bang |
| `work` | *Dune*, *Symphony No. 9*, *Half-Life 2* |
| `species` | Grey wolf, Vulcan |
| `universe` | Marvel Cinematic Universe, Middle-earth |
| `other` | Anything that doesn't fit the above |

### Sections

Each entity has a fixed set of sections:

| Section | Contents |
|---|---|
| `core` | `summary` (1–3 sentences), `aliases`, `categories`, `tags` |
| `timeline` | Dated events: `{ date, event, ref_ids }` |
| `relations` | Typed links to other entities: `{ kind, target_id, note }` |
| `properties` | Free key/value facts specific to the entity type |
| `stubs` | Names of related entities that should get their own entries |
| `vectors` | Embedding vectors (stored here; used for semantic search) |

### Entity IDs

Every entity gets a stable ID in the format `ws_<16 hex chars>`, e.g. `ws_a3f9c2d1b8e4f0a2`. IDs never change after creation. Relations between entities reference each other by ID, not by name — so renaming an entity doesn't break any links.

### Relation Kinds

Relations express how two entities connect. Allowed kinds:

`parent_of`, `child_of`, `member_of`, `contains`, `created_by`, `created`, `located_in`, `location_of`, `part_of`, `has_part`, `preceded_by`, `followed_by`, `related_to`, `instance_of`, `has_instance`, `influenced_by`, `influenced`, `participated_in`, `has_participant`

---

## Multiple Databases

AethvionDB supports multiple independent databases. Each has a name (e.g. `default`, `my-world`, `research`) and lives in its own folder under `data/aethviondb/<name>/`.

Switch between databases using the **database selector** in the top-right of the AethvionDB tab. You can also create new databases, rename them, and point to a database at any absolute path on your machine.

---

## The Dashboard Interface

The AethvionDB header has five tabs: **Explorer**, **Distiller**, **Graph**, **Import**, and **Tools**. The **Tools** sidebar (inside the Tools tab) contains all power-user utilities: Vector Embedding, Semantic Search, Bake, Test, and Benchmark.

### Entity List (Explorer)

The left panel lists all entities in the current database. Click one to open it in the editor. Use the search box to filter by name.

**Column customizer:** Click the **Columns** button in the filter row to choose which columns are shown. Settings persist across sessions via `localStorage`.

| Column | Default | Description |
|---|---|---|
| Tags | ✅ On | Entity tags from `core.tags` |
| Relations | ✅ On | Number of linked entities |
| Sub-topics | ✅ On | Count of stub entries |
| Status | ✅ On | `active` / `stub` / `deleted` |
| Created | Off | Creation timestamp |
| Updated | Off | Last-modified timestamp |
| Source | Off | How the entity was created (`distiller`, `manual`, etc.) |

Click any column header to sort by that column.

### Entity Editor

The editor shows all sections of the selected entity. You can:
- Edit the summary, aliases, tags, categories
- Add and remove timeline events
- Add and remove relations (search for the target entity by name)
- Add and remove free-form properties
- Add stubs (entity names to expand later)

Every save increments the entity's `version` number and updates `updated`.

### Graph View

Click **Graph** in the toolbar to switch to the relationship graph. Entities appear as nodes; relations appear as edges. Click a node to focus it and see its connections. The graph is interactive — drag, zoom, and explore the knowledge web.

**Graph controls (toolbar):**

| Control | What it does |
|---|---|
| Node limit slider (50–2000) | Cap how many nodes are rendered at once — drag left for speed, right for completeness |
| No stubs checkbox | Hide stub-status entities from the graph — shows only fully populated entities |

**Entity info card:** Clicking a node opens a side panel (340 px wide) with the full entity summary, type, status, tags, and relation count. The card body scrolls so long summaries are fully readable.

### Status

Entity status controls visibility in searches:
- `active` — fully populated, appears in all searches
- `stub` — placeholder with minimal content, appears in stub-expansion queue
- `deleted` — soft-deleted, excluded from all searches

---

## Adding Knowledge

### Manual Entry

Click **New Entity** to create an entity by hand. Fill in the name, select the type, and start populating sections in the editor.

### Distiller — AI-Powered Extraction

Paste any text into the **Distiller** panel and click **Distill**. The AI reads the text and produces a fully structured entity automatically:

- Determines the canonical name and entity type itself
- Extracts summary, aliases, tags, categories
- Identifies timeline events with dates
- Discovers relations to other entities mentioned in the text
- Notes sub-topics as stubs for future expansion

The distiller never invents facts — it only extracts what's explicitly present in the text. Missing fields are left empty rather than filled with guesses.

**Supported input:** any text — Wikipedia articles, book excerpts, research papers, raw notes, transcripts, documentation.

### Folder Distiller

Drop an entire folder of text files into the **Folder Distiller** to batch-distill all of them. Each file becomes one or more entities. The engine deduplicates: if a name already exists in the database, the new content is merged into the existing entity rather than creating a duplicate.

### Importer

The **Importer** accepts structured JSON files (matching the AethvionDB entity schema) from external sources. Use this to bring in data from other databases or tool exports.

---

## Stub Expansion

When the distiller encounters names of people, places, or concepts in the text that seem important, it creates **stub entities** — minimal placeholders with just a name and type. Stubs act as a queue for future expansion.

Click **Expand Stubs** (or set it to run autonomously) to have the AI generate full entity content for each stub, using context from related entities already in the database. The expansion engine:

- Finds all entities with `status: "stub"`
- For each stub, generates a full structured entity via AI
- Never overwrites existing data — only fills in empty fields
- Is safe to run multiple times (idempotent via the name index)

You can also expand individual stubs from the entity editor.

---

## Semantic Search and Vectors

### Vectorizing the Database

The tool was renamed from "Vector Search" to **Vector Embedding** to more accurately reflect what it does — it generates and stores vectors; the search happens in the Semantic Search tool.

Click **Vector Embedding** (inside the Tools section) to generate embedding vectors for all entities. Vectors are stored directly inside each entity's `sections.vectors` section.

**Supported embedding models:**

| Model | Provider | Dimensions | Notes |
|---|---|---|---|
| `text-embedding-3-small` | OpenAI | 1536 | Fast, efficient |
| `text-embedding-3-large` | OpenAI | 3072 | Highest quality |
| `text-embedding-ada-002` | OpenAI | 1536 | Legacy |
| `text-embedding-004` | Google | 768 | Gemini embedding — recommended |
| `text-multilingual-embedding-002` | Google | 768 | Multilingual |
| `all-MiniLM-L6-v2` | **Local** | 384 | Fastest local model — no API key needed |
| `all-MiniLM-L12-v2` | **Local** | 384 | Slightly higher quality |
| `all-mpnet-base-v2` | **Local** | 768 | Best local quality |
| `BAAI/bge-small-en-v1.5` | **Local** | 384 | Compact, high performance |
| `BAAI/bge-base-en-v1.5` | **Local** | 768 | Balanced local model |

Cloud models require an OpenAI or Google API key. **Local models** run entirely on your machine with no API key required — install them with `pip install sentence-transformers` (or `pip install aethvion-suite[local-llm]`).

### Semantic Search

Once vectors are generated, use the **Semantic Search** panel to find entities by meaning. Type a natural-language query — the database returns entities ranked by cosine similarity to your query's embedding, not just keyword matches.

Example: searching `"ruler of the sky"` might return entities about Zeus, eagles, or atmospheric phenomena even if none of them contain that exact phrase.

---

## Baking — Snapshot Export

**Baking** compiles your entire database into a single optimized file, ready for external use (RAG pipelines, LLM context injection, vector databases, sharing).

### Creating a Bake

Go to the **Bake** panel and configure:

| Option | Description |
|---|---|
| **Name** | Identifier for this bake (e.g. `default`, `v2`, `full-with-vectors`) |
| **Format** | `jsonl` / `json` / `markdown` / `txt` |
| **Include stubs** | Whether to include stub-status entities |
| **Include vectors** | Whether to embed the vector arrays in the output |
| **Vector models** | Optionally filter to only specific embedding model keys |

Multiple named bakes coexist independently — you can have `default.jsonl` and `full.md` and `rag-ready.jsonl` all at once.

### Bake Formats

| Format | Best For |
|---|---|
| `jsonl` | Streaming, vector database ingestion (one entity per line) |
| `json` | Single structured document with metadata header |
| `markdown` | RAG pipelines, LLM prompt injection, human reading |
| `txt` | Maximum density for token-constrained context windows |

### Bake Files Location

Bake output files live in `{db_root}/baked/`:
- `{name}.jsonl` / `.json` / `.md` / `.txt` — the data file
- `{name}.meta.json` — metadata (entity count, size, timestamp, options used)

### Renaming and Deleting Bakes

Bakes can be renamed or deleted from the Bake panel without affecting the live database.

---

## Backups

Click **Backup** to create a snapshot of the entire database at that moment. Backups are stored in `{db_root}/backups/{timestamp}_{label}/`.

Each backup contains:
- `entities/` — all entity JSON files
- `name_index.json` — the name-to-ID index
- `AethvionDB.BACKUP` — metadata (timestamp, entity count, size)

Restore a backup at any time from the Backups panel. Per-database backup settings (enable automatic backups, keep N most recent) are in the database registry.

---

## Public API (v1)

AethvionDB exposes a full HTTP API for external integrations. It runs on the same port as the Aethvion Suite dashboard.

**Base URL:** `http://localhost:8080/api/v1/`

### Authentication

API endpoints require an API key passed as the `X-API-Key` header. Generate keys in the AethvionDB tab under **Settings → API Keys**.

### Discovery

```
GET /api/v1/
```
Returns version info and a list of all registered databases.

### Raw (Live Database) Endpoints

```
GET    /api/v1/{db}/raw/entities          List entities (paginated, filterable)
GET    /api/v1/{db}/raw/entities/{id}     Get one entity by ID
POST   /api/v1/{db}/raw/entities          Create entity
PUT    /api/v1/{db}/raw/entities/{id}     Full update (replaces entity)
PATCH  /api/v1/{db}/raw/entities/{id}     Partial update (merges sections)
DELETE /api/v1/{db}/raw/entities/{id}     Soft-delete (sets status=deleted)

GET    /api/v1/{db}/raw/search            Keyword + filter search
GET    /api/v1/{db}/raw/vector-search     Semantic similarity search
GET    /api/v1/{db}/raw/graph/{id}        Graph traversal from an entity
POST   /api/v1/{db}/raw/distill           AI-distill text into an entity
POST   /api/v1/{db}/raw/upsert            Smart create-or-update by name

GET    /api/v1/{db}/keys/                 List API keys
POST   /api/v1/{db}/keys/                 Create API key
DELETE /api/v1/{db}/keys/{key_id}         Revoke API key
```

### Baked (Snapshot) Endpoints

```
GET  /api/v1/{db}/baked/                  List bakes
POST /api/v1/{db}/baked/start             Start a new bake
GET  /api/v1/{db}/baked/{name}/status     Bake progress
GET  /api/v1/{db}/baked/{name}/download   Download the bake file
GET  /api/v1/{db}/baked/{name}/search     Search within the snapshot (keyword)
GET  /api/v1/{db}/baked/{name}/vector-search  Search within the snapshot (semantic)
```

### Response Envelope

All responses follow a standard envelope:

```json
{
  "ok":    true,
  "data":  { ... },
  "took":  "12ms",
  "error": null
}
```

---

## Using AethvionDB in Automate Workflows

Four Automate nodes connect directly to AethvionDB:

| Node | What It Does |
|---|---|
| `aethviondb.search` | Keyword search against a live database |
| `aethviondb.semantic_search` | Vector similarity search against a live database |
| `aethviondb.snapshot_search` | Keyword search against a baked snapshot file |
| `aethviondb.snapshot_semantic_search` | Semantic search against a baked snapshot |

All four nodes output:
- `out` — the matching entities as a JSON string
- `count` — number of results
- `error` — error message if the query failed

**Example pattern:**

```
trigger.manual → input.text (query) → aethviondb.semantic_search → ai.any (summarize results) → output.display
```

This workflow: takes a search query, finds semantically similar entities in your knowledge base, feeds them to an AI model for synthesis, and displays the answer.

---

## File Structure

```
data/aethviondb/
├── _db_registry.json           ← Registry: name → path + metadata for all databases
└── default/                    ← One folder per database
    ├── entities/               ← Entity JSON files (one per entity: ws_<id>.json)
    ├── name_index.json         ← Name → ID index (prevents duplicate entity names)
    ├── AethvionDB.VECINFO      ← Vector generation state and progress
    ├── baked/                  ← Bake output files
    │   ├── default.jsonl
    │   ├── default.meta.json
    │   └── ...
    └── backups/                ← Point-in-time backups
        └── 20260526_143022_before-merge/
            ├── entities/
            ├── name_index.json
            └── AethvionDB.BACKUP
```

---

## Entity JSON Format (Reference)

```json
{
  "id":      "ws_a3f9c2d1b8e4f0a2",
  "type":    "person",
  "name":    "Marie Curie",
  "status":  "active",
  "version": 3,
  "created": "2026-01-10T09:00:00+00:00",
  "updated": "2026-05-26T14:22:00+00:00",
  "source":  "distiller",
  "sections": {
    "core": {
      "summary":    "Polish-French physicist and chemist, pioneer of radioactivity research.",
      "aliases":    ["Maria Skłodowska-Curie", "Madame Curie"],
      "categories": ["Science", "Physics", "Chemistry"],
      "tags":       ["radioactivity", "Nobel Prize", "polonium", "radium"]
    },
    "timeline": [
      { "date": "1867-11-07", "event": "Born in Warsaw, Poland", "ref_ids": [] },
      { "date": "1903",       "event": "Awarded Nobel Prize in Physics", "ref_ids": [] },
      { "date": "1911",       "event": "Awarded Nobel Prize in Chemistry", "ref_ids": [] },
      { "date": "1934-07-04", "event": "Died of aplastic anemia", "ref_ids": [] }
    ],
    "relations": [
      { "kind": "related_to", "target_id": "ws_b1c2d3e4f5a6b7c8", "note": "Co-discovered polonium and radium" }
    ],
    "properties": {
      "nationality": "Polish-French",
      "field":       "Physics, Chemistry",
      "awards":      "Nobel Prize Physics 1903, Nobel Prize Chemistry 1911"
    },
    "stubs": ["Pierre Curie", "Polonium", "Radium"],
    "vectors": {
      "text-embedding-3-small": {
        "embedding":    [0.012, -0.034, ...],
        "model":        "text-embedding-3-small",
        "dimensions":   1536,
        "generated_at": "2026-05-26T14:00:00+00:00"
      }
    }
  }
}
```

---

## Tips and Best Practices

### Start with the Distiller

Rather than typing entities by hand, paste Wikipedia articles, research papers, or any text you have. Let the AI do the extraction work. Manual editing is faster when you have a structured draft to start from.

### Use Stubs as Your Queue

Don't try to build a complete database in one session. Distill a few core entities, then run Expand Stubs to let the engine fill out the graph. Each expansion generates new stubs, which become the next round of expansion.

### Vectorize Before Searching Semantically

Semantic search only works if vectors exist. Run Vectorize after adding or importing a batch of entities. You don't need to re-vectorize unchanged entities — the vectorizer skips entities that already have the selected model's embedding stored.

### Bake for External Use

If you're using your database as RAG context for LLM prompts, bake to Markdown (`markdown` format). The output is structured but human-readable, making it easy to inject into a system prompt or document. Use `jsonl` format for vector database ingestion.

### Back Up Before Major Operations

Create a backup before running bulk operations (batch distillation, expansion runs, imports). Restoring from backup takes seconds.

### Multiple Databases

Use separate databases for separate domains. A `fiction` database for worldbuilding, a `research` database for a project, and a `default` database for general knowledge all stay cleanly separated. Automate workflows specify which database to query, so you can target the right knowledge base from each workflow.
