"""
core/project_mapper/routes.py
FastAPI routes for the ProjectMapper module.

Prefix: /api/project-mapper
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.utils.logger import get_logger
from core.utils.paths import AETHVIONDB

from .scanner import (
    scan_folder_preview,
    scan_status,
    start_scan,
    cancel_scan,
    is_running,
    SCANINFO,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/project-mapper", tags=["project-mapper"])


# ---------------------------------------------------------------------------
# Helpers  (mirrors aethviondb_routes.py patterns)
# ---------------------------------------------------------------------------

import re
_SAFE_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


def _db_root(db: str = "default", path: Optional[str] = None) -> Path:
    if path:
        return Path(path)
    if not _SAFE_RE.match(db):
        raise HTTPException(400, f"Invalid database name {db!r}")
    from core.aethviondb.db_registry import resolve_db_root
    return resolve_db_root(db)


def _get_writer(db: str = "default", path: Optional[str] = None):
    from core.aethviondb.entity_writer import EntityWriter
    from core.aethviondb.name_index import NameIndex
    root  = _db_root(db, path)
    index = NameIndex(index_path=root / "name_index.json")
    return EntityWriter(entities_dir=root / "entities", index=index)


def _get_index(db: str = "default", path: Optional[str] = None):
    from core.aethviondb.name_index import NameIndex
    root = _db_root(db, path)
    return NameIndex(index_path=root / "name_index.json")


def _get_file_manifest(db: str = "default", path: Optional[str] = None):
    from core.aethviondb.file_manifest import FileManifest
    return FileManifest(_db_root(db, path))


def _ensure_db(root: Path) -> None:
    (root / "entities").mkdir(parents=True, exist_ok=True)
    (root / "chunks").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    project_root: str                    # absolute path to the project directory
    db:           str = "default"        # target AethvionDB database name
    db_path:      Optional[str] = None   # custom db path (overrides db name)
    model:        Optional[str] = None   # AI model for LLM enrichment
    enrich:       bool = True            # run Phase 2 LLM enrichment
    concurrency:  int = 3                # parallel file processing
    incremental:  bool = True            # skip files with unchanged hashes


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/preview")
async def preview_project(
    project_root: str = Query(..., description="Absolute path to the project directory"),
):
    """
    Walk the project directory and count files by type — no scanning or entity creation.
    Use this before /scan to understand what will be processed.
    """
    try:
        result = await asyncio.to_thread(scan_folder_preview, project_root)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(400, str(exc))
    return result


@router.post("/scan")
async def start_project_scan(req: ScanRequest):
    """
    Start a background scan of the given project directory.
    Ingests the project structure into the specified AethvionDB database.

    - Phase 1 (always): Static AST analysis → creates module/class/function entities.
    - Phase 2 (if enrich=True): LLM enrichment → adds semantic summaries to modules.
    - If incremental=True: skips files whose hash matches the last scan.

    Returns immediately. Poll /scan/status for progress.
    """
    root = _db_root(req.db, req.db_path)
    _ensure_db(root)

    if is_running(root):
        raise HTTPException(409, "A scan is already running for this database. Cancel it first.")

    project_path = Path(req.project_root)
    if not project_path.exists():
        raise HTTPException(400, f"Project root does not exist: {req.project_root}")
    if not project_path.is_dir():
        raise HTTPException(400, f"Project root is not a directory: {req.project_root}")

    writer        = _get_writer(req.db, req.db_path)
    index         = _get_index(req.db, req.db_path)
    file_manifest = _get_file_manifest(req.db, req.db_path)

    started = start_scan(
        db_root=root,
        project_root=req.project_root,
        db_name=req.db,
        writer=writer,
        index=index,
        file_manifest=file_manifest,
        model=req.model,
        enrich=req.enrich,
        concurrency=max(1, min(req.concurrency, 8)),
        incremental=req.incremental,
    )

    if not started:
        raise HTTPException(409, "Could not start scan — another task may have started concurrently.")

    return {
        "status":       "started",
        "project_root": req.project_root,
        "db":           req.db,
        "enrich":       req.enrich,
        "incremental":  req.incremental,
    }


@router.get("/scan/status")
async def get_scan_status(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Return the current (or most recent) scan status and progress stats."""
    root = _db_root(db, path)
    return scan_status(root)


@router.post("/scan/cancel")
async def cancel_project_scan(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """Cancel the running scan for this database."""
    root = _db_root(db, path)
    return cancel_scan(root)


@router.get("/stats")
async def project_mapper_stats(
    db:   str = Query("default"),
    path: Optional[str] = Query(None),
):
    """
    Return a combined view: last scan info + file manifest stats +
    entity count breakdown by ProjectMapper-created types.
    """
    root   = _db_root(db, path)
    status = scan_status(root)

    fm_stats = _get_file_manifest(db, path).stats()

    writer = _get_writer(db, path)
    pm_types = {"module", "class", "function", "service", "endpoint", "model",
                "workflow", "config", "dependency", "decision", "goal", "constraint"}
    type_counts: dict[str, int] = {}
    total_pm_entities = 0
    try:
        for e in writer.list_all():
            t = e.get("type", "other")
            if t in pm_types:
                type_counts[t] = type_counts.get(t, 0) + 1
                total_pm_entities += 1
    except Exception:
        pass

    return {
        "last_scan":          status,
        "file_manifest":      fm_stats,
        "entity_counts":      type_counts,
        "total_pm_entities":  total_pm_entities,
    }


@router.post("/enrich")
async def enrich_unenriched_modules(
    db:          str = Query("default"),
    path:        Optional[str] = Query(None),
    model:       Optional[str] = Query(None),
    limit:       int = Query(20, le=100),
):
    """
    Run LLM enrichment on module entities that have no summary yet.
    Useful after a static-only scan (enrich=False) or to refresh stale entries.
    """
    from .ingestor import ProjectIngestor
    from .code_analyzer import analyze_python

    root          = _db_root(db, path)
    writer        = _get_writer(db, path)
    index         = _get_index(db, path)
    file_manifest = _get_file_manifest(db, path)

    ingestor = ProjectIngestor(
        db_root=root, writer=writer, index=index,
        file_manifest=file_manifest, model=model or "auto",
    )

    # Find module entities with no summary
    candidates = [
        e for e in writer.list_all()
        if e.get("type") == "module"
        and not e.get("sections", {}).get("core", {}).get("summary", "")
    ][:limit]

    enriched = 0
    errors:  list[str] = []
    for e in candidates:
        source_files = e.get("sections", {}).get("source_files", [])
        if not source_files:
            continue
        sf    = source_files[0]
        fpath = sf.get("path", "")
        if not fpath:
            continue
        try:
            content = await asyncio.to_thread(Path(fpath).read_text, encoding="utf-8", errors="replace")
            analysis = await asyncio.to_thread(analyze_python, fpath, content)
            ok = await ingestor.enrich_module(e["id"], analysis, model)
            if ok:
                enriched += 1
        except Exception as exc:
            errors.append(f"{fpath}: {exc}")

    return {"enriched": enriched, "candidates": len(candidates), "errors": errors}
