"""
core/interfaces/dashboard/project_mapper_explorer_routes.py
Read-only explorer over Project Mapper snapshots, for the Suite's PM tab.

Project Mapper is consumed as a package and is deliberately query-oriented — it
exposes no list-entities endpoint. Rather than bloat PM with a view API, the
Suite reads a PM snapshot through PM's *own* loader
(``project_mapper.db.snapshot.load``), caches it by snapshot mtime, and serves
paginated/filtered entities to the explorer. PM stays lean; the snapshot format
stays PM's concern (we never parse the file ourselves).

Prefix: /api/pm-explorer  (distinct from the package's own /api/project-mapper)
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from core.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/pm-explorer", tags=["project-mapper-explorer"])

# db_root path -> {"mtime": float, "entities": list[dict]}
_CACHE: dict[str, dict] = {}
_LOCK = threading.Lock()


def _load_entities(db: str) -> list[dict[str, Any]]:
    """Return active entities for a PM database, cached by snapshot mtime.

    Reads through Project Mapper's own loader, so the on-disk format stays PM's
    concern. Returns [] when nothing has been scanned yet; raises 503 if the
    Project Mapper package isn't installed.
    """
    try:
        from project_mapper.db.db_registry import resolve_db_root
        from project_mapper.db import snapshot as pm_snap
    except Exception:
        raise HTTPException(503, "Project Mapper is not installed in this environment.")

    root = resolve_db_root(db)
    snap = pm_snap.snapshot_path(root)
    if not snap.exists():
        return []
    try:
        mtime = snap.stat().st_mtime
    except OSError:
        return []

    key = str(root)
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and cached["mtime"] == mtime:
            return cached["entities"]

    entities = [e for e in (pm_snap.load(root) or []) if e.get("status") != "deleted"]
    with _LOCK:
        _CACHE[key] = {"mtime": mtime, "entities": entities}
    return entities


@router.get("/stats")
async def explorer_stats(db: str = Query("default")):
    """Entity counts by type for the explorer stats bar."""
    entities = await asyncio.to_thread(_load_entities, db)
    by_type: dict[str, int] = {}
    for e in entities:
        t = e.get("type", "other")
        by_type[t] = by_type.get(t, 0) + 1
    return {"total_entities": len(entities), "by_type": by_type}


@router.get("/entities")
async def explorer_entities(
    db:          str = Query("default"),
    entity_type: Optional[str] = Query(None),
    limit:       int = Query(200, le=1000),
    offset:      int = Query(0, ge=0),
):
    """Paginated, optionally type-filtered list of entities (slim fields)."""
    def _work() -> dict:
        entities = _load_entities(db)
        if entity_type:
            entities = [e for e in entities if e.get("type") == entity_type]
        total = len(entities)
        page = entities[offset:offset + limit]
        slim = [
            {"id": e.get("id"), "name": e.get("name"),
             "type": e.get("type"), "status": e.get("status")}
            for e in page
        ]
        return {"entities": slim, "total": total, "offset": offset, "limit": limit}

    return await asyncio.to_thread(_work)


@router.get("/entities/{entity_id}")
async def explorer_entity(entity_id: str, db: str = Query("default")):
    """Full entity body for the explorer detail pane."""
    def _work() -> dict:
        for e in _load_entities(db):
            if e.get("id") == entity_id:
                return e
        raise HTTPException(404, f"Entity '{entity_id}' not found")

    return await asyncio.to_thread(_work)
