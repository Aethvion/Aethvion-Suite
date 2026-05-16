"""
core/aethviondb/aethviondb_routes.py
══════════════════════════════════════
FastAPI routes for the AethvionDB dashboard tab.

Prefix: /api/aethviondb

Multiple databases
------------------
Every endpoint accepts ?db=<name> (default: "default").
Named databases live at  AETHVIONDB/<name>/
Use ?path=<absolute_path> to point at an arbitrary location instead.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.utils.logger import get_logger
from core.utils.paths import AETHVIONDB

logger = get_logger(__name__)
router = APIRouter(prefix="/api/aethviondb", tags=["aethviondb"])

_SAFE_DB_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


# ── Database resolution ───────────────────────────────────────────────────────

def _db_root(db: str = "default", path: Optional[str] = None) -> Path:
    """Return the root directory for a database."""
    if path:
        return Path(path)
    if not _SAFE_DB_RE.match(db):
        raise HTTPException(400, f"Invalid database name {db!r}")
    return AETHVIONDB / db


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


# ── AethvionDB.INFO helpers ───────────────────────────────────────────────────

_INFO_FILE = "AethvionDB.INFO"

def _read_db_info(root: Path) -> dict:
    """Return the contents of AethvionDB.INFO, or {} if absent / unreadable."""
    p = root / _INFO_FILE
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _write_db_info(root: Path, data: dict) -> None:
    """Persist data to AethvionDB.INFO (best-effort — never raises)."""
    try:
        (root / _INFO_FILE).write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning(f"[WorldSim] Could not write {_INFO_FILE}: {exc}")


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
    path: Optional[str] = None   # Custom filesystem path; if omitted uses AETHVIONDB/<name>


# ── Database management ───────────────────────────────────────────────────────

@router.get("/databases")
async def list_databases():
    """List all named databases stored in the default WorldSim root."""
    AETHVIONDB.mkdir(parents=True, exist_ok=True)
    dbs = []
    for d in sorted(AETHVIONDB.iterdir()):
        if d.is_dir() and (d / "entities").exists():
            entity_count = sum(1 for _ in (d / "entities").glob("ws_*.json"))
            dbs.append({"name": d.name, "path": str(d), "entity_count": entity_count})
    return {"databases": dbs}


@router.post("/databases")
async def create_database(req: CreateDatabaseRequest):
    """Create a new database (named or at a custom path)."""
    if not _SAFE_DB_RE.match(req.name):
        raise HTTPException(400, f"Invalid database name {req.name!r}")
    root = Path(req.path) if req.path else AETHVIONDB / req.name
    if (root / "entities").exists():
        raise HTTPException(409, f"Database '{req.name}' already exists at {root}")
    _ensure_db(root)
    now = datetime.now(timezone.utc).isoformat()
    _write_db_info(root, {
        "name":             req.name,
        "created":          now,
        "last_updated":     now,
        "total_entities":   0,
        "stub_count":       0,
        "index_size":       0,
        "by_type":          {},
        "by_status":        {},
        "total_size_bytes": 0,
    })
    return {"name": req.name, "path": str(root), "created": True}


@router.delete("/databases/{name}")
async def delete_database(name: str, confirm: bool = Query(False)):
    """Delete a named database. Requires ?confirm=true."""
    if not confirm:
        raise HTTPException(400, "Pass ?confirm=true to delete a database.")
    root = AETHVIONDB / name
    if not root.exists():
        raise HTTPException(404, f"Database '{name}' not found")
    shutil.rmtree(root)
    return {"deleted": name}


@router.get("/info")
async def get_db_info(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """
    Return cached database metadata from AethvionDB.INFO (zero-cost read).
    Returns {"cached": false} when no INFO file exists yet.
    Call /stats to compute fresh values and update the file.
    """
    root = _db_root(db, path)
    info = _read_db_info(root)
    if not info:
        return {"cached": False}
    return {"cached": True, **info}


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

    # Total size of entity files — reads only OS metadata, not file contents
    total_size_bytes = 0
    entities_dir = _db_root(db, path) / "entities"
    if entities_dir.exists():
        for f in entities_dir.iterdir():
            if f.suffix == ".json":
                try:
                    total_size_bytes += f.stat().st_size
                except OSError:
                    pass

    # Count incoming relations for each stub entity.
    # An "incoming relation" is when an active entity has a relation whose
    # target_id points to a stub.  More incoming = more likely to be important.
    stub_ids = {e["id"] for e in all_e if e.get("status") == "stub"}
    incoming: dict[str, int] = {sid: 0 for sid in stub_ids}
    for e in all_e:
        if e.get("status") == "deleted":
            continue
        for rel in (e.get("sections") or {}).get("relations", []):
            tid = rel.get("target_id")
            if tid in incoming:
                incoming[tid] += 1

    stubs_by_min_relations = {
        "1": sum(1 for c in incoming.values() if c >= 1),
        "2": sum(1 for c in incoming.values() if c >= 2),
        "3": sum(1 for c in incoming.values() if c >= 3),
    }

    result = {
        "db":                    db,
        "total_entities":        len(all_e),
        "by_status":             by_status,
        "by_type":               by_type,
        "index_size":            index.count(),
        "stub_count":            by_status.get("stub", 0),
        "total_size_bytes":      total_size_bytes,
        "stubs_by_min_relations": stubs_by_min_relations,
    }

    # Persist to AethvionDB.INFO so the UI can display stats on next page load
    # without re-scanning (especially important for large databases).
    root = _db_root(db, path)
    existing = _read_db_info(root)
    _write_db_info(root, {
        **existing,                              # preserve name, created, etc.
        **result,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    })

    return result


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
            "id":              e["id"],
            "name":            e["name"],
            "type":            e.get("type"),
            "status":          e.get("status"),
            "summary":         e["sections"]["core"].get("summary", "")[:200],
            "tags":            e["sections"]["core"].get("tags", [])[:5],
            "relations_count": len(e["sections"].get("relations", [])),
            "stubs_count":     len(e["sections"].get("stubs", [])),
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


@router.post("/expand/smart")
async def smart_expand(
    min_relations: int = Query(1, ge=1, le=10, description="Minimum incoming relations a stub must have"),
    max_entities:  int = Query(20, le=100),
    model:         Optional[str] = Query(None),
    db:            str = Query("default"),
    path:          Optional[str] = Query(None),
):
    """
    Expand only the stubs that have at least `min_relations` incoming references
    from other entities.  Stubs with more incoming references are more likely to
    be important nodes worth expanding first.
    """
    writer = _get_writer(db, path)
    all_e  = writer.list_all()

    # Build incoming-relation count for every stub
    stub_ids = {e["id"] for e in all_e if e.get("status") == "stub"}
    incoming: dict[str, int] = {sid: 0 for sid in stub_ids}
    for e in all_e:
        if e.get("status") == "deleted":
            continue
        for rel in (e.get("sections") or {}).get("relations", []):
            tid = rel.get("target_id")
            if tid in incoming:
                incoming[tid] += 1

    target_ids = [sid for sid, c in incoming.items() if c >= min_relations]

    if not target_ids:
        return {
            "expanded": [], "failed": [], "skipped": [], "new_stubs": [],
            "total_processed": 0,
            "message": f"No stubs with {min_relations}+ incoming relations found.",
        }

    from .expansion_engine import ExpansionEngine
    engine = ExpansionEngine(writer=writer, index=_get_index(db, path))
    report = await engine.run(
        max_entities=min(max_entities, len(target_ids)),
        model=model,
        only_ids=target_ids,
    )
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


# ── Graph ─────────────────────────────────────────────────────────────────────

def _graph_bfs(writer, start_id: str, depth: int) -> set:
    """Return all entity IDs reachable from start_id within `depth` hops."""
    visited  = {start_id}
    frontier = {start_id}
    for _ in range(depth):
        nxt: set = set()
        for eid in frontier:
            entity = writer.get(eid)
            if not entity:
                continue
            for rel in (entity.get("sections") or {}).get("relations", []):
                tid = rel.get("target_id")
                if tid and tid not in visited:
                    nxt.add(tid)
                    visited.add(tid)
        frontier = nxt
        if not frontier:
            break
    return visited


@router.get("/graph")
async def get_graph(
    db:        str = Query("default"),
    path:      Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None, description="Focus node — returns BFS neighbourhood"),
    depth:     int = Query(2, ge=1, le=4),
    limit:     int = Query(500, le=2000),
):
    """
    Return nodes + directed edges for graph visualisation.

    Without entity_id: all entities up to `limit` (full graph).
    With entity_id:    BFS neighbourhood up to `depth` hops from that entity.
    """
    writer = _get_writer(db, path)
    all_e  = writer.list_all()          # full entities, no deleted

    if entity_id:
        included = await asyncio.to_thread(_graph_bfs, writer, entity_id, depth)
    else:
        included = {e["id"] for e in all_e[:limit]}

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_edges: set   = set()
    id_set: set       = set()

    for e in all_e:
        if e["id"] not in included:
            continue
        id_set.add(e["id"])
        core = (e.get("sections") or {}).get("core", {})
        nodes.append({
            "id":        e["id"],
            "name":      e["name"],
            "type":      e.get("type", "other"),
            "status":    e.get("status", "active"),
            "summary":   core.get("summary", "")[:120],
            "rel_count": len((e.get("sections") or {}).get("relations", [])),
        })

    # Edges — only where both endpoints are in the node set
    for e in all_e:
        if e["id"] not in id_set:
            continue
        for rel in (e.get("sections") or {}).get("relations", []):
            tid = rel.get("target_id")
            if not tid or tid not in id_set:
                continue
            kind = rel.get("kind", "related_to")
            # Dedup undirected (keep first direction encountered)
            key = (min(e["id"], tid), max(e["id"], tid), kind)
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append({"source": e["id"], "target": tid, "kind": kind})

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes":      nodes,
        "edges":      edges,
        "focused_id": entity_id,
        "truncated":  (entity_id is None) and len(all_e) > limit,
    }


# ── Folder distillation ───────────────────────────────────────────────────────

@router.get("/distill-folder/scan")
async def scan_folder_endpoint(
    folder: str = Query(..., description="Absolute path to the folder to scan"),
):
    """Scan a folder and return file metadata without starting distillation."""
    from .folder_distiller import scan_folder
    try:
        return await asyncio.to_thread(scan_folder, folder)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except NotADirectoryError as e:
        raise HTTPException(400, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.get("/distill-folder/status")
async def get_distill_status(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """
    Return the current folder-distillation job status from AethvionDB.DISTILLINFO.
    If the task was running when the server restarted the status is corrected
    to "paused" automatically.
    """
    from .folder_distiller import read_distill_info, write_distill_info, is_running
    root = _db_root(db, path)
    info = read_distill_info(root)
    if not info:
        return {"status": "idle"}

    status = info.get("status", "idle")
    # Server was killed mid-run — treat as paused so user can resume
    if status == "running" and not is_running(root):
        status = "paused"
        info   = {**info, "status": "paused", "last_updated": datetime.now(timezone.utc).isoformat()}
        write_distill_info(root, info)

    total    = info.get("total_files", 0)
    next_idx = info.get("next_index",  0)
    pct      = round(next_idx / total * 100, 1) if total else 0.0

    return {**info, "status": status, "progress_pct": pct, "is_running": is_running(root)}


@router.post("/distill-folder/start")
async def start_folder_distill(
    folder: str = Query(..., description="Absolute path to the source folder"),
    model:  str = Query("auto"),
    db:     str = Query("default"),
    path:   Optional[str] = Query(None),
):
    """
    Start distilling a folder from scratch.
    Scans the folder in a thread (non-blocking), then launches a background task.
    """
    from .folder_distiller import (
        _active_tasks, _pause_events,
        prepare_start_job, run_distill_job,
    )
    root = _db_root(db, path)
    key  = str(root)

    if key in _active_tasks:
        raise HTTPException(409, "A distillation job is already running for this database.")

    _ensure_db(root)

    # Scan + write queue in a thread (can take seconds for large folders)
    total = await asyncio.to_thread(
        prepare_start_job, root, folder, model, "folder_distill"
    )

    # Event must be created from the async context so it belongs to the running loop
    ev = asyncio.Event()
    ev.set()                       # set = not paused = running
    _pause_events[key] = ev

    writer = _get_writer(db, path)
    index  = _get_index(db, path)

    task = asyncio.create_task(run_distill_job(root, writer, index, model, "folder_distill"))
    _active_tasks[key] = task
    task.add_done_callback(lambda _: _active_tasks.pop(key, None))

    return {"started": True, "total_files": total}


@router.post("/distill-folder/pause")
async def pause_folder_distill(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Signal the running job to pause after the current file."""
    from .folder_distiller import pause_job
    return pause_job(_db_root(db, path))


@router.post("/distill-folder/resume")
async def resume_folder_distill(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Resume a paused (or interrupted) folder distillation job."""
    from .folder_distiller import (
        _active_tasks, _pause_events,
        read_distill_info, write_distill_info, run_distill_job,
    )
    root = _db_root(db, path)
    key  = str(root)

    if key in _active_tasks:
        raise HTTPException(409, "Job is already running.")

    info = read_distill_info(root)
    if not info:
        raise HTTPException(404, "No distillation job found for this database.")
    if info.get("status") not in ("paused", "error", "starting"):
        raise HTTPException(409, f"Cannot resume — current status is '{info.get('status')}'.")

    folder = info.get("folder_path", "")
    if not folder or not Path(folder).exists():
        raise HTTPException(400, f"Source folder missing or moved: {folder!r}")

    model  = info.get("model",  "auto")
    source = info.get("source", "folder_distill")

    ev = asyncio.Event()
    ev.set()
    _pause_events[key] = ev

    writer = _get_writer(db, path)
    index  = _get_index(db, path)

    task = asyncio.create_task(run_distill_job(root, writer, index, model, source))
    _active_tasks[key] = task
    task.add_done_callback(lambda _: _active_tasks.pop(key, None))

    return {"resumed": True, "next_index": info.get("next_index", 0)}


@router.post("/distill-folder/cancel")
async def cancel_folder_distill(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Pause the job (if running) and mark it as cancelled in DISTILLINFO."""
    from .folder_distiller import (
        pause_job, read_distill_info, write_distill_info,
    )
    root = _db_root(db, path)
    pause_job(root)
    info = read_distill_info(root)
    if info:
        write_distill_info(root, {
            **info,
            "status":       "cancelled",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })
    return {"cancelled": True}


# ── Vectors ───────────────────────────────────────────────────────────────────

@router.get("/vectors/status")
async def get_vector_status(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Return vectorization status from VECINFO."""
    from .vectorizer import read_vec_info, is_vectorizing
    root = _db_root(db, path)
    info = read_vec_info(root)
    if not info:
        return {"status": "idle", "is_vectorizing": False}
    return {**info, "is_vectorizing": is_vectorizing(root)}


@router.post("/vectors/generate")
async def start_vectorize(
    model:         str  = Query("text-embedding-004"),
    force_rewrite: bool = Query(False),
    include_stubs: bool = Query(True),
    db:            str  = Query("default"),
    path:          Optional[str] = Query(None),
):
    """Start background vectorization job."""
    from .vectorizer import _vec_tasks, vectorize_all, is_vectorizing, EMBEDDING_MODELS
    root = _db_root(db, path)
    key  = str(root)

    if is_vectorizing(root):
        raise HTTPException(409, "Vectorization already running for this database.")
    if model not in EMBEDDING_MODELS:
        raise HTTPException(400, f"Unknown embedding model {model!r}")

    writer = _get_writer(db, path)
    task   = asyncio.create_task(
        vectorize_all(root, writer, model, force_rewrite, include_stubs)
    )
    _vec_tasks[key] = task
    task.add_done_callback(lambda _: _vec_tasks.pop(key, None))
    return {"started": True, "model": model, "include_stubs": include_stubs}


@router.post("/vectors/cancel")
async def cancel_vectorize_endpoint(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    from .vectorizer import cancel_vectorize
    return cancel_vectorize(_db_root(db, path))


# ── Bake ──────────────────────────────────────────────────────────────────────

class BakeRequest(BaseModel):
    format:          str  = "jsonl"   # jsonl | json | markdown | txt
    include_stubs:   bool = True
    include_vectors: bool = False


@router.get("/bake/status")
async def get_bake_status(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Return the last bake info from AethvionDB.BAKEINFO."""
    from .baker import read_bake_info, is_baking
    root = _db_root(db, path)
    info = read_bake_info(root)
    if not info:
        return {"status": "idle"}
    return {**info, "is_baking": is_baking(root)}


@router.post("/bake")
async def start_bake(
    req:  BakeRequest,
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """
    Start baking the database into a single export file.
    Runs in the background — poll /bake/status to monitor progress.
    """
    from .baker import (
        _bake_tasks, bake_database, is_baking, write_bake_info, BAKE_FORMATS
    )
    root = _db_root(db, path)
    key  = str(root)

    if is_baking(root):
        raise HTTPException(409, "A bake is already running for this database.")

    if req.format not in BAKE_FORMATS:
        raise HTTPException(400, f"Unknown format {req.format!r}. Must be one of {BAKE_FORMATS}")

    writer = _get_writer(db, path)

    task = asyncio.create_task(
        bake_database(root, writer, fmt=req.format, include_stubs=req.include_stubs, include_vectors=req.include_vectors)
    )
    _bake_tasks[key] = task
    task.add_done_callback(lambda _: _bake_tasks.pop(key, None))

    return {"started": True, "format": req.format, "include_stubs": req.include_stubs, "include_vectors": req.include_vectors}


@router.get("/bake/download")
async def download_bake(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Download the most recently baked output file."""
    from fastapi.responses import FileResponse
    from .baker import read_bake_info

    root = _db_root(db, path)
    info = read_bake_info(root)

    if not info or info.get("status") != "done":
        raise HTTPException(404, "No completed bake found. Run a bake first.")

    out_path = Path(info["output_path"])
    if not out_path.exists():
        raise HTTPException(404, f"Baked file missing: {out_path.name}")

    media = {
        "jsonl":    "application/x-ndjson",
        "json":     "application/json",
        "markdown": "text/markdown",
        "txt":      "text/plain",
    }.get(info.get("format", ""), "application/octet-stream")

    return FileResponse(
        path=str(out_path),
        media_type=media,
        filename=out_path.name,
    )


@router.get("/stubs")
async def list_stubs(
    db:     str = Query("default"),
    path:   Optional[str] = Query(None),
    limit:  int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    writer = _get_writer(db, path)
    stubs  = writer.list_stubs()
    total  = len(stubs)
    paged  = stubs[offset:offset + limit]
    return {
        "count":  total,
        "stubs":  [{"id": e["id"], "name": e["name"], "type": e.get("type")} for e in paged],
    }
