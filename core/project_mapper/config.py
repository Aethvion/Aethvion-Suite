"""
core/project_mapper/config.py
Single source of truth for the data directory location (Suite adaptation).

In the Aethvion Suite the MCP server shares the Suite's AethvionDB data root,
so databases scanned over MCP are the same ones the dashboard sees.

Override with the PM_DATA_DIR environment variable:
    PM_DATA_DIR=/var/data/pm python -m core.project_mapper.mcp_server
"""
import os
from pathlib import Path

_env = os.environ.get("PM_DATA_DIR", "")

if _env:
    DATA_DIR: Path = Path(_env)
else:
    try:
        from core.utils.paths import AETHVIONDB
        DATA_DIR = AETHVIONDB
    except Exception:
        # Fallback when run outside the Suite package context
        DATA_DIR = Path.home() / ".aethvion_pm" / "data"
