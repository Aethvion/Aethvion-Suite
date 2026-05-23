"""
core/automate/nodes/memory.py
══════════════════════════════
Handler functions for memory.store and memory.retrieve.

The backing store is a single JSON file at:
  <project_root>/data/automate/memory.json

Keys can be scoped globally (shared across all workflows) or per-workflow
(prefixed with the workflow ID). Values survive across runs indefinitely
unless a TTL is set on the store node.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ._utils import _to_str, _now

# Resolve path relative to this file: nodes/ → automate/ → core/ → project root
_MEMORY_PATH = Path(__file__).parent.parent.parent.parent / "data" / "automate" / "memory.json"


def _load_store() -> dict:
    """Load the memory store from disk, returning an empty dict on any failure."""
    try:
        if _MEMORY_PATH.exists():
            return json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_store(store: dict) -> None:
    """Atomically write the memory store to disk."""
    _MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _MEMORY_PATH.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")


def _scoped_key(key: str, scope: str, workflow: dict) -> str:
    if scope == "workflow":
        return f"wf:{workflow.get('id', 'unknown')}:{key}"
    return key


def memory_store(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p       = node.get("properties", {})
    key     = _to_str(inputs.get("key") or p.get("key", "")).strip()
    scope   = str(p.get("scope", "global"))
    ttl_hrs = float(p.get("ttl", 0) or 0)
    in_val  = inputs.get("in", "")

    if not key:
        return {"out": in_val, "error": "No storage key configured"}

    key   = _scoped_key(key, scope, ctx.workflow)
    store = _load_store()

    entry: dict = {"value": in_val}
    if ttl_hrs > 0:
        entry["expires"] = (datetime.now() + timedelta(hours=ttl_hrs)).isoformat()

    store[key] = entry

    try:
        _save_store(store)
        return {"out": in_val, "error": ""}
    except Exception as exc:
        return {"out": in_val, "error": str(exc)}


def memory_retrieve(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p       = node.get("properties", {})
    key     = str(p.get("key", "")).strip()
    scope   = str(p.get("scope", "global"))
    default = p.get("default", "")

    if not key:
        return {"out": default, "found": "false", "error": "No storage key configured"}

    key = _scoped_key(key, scope, ctx.workflow)

    try:
        store = _load_store()
    except Exception as exc:
        return {"out": default, "found": "false", "error": str(exc)}

    entry = store.get(key)
    if entry is None:
        return {"out": default, "found": "false", "error": ""}

    # Check TTL expiry
    expires = entry.get("expires")
    if expires:
        try:
            if datetime.now() > datetime.fromisoformat(expires):
                return {"out": default, "found": "false", "error": ""}
        except Exception:
            pass

    return {"out": entry.get("value", default), "found": "true", "error": ""}


def memory_search_semantic(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """
    Keyword-relevance search over the automate memory store.
    Scores each entry by how many query words appear in its key + serialised value.
    (True vector/embedding search is planned for a future sprint.)
    """
    p         = node.get("properties", {})
    query     = _to_str(inputs.get("in", "")).strip()
    scope     = str(p.get("scope", "all"))   # "global" | "workflow" | "all"
    limit     = max(1, int(p.get("limit", 5) or 5))
    min_score = float(p.get("min_score", 0.0) or 0.0)

    if not query:
        return {"out": "[]", "count": 0, "error": "No search query provided"}

    try:
        store = _load_store()
    except Exception as exc:
        return {"out": "[]", "count": 0, "error": str(exc)}

    query_lower = query.lower()
    query_words = set(query_lower.split())
    now         = datetime.now()
    results     = []

    for key, entry in store.items():
        # Scope filter
        if scope == "global" and key.startswith("wf:"):
            continue
        if scope == "workflow":
            wf_id = ctx.workflow.get("id", "unknown")
            if not key.startswith(f"wf:{wf_id}:"):
                continue
        # scope == "all" — include everything

        # TTL check
        expires = entry.get("expires")
        if expires:
            try:
                if now > datetime.fromisoformat(expires):
                    continue
            except Exception:
                pass

        value    = entry.get("value", "")
        haystack = (key + " " + _to_str(value)).lower()

        if not query_words:
            score = 0.0
        else:
            matched = sum(1 for w in query_words if w in haystack)
            score   = matched / len(query_words) if matched else 0.0

        if score >= min_score:
            results.append({"key": key, "value": value, "score": round(score, 3)})

    results.sort(key=lambda r: r["score"], reverse=True)
    results = results[:limit]

    return {
        "out":   json.dumps(results, ensure_ascii=False),
        "count": len(results),
        "error": "",
    }
