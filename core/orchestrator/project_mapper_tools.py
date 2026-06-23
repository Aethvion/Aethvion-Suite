"""
Aethvion Suite - Project Mapper integration
Gives the Code agent's autonomous loop direct, in-process access to Project
Mapper's knowledge-graph queries (pm_context, pm_find, pm_impact, pm_orphans,
pm_path) instead of relying solely on regex search_codebase.

No MCP, no HTTP server, no subprocess -- project_mapper's core/ layer is
built to be transport-agnostic (mcp/ and http/ are thin adapters over it),
so Suite just imports it as a library and reuses project_mapper's own,
already-tested MCP tool handlers directly. Any improvement to those handlers
in a future Project Mapper release benefits Suite automatically.

One workspace = one Project Mapper database, named from a stable hash of the
workspace path so reopening the same workspace reuses its existing index
across Suite restarts (the index is a snapshot file on disk, not in-memory
only).
"""

from __future__ import annotations

import hashlib
import re
import threading
from pathlib import Path
from typing import Any

from core.utils.logger import get_logger

logger = get_logger(__name__)

# project_mapper is an optional dependency at runtime -- if it isn't
# installed, every function below degrades to "unavailable" instead of
# crashing the agent loop. Checked once, lazily, on first use.
_IMPORT_ERROR: Exception | None = None
_CHECKED_IMPORT = False

_CONTEXTS: dict[str, Any] = {}  # workspace key -> project_mapper.mcp.tools.MCPContext
_CONTEXTS_LOCK = threading.Lock()

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")

TOOL_NAMES = ("pm_context", "pm_find", "pm_impact", "pm_orphans", "pm_path")


def _check_available() -> bool:
    global _IMPORT_ERROR, _CHECKED_IMPORT
    if _CHECKED_IMPORT:
        return _IMPORT_ERROR is None
    _CHECKED_IMPORT = True
    try:
        import project_mapper  # noqa: F401
    except Exception as exc:  # pragma: no cover -- environment-dependent
        _IMPORT_ERROR = exc
        logger.warning(f"[project_mapper_tools] project_mapper not importable: {exc}")
    return _IMPORT_ERROR is None


def _db_name_for(workspace: Path) -> str:
    """Stable, filesystem-safe database name derived from the workspace path."""
    resolved = str(workspace.resolve())
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:12]
    slug = _SAFE_NAME_RE.sub("-", workspace.name)[:24] or "workspace"
    return f"suite-{slug}-{digest}"


def _get_ctx(workspace: Path):
    """Return a cached project_mapper.mcp.tools.MCPContext for this workspace,
    constructing it on first use. Raises if project_mapper isn't installed --
    callers must check _check_available() first."""
    from project_mapper.db import snapshot as _snap
    from project_mapper.db.db_registry import resolve_db_root
    from project_mapper.db.file_manifest import FileManifest
    from project_mapper.db.pm_store import PMEntityStore, PMNameIndex
    from project_mapper.mcp.tools import MCPContext

    key = str(workspace.resolve())
    with _CONTEXTS_LOCK:
        ctx = _CONTEXTS.get(key)
        if ctx is not None:
            return ctx

        db_name = _db_name_for(workspace)
        db_root = resolve_db_root(db_name)
        db_root.mkdir(parents=True, exist_ok=True)

        index = PMNameIndex(index_path=db_root / "name_index.json")
        if _snap.snapshot_path(db_root).exists():
            writer = PMEntityStore.from_snapshot(db_root, index)
        else:
            writer = PMEntityStore(db_root, index)
        file_manifest = FileManifest(db_root)

        ctx = MCPContext(
            db_root=db_root,
            db_name=db_name,
            writer=writer,
            index=index,
            file_manifest=file_manifest,
            project_root=str(workspace.resolve()),
            scan_lock=threading.Lock(),
        )
        _CONTEXTS[key] = ctx
        return ctx


def ensure_scanned(workspace: Path) -> str:
    """Index (or incrementally refresh) the workspace. Safe and cheap to call
    at the start of every agent run: incremental=True means a brand-new
    database does a full scan (nothing cached to compare against yet) and
    every call after that only reprocesses changed files -- typically well
    under a second on a pre-indexed repo.

    Never raises. On any failure, returns a short error string and Project
    Mapper tools are simply unavailable for this run -- the agent falls back
    to search_codebase / read_file, exactly as if these actions didn't exist.
    """
    if not _check_available():
        return f"Project Mapper not installed ({_IMPORT_ERROR})"

    from project_mapper.mcp.tools import HANDLERS

    try:
        ctx = _get_ctx(workspace)
        return HANDLERS["pm_scan"](
            {"project_root": str(workspace.resolve()), "incremental": True, "concurrency": 4},
            ctx,
        )
    except Exception as exc:
        logger.warning(f"[project_mapper_tools] scan failed for {workspace}: {exc}")
        return f"Project Mapper indexing failed: {exc}"


def call_tool(name: str, workspace: Path, args: dict[str, Any]) -> str:
    """Call one of TOOL_NAMES against the given workspace's index. Returns a
    plain-text result formatted by project_mapper's own MCP tool handlers --
    never raises; tool-level errors come back as a string the agent can read
    and recover from, the same as every other ACTION handler in this loop."""
    if not _check_available():
        return f"[{name}] Project Mapper not installed ({_IMPORT_ERROR})"
    if name not in TOOL_NAMES:
        return f"[{name}] not a Project Mapper tool"

    from project_mapper.mcp.tools import HANDLERS

    try:
        ctx = _get_ctx(workspace)
        return HANDLERS[name](args, ctx)
    except ValueError as exc:
        return f"[{name}] {exc}"
    except Exception as exc:
        logger.warning(f"[project_mapper_tools] {name} failed: {exc}")
        return f"[{name}] error: {exc}"
