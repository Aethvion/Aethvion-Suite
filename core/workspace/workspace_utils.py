"""
Aethvion Suite - Workspace Utilities
Shared logic for workspace management and path validation.
"""

import json
import logging
from pathlib import Path
from typing import List, Tuple, Optional


logger = logging.getLogger(__name__)

from core.utils.paths import COMPANIONS

def get_workspaces_file(companion_id: str) -> Path:
    """Resolve the workspaces.json path for a specific companion."""
    return COMPANIONS / companion_id / "workspaces.json"

def load_workspaces(companion_id: str) -> List[dict]:
    """Load workspace configurations from disk for a specific companion."""
    ws_file = get_workspaces_file(companion_id)
    if not ws_file.exists():
        return []
    try:
        with open(ws_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load workspaces for {companion_id}: {e}")
        return []

def save_workspaces(companion_id: str, workspaces: List[dict]) -> None:
    """Save workspace configurations to disk for a specific companion."""
    try:
        ws_file = get_workspaces_file(companion_id)
        ws_file.parent.mkdir(parents=True, exist_ok=True)
        with open(ws_file, "w", encoding="utf-8") as f:
            json.dump(workspaces, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save workspaces for {companion_id}: {e}")

def validate_path(target_path: str, workspaces: List[dict], required_permission: str) -> Tuple[bool, str]:
    """
    Check if a target_path is allowed under any configured workspace with the required permission.
    Returns (is_allowed, reason).
    """
    try:
        tp = Path(target_path).resolve()
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

def build_workspace_block(workspaces: List[dict]) -> str:
    """Format workspace metadata into instructions for the LLM."""
    if not workspaces:
        return "WORKSPACE ACCESS: Disabled. You do not have permissions to read/write local files."
    
    lines = [
        "WORKSPACE ACCESS: Enabled. Use [tool:file action=\"...\" path=\"...\"] syntax.",
        "You have access to the following local locations:"
    ]
    for ws in workspaces:
        label = ws.get("label", "Untitled")
        path = ws.get("path", "?")
        perms = ", ".join(ws.get("permissions", []))
        recursive = "(recursive)" if ws.get("recursive", True) else "(non-recursive)"
        lines.append(f"  - {label}: {path} [{perms}] {recursive}")
    
    lines.extend([
        "All file paths MUST be absolute paths using forward slashes (e.g. C:/Data/file.txt).",
        "ACTIONS: read_file, write_file, list_dir, delete_file, make_dir",
        "Example: [tool:file action=\"read_file\" path=\"C:/Users/Data/config.json\"]"
    ])
    return "\n".join(lines)
