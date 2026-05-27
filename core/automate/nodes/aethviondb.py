"""
core/automate/nodes/aethviondb.py
══════════════════════════════════
Handlers for AethvionDB workflow nodes.

  aethviondb_search          — keyword search over live (raw) entity files
  aethviondb_snapshot_search — keyword search over a baked/snapshot dataset
  aethviondb_semantic_search — vector cosine-similarity search over live entities

  aethviondb_create_database — create and register a new AethvionDB database
  aethviondb_get_stats       — statistics for a database (counts by status)
  aethviondb_list_entities   — list entities with optional type/status filters
  aethviondb_get_entity      — fetch a single entity by ID or name
  aethviondb_create_entity   — create a new entity record
  aethviondb_update_entity   — update fields on an existing entity
  aethviondb_delete_entity   — soft-delete an entity
  aethviondb_distill         — distil free-text into a structured entity via AI
  aethviondb_expand_entity   — expand a stub entity with AI-generated content
  aethviondb_deepen_entity   — deepen sub-topics / relations of an active entity
  aethviondb_create_snapshot — bake the database to a portable snapshot file
  aethviondb_list_snapshots  — list all snapshots for a database
  aethviondb_validate        — run integrity checks across the database
  aethviondb_generate_vectors— generate embeddings for all entities

Keyword nodes share the same scoring logic but differ in where they load entity
data from: raw reads db_root/entities/*.json directly; snapshot reads the JSONL/
JSON file produced by the baker.

Semantic search embeds the query via the configured embedding model and compares
it against vectors pre-generated and stored in entity["sections"]["vectors"].
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from pathlib import Path
from typing import Any

from ._utils import _to_str


# ── Scoring ────────────────────────────────────────────────────────────────────

def _score_raw(query: str, entity: dict) -> float:
    """Score a raw (live) entity — fields live inside sections.core."""
    if not query:
        return 1.0
    q    = query.lower()
    core = entity.get("sections", {}).get("core", {})
    name    = entity.get("name",          "").lower()
    summary = core.get("summary",         "").lower()
    aliases = " ".join(core.get("aliases", [])).lower()
    tags    = " ".join(core.get("tags",    [])).lower()

    if name == q:           return 1.0
    if q in name:           return 0.90
    if q in summary[:400]:  return 0.70
    if q in aliases:        return 0.65
    if q in tags:           return 0.60

    words = q.split()
    if len(words) > 1:
        hay     = f"{name} {summary[:600]} {aliases} {tags}"
        matched = sum(1 for w in words if w in hay)
        if matched:
            return round(0.5 * matched / len(words), 3)
    return 0.0


def _score_baked(query: str, entity: dict) -> float:
    """Score a baked entity — fields are flat (name/summary/aliases/tags)."""
    if not query:
        return 1.0
    q       = query.lower()
    name    = entity.get("name",    "").lower()
    summary = entity.get("summary", "").lower()
    tags    = " ".join(entity.get("tags",    [])).lower()
    aliases = " ".join(entity.get("aliases", [])).lower()

    if name == q:           return 1.0
    if q in name:           return 0.90
    if q in summary[:400]:  return 0.70
    if q in aliases:        return 0.65
    if q in tags:           return 0.60

    words = q.split()
    if len(words) > 1:
        hay     = f"{name} {summary[:600]} {aliases} {tags}"
        matched = sum(1 for w in words if w in hay)
        if matched:
            return round(0.5 * matched / len(words), 3)
    return 0.0


# ── Snapshot loader ────────────────────────────────────────────────────────────

def _load_snapshot_entities(meta: dict) -> list[dict]:
    """Load entities from a bake output file. Returns [] for unsupported formats."""
    fmt      = meta.get("format", "jsonl")
    out_path = Path(meta.get("output_path", ""))
    if not out_path.exists():
        return []

    if fmt == "jsonl":
        entities: list[dict] = []
        for line in out_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entities.append(json.loads(line))
                except Exception:
                    pass
        return entities

    if fmt == "json":
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
            return data.get("entities", [])
        except Exception:
            return []

    return []   # markdown / txt — not searchable


# ── Handlers ───────────────────────────────────────────────────────────────────

def aethviondb_search(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Search live (raw) entity files in an AethvionDB database.

    Reads entity JSON files directly from db_root/entities/ — no bake needed.
    """
    p           = node.get("properties", {})
    query       = _to_str(inputs.get("in", "")).strip()
    db_name     = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")
    entity_type = str(p.get("entity_type", "")).strip()
    limit       = max(1, int(p.get("limit",     10) or 10))
    min_score   = float(p.get("min_score", 0.0) or 0.0)

    if not query:
        return {"out": "[]", "count": 0, "speed": "0ms", "error": "No search query provided"}

    try:
        from core.aethviondb.db_registry import resolve_db_root  # noqa: PLC0415
    except ImportError as exc:
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": f"Database '{db_name}' not found: {exc}"}

    entities_dir = root / "entities"
    if not entities_dir.exists():
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": f"Database '{db_name}' has no entities yet (entities/ folder missing)"}

    _t0 = time.perf_counter()

    # Load all raw entity files
    entities: list[dict] = []
    for fp in entities_dir.glob("*.json"):
        try:
            entities.append(json.loads(fp.read_text(encoding="utf-8")))
        except Exception:
            pass

    if not entities:
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": f"Database '{db_name}' is empty"}

    # Optional entity-type filter
    if entity_type:
        entities = [e for e in entities if e.get("type") == entity_type]

    # Score and rank
    scored = [(e, _score_raw(query, e)) for e in entities]
    scored = [(e, s) for e, s in scored if s >= min_score]
    scored.sort(key=lambda x: x[1], reverse=True)

    results = []
    for entity, s in scored[:limit]:
        core = entity.get("sections", {}).get("core", {})
        results.append({
            "id":      entity.get("id",   ""),
            "name":    entity.get("name", ""),
            "type":    entity.get("type", ""),
            "summary": core.get("summary", ""),
            "tags":    core.get("tags", []),
            "_score":  round(s, 3),
        })

    elapsed_ms = round((time.perf_counter() - _t0) * 1000, 2)
    return {
        "out":   json.dumps(results, ensure_ascii=False),
        "count": len(results),
        "speed": f"{elapsed_ms}ms",
        "error": "",
    }


def aethviondb_snapshot_search(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Search a baked snapshot of an AethvionDB database.

    Reads from the optimised export file (db_root/baked/<snapshot>.*).
    Leaves snapshot blank to use the most recent bake.
    """
    p           = node.get("properties", {})
    query       = _to_str(inputs.get("in", "")).strip()
    db_name     = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")
    snap_name   = (_to_str(inputs.get("snapshot", "")).strip() or str(p.get("snapshot", "")).strip())
    entity_type = str(p.get("entity_type", "")).strip()
    limit       = max(1, int(p.get("limit",     10) or 10))
    min_score   = float(p.get("min_score", 0.0) or 0.0)

    if not query:
        return {"out": "[]", "count": 0, "speed": "0ms", "error": "No search query provided"}

    try:
        from core.aethviondb.db_registry import resolve_db_root  # noqa: PLC0415
        from core.aethviondb.baker import list_bakes              # noqa: PLC0415
    except ImportError as exc:
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": f"Database '{db_name}' not found: {exc}"}

    # Find the requested snapshot by name, fall back to the most recent one
    bakes = list_bakes(root)
    meta  = next((b for b in bakes if b.get("name") == snap_name), None) if snap_name else None
    if meta is None and bakes:
        meta = bakes[0]   # list_bakes returns newest-first
    if meta is None:
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": f"No snapshot found in database '{db_name}'"}

    _t0 = time.perf_counter()

    entities = _load_snapshot_entities(meta)

    # Optional type filter
    if entity_type:
        entities = [e for e in entities if e.get("type") == entity_type]

    # Score and rank
    scored = [(e, _score_baked(query, e)) for e in entities]
    scored = [(e, s) for e, s in scored if s >= min_score]
    scored.sort(key=lambda x: x[1], reverse=True)

    results = []
    for entity, s in scored[:limit]:
        results.append({**entity, "_score": round(s, 3)})

    elapsed_ms = round((time.perf_counter() - _t0) * 1000, 2)
    return {
        "out":   json.dumps(results, ensure_ascii=False),
        "count": len(results),
        "speed": f"{elapsed_ms}ms",
        "error": "",
    }


def aethviondb_semantic_search(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Search a live AethvionDB database using vector cosine similarity.

    Compares an embedding of the query against pre-generated vectors stored in
    entity["sections"]["vectors"][<model>]["embedding"].  Entities that have not
    been vectorized for the chosen model are silently skipped (a warning is
    returned in the "error" port so the workflow can still continue).

    Run the AethvionDB vectorization job first to prepare the entities.
    """
    p           = node.get("properties", {})
    query       = _to_str(inputs.get("in", "")).strip()
    db_name     = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")
    model       = str(p.get("model",       "text-embedding-004")).strip() or "text-embedding-004"
    entity_type = str(p.get("entity_type", "")).strip()
    limit       = max(1, int(p.get("limit",     10) or 10))
    min_score   = float(p.get("min_score", 0.5) or 0.0)

    if not query:
        return {"out": "[]", "count": 0, "speed": "0ms", "error": "No search query provided"}

    try:
        from core.aethviondb.db_registry import resolve_db_root  # noqa: PLC0415
        from core.aethviondb.vectorizer  import embed_sync        # noqa: PLC0415
    except ImportError as exc:
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": f"Database '{db_name}' not found: {exc}"}

    entities_dir = root / "entities"
    if not entities_dir.exists():
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": f"Database '{db_name}' has no entities yet (entities/ folder missing)"}

    _t0 = time.perf_counter()

    # ── Embed the query ────────────────────────────────────────────────────────
    try:
        query_vec = embed_sync(query, model)
    except Exception as exc:
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": f"Embedding failed ({model}): {exc}"}

    # ── Load entities ──────────────────────────────────────────────────────────
    entities: list[dict] = []
    for fp in entities_dir.glob("*.json"):
        try:
            entities.append(json.loads(fp.read_text(encoding="utf-8")))
        except Exception:
            pass

    if not entities:
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": f"Database '{db_name}' is empty"}

    if entity_type:
        entities = [e for e in entities if e.get("type") == entity_type]

    # ── Cosine similarity ──────────────────────────────────────────────────────
    def _cosine(a: list[float], b: list[float]) -> float:
        dot   = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0

    scored: list[tuple[dict, float]] = []
    no_vec_count = 0
    for entity in entities:
        vecs      = (entity.get("sections") or {}).get("vectors", {})
        vec_data  = vecs.get(model)
        embedding = vec_data.get("embedding") if isinstance(vec_data, dict) else None
        if not embedding:
            no_vec_count += 1
            continue
        score = _cosine(query_vec, embedding)
        if score >= min_score:
            scored.append((entity, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    results = []
    for entity, s in scored[:limit]:
        core = (entity.get("sections") or {}).get("core", {})
        results.append({
            "id":      entity.get("id",   ""),
            "name":    entity.get("name", ""),
            "type":    entity.get("type", ""),
            "summary": core.get("summary", ""),
            "tags":    core.get("tags",    []),
            "_score":  round(s, 4),
        })

    elapsed_ms = round((time.perf_counter() - _t0) * 1000, 2)

    warning = ""
    if no_vec_count:
        warning = (
            f"{no_vec_count} entity/entities had no '{model}' embedding and were skipped. "
            "Run the AethvionDB vectorization job to include them."
        )

    return {
        "out":   json.dumps(results, ensure_ascii=False),
        "count": len(results),
        "speed": f"{elapsed_ms}ms",
        "error": warning,
    }


def aethviondb_snapshot_semantic_search(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Search a baked AethvionDB snapshot using vector cosine similarity.

    Reads entity vectors from the flat baked format:
        entity["vectors"]["<model>"]["embedding"]
    (contrast with the live/nested entity["sections"]["vectors"][...] format).

    The snapshot must have been baked with include_vectors=True.  Entities
    that lack the chosen model's embedding are silently skipped and counted
    in the "error" port warning so the workflow can still continue.
    """
    p           = node.get("properties", {})
    query       = _to_str(inputs.get("in", "")).strip()
    db_name     = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")
    snap_name   = (_to_str(inputs.get("snapshot", "")).strip() or str(p.get("snapshot", "")).strip())
    model       = str(p.get("model",       "text-embedding-004")).strip() or "text-embedding-004"
    entity_type = str(p.get("entity_type", "")).strip()
    limit       = max(1, int(p.get("limit",     10) or 10))
    min_score   = float(p.get("min_score", 0.5) or 0.0)

    if not query:
        return {"out": "[]", "count": 0, "speed": "0ms", "error": "No search query provided"}

    try:
        from core.aethviondb.db_registry import resolve_db_root  # noqa: PLC0415
        from core.aethviondb.baker import list_bakes              # noqa: PLC0415
        from core.aethviondb.vectorizer import embed_sync         # noqa: PLC0415
    except ImportError as exc:
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": f"Database '{db_name}' not found: {exc}"}

    # Find the requested snapshot, fall back to newest
    bakes = list_bakes(root)
    meta  = next((b for b in bakes if b.get("name") == snap_name), None) if snap_name else None
    if meta is None and bakes:
        meta = bakes[0]   # list_bakes returns newest-first
    if meta is None:
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": f"No snapshot found in database '{db_name}'"}

    _t0 = time.perf_counter()

    # ── Embed the query ────────────────────────────────────────────────────────
    try:
        query_vec = embed_sync(query, model)
    except Exception as exc:
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": f"Embedding failed ({model}): {exc}"}

    # ── Load entities from snapshot ────────────────────────────────────────────
    entities = _load_snapshot_entities(meta)

    if not entities:
        return {"out": "[]", "count": 0, "speed": "0ms",
                "error": "Snapshot is empty or could not be loaded"}

    if entity_type:
        entities = [e for e in entities if e.get("type") == entity_type]

    # ── Cosine similarity — baked format: entity["vectors"][model]["embedding"] ─
    def _cosine(a: list[float], b: list[float]) -> float:
        dot   = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0

    scored: list[tuple[dict, float]] = []
    no_vec_count = 0
    for entity in entities:
        vecs      = entity.get("vectors") or {}
        vec_data  = vecs.get(model)
        embedding = vec_data.get("embedding") if isinstance(vec_data, dict) else None
        if not embedding:
            no_vec_count += 1
            continue
        score = _cosine(query_vec, embedding)
        if score >= min_score:
            scored.append((entity, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    results = []
    for entity, s in scored[:limit]:
        results.append({**entity, "_score": round(s, 4)})

    elapsed_ms = round((time.perf_counter() - _t0) * 1000, 2)

    warning = ""
    if no_vec_count:
        warning = (
            f"{no_vec_count} entity/entities had no '{model}' embedding and were skipped. "
            "Bake with 'Include Vectors' enabled to include them."
        )

    return {
        "out":   json.dumps(results, ensure_ascii=False),
        "count": len(results),
        "speed": f"{elapsed_ms}ms",
        "error": warning,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Database + CRUD + AI operations
# ══════════════════════════════════════════════════════════════════════════════

# ── Shared helpers ─────────────────────────────────────────────────────────────

def _get_writer(root: Path):
    """Return (EntityWriter, NameIndex) for the given database root."""
    from core.aethviondb.entity_writer import EntityWriter  # noqa: PLC0415
    from core.aethviondb.name_index    import NameIndex     # noqa: PLC0415
    idx = NameIndex(index_path=root / "name_index.json")
    return EntityWriter(entities_dir=root / "entities", index=idx), idx


def _resolve_entity(writer, idx, ref: str):
    """Resolve *ref* (entity ID or name) → entity_id string, or None."""
    if not ref:
        return None
    if writer.exists(ref):
        return ref
    return idx.get(ref)  # name-based lookup


# ── aethviondb.create_database ────────────────────────────────────────────────

def aethviondb_create_database(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Create and register a new AethvionDB database on disk."""
    p       = node.get("properties", {})
    db_name = str(p.get("name", "")).strip() or _to_str(inputs.get("in", "")).strip()
    if not db_name:
        return {"out": "", "name": "", "path": "", "error": "Database name is required"}

    description = str(p.get("description", "")).strip()
    custom_path = str(p.get("path",        "")).strip()

    try:
        from core.aethviondb.db_registry import register_db  # noqa: PLC0415
        from core.utils.paths            import AETHVIONDB    # noqa: PLC0415
    except ImportError as exc:
        return {"out": "", "name": "", "path": "", "error": f"AethvionDB not available: {exc}"}

    try:
        root = Path(custom_path) if custom_path else (AETHVIONDB / db_name)
        (root / "entities").mkdir(parents=True, exist_ok=True)
        (root / "baked").mkdir(parents=True,    exist_ok=True)
        entry = register_db(db_name, str(root), description=description, overwrite=False)
        return {
            "out":  json.dumps(entry, ensure_ascii=False),
            "name": db_name,
            "path": str(root),
            "error": "",
        }
    except Exception as exc:
        return {"out": "", "name": "", "path": "", "error": str(exc)}


# ── aethviondb.get_stats ──────────────────────────────────────────────────────

def aethviondb_get_stats(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Return entity counts (total / active / stubs / deleted) for a database."""
    p       = node.get("properties", {})
    db_name = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")

    try:
        from core.aethviondb.db_registry import resolve_db_root  # noqa: PLC0415
    except ImportError as exc:
        return {"out": "", "total": 0, "active": 0, "stubs": 0, "deleted": 0,
                "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "", "total": 0, "active": 0, "stubs": 0, "deleted": 0,
                "error": f"Database '{db_name}' not found: {exc}"}

    try:
        writer, _ = _get_writer(root)
        entities  = writer.list_all(include_deleted=True)

        by_status: dict[str, int] = {}
        for e in entities:
            s = e.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1

        total   = len(entities)
        active  = by_status.get("active",  0)
        stubs   = by_status.get("stub",    0)
        deleted = by_status.get("deleted", 0)

        stats = {
            "database":  db_name,
            "total":     total,
            "active":    active,
            "stubs":     stubs,
            "deleted":   deleted,
            "by_status": by_status,
        }
        return {
            "out":     json.dumps(stats, ensure_ascii=False),
            "total":   total,
            "active":  active,
            "stubs":   stubs,
            "deleted": deleted,
            "error":   "",
        }
    except Exception as exc:
        return {"out": "", "total": 0, "active": 0, "stubs": 0, "deleted": 0,
                "error": str(exc)}


# ── aethviondb.list_entities ──────────────────────────────────────────────────

def aethviondb_list_entities(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """List entities with optional type / status filters."""
    p           = node.get("properties", {})
    db_name     = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")
    type_filter = str(p.get("entity_type", "")).strip()
    stat_filter = str(p.get("status",      "")).strip()   # "active", "stub", "" = all
    limit       = max(1, int(p.get("limit", 50) or 50))

    try:
        from core.aethviondb.db_registry import resolve_db_root  # noqa: PLC0415
    except ImportError as exc:
        return {"out": "[]", "count": 0, "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "[]", "count": 0, "error": f"Database '{db_name}' not found: {exc}"}

    try:
        writer, _ = _get_writer(root)
        include_deleted = (stat_filter == "deleted")
        entities        = writer.list_all(include_deleted=include_deleted)

        if type_filter:
            entities = [e for e in entities if e.get("type") == type_filter]
        if stat_filter:
            entities = [e for e in entities if e.get("status") == stat_filter]

        results = []
        for e in entities[:limit]:
            core = (e.get("sections") or {}).get("core", {})
            results.append({
                "id":      e.get("id",      ""),
                "name":    e.get("name",    ""),
                "type":    e.get("type",    ""),
                "status":  e.get("status",  ""),
                "summary": core.get("summary", ""),
                "tags":    core.get("tags",    []),
            })

        return {
            "out":   json.dumps(results, ensure_ascii=False),
            "count": len(results),
            "error": "",
        }
    except Exception as exc:
        return {"out": "[]", "count": 0, "error": str(exc)}


# ── aethviondb.get_entity ─────────────────────────────────────────────────────

def aethviondb_get_entity(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Fetch a single entity by ID or name."""
    p       = node.get("properties", {})
    ref     = _to_str(inputs.get("in", "")).strip() or str(p.get("entity_ref", "")).strip()
    db_name = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")

    if not ref:
        return {"out": "", "entity_id": "", "entity_name": "",
                "error": "Entity ID or name is required"}

    try:
        from core.aethviondb.db_registry import resolve_db_root  # noqa: PLC0415
    except ImportError as exc:
        return {"out": "", "entity_id": "", "entity_name": "",
                "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "", "entity_id": "", "entity_name": "",
                "error": f"Database '{db_name}' not found: {exc}"}

    try:
        writer, idx = _get_writer(root)
        entity_id   = _resolve_entity(writer, idx, ref)
        if not entity_id:
            return {"out": "", "entity_id": "", "entity_name": "",
                    "error": f"Entity not found: {ref!r}"}

        entity = writer.get(entity_id)
        if not entity:
            return {"out": "", "entity_id": "", "entity_name": "",
                    "error": f"Entity file missing for ID {entity_id!r}"}

        return {
            "out":         json.dumps(entity, ensure_ascii=False),
            "entity_id":   entity.get("id",   ""),
            "entity_name": entity.get("name", ""),
            "error":       "",
        }
    except Exception as exc:
        return {"out": "", "entity_id": "", "entity_name": "", "error": str(exc)}


# ── aethviondb.create_entity ──────────────────────────────────────────────────

def aethviondb_create_entity(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Create a new entity record (no AI — manual creation)."""
    p           = node.get("properties", {})
    name        = _to_str(inputs.get("in", "")).strip() or str(p.get("name", "")).strip()
    db_name     = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")
    entity_type = str(p.get("entity_type", "other")).strip()    or "other"
    source      = str(p.get("source",      "workflow")).strip() or "workflow"

    if not name:
        return {"out": "", "entity_id": "", "was_created": False,
                "error": "Entity name is required"}

    try:
        from core.aethviondb.db_registry import resolve_db_root  # noqa: PLC0415
    except ImportError as exc:
        return {"out": "", "entity_id": "", "was_created": False,
                "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "", "entity_id": "", "was_created": False,
                "error": f"Database '{db_name}' not found: {exc}"}

    try:
        writer, _   = _get_writer(root)
        entity, was = writer.create(name, entity_type=entity_type, source=source)
        return {
            "out":         json.dumps(entity, ensure_ascii=False),
            "entity_id":   entity["id"],
            "was_created": was,
            "error":       "",
        }
    except Exception as exc:
        return {"out": "", "entity_id": "", "was_created": False, "error": str(exc)}


# ── aethviondb.update_entity ──────────────────────────────────────────────────

def aethviondb_update_entity(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Update fields on an existing entity.

    Connect the entity ID or name to the *entity* input port.
    Connect a JSON patch object to the *in* port, e.g.:
        {"type": "person", "sections": {"core": {"summary": "Updated text"}}}
    """
    p       = node.get("properties", {})
    ref     = _to_str(inputs.get("entity", "")).strip() or str(p.get("entity_ref", "")).strip()
    patch_s = _to_str(inputs.get("in", "")).strip()
    db_name = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")

    if not ref:
        return {"out": "", "entity_id": "",
                "error": "Entity ID or name is required (entity port)"}

    patch: dict[str, Any] = {}
    if patch_s:
        try:
            patch = json.loads(patch_s)
        except Exception:
            return {"out": "", "entity_id": "",
                    "error": "Invalid JSON patch on 'in' port"}

    # Fold in any inline property overrides from the node panel
    inline_summary = str(p.get("summary",     "")).strip()
    inline_type    = str(p.get("entity_type", "")).strip()
    if inline_summary:
        patch.setdefault("sections", {}).setdefault("core", {})["summary"] = inline_summary
    if inline_type:
        patch["type"] = inline_type

    if not patch:
        return {"out": "", "entity_id": "",
                "error": "Nothing to update — provide a JSON patch or inline fields"}

    try:
        from core.aethviondb.db_registry import resolve_db_root  # noqa: PLC0415
    except ImportError as exc:
        return {"out": "", "entity_id": "", "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "", "entity_id": "",
                "error": f"Database '{db_name}' not found: {exc}"}

    try:
        writer, idx = _get_writer(root)
        entity_id   = _resolve_entity(writer, idx, ref)
        if not entity_id:
            return {"out": "", "entity_id": "",
                    "error": f"Entity not found: {ref!r}"}

        updated = writer.update(entity_id, patch)
        return {
            "out":       json.dumps(updated, ensure_ascii=False),
            "entity_id": entity_id,
            "error":     "",
        }
    except Exception as exc:
        return {"out": "", "entity_id": "", "error": str(exc)}


# ── aethviondb.delete_entity ──────────────────────────────────────────────────

def aethviondb_delete_entity(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Soft-delete an entity (marks status='deleted', does not erase the file)."""
    p       = node.get("properties", {})
    ref     = _to_str(inputs.get("in", "")).strip() or str(p.get("entity_ref", "")).strip()
    db_name = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")

    if not ref:
        return {"out": "false", "entity_id": "",
                "error": "Entity ID or name is required"}

    try:
        from core.aethviondb.db_registry import resolve_db_root  # noqa: PLC0415
    except ImportError as exc:
        return {"out": "false", "entity_id": "",
                "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "false", "entity_id": "",
                "error": f"Database '{db_name}' not found: {exc}"}

    try:
        writer, idx = _get_writer(root)
        entity_id   = _resolve_entity(writer, idx, ref)
        if not entity_id:
            return {"out": "false", "entity_id": "",
                    "error": f"Entity not found: {ref!r}"}

        ok = writer.delete(entity_id, soft=True)
        return {
            "out":       "true" if ok else "false",
            "entity_id": entity_id,
            "error":     "" if ok else "Delete returned False",
        }
    except Exception as exc:
        return {"out": "false", "entity_id": "", "error": str(exc)}


# ── aethviondb.distill ────────────────────────────────────────────────────────

def aethviondb_distill(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Distil free-text (article, notes, book excerpt) into a structured entity via AI.

    The AI identifies the primary subject automatically and writes a full
    entity structure.  Set auto_save=false to preview without writing.
    """
    p         = node.get("properties", {})
    content   = _to_str(inputs.get("in", "")).strip()
    db_name   = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")
    model     = str(p.get("model",     "auto")).strip()    or "auto"
    auto_save = str(p.get("auto_save", "true")).lower() not in ("false", "0", "no")

    if not content:
        return {"out": "", "entity_id": "", "entity_name": "", "stub_count": 0,
                "error": "No content provided on 'in' port"}

    try:
        from core.aethviondb.db_registry    import resolve_db_root  # noqa: PLC0415
        from core.aethviondb.distiller      import ContentDistiller  # noqa: PLC0415
        from core.aethviondb.entity_writer  import EntityWriter      # noqa: PLC0415
        from core.aethviondb.name_index     import NameIndex         # noqa: PLC0415
    except ImportError as exc:
        return {"out": "", "entity_id": "", "entity_name": "", "stub_count": 0,
                "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "", "entity_id": "", "entity_name": "", "stub_count": 0,
                "error": f"Database '{db_name}' not found: {exc}"}

    try:
        idx       = NameIndex(index_path=root / "name_index.json")
        writer    = EntityWriter(entities_dir=root / "entities", index=idx)
        distiller = ContentDistiller(writer=writer, index=idx, model=model)

        result = asyncio.run(distiller.distill(content, model=model, source="workflow"))

        if result.get("errors"):
            return {"out": "", "entity_id": "", "entity_name": "", "stub_count": 0,
                    "error": "; ".join(result["errors"])}

        entity_id = result.get("entity_id", "")
        entity    = writer.get(entity_id) if entity_id else None

        # Roll back if auto_save is disabled and this call created the entity
        if not auto_save and entity and result.get("was_created"):
            writer.delete(entity_id, soft=True)

        return {
            "out":         json.dumps(entity, ensure_ascii=False) if entity else "",
            "entity_id":   entity_id,
            "entity_name": result.get("entity_name", ""),
            "stub_count":  result.get("stub_count",  0),
            "error":       "",
        }
    except Exception as exc:
        return {"out": "", "entity_id": "", "entity_name": "", "stub_count": 0,
                "error": str(exc)}


# ── aethviondb.expand_entity ──────────────────────────────────────────────────

def aethviondb_expand_entity(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Expand a stub entity with AI-generated content (saves immediately).

    Pass entity ID or name via the *in* port or *entity_ref* property.
    Already-active entities pass through without re-expanding.
    Optionally wire extra source material to the *context* port.
    """
    p       = node.get("properties", {})
    ref     = _to_str(inputs.get("in", "")).strip() or str(p.get("entity_ref", "")).strip()
    db_name = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")
    model   = str(p.get("model",    "auto")).strip()    or "auto"
    context = (_to_str(inputs.get("context", "")).strip()
               or str(p.get("extra_context", "")).strip())

    if not ref:
        return {"out": "", "entity_id": "", "entity_name": "",
                "error": "Entity ID or name is required"}

    try:
        from core.aethviondb.db_registry      import resolve_db_root   # noqa: PLC0415
        from core.aethviondb.expansion_engine import ExpansionEngine    # noqa: PLC0415
        from core.aethviondb.entity_writer    import EntityWriter       # noqa: PLC0415
        from core.aethviondb.name_index       import NameIndex          # noqa: PLC0415
    except ImportError as exc:
        return {"out": "", "entity_id": "", "entity_name": "",
                "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "", "entity_id": "", "entity_name": "",
                "error": f"Database '{db_name}' not found: {exc}"}

    try:
        idx       = NameIndex(index_path=root / "name_index.json")
        writer    = EntityWriter(entities_dir=root / "entities", index=idx)
        entity_id = _resolve_entity(writer, idx, ref)

        if not entity_id:
            return {"out": "", "entity_id": "", "entity_name": "",
                    "error": f"Entity not found: {ref!r}"}

        engine = ExpansionEngine(writer=writer, index=idx, model=model)

        async def _expand():
            if context:
                preview = await engine.preview_expand_stub(
                    entity_id, model=model, extra_context=context)
                if preview.get("error"):
                    return {"success": False, "error": preview["error"], "new_stubs": []}
                proposed = preview.get("proposed")
                if not proposed:
                    return {"success": False, "error": "AI returned no proposed data",
                            "new_stubs": []}
                apply_r = await engine.apply_expand_preview(entity_id, proposed)
                return {"success": apply_r.get("success", False),
                        "error":   apply_r.get("error",   ""),
                        "new_stubs": apply_r.get("new_stubs", [])}
            return await engine.expand_stub(entity_id, model=model)

        result = asyncio.run(_expand())

        if not result.get("success"):
            err = result.get("error", "Unknown error")
            if err == "already_active":
                entity = writer.get(entity_id)
                return {
                    "out":         json.dumps(entity, ensure_ascii=False) if entity else "",
                    "entity_id":   entity_id,
                    "entity_name": (entity or {}).get("name", ""),
                    "error":       "",
                }
            return {"out": "", "entity_id": entity_id, "entity_name": "", "error": err}

        entity = writer.get(entity_id)
        return {
            "out":         json.dumps(entity, ensure_ascii=False) if entity else "",
            "entity_id":   entity_id,
            "entity_name": (entity or {}).get("name", ""),
            "error":       "",
        }
    except Exception as exc:
        return {"out": "", "entity_id": "", "entity_name": "", "error": str(exc)}


# ── aethviondb.deepen_entity ──────────────────────────────────────────────────

def aethviondb_deepen_entity(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Expand the stub sub-topics and relation-stubs of an active entity via AI.

    Finds unresolved stubs in sections.stubs and relation targets that are still
    stubs, then generates full entries for them (up to max_stubs at a time).
    """
    p         = node.get("properties", {})
    ref       = _to_str(inputs.get("in", "")).strip() or str(p.get("entity_ref", "")).strip()
    db_name   = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")
    model     = str(p.get("model",     "auto")).strip()    or "auto"
    max_stubs = max(1, int(p.get("max_stubs", 5) or 5))
    context   = (_to_str(inputs.get("context", "")).strip()
                 or str(p.get("extra_context", "")).strip())

    if not ref:
        return {"out": "", "entity_id": "", "applied": 0, "failed": 0,
                "error": "Entity ID or name is required"}

    try:
        from core.aethviondb.db_registry      import resolve_db_root   # noqa: PLC0415
        from core.aethviondb.expansion_engine import ExpansionEngine    # noqa: PLC0415
        from core.aethviondb.entity_writer    import EntityWriter       # noqa: PLC0415
        from core.aethviondb.name_index       import NameIndex          # noqa: PLC0415
    except ImportError as exc:
        return {"out": "", "entity_id": "", "applied": 0, "failed": 0,
                "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "", "entity_id": "", "applied": 0, "failed": 0,
                "error": f"Database '{db_name}' not found: {exc}"}

    try:
        idx       = NameIndex(index_path=root / "name_index.json")
        writer    = EntityWriter(entities_dir=root / "entities", index=idx)
        entity_id = _resolve_entity(writer, idx, ref)

        if not entity_id:
            return {"out": "", "entity_id": "", "applied": 0, "failed": 0,
                    "error": f"Entity not found: {ref!r}"}

        engine = ExpansionEngine(writer=writer, index=idx, model=model)

        async def _deepen():
            if context:
                # Use the preview path to inject extra_context, then apply
                preview_result = await engine.preview_deepen_stubs_for(
                    entity_id, max_stubs=max_stubs, model=model,
                    include_relations=True, extra_context=context,
                )
                if preview_result.get("error"):
                    return {"applied": [], "failed": [{"error": preview_result["error"]}],
                            "total": 0}
                previews = preview_result.get("previews", [])
                if not previews:
                    return {"applied": [], "failed": [], "total": 0}
                return await engine.apply_deepen_previews(entity_id, previews)
            # Direct path — generates and saves in one step
            report = await engine.deepen_stubs_for(
                entity_id, max_stubs=max_stubs, model=model, include_relations=True,
            )
            return {
                "applied": [{"entity_id": eid} for eid in report.expanded],
                "failed":  [{"name": n} for n in report.failed],
                "total":   report.total,
            }

        r       = asyncio.run(_deepen())
        applied = r.get("applied", [])
        failed  = r.get("failed",  [])

        return {
            "out":       json.dumps({"applied": applied, "failed": failed},
                                    ensure_ascii=False),
            "entity_id": entity_id,
            "applied":   len(applied),
            "failed":    len(failed),
            "error":     "",
        }
    except Exception as exc:
        return {"out": "", "entity_id": "", "applied": 0, "failed": 0,
                "error": str(exc)}


# ── aethviondb.create_snapshot ────────────────────────────────────────────────

def aethviondb_create_snapshot(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Bake the database to a portable snapshot file (JSONL / JSON / Markdown / TXT)."""
    p               = node.get("properties", {})
    snap_name       = (_to_str(inputs.get("in", "")).strip()
                       or str(p.get("snapshot_name", "")).strip()
                       or "snapshot")
    db_name         = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")
    fmt             = str(p.get("format",           "jsonl")).strip()   or "jsonl"
    include_stubs   = str(p.get("include_stubs",   "true")).lower()  not in ("false", "0", "no")
    include_vectors = str(p.get("include_vectors", "false")).lower() not in ("false", "0", "no")

    try:
        from core.aethviondb.db_registry   import resolve_db_root  # noqa: PLC0415
        from core.aethviondb.baker         import bake_sync         # noqa: PLC0415
        from core.aethviondb.entity_writer import EntityWriter      # noqa: PLC0415
        from core.aethviondb.name_index    import NameIndex         # noqa: PLC0415
    except ImportError as exc:
        return {"out": "", "path": "", "count": 0,
                "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "", "path": "", "count": 0,
                "error": f"Database '{db_name}' not found: {exc}"}

    try:
        idx    = NameIndex(index_path=root / "name_index.json")
        writer = EntityWriter(entities_dir=root / "entities", index=idx)

        _t0  = time.perf_counter()
        meta = bake_sync(
            db_root=root,
            writer=writer,
            name=snap_name,
            fmt=fmt,
            include_stubs=include_stubs,
            include_vectors=include_vectors,
        )
        elapsed = round((time.perf_counter() - _t0) * 1000, 1)

        if meta.get("status") == "error":
            return {"out": "", "path": "", "count": 0,
                    "error": meta.get("error", "Bake failed")}

        return {
            "out":   json.dumps(meta, ensure_ascii=False),
            "path":  meta.get("output_path", ""),
            "count": meta.get("entity_count", 0),
            "speed": f"{elapsed}ms",
            "error": "",
        }
    except Exception as exc:
        return {"out": "", "path": "", "count": 0, "error": str(exc)}


# ── aethviondb.list_snapshots ─────────────────────────────────────────────────

def aethviondb_list_snapshots(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """List all baked snapshots for a database, newest first."""
    p       = node.get("properties", {})
    db_name = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")

    try:
        from core.aethviondb.db_registry import resolve_db_root  # noqa: PLC0415
        from core.aethviondb.baker       import list_bakes        # noqa: PLC0415
    except ImportError as exc:
        return {"out": "[]", "count": 0, "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "[]", "count": 0,
                "error": f"Database '{db_name}' not found: {exc}"}

    try:
        bakes   = list_bakes(root)
        summary = []
        for b in bakes:
            summary.append({
                "name":         b.get("name",         ""),
                "format":       b.get("format",       ""),
                "entity_count": b.get("entity_count", 0),
                "size":         b.get("size",         ""),
                "baked_at":     b.get("baked_at", b.get("started_at", "")),
                "output_file":  b.get("output_file",  ""),
            })
        return {
            "out":   json.dumps(summary, ensure_ascii=False),
            "count": len(summary),
            "error": "",
        }
    except Exception as exc:
        return {"out": "[]", "count": 0, "error": str(exc)}


# ── aethviondb.validate ───────────────────────────────────────────────────────

def aethviondb_validate(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Run integrity checks across the entire database (or a single entity).

    The *error* output port fires only when the node itself fails.
    Validation issues are surfaced as structured JSON on the *out* port.
    """
    p          = node.get("properties", {})
    db_name    = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")
    entity_ref = (_to_str(inputs.get("in", "")).strip()
                  or str(p.get("entity_ref", "")).strip())

    try:
        from core.aethviondb.db_registry   import resolve_db_root  # noqa: PLC0415
        from core.aethviondb.validator     import Validator         # noqa: PLC0415
        from core.aethviondb.entity_writer import EntityWriter      # noqa: PLC0415
        from core.aethviondb.name_index    import NameIndex         # noqa: PLC0415
    except ImportError as exc:
        return {"out": "", "total": 0, "ok": 0, "errors": 0,
                "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "", "total": 0, "ok": 0, "errors": 0,
                "error": f"Database '{db_name}' not found: {exc}"}

    try:
        idx       = NameIndex(index_path=root / "name_index.json")
        writer    = EntityWriter(entities_dir=root / "entities", index=idx)
        validator = Validator(writer)

        if entity_ref:
            entity_id = _resolve_entity(writer, idx, entity_ref)
            if not entity_id:
                return {"out": "", "total": 0, "ok": 0, "errors": 0,
                        "error": f"Entity not found: {entity_ref!r}"}
            results = [validator.validate(entity_id)]
        else:
            results = validator.validate_all()

        total     = len(results)
        ok_count  = sum(1 for r in results if r.ok)
        err_count = total - ok_count

        report = {
            "total":  total,
            "ok":     ok_count,
            "errors": err_count,
            "issues": [r.as_dict() for r in results if not r.ok],
        }
        return {
            "out":    json.dumps(report, ensure_ascii=False),
            "total":  total,
            "ok":     ok_count,
            "errors": err_count,
            "error":  "",
        }
    except Exception as exc:
        return {"out": "", "total": 0, "ok": 0, "errors": 0, "error": str(exc)}


# ── aethviondb.generate_vectors ───────────────────────────────────────────────

def aethviondb_generate_vectors(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Generate embeddings for all entities in the database.

    Runs the full vectorization job inline and blocks until complete.
    Reads the VECINFO sidecar after completion for final counts.
    """
    p             = node.get("properties", {})
    db_name       = (_to_str(inputs.get("database", "")).strip() or str(p.get("database", "default")).strip() or "default")
    model         = str(p.get("model",         "text-embedding-004")).strip() or "text-embedding-004"
    force_rewrite = str(p.get("force_rewrite", "false")).lower() not in ("false", "0", "no")
    include_stubs = str(p.get("include_stubs", "false")).lower() not in ("false", "0", "no")

    try:
        from core.aethviondb.db_registry   import resolve_db_root  # noqa: PLC0415
        from core.aethviondb.vectorizer    import vectorize_all, read_vec_info  # noqa: PLC0415
        from core.aethviondb.entity_writer import EntityWriter      # noqa: PLC0415
        from core.aethviondb.name_index    import NameIndex         # noqa: PLC0415
    except ImportError as exc:
        return {"out": "", "vectorized": 0, "skipped": 0, "failed": 0,
                "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "", "vectorized": 0, "skipped": 0, "failed": 0,
                "error": f"Database '{db_name}' not found: {exc}"}

    try:
        idx    = NameIndex(index_path=root / "name_index.json")
        writer = EntityWriter(entities_dir=root / "entities", index=idx)

        _t0 = time.perf_counter()
        asyncio.run(vectorize_all(
            db_root=root,
            writer=writer,
            model=model,
            force_rewrite=force_rewrite,
            include_stubs=include_stubs,
        ))
        elapsed = round((time.perf_counter() - _t0) * 1000, 1)

        info       = read_vec_info(root) or {}
        vectorized = info.get("vectorized", 0)
        skipped    = info.get("skipped",    0)
        failed_n   = len(info.get("failed", []))
        error_msg  = ("" if info.get("status") != "error"
                      else info.get("error", "Unknown error"))

        result = {
            "database":   db_name,
            "model":      model,
            "vectorized": vectorized,
            "skipped":    skipped,
            "failed":     failed_n,
            "speed":      f"{elapsed}ms",
        }
        return {
            "out":        json.dumps(result, ensure_ascii=False),
            "vectorized": vectorized,
            "skipped":    skipped,
            "failed":     failed_n,
            "speed":      f"{elapsed}ms",
            "error":      error_msg,
        }
    except Exception as exc:
        return {"out": "", "vectorized": 0, "skipped": 0, "failed": 0,
                "error": str(exc)}
