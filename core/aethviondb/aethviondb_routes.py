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
import threading
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

# Shared NameIndex instances per database path — prevents TOCTOU duplicates
# when concurrent requests both attempt to create the same entity name.
_INDEX_CACHE: dict[str, Any] = {}
_INDEX_CACHE_LOCK = threading.Lock()


# ── Database resolution ───────────────────────────────────────────────────────

def _db_root(db: str = "default", path: Optional[str] = None) -> Path:
    """Return the root directory for a database."""
    if path:
        # Register so the v1 API can find this path-based database by name
        from .db_registry import register_path_db
        register_path_db(path)
        return Path(path)
    if not _SAFE_DB_RE.match(db):
        raise HTTPException(400, f"Invalid database name {db!r}")
    from .db_registry import resolve_db_root
    return resolve_db_root(db)


def _get_index(db: str = "default", path: Optional[str] = None):
    """Return the shared NameIndex singleton for this database path.

    A single instance is cached per resolved root path so that all concurrent
    requests share the same threading.Lock — making get_or_create truly atomic
    across threads and preventing duplicate-entity races.
    """
    from .name_index import NameIndex
    root = _db_root(db, path)
    key = str(root)
    with _INDEX_CACHE_LOCK:
        if key not in _INDEX_CACHE:
            _INDEX_CACHE[key] = NameIndex(index_path=root / "name_index.json")
        return _INDEX_CACHE[key]


def _get_writer(db: str = "default", path: Optional[str] = None):
    """Return an EntityWriter wired to the shared NameIndex for this database."""
    from .entity_writer import EntityWriter
    root = _db_root(db, path)
    return EntityWriter(entities_dir=root / "entities", index=_get_index(db, path))


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
        logger.warning(f"[AethvionDB] Could not write {_INFO_FILE}: {exc}")


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


class ImportRequest(BaseModel):
    content:        str
    filename:       str           = "import.json"
    conflict_mode:  str           = "skip"       # 'skip' | 'overwrite'
    source:         Optional[str] = None


class ApplyExpandRequest(BaseModel):
    proposed: dict[str, Any]


class ApplyDeepenRequest(BaseModel):
    previews: list[dict[str, Any]]


class CreateDatabaseRequest(BaseModel):
    name:        str
    path:        Optional[str] = None   # Custom filesystem path; if omitted uses AETHVIONDB/<name>
    description: str           = ""


class UpdateDatabaseSettingsRequest(BaseModel):
    description: Optional[str]  = None
    backup:      Optional[dict] = None   # {enabled: bool, keep_count: int}


class CreateBackupRequest(BaseModel):
    label: str = ""


# ── Database management ───────────────────────────────────────────────────────

@router.get("/databases")
async def list_databases():
    """List all named databases (registry + auto-discovered)."""
    from .db_registry import register_db, list_dbs

    AETHVIONDB.mkdir(parents=True, exist_ok=True)

    # ── Legacy migration (one-time, non-destructive) ──────────────────────────
    # If databases lived in the old data/modes/worldsim/ root, register them
    # with their original absolute paths so nothing is lost when the root moves.
    from core.utils.paths import MODES
    _legacy_root = MODES / "worldsim"
    if _legacy_root.exists():
        for d in _legacy_root.iterdir():
            if (d.is_dir()
                    and not d.name.startswith("_")
                    and (d / "entities").exists()):
                register_db(d.name, str(d), overwrite=False)

    # Auto-discover databases in the new default root
    for d in AETHVIONDB.iterdir():
        if (d.is_dir()
                and not d.name.startswith("_")
                and (d / "entities").exists()):
            register_db(d.name, str(d), overwrite=False)

    # Build enriched list from registry
    from .backup import list_backups as _lb
    dbs: list[dict] = []
    for entry in list_dbs():
        db_path      = Path(entry["path"])
        entity_count = 0
        size_bytes   = 0
        if (db_path / "entities").exists():
            for f in (db_path / "entities").glob("ws_*.json"):
                entity_count += 1
                try:   size_bytes += f.stat().st_size
                except OSError: pass
        backups     = _lb(db_path)
        last_backup = backups[0].get("created") if backups else None
        info        = _read_db_info(db_path)
        last_updated = info.get("last_updated")
        dbs.append({
            **entry,
            "entity_count": entity_count,
            "size_bytes":   size_bytes,
            "backup_count": len(backups),
            "last_backup":  last_backup,
            "last_updated": last_updated,
            "path_exists":  db_path.exists(),
        })

    return {"databases": sorted(dbs, key=lambda d: d["name"])}


@router.post("/databases")
async def create_database(req: CreateDatabaseRequest):
    """Create a new database or register an existing folder under a name."""
    from .db_registry import register_db

    if not _SAFE_DB_RE.match(req.name):
        raise HTTPException(400, f"Invalid database name {req.name!r}")

    root           = Path(req.path) if req.path else AETHVIONDB / req.name
    already_exists = (root / "entities").exists()

    if not already_exists:
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

    register_db(req.name, str(root), description=req.description)
    return {"name": req.name, "path": str(root), "created": not already_exists}


@router.delete("/databases/{name}")
async def delete_database(name: str, confirm: bool = Query(False)):
    """Delete a named database and remove it from the registry. Requires ?confirm=true."""
    from .db_registry import remove_db, get_db

    if not confirm:
        raise HTTPException(400, "Pass ?confirm=true to delete a database.")

    # Resolve path via registry, fall back to default location
    entry = get_db(name)
    root  = Path(entry["path"]) if entry else AETHVIONDB / name
    if not root.exists():
        raise HTTPException(404, f"Database '{name}' not found at {root}")
    shutil.rmtree(root)
    remove_db(name)
    return {"deleted": name}


@router.put("/databases/{name}/settings")
async def update_database_settings(name: str, req: UpdateDatabaseSettingsRequest):
    """Update description and/or backup settings for a named database."""
    from .db_registry import update_db, get_db

    if not _SAFE_DB_RE.match(name):
        raise HTTPException(400, f"Invalid database name {name!r}")
    if not get_db(name):
        raise HTTPException(404, f"Database '{name}' not registered")

    kwargs: dict = {}
    if req.description is not None:
        kwargs["description"] = req.description
    if req.backup is not None:
        # Validate and sanitise backup sub-fields
        bk: dict = {}
        if "enabled" in req.backup:
            bk["enabled"] = bool(req.backup["enabled"])
        if "keep_count" in req.backup:
            bk["keep_count"] = max(1, int(req.backup["keep_count"]))
        kwargs["backup"] = bk

    entry = update_db(name, **kwargs)
    return {"updated": True, "entry": entry}


@router.post("/databases/{name}/backup")
async def create_backup_route(
    name: str,
    req:  CreateBackupRequest,
):
    """Create a point-in-time backup of a named database."""
    from .backup import create_backup
    from .db_registry import get_db

    if not _SAFE_DB_RE.match(name):
        raise HTTPException(400, f"Invalid database name {name!r}")

    entry    = get_db(name)
    db_root  = Path(entry["path"]) if entry else AETHVIONDB / name
    if not db_root.exists():
        raise HTTPException(404, f"Database '{name}' not found")

    try:
        meta = await asyncio.to_thread(create_backup, db_root, name, req.label)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))

    # Prune old backups if keep_count is configured
    if entry:
        keep_count = entry.get("backup", {}).get("keep_count", 0)
        if entry.get("backup", {}).get("enabled") and keep_count > 0:
            from .backup import prune_backups
            await asyncio.to_thread(prune_backups, db_root, keep_count)

    return meta


@router.get("/databases/{name}/backups")
async def list_backups_route(name: str):
    """List all backups for a named database, newest first."""
    from .backup import list_backups
    from .db_registry import get_db

    if not _SAFE_DB_RE.match(name):
        raise HTTPException(400, f"Invalid database name {name!r}")

    entry   = get_db(name)
    db_root = Path(entry["path"]) if entry else AETHVIONDB / name
    backups = await asyncio.to_thread(list_backups, db_root)
    return {"backups": backups}


@router.post("/databases/{name}/backups/{backup_id}/restore")
async def restore_backup_route(name: str, backup_id: str):
    """Restore a backup, replacing the current database contents."""
    from .backup import restore_backup
    from .db_registry import get_db

    if not _SAFE_DB_RE.match(name):
        raise HTTPException(400, f"Invalid database name {name!r}")

    entry   = get_db(name)
    db_root = Path(entry["path"]) if entry else AETHVIONDB / name

    try:
        result = await asyncio.to_thread(restore_backup, db_root, backup_id)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))

    return result


@router.delete("/databases/{name}/backups/{backup_id}")
async def delete_backup_route(name: str, backup_id: str):
    """Delete a specific backup."""
    from .backup import delete_backup
    from .db_registry import get_db

    if not _SAFE_DB_RE.match(name):
        raise HTTPException(400, f"Invalid database name {name!r}")

    entry   = get_db(name)
    db_root = Path(entry["path"]) if entry else AETHVIONDB / name
    deleted = await asyncio.to_thread(delete_backup, db_root, backup_id)
    if not deleted:
        raise HTTPException(404, f"Backup '{backup_id}' not found")
    return {"deleted": backup_id}


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
    # Exclude soft-deleted entities — they are tombstones on disk but carry no
    # useful information and should not inflate any user-visible count.
    all_e  = writer.list_all(include_deleted=False)

    by_type:   dict[str, int] = {}
    by_status: dict[str, int] = {}
    for e in all_e:
        t = e.get("type", "other"); s = e.get("status", "active")
        by_type[t]   = by_type.get(t, 0) + 1
        by_status[s] = by_status.get(s, 0) + 1

    # Total size of *active* entity files — reads only OS metadata, not file contents
    total_size_bytes = 0
    active_ids = {e["id"] for e in all_e}
    entities_dir = _db_root(db, path) / "entities"
    if entities_dir.exists():
        for f in entities_dir.iterdir():
            if f.suffix == ".json" and f.stem in active_ids:
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
    entity_id:       str,
    req:             UpdateEntityRequest,
    db:              str  = Query("default"),
    path:            Optional[str] = Query(None),
    replace_sections: bool = Query(False, description="When true, replace sections instead of merging"),
):
    writer = _get_writer(db, path)
    if not writer.exists(entity_id):
        raise HTTPException(404, f"Entity '{entity_id}' not found")
    return writer.update(entity_id, req.mutations, merge_sections=not replace_sections)


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


# ── Import ───────────────────────────────────────────────────────────────────

@router.post("/import")
async def import_entities_route(
    req:  ImportRequest,
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """
    Import entities from a baked .jsonl / .json file or a raw entity JSON.
    Accepts the file content as a string in the request body.
    """
    from .importer import import_entities
    root   = _db_root(db, path)
    _ensure_db(root)
    writer = _get_writer(db, path)
    index  = _get_index(db, path)
    result = await asyncio.to_thread(
        import_entities,
        writer, index,
        req.content, req.filename, req.conflict_mode, req.source,
    )
    if result.get("status") == "error":
        raise HTTPException(400, result["error"])
    return result


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


@router.post("/entities/{entity_id}/expand/preview")
async def preview_expand_single(
    entity_id: str,
    model:     Optional[str] = Query(None),
    db:        str = Query("default"),
    path:      Optional[str] = Query(None),
):
    """Generate an expansion preview for a stub entity WITHOUT writing it."""
    from .expansion_engine import ExpansionEngine
    engine = ExpansionEngine(writer=_get_writer(db, path), index=_get_index(db, path))
    result = await engine.preview_expand_stub(entity_id, model=model)
    if result.get("error"):
        raise HTTPException(500, result["error"])
    return result


@router.post("/entities/{entity_id}/expand/apply")
async def apply_expand_single(
    entity_id: str,
    req:       ApplyExpandRequest,
    db:        str = Query("default"),
    path:      Optional[str] = Query(None),
):
    """Apply a previously previewed expansion to a stub entity."""
    from .expansion_engine import ExpansionEngine
    engine = ExpansionEngine(writer=_get_writer(db, path), index=_get_index(db, path))
    result = await engine.apply_expand_preview(entity_id, req.proposed)
    if not result["success"]:
        raise HTTPException(500, result.get("error", "Apply failed"))
    return result


@router.post("/entities/{entity_id}/deepen/preview")
async def preview_deepen_entity(
    entity_id: str,
    max_stubs: int = Query(5, le=20),
    model:     Optional[str] = Query(None),
    db:        str = Query("default"),
    path:      Optional[str] = Query(None),
):
    """Preview deepening the sub-topics of an active entity WITHOUT writing."""
    from .expansion_engine import ExpansionEngine
    engine = ExpansionEngine(writer=_get_writer(db, path), index=_get_index(db, path))
    result = await engine.preview_deepen_stubs_for(entity_id, max_stubs=max_stubs, model=model)
    if result.get("error"):
        raise HTTPException(500, result["error"])
    return result


@router.post("/entities/{entity_id}/deepen/apply")
async def apply_deepen_entity(
    entity_id: str,
    req:       ApplyDeepenRequest,
    db:        str = Query("default"),
    path:      Optional[str] = Query(None),
):
    """Apply selected previewed stub expansions for an active entity."""
    from .expansion_engine import ExpansionEngine
    engine = ExpansionEngine(writer=_get_writer(db, path), index=_get_index(db, path))
    result = await engine.apply_deepen_previews(entity_id, req.previews)
    return result


# ── Validation ────────────────────────────────────────────────────────────────

@router.get("/validate")
async def validate_all(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    summary = await asyncio.to_thread(_get_validator(db, path).summary)
    return summary


@router.post("/validate/fix-status-mismatches")
async def fix_status_mismatches(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """
    Promote every entity that is marked 'stub' but already has a non-empty
    summary to 'active'.  Returns the list of fixed entity IDs.
    """
    writer = _get_writer(db, path)
    fixed: list[dict[str, str]] = []
    for entity in writer.list_all():
        if entity.get("status") == "stub" and entity["sections"]["core"].get("summary"):
            writer.update(entity["id"], {"status": "active"})
            fixed.append({"id": entity["id"], "name": entity.get("name", entity["id"])})
    logger.info(f"[AethvionDB] fix-status-mismatches: promoted {len(fixed)} entities to active")
    return {"fixed": len(fixed), "entities": fixed}


class _DuplicateFixBody(BaseModel):
    primary_id:  str
    remove_ids:  list[str]
    merge:       bool = True   # copy content from losers into winner before removing


@router.post("/validate/fix-duplicates")
async def fix_duplicates(
    body: _DuplicateFixBody,
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """
    Resolve a duplicate-entity cluster.

    1. Optionally merge content from ``remove_ids`` entities into ``primary_id``.
    2. Rewrite every relation / timeline reference that points at a removed entity
       to point at the primary instead.
    3. Remap every removed entity's name and aliases in the NameIndex to the
       primary ID so future look-ups still resolve correctly.
    4. Soft-delete each removed entity.
    """
    def _run():
        writer = _get_writer(db, path)
        index  = _get_index(db, path)
        remove_set = set(body.remove_ids)

        primary = writer.get(body.primary_id)
        if not primary:
            raise HTTPException(404, f"Primary entity {body.primary_id!r} not found")

        merged_count = 0

        # ── 1. Merge content from losers into winner ──────────────────────────
        if body.merge:
            for rid in body.remove_ids:
                removed = writer.get(rid)
                if not removed:
                    continue

                r_sections = removed.get("sections", {})
                p_sections = primary.get("sections", {})
                r_core     = r_sections.get("core", {})
                p_core     = p_sections.get("core", {})

                mutations: dict[str, Any] = {"sections": {}}

                # Summary — take remove's if primary is empty
                if not p_core.get("summary") and r_core.get("summary"):
                    mutations["sections"].setdefault("core", {})["summary"] = r_core["summary"]

                # Aliases — add remove entity's primary name + its aliases
                p_aliases   = set(p_core.get("aliases", []))
                new_aliases = list(p_aliases)
                for candidate in [removed.get("name", ""), *r_core.get("aliases", [])]:
                    if candidate and candidate != primary.get("name") and candidate not in p_aliases:
                        new_aliases.append(candidate)
                        p_aliases.add(candidate)
                if new_aliases != list(p_core.get("aliases", [])):
                    mutations["sections"].setdefault("core", {})["aliases"] = new_aliases

                # Timeline, relations, properties — writer.update deduplicates lists
                for sec in ("timeline", "relations"):
                    if r_sections.get(sec):
                        mutations["sections"][sec] = r_sections[sec]
                r_props = r_sections.get("properties") or {}
                p_props = p_sections.get("properties") or {}
                new_props = {k: v for k, v in r_props.items() if k not in p_props}
                if new_props:
                    mutations["sections"]["properties"] = new_props

                if mutations["sections"]:
                    primary = writer.update(body.primary_id, mutations)
                    merged_count += 1

        # ── 2. Rewrite references in every other entity ───────────────────────
        ref_updates = 0
        for entity in writer.list_all(include_deleted=True):
            eid = entity["id"]
            if eid == body.primary_id or eid in remove_set:
                continue

            sections   = entity.get("sections", {})
            changed    = False
            new_rels   = []

            for rel in sections.get("relations", []):
                if isinstance(rel, dict) and rel.get("target_id") in remove_set:
                    rel     = {**rel, "target_id": body.primary_id}
                    changed = True
                new_rels.append(rel)

            new_timeline = []
            for ev in sections.get("timeline", []):
                if isinstance(ev, dict):
                    old_refs = ev.get("ref_ids", [])
                    new_refs = [body.primary_id if r in remove_set else r for r in old_refs]
                    if new_refs != old_refs:
                        ev      = {**ev, "ref_ids": new_refs}
                        changed = True
                new_timeline.append(ev)

            if changed:
                mutations = {"sections": {}}
                if new_rels     != sections.get("relations", []):
                    mutations["sections"]["relations"] = new_rels
                if new_timeline != sections.get("timeline", []):
                    mutations["sections"]["timeline"]  = new_timeline
                writer.update(eid, mutations, merge_sections=False)
                ref_updates += 1

        # ── 3. Remap NameIndex entries & soft-delete losers ───────────────────
        for rid in body.remove_ids:
            removed = writer.get(rid)
            if removed:
                r_name    = removed.get("name", "")
                r_aliases = removed.get("sections", {}).get("core", {}).get("aliases", [])
                if r_name:
                    index.register(r_name, body.primary_id)
                if r_aliases:
                    index.register_aliases(body.primary_id, r_aliases)
            writer.delete(rid, soft=True)

        logger.info(
            f"[AethvionDB] fix-duplicates: kept={body.primary_id} "
            f"removed={body.remove_ids} merged={merged_count} refs={ref_updates}"
        )
        return {
            "primary_id":  body.primary_id,
            "removed":     body.remove_ids,
            "merged":      merged_count,
            "ref_updates": ref_updates,
        }

    return await asyncio.to_thread(_run)


@router.post("/validate/fix-orphan-stubs")
async def fix_orphan_stubs(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """
    Soft-delete all stub entities that have no outgoing relations and are
    not referenced by any other entity (via relations or timeline ref_ids).

    These are empty placeholder stubs that carry no useful information and
    are fully disconnected from the knowledge graph.

    Returns {fixed: N, entities: [{id, name}]}.
    """
    def _run():
        writer = _get_writer(db, path)
        all_entities = writer.list_all()

        # Build the set of all entity IDs referenced by others
        referenced_ids: set[str] = set()
        for entity in all_entities:
            for rel in entity.get("sections", {}).get("relations", []):
                if isinstance(rel, dict) and rel.get("target_id"):
                    referenced_ids.add(rel["target_id"])
            for ev in entity.get("sections", {}).get("timeline", []):
                if isinstance(ev, dict):
                    for ref_id in ev.get("ref_ids", []):
                        referenced_ids.add(ref_id)

        fixed: list[dict[str, str]] = []
        for entity in all_entities:
            if entity.get("status") != "stub":
                continue
            has_outgoing  = bool(entity.get("sections", {}).get("relations", []))
            is_referenced = entity["id"] in referenced_ids
            if not has_outgoing and not is_referenced:
                writer.delete(entity["id"], soft=True)
                fixed.append({"id": entity["id"], "name": entity.get("name", entity["id"])})

        logger.info(f"[AethvionDB] fix-orphan-stubs: removed {len(fixed)} orphan stubs")
        return {"fixed": len(fixed), "entities": fixed}

    return await asyncio.to_thread(_run)


@router.post("/validate/purge-deleted")
async def purge_deleted(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """
    Permanently remove all soft-deleted entity files from disk and unregister
    their names/aliases from the NameIndex.  This is irreversible — use with care.

    Returns {purged: N, entities: [{id, name}]}.
    """
    def _run():
        writer = _get_writer(db, path)
        index  = _get_index(db, path)

        purged: list[dict[str, str]] = []
        for entity in writer.list_all(include_deleted=True):
            if entity.get("status") != "deleted":
                continue
            eid     = entity["id"]
            name    = entity.get("name", "")
            aliases = entity.get("sections", {}).get("core", {}).get("aliases", [])

            # Remove name and all aliases from the NameIndex so future
            # look-ups don't resolve to a file that no longer exists.
            if name:
                index.unregister(name)
            for alias in aliases:
                index.unregister(alias)

            # Hard-delete: remove the file from disk
            writer.delete(eid, soft=False)
            purged.append({"id": eid, "name": name})

        logger.info(f"[AethvionDB] purge-deleted: permanently removed {len(purged)} entities")
        return {"purged": len(purged), "entities": purged}

    return await asyncio.to_thread(_run)


@router.post("/validate/fix-timeline-sort")
async def fix_timeline_sort(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """
    Sort each entity's timeline events into chronological order by parsed year.
    Events with unparseable or missing dates are moved to the end, preserving
    their relative order.  Only entities whose timeline ordering actually changes
    are written.

    Returns {fixed: N, events_sorted: M} where N is entities reordered and
    M is the total number of events across those entities.
    """
    def _run():
        from .validator import _parse_year
        writer = _get_writer(db, path)
        fixed         = 0
        events_sorted = 0
        for entity in writer.list_all():
            timeline = entity.get("sections", {}).get("timeline", [])
            if len(timeline) < 2:
                continue
            def _sort_key(ev, _py=_parse_year):
                if not isinstance(ev, dict):
                    return (1, 0)
                yr = _py(ev.get("date", ""))
                return (0, yr) if yr is not None else (1, 0)
            sorted_tl = sorted(timeline, key=_sort_key)
            if sorted_tl != timeline:
                writer.update(
                    entity["id"],
                    {"sections": {"timeline": sorted_tl}},
                    merge_sections=False,
                )
                fixed         += 1
                events_sorted += len(sorted_tl)
        logger.info(
            f"[AethvionDB] fix-timeline-sort: reordered {fixed} entities "
            f"({events_sorted} total events)"
        )
        return {"fixed": fixed, "events_sorted": events_sorted}

    return await asyncio.to_thread(_run)


@router.post("/validate/fix-broken-relations")
async def fix_broken_relations(
    db:        str           = Query("default"),
    path:      Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
):
    """
    Remove every relation (and timeline ref_id) whose target does not exist.

    When *entity_id* is supplied only that entity is repaired; otherwise the
    entire store is scanned.

    Returns {fixed: N, removed_relations: M, entities: [{id, name, removed}]}.
    """
    def _run():
        writer   = _get_writer(db, path)
        entities = ([writer.get(entity_id)] if entity_id else writer.list_all())
        entities = [e for e in entities if e]

        fixed:            list[dict] = []
        total_removed:    int        = 0

        for entity in entities:
            eid       = entity["id"]
            sections  = entity.get("sections", {})
            relations = sections.get("relations", [])
            timeline  = sections.get("timeline",  [])

            # ── Relations ─────────────────────────────────────────────────────
            clean_rels   = [
                rel for rel in relations
                if not isinstance(rel, dict)
                or not rel.get("target_id")
                or writer.exists(rel["target_id"])
            ]
            removed_rels = len(relations) - len(clean_rels)

            # ── Timeline ref_ids ──────────────────────────────────────────────
            clean_timeline = []
            removed_refs   = 0
            for ev in timeline:
                if not isinstance(ev, dict):
                    clean_timeline.append(ev)
                    continue
                ref_ids      = ev.get("ref_ids", [])
                clean_refs   = [r for r in ref_ids if not r or writer.exists(r)]
                removed_refs += len(ref_ids) - len(clean_refs)
                if len(clean_refs) != len(ref_ids):
                    ev = {**ev, "ref_ids": clean_refs}
                clean_timeline.append(ev)

            total_removed_here = removed_rels + removed_refs
            if total_removed_here == 0:
                continue

            # Build section patch — only include changed sections
            patch: dict = {}
            if removed_rels:
                patch["relations"] = clean_rels
            if removed_refs:
                patch["timeline"]  = clean_timeline

            writer.update(eid, {"sections": patch}, merge_sections=False)
            total_removed += total_removed_here
            fixed.append({
                "id":      eid,
                "name":    entity.get("name", eid),
                "removed": total_removed_here,
            })

        logger.info(
            f"[AethvionDB] fix-broken-relations: "
            f"repaired {len(fixed)} entities, removed {total_removed} broken references"
        )
        return {
            "fixed":             len(fixed),
            "removed_relations": total_removed,
            "entities":          fixed,
        }

    return await asyncio.to_thread(_run)


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
    chunk_id:  Optional[str] = Query(None, description="Restrict graph to entities in this chunk"),
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
    elif chunk_id:
        # Restrict graph to the entities belonging to a specific chunk
        from .chunker import get_chunk
        root  = _db_root(db, path)
        chunk = await asyncio.to_thread(get_chunk, root, chunk_id)
        if chunk:
            included = set(chunk["entity_ids"])
        else:
            included = {e["id"] for e in all_e[:limit]}
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
            "summary":   core.get("summary", "")[:200],
            "tags":      core.get("tags", [])[:8],
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
            # Dedup directed edges — (source, target, kind) so A→B and B→A
            # with the same kind are both preserved as distinct edges.
            key = (e["id"], tid, kind)
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
    folder:      str = Query(..., description="Absolute path to the source folder"),
    model:       str = Query("auto"),
    concurrency: int = Query(1, ge=1, le=16, description="Files to distil in parallel"),
    db:          str = Query("default"),
    path:        Optional[str] = Query(None),
):
    """
    Start distilling a folder from scratch.
    Scans the folder in a thread (non-blocking), then launches a background task.
    ``concurrency`` controls how many files are distilled simultaneously.
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
        prepare_start_job, root, folder, model, "folder_distill", concurrency
    )

    # Event must be created from the async context so it belongs to the running loop
    ev = asyncio.Event()
    ev.set()                       # set = not paused = running
    _pause_events[key] = ev

    writer = _get_writer(db, path)
    index  = _get_index(db, path)

    task = asyncio.create_task(
        run_distill_job(root, writer, index, model, "folder_distill", concurrency)
    )
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

    model       = info.get("model",       "auto")
    source      = info.get("source",      "folder_distill")
    concurrency = info.get("concurrency", 1)

    ev = asyncio.Event()
    ev.set()
    _pause_events[key] = ev

    writer = _get_writer(db, path)
    index  = _get_index(db, path)

    task = asyncio.create_task(run_distill_job(root, writer, index, model, source, concurrency))
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


@router.get("/vectors/models")
async def list_vector_models(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """
    Scan all entities and return the unique embedding model names found
    in their sections.vectors, plus per-model entity counts.

    Cheap to call — embeddings are not loaded, only the keys of the
    vectors dict are inspected (plus a truthiness check for the value).

    Response
    --------
    {
        "models": ["model-a", ...],          # sorted alphabetically
        "counts": {"model-a": 125, ...}      # entities that have a non-empty vector
    }
    """
    writer = _get_writer(db, path)
    model_counts: dict[str, int] = {}
    for entity in writer.list_all(include_deleted=False):
        vecs = (entity.get("sections") or {}).get("vectors", {})
        for model_name, vec in vecs.items():
            if vec:  # non-empty vector list — skip placeholder nulls
                model_counts[model_name] = model_counts.get(model_name, 0) + 1
    sorted_models = sorted(model_counts.keys())
    return {
        "models": sorted_models,
        "counts": {m: model_counts[m] for m in sorted_models},
    }


@router.post("/vectors/cancel")
async def cancel_vectorize_endpoint(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    from .vectorizer import cancel_vectorize
    return cancel_vectorize(_db_root(db, path))


# ── Bake ──────────────────────────────────────────────────────────────────────

class BakeRequest(BaseModel):
    name:            str       = "default"
    format:          str       = "jsonl"
    include_stubs:   bool      = True
    include_vectors: bool      = False
    vector_models:   list[str] = []        # empty = all models; non-empty = only those keys


class RenameRequest(BaseModel):
    new_name: str


@router.get("/bake/status")
async def get_bake_status(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Return the status of the currently running bake, or idle."""
    from .baker import is_baking, current_bake_name, read_bake_meta
    root = _db_root(db, path)
    name = current_bake_name(root)
    if name:
        meta = read_bake_meta(root, name)
        return {**meta, "is_baking": True}
    return {"status": "idle", "is_baking": False}


@router.post("/bake/open-folder")
async def open_bake_folder(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Open the baked/ folder in the OS file manager."""
    import subprocess, sys
    from .baker import bake_dir
    folder = bake_dir(_db_root(db, path))
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == "win32":
            import os; os.startfile(str(folder))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
        return {"opened": str(folder)}
    except Exception as e:
        raise HTTPException(500, f"Could not open folder: {e}")


@router.get("/bake/list")
async def list_bakes_endpoint(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Return all named bakes for this database, newest first."""
    from .baker import list_bakes
    return {"bakes": list_bakes(_db_root(db, path))}


@router.post("/bake")
async def start_bake(
    req:  BakeRequest,
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Start a named bake in the background. Poll /bake/status for progress."""
    from .baker import (
        _bake_tasks, _bake_current_name, bake_database, is_baking, BAKE_FORMATS, safe_name,
    )
    root = _db_root(db, path)
    key  = str(root)

    if is_baking(root):
        raise HTTPException(409, "A bake is already running for this database.")
    if req.format not in BAKE_FORMATS:
        raise HTTPException(400, f"Unknown format {req.format!r}. Must be one of {BAKE_FORMATS}")
    if not safe_name(req.name):
        raise HTTPException(400, "Bake name must be 1-64 chars: letters, digits, _ or -")

    writer = _get_writer(db, path)
    _bake_current_name[key] = req.name

    task = asyncio.create_task(
        bake_database(
            root, writer,
            name=req.name,
            fmt=req.format,
            include_stubs=req.include_stubs,
            include_vectors=req.include_vectors,
            vector_models=req.vector_models or None,
        )
    )
    _bake_tasks[key] = task
    task.add_done_callback(lambda _: (_bake_tasks.pop(key, None), _bake_current_name.pop(key, None)))

    return {"started": True, "name": req.name, "format": req.format}


@router.delete("/bake/{name}")
async def delete_bake_endpoint(
    name: str,
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    from .baker import delete_bake, is_baking, current_bake_name
    root = _db_root(db, path)
    if is_baking(root) and current_bake_name(root) == name:
        raise HTTPException(409, f"Bake {name!r} is currently running — cancel it first.")
    if not delete_bake(root, name):
        raise HTTPException(404, f"Bake {name!r} not found.")
    return {"deleted": name}


@router.patch("/bake/{name}")
async def rename_bake_endpoint(
    name: str,
    req:  RenameRequest,
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    from .baker import rename_bake, safe_name
    if not safe_name(req.new_name):
        raise HTTPException(400, "New name must be 1-64 chars: letters, digits, _ or -")
    if not rename_bake(_db_root(db, path), name, req.new_name):
        raise HTTPException(404, f"Bake {name!r} not found.")
    return {"renamed": True, "old_name": name, "new_name": req.new_name}


@router.get("/bake/{name}/download")
async def download_bake(
    name: str,
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    from fastapi.responses import FileResponse
    from .baker import read_bake_meta
    root = _db_root(db, path)
    meta = read_bake_meta(root, name)
    if not meta or meta.get("status") != "done":
        raise HTTPException(404, f"Bake {name!r} not found or not completed.")
    out_path = Path(meta["output_path"])
    if not out_path.exists():
        raise HTTPException(404, f"Baked file missing: {out_path.name}")
    media = {
        "jsonl":    "application/x-ndjson",
        "json":     "application/json",
        "markdown": "text/markdown",
        "txt":      "text/plain",
    }.get(meta.get("format", ""), "application/octet-stream")
    return FileResponse(path=str(out_path), media_type=media, filename=out_path.name)


# ── Chunks ───────────────────────────────────────────────────────────────────

class ChunkSearchRequest(BaseModel):
    query:    str
    chunk_id: Optional[str] = None
    top_k:    int           = 20


@router.post("/chunks/build")
async def build_chunks_endpoint(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Build (or rebuild) the smart chunk manifest and per-chunk inverted index files."""
    from .chunker import build_chunks
    root   = _db_root(db, path)
    writer = _get_writer(db, path)
    result = await asyncio.to_thread(build_chunks, root, writer)
    return result


@router.get("/chunks")
async def list_chunks_endpoint(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Return the chunk manifest (chunk list + build metadata)."""
    from .chunker import read_manifest
    manifest = read_manifest(_db_root(db, path))
    if not manifest:
        return {"chunks": [], "built_at": None, "entity_count": 0, "chunk_count": 0}
    return manifest


@router.get("/chunks/{chunk_id}")
async def get_chunk_endpoint(
    chunk_id:      str,
    include_index: bool = Query(False, description="Include the full inverted index in the response"),
    db:            str  = Query("default"),
    path:          Optional[str] = Query(None),
):
    """Return entity IDs (and optionally the inverted index) for one chunk."""
    from .chunker import get_chunk
    chunk = await asyncio.to_thread(get_chunk, _db_root(db, path), chunk_id)
    if not chunk:
        raise HTTPException(404, f"Chunk {chunk_id!r} not found. Run /chunks/build first.")
    if not include_index:
        chunk = {k: v for k, v in chunk.items() if k != "index"}
    return chunk


@router.post("/chunks/search")
async def search_chunks_endpoint(
    req:  ChunkSearchRequest,
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """BM25-style full-text search across one chunk or all chunks."""
    from .chunker import search_chunks
    results = await asyncio.to_thread(
        search_chunks, _db_root(db, path), req.query, req.chunk_id, req.top_k
    )
    return {"results": results, "total": len(results), "query": req.query}


# ── Speed benchmark ───────────────────────────────────────────────────────────

@router.get("/benchmark")
async def run_benchmark(
    db:        str = Query("default"),
    path:      Optional[str] = Query(None),
    query:     str = Query("a",  description="Name / keyword to use for search benchmarks"),
    bakes:     str = Query("",   description="Comma-separated bake names to test. Empty = first available JSONL bake."),
    vec_model: str = Query("",   description="Embedding model for vector search test. Empty = skip."),
):
    """
    Time common database operations and return the results.

    Order: raw files → chunk index → vector search (optional) → baked snapshots.
    All tests run sequentially; timings are isolated wall-clock measurements.
    """
    import math as _math
    import time as _time
    from .baker import list_bakes, bake_output_path
    from .chunker import read_manifest, search_chunks

    results: list[dict] = []
    root    = _db_root(db, path)
    writer  = _get_writer(db, path)
    q_lower = query.lower()

    # ── 1. Load all entities (raw) ────────────────────────────────────────────
    t0    = _time.perf_counter()
    all_e = writer.list_all(include_deleted=False)
    results.append({
        "category": "raw",
        "test":     "Load all entities",
        "ms":       round((_time.perf_counter() - t0) * 1000, 2),
        "note":     f"{len(all_e)} entities",
    })

    # Build a fast id→entity map for resolving chunk/vector hit names
    entity_map: dict[str, dict] = {e["id"]: e for e in all_e}

    # ── 2. Get entity by ID (raw) ─────────────────────────────────────────────
    sample_id = all_e[0]["id"] if all_e else None
    if sample_id:
        t0 = _time.perf_counter()
        writer.get(sample_id)
        results.append({
            "category": "raw",
            "test":     "Get by ID",
            "ms":       round((_time.perf_counter() - t0) * 1000, 2),
            "note":     f"id={sample_id[:8]}…",
        })

    # ── 3. Name search (raw) ──────────────────────────────────────────────────
    t0           = _time.perf_counter()
    name_matches = [e for e in all_e if q_lower in e.get("name", "").lower()]
    results.append({
        "category": "raw",
        "test":     "Name search",
        "ms":       round((_time.perf_counter() - t0) * 1000, 2),
        "note":     f"{len(name_matches)} match(es) for '{query}'",
        "matches":  [{"id": e["id"], "name": e.get("name", ""), "type": e.get("type", "other")}
                     for e in name_matches[:20]],
        "total_matches": len(name_matches),
    })

    # ── 4. Chunk index search ─────────────────────────────────────────────────
    manifest = read_manifest(root)
    if manifest:
        t0         = _time.perf_counter()
        chunk_hits = search_chunks(root, query, top_k=20)
        chunk_ms   = round((_time.perf_counter() - t0) * 1000, 2)
        results.append({
            "category": "chunks",
            "test":     "Chunk index search",
            "ms":       chunk_ms,
            "note":     f"{len(chunk_hits)} match(es) for '{query}' across {manifest.get('chunk_count', '?')} chunks",
            "matches":  [{"id":    h["entity_id"],
                          "name":  entity_map.get(h["entity_id"], {}).get("name", h["entity_id"]),
                          "type":  entity_map.get(h["entity_id"], {}).get("type", "other"),
                          "score": h["score"]}
                         for h in chunk_hits],
            "total_matches": len(chunk_hits),
        })
    else:
        results.append({
            "category": "chunks",
            "test":     "Chunk index search",
            "ms":       None,
            "note":     "No chunks built — use Smart Chunks in the Tools tab",
        })

    # ── 5. Vector search (optional) ───────────────────────────────────────────
    if vec_model:
        from .vectorizer import _embed, EMBEDDING_MODELS

        def _cosine(a: list, b: list) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            na  = _math.sqrt(sum(x * x for x in a))
            nb  = _math.sqrt(sum(y * y for y in b))
            return dot / (na * nb) if na and nb else 0.0

        if vec_model not in EMBEDDING_MODELS:
            results.append({
                "category": "vectors",
                "test":     f"Vector search ({vec_model})",
                "ms":       None,
                "note":     "Unknown embedding model",
            })
        else:
            t0 = _time.perf_counter()
            try:
                query_vec = await _embed(query, vec_model)
                scored: list[tuple[float, str]] = []
                for e in all_e:
                    vecs  = (e.get("sections") or {}).get("vectors", {})
                    vdata = vecs.get(vec_model)
                    emb   = vdata.get("embedding") if isinstance(vdata, dict) else None
                    if emb:
                        scored.append((_cosine(query_vec, emb), e.get("id", "")))
                scored.sort(key=lambda x: x[0], reverse=True)
                embed_ms = round((_time.perf_counter() - t0) * 1000, 2)
                top20 = scored[:20]
                results.append({
                    "category": "vectors",
                    "test":     f"Semantic search ({vec_model})",
                    "ms":       embed_ms,
                    "note":     f"{len(scored)} entities searched · includes API embed latency",
                    "matches":  [{"id":    eid,
                                  "name":  entity_map.get(eid, {}).get("name", eid),
                                  "type":  entity_map.get(eid, {}).get("type", "other"),
                                  "score": round(sc, 4)}
                                 for sc, eid in top20],
                    "total_matches": len(scored),
                })
            except Exception as exc:
                results.append({
                    "category": "vectors",
                    "test":     f"Semantic search ({vec_model})",
                    "ms":       None,
                    "note":     f"Error: {exc}",
                })

    # ── 6+. Baked snapshot tests ──────────────────────────────────────────────
    all_bakes     = list_bakes(root)
    bake_name_map = {b["name"]: b for b in all_bakes if b.get("status") == "done"}

    requested_names: list[str] = [n.strip() for n in bakes.split(",") if n.strip()]
    if not requested_names:
        first_jsonl = next((b for b in all_bakes if b.get("format") == "jsonl" and b.get("status") == "done"), None)
        if first_jsonl:
            requested_names = [first_jsonl["name"]]

    if requested_names:
        for bake_name in requested_names:
            meta = bake_name_map.get(bake_name)
            if not meta:
                results.append({
                    "category": f"bake:{bake_name}",
                    "test":     "Load bake",
                    "ms":       None,
                    "note":     "Bake not found or not completed",
                })
                continue

            bake_path = Path(meta.get("output_path", ""))
            if not bake_path.exists():
                results.append({
                    "category": f"bake:{bake_name}",
                    "test":     "Load bake",
                    "ms":       None,
                    "note":     "Output file missing — re-bake first",
                })
                continue

            fmt         = meta.get("format", "jsonl")
            t0          = _time.perf_counter()
            raw_content = bake_path.read_text(encoding="utf-8")

            if fmt == "jsonl":
                bake_entities = [json.loads(l) for l in raw_content.splitlines() if l.strip()]
            elif fmt == "json":
                bake_entities = json.loads(raw_content).get("entities", [])
            else:
                bake_entities = []

            load_ms      = round((_time.perf_counter() - t0) * 1000, 2)
            entity_info  = f"{len(bake_entities)} entities" if bake_entities else meta.get("size_fmt", "")
            vectors_info = " · vectors" if meta.get("include_vectors") else ""
            results.append({
                "category": f"bake:{bake_name}",
                "test":     "Load snapshot",
                "ms":       load_ms,
                "note":     f"{entity_info} — {fmt}{vectors_info} · {meta.get('size_fmt', '?')}",
            })

            if bake_entities:
                t0         = _time.perf_counter()
                bk_matches = [e for e in bake_entities if q_lower in e.get("name", "").lower()]
                results.append({
                    "category":     f"bake:{bake_name}",
                    "test":         "Name search",
                    "ms":           round((_time.perf_counter() - t0) * 1000, 2),
                    "note":         f"{len(bk_matches)} match(es) for '{query}'",
                    "matches":      [{"name": e.get("name", ""), "type": e.get("type", "other")}
                                     for e in bk_matches[:20]],
                    "total_matches": len(bk_matches),
                })
    else:
        results.append({
            "category": "baked",
            "test":     "Baked snapshot",
            "ms":       None,
            "note":     "No bakes configured — run a bake first",
        })

    return {
        "db":        db,
        "path":      path,
        "query":     query,
        "bakes":     requested_names,
        "vec_model": vec_model,
        "results":   results,
    }


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
