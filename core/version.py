"""
core/version.py
══════════════
Auto-computed version derived from the git history at startup.

Format:  YYYY.MM.count (shorthash)
Example: 2026.05.1142 (fc86ae4)

  YYYY      — 4-digit year of the HEAD commit
  MM        — zero-padded month of the HEAD commit
  count     — total number of commits reachable from HEAD (git rev-list --count)
  shorthash — 7-char abbreviated commit hash

Falls back to "unknown" if git is not available (e.g. in a zip-distributed build).
"""
from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_CREATE_NO_WINDOW = 0x08000000  # Windows only — suppress console popup


def _git(*args: str) -> str:
    """Run a git command from the repo root; return stripped stdout or raise."""
    flags = {"cwd": str(_ROOT), "text": True, "stderr": subprocess.DEVNULL}
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags["creationflags"] = _CREATE_NO_WINDOW
    try:
        flags["creationflags"] = _CREATE_NO_WINDOW
    except AttributeError:
        pass
    return subprocess.check_output(["git", *args], **flags).strip()


@lru_cache(maxsize=1)
def get_version_parts() -> dict:
    """Return the individual pieces used to build the version string."""
    try:
        date   = _git("log", "-1", "--format=%ad", "--date=format:%Y.%m")
        count  = _git("rev-list", "--count", "HEAD")
        short  = _git("rev-parse", "--short=7", "HEAD")
        year, month = date.split(".")
        return {
            "year":  year,
            "month": month,
            "count": int(count),
            "short": short,
            "string": f"{date}.{count} ({short})",
        }
    except Exception:
        return {
            "year":  "0000",
            "month": "00",
            "count": 0,
            "short": "unknown",
            "string": "unknown",
        }


@lru_cache(maxsize=1)
def get_version() -> str:
    """Return the full version string, e.g. '2026.05.1142 (fc86ae4)'."""
    return get_version_parts()["string"]


# Module-level constant — safe to import directly anywhere.
# Computed once at first import; cached for the lifetime of the process.
VERSION: str = get_version()
