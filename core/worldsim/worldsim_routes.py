"""
core/worldsim/worldsim_routes.py
═════════════════════════════════
FastAPI routes for the WorldSim dashboard tab.

Prefix: /api/worldsim

Multiple databases
------------------
Every endpoint accepts ?db=<name> (default: "default").
Named databases live at  WORLDSIM/<name>/
Use ?path=<absolute_path> to point at an arbitrary location instead.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.utils.logger import get_logger
from core.utils.paths import WORLDSIM

logger = get_logger(__name__)
router = APIRouter(prefix="/api/worldsim", tags=["worldsim"])

_SAFE_DB_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


# ── Database resolution ───────────────────────────────────────────────────────

def _db_root(db: str = "default", path: Optional[str] = None) -> Path:
    """Return the root directory for a database."""
    if path:
        return Path(path)
    if not _SAFE_DB_RE.match(db):
        raise HTTPException(400, f"Invalid database name {db!r}")
    return WORLDSIM / db


def _get_writer(db: str = "default", path: Optional[str] = None):
    from .entity_writer import EntityWriter
    root = _db_root(db, path)
    return EntityWriter(entities_dir=root / "entities")


def _get_index(db: str = "default", path: Optional[str] = None):
    from .name_index import NameIndex
    root = _db_root(db, path)
    return NameIndex(index_path=root / "name_index.json")


def _get_validator(db: str = "default", path: Optional[str] = None):
    from .validator import Validator
    return Validator(_get_writer(db, path))


def _ensure_db(root: Path) -> None:
    (root / "entities").mkdir(parents=True, exist_ok=True)
    (root / "chunks").mkdir(parents=True, exist_ok=True)


# ── Request schemas ───────────────────────────────────────────────────────────

class DistillRequest(BaseModel):
    content: str                  # Text to extract an entity from
    model:   Optional[str] = None
    source:  str = "distilled"


class ExpandRequest(BaseModel):
    entity_ids:   Optional[list[str]] = None
    max_entities: int = 10
    model:        Optional[str] = None


class CreateEntityRequest(BaseModel):
    name:        str
    entity_type: str = "other"
    source:      str = "manual"
    summary:     str = ""
    tags:        list[str] = []
    properties:  dict[str, str] = {}


class UpdateEntityRequest(BaseModel):
    mutations: dict[str, Any]


class CreateDatabaseRequest(BaseModel):
    name: str
    path: Optional[str] = None   # Custom filesystem path; if omitted uses WORLDSIM/<name>


# ── Database management ───────────────────────────────────────────────────────

@router.get("/databases")
async def list_databases():
    """List all named databases stored in the default WorldSim root."""
    WORLDSIM.mkdir(parents=True, exist_ok=True)
    dbs = []
    for d in sorted(WORLDSIM.iterdir()):
        if d.is_dir() and (d / "entities").exists():
            entity_count = sum(1 for _ in (d / "entities").glob("ws_*.json"))
            dbs.append({"name": d.name, "path": str(d), "entity_count": entity_count})
    return {"databases": dbs}


@router.post("/databases")
async def create_database(req: CreateDatabaseRequest):
    """Create a new database (named or at a custom path)."""
    if not _SAFE_DB_RE.match(req.name):
        raise HTTPException(400, f"Invalid database name {req.name!r}")
    root = Path(req.path) if req.path else WORLDSIM / req.name
    if (root / "entities").exists():
        raise HTTPException(409, f"Database '{req.name}' already exists at {root}")
    _ensure_db(root)
    return {"name": req.name, "path": str(root), "created": True}


@router.delete("/databases/{name}")
async def delete_database(name: str, confirm: bool = Query(False)):
    """Delete a named database. Requires ?confirm=true."""
    if not confirm:
        raise HTTPException(400, "Pass ?confirm=true to delete a database.")
    root = WORLDSIM / name
    if not root.exists():
        raise HTTPException(404, f"Database '{name}' not found")
    shutil.rmtree(root)
    return {"deleted": name}


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    writer = _get_writer(db, path)
    index  = _get_index(db, path)
    all_e  = writer.list_all(include_deleted=True)

    by_type:   dict[str, int] = {}
    by_status: dict[str, int] = {}
    for e in all_e:
        t = e.get("type", "other"); s = e.get("status", "active")
        by_type[t]   = by_type.get(t, 0) + 1
        by_status[s] = by_status.get(s, 0) + 1

    return {
        "db":             db,
        "total_entities": len(all_e),
        "by_status":      by_status,
        "by_type":        by_type,
        "index_size":     index.count(),
        "stub_count":     by_status.get("stub", 0),
    }


# ── Entity CRUD ───────────────────────────────────────────────────────────────

@router.get("/entities")
async def list_entities(
    db:          str = Query("default"),
    path:        Optional[str] = Query(None),
    status:      Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    limit:       int = Query(100, le=500),
    offset:      int = Query(0, ge=0),
):
    writer   = _get_writer(db, path)
    entities = writer.list_all(include_deleted=(status == "deleted"))
    if status and status != "all":
        entities = [e for e in entities if e.get("status") == status]
    if entity_type:
        entities = [e for e in entities if e.get("type") == entity_type]
    return {"total": len(entities), "offset": offset, "limit": limit,
            "entities": entities[offset:offset + limit]}


@router.get("/entities/{entity_id}")
async def get_entity(
    entity_id: str,
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    entity = _get_writer(db, path).get(entity_id)
    if not entity:
        raise HTTPException(404, f"Entity '{entity_id}' not found")
    return entity


@router.get("/lookup")
async def lookup_by_name(
    name: str = Query(...),
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    index  = _get_index(db, path)
    writer = _get_writer(db, path)
    eid = index.get(name)
    if not eid:
        raise HTTPException(404, f"No entity for name '{name}'")
    entity = writer.get(eid)
    if not entity:
        raise HTTPException(404, f"Index points to {eid} but entity file is missing")
    return entity


@router.post("/entities")
async def create_entity(
    req:  CreateEntityRequest,
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    writer = _get_writer(db, path)
    _ensure_db(_db_root(db, path))
    entity, was_created = writer.create(
        name=req.name,
        entity_type=req.entity_type,
        source=req.source,
        sections_override={
            "core":       {"summary": req.summary, "tags": req.tags},
            "properties": req.properties,
        },
    )
    return {"entity": entity, "was_created": was_created}


@router.put("/entities/{entity_id}")
async def update_entity(
    entity_id: str,
    req:  UpdateEntityRequest,
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    writer = _get_writer(db, path)
    if not writer.exists(entity_id):
        raise HTTPException(404, f"Entity '{entity_id}' not found")
    return writer.update(entity_id, req.mutations)


@router.delete("/entities/{entity_id}")
async def delete_entity(
    entity_id: str,
    hard: bool = Query(False),
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    writer = _get_writer(db, path)
    if not writer.exists(entity_id):
        raise HTTPException(404, f"Entity '{entity_id}' not found")
    writer.delete(entity_id, soft=not hard)
    return {"success": True, "entity_id": entity_id, "mode": "hard" if hard else "soft"}


# ── Search ────────────────────────────────────────────────────────────────────

@router.get("/search")
async def search_entities(
    q:           str = Query(""),
    entity_type: Optional[str] = Query(None),
    tag:         Optional[str] = Query(None),
    limit:       int = Query(50, le=200),
    db:          str = Query("default"),
    path:        Optional[str] = Query(None),
):
    writer  = _get_writer(db, path)
    q_lower = q.lower()
    results = []
    for e in writer.list_all():
        if entity_type and e.get("type") != entity_type:
            continue
        if tag:
            if not any(t.lower() == tag.lower() for t in e["sections"]["core"].get("tags", [])):
                continue
        if q_lower:
            name    = e.get("name", "").lower()
            summary = e["sections"]["core"].get("summary", "").lower()
            aliases = [a.lower() for a in e["sections"]["core"].get("aliases", [])]
            if q_lower not in name and q_lower not in summary and not any(q_lower in a for a in aliases):
                continue
        results.append({
            "id":      e["id"],
            "name":    e["name"],
            "type":    e.get("type"),
            "status":  e.get("status"),
            "summary": e["sections"]["core"].get("summary", "")[:200],
        })
        if len(results) >= limit:
            break
    return {"count": len(results), "results": results}


# ── Distillation ──────────────────────────────────────────────────────────────

@router.post("/distill")
async def distill_content(
    req:  DistillRequest,
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Distill any text into an entity. The AI determines the entity name."""
    from .distiller import ContentDistiller
    root   = _db_root(db, path)
    _ensure_db(root)
    writer = _get_writer(db, path)
    index  = _get_index(db, path)
    d      = ContentDistiller(writer=writer, index=index)
    result = await d.distill(content=req.content, model=req.model, source=req.source)
    if result["errors"]:
        raise HTTPException(500, {"message": "Distillation errors", "errors": result["errors"]})
    return result


# ── Expansion ─────────────────────────────────────────────────────────────────

@router.post("/expand")
async def expand_stubs(
    req:  ExpandRequest,
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    from .expansion_engine import ExpansionEngine
    engine = ExpansionEngine(writer=_get_writer(db, path), index=_get_index(db, path))
    report = await engine.run(max_entities=req.max_entities, model=req.model, only_ids=req.entity_ids)
    return report.as_dict()


@router.post("/entities/{entity_id}/expand")
async def expand_single(
    entity_id: str,
    model: Optional[str] = Query(None),
    db:    str = Query("default"),
    path:  Optional[str] = Query(None),
):
    from .expansion_engine import ExpansionEngine
    engine = ExpansionEngine(writer=_get_writer(db, path), index=_get_index(db, path))
    result = await engine.expand_stub(entity_id, model=model)
    if not result["success"] and result["error"] != "already_active":
        raise HTTPException(500, result["error"])
    return result


@router.post("/entities/{entity_id}/deepen")
async def deepen_entity(
    entity_id: str,
    max_stubs: int = Query(5, le=20),
    model:     Optional[str] = Query(None),
    db:        str = Query("default"),
    path:      Optional[str] = Query(None),
):
    from .expansion_engine import ExpansionEngine
    engine = ExpansionEngine(writer=_get_writer(db, path), index=_get_index(db, path))
    report = await engine.deepen_stubs_for(entity_id, max_stubs=max_stubs, model=model)
    return report.as_dict()


# ── Validation ────────────────────────────────────────────────────────────────

@router.get("/validate")
async def validate_all(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    summary = await asyncio.to_thread(_get_validator(db, path).summary)
    return summary


@router.get("/validate/{entity_id}")
async def validate_entity(
    entity_id: str,
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    result = await asyncio.to_thread(_get_validator(db, path).validate, entity_id)
    return result.as_dict()


# ── Index / stubs ─────────────────────────────────────────────────────────────

@router.get("/index")
async def get_index_snapshot(
    limit: int = Query(200, le=1000),
    db:    str = Query("default"),
    path:  Optional[str] = Query(None),
):
    index = _get_index(db, path)
    items = list(index.list_all().items())[:limit]
    return {"total": index.count(), "entries": [{"name": k, "id": v} for k, v in items]}


@router.get("/stubs")
async def list_stubs(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    writer = _get_writer(db, path)
    stubs  = writer.list_stubs()
    return {
        "count": len(stubs),
        "stubs": [{"id": e["id"], "name": e["name"], "type": e.get("type")} for e in stubs],
    }
