"""
core/automate/nodes/aethviondb.py
══════════════════════════════════
Handler for aethviondb.search — keyword search over a baked AethvionDB dataset.

Replicates the scoring logic from core/aethviondb/api_v1/baked_routes.py so this
node works without going through HTTP; all reads are direct Python calls.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._utils import _to_str


# ── Scoring (mirrors _bake_keyword_score in baked_routes.py) ─────────────────

def _score(query: str, entity: dict) -> float:
    if not query:
        return 1.0
    q       = query.lower()
    name    = entity.get("name", "").lower()
    summary = entity.get("summary", "").lower()
    tags    = " ".join(entity.get("tags",    [])).lower()
    aliases = " ".join(entity.get("aliases", [])).lower()

    if name == q:          return 1.0
    if q in name:          return 0.90
    if q in summary[:400]: return 0.70
    if q in aliases:       return 0.65
    if q in tags:          return 0.60

    words   = q.split()
    if len(words) > 1:
        hay     = f"{name} {summary[:600]} {aliases} {tags}"
        matched = sum(1 for w in words if w in hay)
        if matched:
            return round(0.5 * matched / len(words), 3)
    return 0.0


def _load_entities(meta: dict) -> list[dict]:
    """Load entities from the bake output file. Returns [] for unsupported formats."""
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


# ── Handler ───────────────────────────────────────────────────────────────────

def aethviondb_search(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p           = node.get("properties", {})
    query       = _to_str(inputs.get("in", "")).strip()
    db_name     = str(p.get("database",    "default")).strip() or "default"
    bake_name   = str(p.get("bake_name",   "default")).strip() or "default"
    entity_type = str(p.get("entity_type", "")).strip()
    limit       = max(1, int(p.get("limit", 10) or 10))
    min_score   = float(p.get("min_score", 0.0) or 0.0)

    if not query:
        return {"out": "[]", "count": 0, "error": "No search query provided"}

    try:
        from core.aethviondb.db_registry import resolve_db_root   # noqa: PLC0415
        from core.aethviondb.baker import list_bakes               # noqa: PLC0415
    except ImportError as exc:
        return {"out": "[]", "count": 0,
                "error": f"AethvionDB not available: {exc}"}

    try:
        root = resolve_db_root(db_name)
    except Exception as exc:
        return {"out": "[]", "count": 0,
                "error": f"Database '{db_name}' not found: {exc}"}

    # Find the requested bake by name, fall back to the most recent one
    bakes = list_bakes(root)
    meta  = next((b for b in bakes if b.get("name") == bake_name), None)
    if meta is None and bakes:
        meta = bakes[0]   # list_bakes returns newest-first
    if meta is None:
        return {"out": "[]", "count": 0,
                "error": f"No baked dataset found in database '{db_name}'"}

    entities = _load_entities(meta)

    # Optional type filter
    if entity_type:
        entities = [e for e in entities if e.get("type") == entity_type]

    # Score and rank
    scored = [(e, _score(query, e)) for e in entities]
    scored = [(e, s) for e, s in scored if s >= min_score]
    scored.sort(key=lambda x: x[1], reverse=True)

    results = []
    for entity, s in scored[:limit]:
        results.append({**entity, "_score": round(s, 3)})

    return {
        "out":   json.dumps(results, ensure_ascii=False),
        "count": len(results),
        "error": "",
    }
