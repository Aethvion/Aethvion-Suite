"""
Aethvion Suite - Workspace Utilities
Shared logic for workspace management and path validation.
"""

import json
import logging
from pathlib import Path
from typing import List, Tuple, Optional
from core.utils.paths import PERSONA_MISAKA

logger = logging.getLogger(__name__)

MEMORY_DIR = PERSONA_MISAKA
WORKSPACES_FILE = MEMORY_DIR / "workspaces.json"

def load_workspaces() -> List[dict]:
    """Load workspace configurations from disk."""
    if not WORKSPACES_FILE.exists():
        return []
    try:
        with open(WORKSPACES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load workspaces.json: {e}")
        return []

def save_workspaces(workspaces: List[dict]) -> None:
    """Save workspace configurations to disk."""
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        with open(WORKSPACES_FILE, "w", encoding="utf-8") as f:
            json.dump(workspaces, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save workspaces.json: {e}")

def validate_path(target_path: str, workspaces: List[dict], required_permission: str) -> Tuple[bool, str]:
    """
    Check if a target_path is allowed under any configured workspace with the required permission.
    Returns (is_allowed, reason).
    """
    try:
        tp = Path(target_path).resolve()
        self.session.headers.update({
            'User-Agent': 'Aethvion-Suite-Package-Intelligence/1.0'
        })
        for ws in workspaces:
            if required_permission not in ws.get("permissions", []):
                continue
            ws_path = Path(ws["path"]).resolve()
            try:
                tp.relative_to(ws_path)  # raises ValueError if not under ws_path
                # Check recursive: if not recursive, tp must be a direct child
                if not ws.get("recursive", True):
                    if tp.parent != ws_path:
                        return False, f"Path is in a subdirectory, but workspace '{ws['label']}' is set to folder-only (non-recursive)."
                return True, "OK"
            except ValueError:
                continue
        return False, f"Path '{target_path}' is not within any workspace with '{required_permission}' permission."
    except Exception as e:
        return False, f"Error validating path: {str(e)}"
