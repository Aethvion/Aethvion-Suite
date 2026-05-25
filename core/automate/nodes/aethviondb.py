"""
core/automate/nodes/aethviondb.py
══════════════════════════════════
Handlers for AethvionDB workflow nodes.

  aethviondb_search          — keyword search over live (raw) entity files
  aethviondb_snapshot_search — keyword search over a baked/snapshot dataset
  aethviondb_semantic_search — vector cosine-similarity search over live entities

Keyword nodes share the same scoring logic but differ in where they load entity
data from: raw reads db_root/entities/*.json directly; snapshot reads the JSONL/
JSON file produced by the baker.

Semantic search embeds the query via the configured embedding model and compares
it against vectors pre-generated and stored in entity["sections"]["vectors"].
"""
from __future__ import annotations

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
    db_name     = str(p.get("database",    "default")).strip() or "default"
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
    db_name     = str(p.get("database",    "default")).strip() or "default"
    snap_name   = str(p.get("snapshot",    "")).strip()
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
    db_name     = str(p.get("database",    "default")).strip() or "default"
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
    db_name     = str(p.get("database",    "default")).strip() or "default"
    snap_name   = str(p.get("snapshot",    "")).strip()
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
