"""
core/aethviondb/config.py
Filesystem locations for the AethvionDB engine.

The data directory is configurable with the ``AETHVIONDB_DATA_DIR`` environment
variable. While AethvionDB still lives inside Aethvion Suite, the default
preserves the historical ``<repo>/data/aethviondb`` location so nothing breaks;
the standalone build changes this default to ``~/.aethvion/db`` (the shared
``~/.aethvion/<product>`` convention).
"""
from __future__ import annotations

import os
from pathlib import Path

# This file is core/aethviondb/config.py, so parents[2] is the repo root.
_IN_SUITE_DEFAULT = Path(__file__).resolve().parents[2] / "data" / "aethviondb"

DATA_DIR = Path(os.environ.get("AETHVIONDB_DATA_DIR") or _IN_SUITE_DEFAULT)

# Backwards-compatible alias for the name used across the engine.
AETHVIONDB = DATA_DIR

# Legacy: location of the old WorldSim databases, used only by the one-time
# migration in the dashboard routes. Harmless when absent (standalone).
MODES = _IN_SUITE_DEFAULT.parent / "modes"
