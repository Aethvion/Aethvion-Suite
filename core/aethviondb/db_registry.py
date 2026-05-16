"""
core/aethviondb/db_registry.py
════════════════════════════════
Lightweight path registry that bridges path-based databases (opened via the
legacy ?path= parameter) to the v1 API (which routes by name only).

Problem:
  The legacy API accepts ?path=<absolute_path> so users can open any folder as
  a database.  The v1 REST API uses /{db}/ in the URL — it can only receive a
  name.  When the user browses to C:\\MyData\\DB_Test_2 in the explorer, the
  legacy API reads from that path, but the v1 API defaults to
  AETHVIONDB/DB_Test_2/, which is a completely different (possibly empty)
  directory.

Solution:
  Every time the legacy API opens a path-based database it calls
  register_path_db(path).  This writes  name → actual_path  to a small JSON
  file at AETHVIONDB/_db_registry.json.  The v1 API calls resolve_db_root(db)
  which checks that file before falling back to AETHVIONDB/<db>.

Registry file: AETHVIONDB/_db_registry.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from core.utils.logger import get_logger
from core.utils.paths import AETHVIONDB

logger = get_logger(__name__)

_REGISTRY_FILE = AETHVIONDB / "_db_registry.json"
_SAFE_RE       = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _read() -> dict:
    """Read the registry file; returns {} on any error."""
    if _REGISTRY_FILE.exists():
        try:
            return json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write(registry: dict) -> None:
    """Persist the registry; silently ignores write errors."""
    try:
        AETHVIONDB.mkdir(parents=True, exist_ok=True)
        _REGISTRY_FILE.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.debug(f"[DBRegistry] Write failed: {exc}")


# ── Public API ────────────────────────────────────────────────────────────────

def register_path_db(path: str | Path) -> None:
    """Register a path-based database by its folder name.

    Called by the legacy API whenever it processes a request that includes
    ?path=<absolute_path>.  Only names that match the v1 safe-name regex are
    registered (others can't be addressed via the v1 API anyway).

    Duplicate registrations simply overwrite the previous entry so the most
    recently opened path is always authoritative.
    """
    try:
        p    = Path(path)
        name = p.name
        if not name or not _SAFE_RE.match(name):
            return
        registry       = _read()
        registry[name] = str(p)
        _write(registry)
        logger.debug(f"[DBRegistry] Registered {name!r} → {p}")
    except Exception as exc:
        logger.debug(f"[DBRegistry] Could not register {path!r}: {exc}")


def resolve_db_root(db: str) -> Path:
    """Return the actual filesystem root for a named database.

    Lookup order:
      1. Registry (path-based DBs registered by the legacy API)
      2. AETHVIONDB/<db>  (default for named databases)

    The registry entry is only used when the registered path still exists on
    disk.  If the path was deleted or moved, the fallback is used instead.
    """
    registry = _read()
    if db in registry:
        p = Path(registry[db])
        if p.exists():
            logger.debug(f"[DBRegistry] Resolved {db!r} → {p} (registry)")
            return p
        # Stale entry — remove it and fall through
        logger.debug(f"[DBRegistry] Stale entry for {db!r}, path gone: {p}")
        registry.pop(db, None)
        _write(registry)

    return AETHVIONDB / db


def list_registered() -> dict[str, str]:
    """Return a copy of the current registry (name → path string)."""
    return dict(_read())
