"""
Misaka Cipher - Preferences Manager
Manages user UI preferences and persistence to a local JSON file.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from core.utils import get_logger
from core.utils.paths import WS_PREFERENCES, WORKSPACES

logger = get_logger("workspace.preferences")

class PreferencesManager:
    """
    Manages user preferences for the web interface.
    Persists data to workspace/user_preferences.json.
    """
    
    def __init__(self, workspace_root: Path):
        """
        Initialize the preferences manager.
        
        Args:
            workspace_root: Root directory for workspace files
        """
        self.workspace_root = workspace_root
        # Data files live in data/workspaces/
        self.config_root = WORKSPACES
        self.prefs_file = WS_PREFERENCES
        self.preferences: Dict[str, Any] = {}
        self._load_prefs()
        
    def _load_prefs(self) -> None:
        """Load preferences from file."""
        if not self.prefs_file.exists():
            self.preferences = {
                "active_tab": "chat",
                "package_filters": {
                    "status": "all",
                    "hide_system": False,
                    "search": ""
                },
                "tool_filters": {
                    "hide_system": False
                },
                "package_sort": {
                    "column": "updated",
                    "direction": "desc"
                },
                "ui_toggles": {
                    "hide_agents_panel": False,
                    "hide_system_logs": False
                },
                "theme": "dark"
            }
            self._save_prefs()
            return

        try:
            with open(self.prefs_file, 'r') as f:
                self.preferences = json.load(f)
            logger.debug(f"Loaded user preferences from {self.prefs_file}")
        except Exception as e:
            logger.error(f"Failed to load user preferences: {e}")
            # Fallback to defaults if file is corrupted
            self.preferences = {}
            
    def _save_prefs(self) -> None:
        """Save preferences to file."""
        try:
            # Ensure workspace directory exists
            self.config_root.mkdir(parents=True, exist_ok=True)
            
            with open(self.prefs_file, 'w') as f:
                json.dump(self.preferences, f, indent=2)
            logger.debug("Saved user preferences")
        except Exception as e:
            logger.error(f"Failed to save user preferences: {e}")

    def get_all(self) -> Dict[str, Any]:
        """Get all preferences."""
        return self.preferences.copy()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a specific preference value."""
        if '.' in key:
            parts = key.split('.')
            target = self.preferences
            for part in parts:
                if isinstance(target, dict) and part in target:
                    target = target[part]
                else:
                    return default
            return target
        return self.preferences.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Set a specific preference value.
        
        Args:
            key: Preference key (can be nested using dot notation, e.g. 'package_filters.status')
            value: Value to set
        """
        if '.' in key:
            # Handle nested keys deeply
            parts = key.split('.')
            target = self.preferences
            for part in parts[:-1]:
                if part not in target or not isinstance(target[part], dict):
                    target[part] = {}
                target = target[part]
            target[parts[-1]] = value
        else:
            self.preferences[key] = value
            
        self._save_prefs()
        
    def update(self, updates: Dict[str, Any]) -> None:
        """Update multiple preferences at once."""
        self.preferences.update(updates)
        self._save_prefs()


# Singleton instance pattern
_prefs_manager = None

def get_preferences_manager() -> PreferencesManager:
    """Get the singleton PreferencesManager instance."""
    global _prefs_manager
    if _prefs_manager is None:
        from core.tools.standard.file_ops import WORKSPACE_ROOT
        _prefs_manager = PreferencesManager(WORKSPACE_ROOT)
    return _prefs_manager
