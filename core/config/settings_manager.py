"""
Misaka Cipher - Settings Manager
Manages system configuration and user preferences
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from core.utils import get_logger
from core.utils.paths import SETTINGS

logger = get_logger(__name__)

SETTINGS_FILE = SETTINGS



class SettingsManager:
    """
    Manages system settings and user preferences.
    
    Handles:
    - Output validation rules
    - System settings (browser startup)
    - Settings persistence
    """
    
    def __init__(self):
        """Initialize settings manager."""
        self.settings = self._load_settings()
        logger.info("Settings Manager initialized")
    
    def _load_settings(self) -> Dict[str, Any]:
        """Load settings from file."""
        if not SETTINGS_FILE.exists():
            logger.warning(f"Settings file not found: {SETTINGS_FILE}")
            return self._get_default_settings()
        
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
            logger.info("Settings loaded successfully")
            return settings
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
            return self._get_default_settings()
    
    def _get_default_settings(self) -> Dict[str, Any]:
        """Get default settings."""
        return {
            "output_validation": {
                "check_file_content": True,
                "check_file_location": True,
                "min_file_size": 10,
                "min_content_length": 50
            },
            "system": {
                "open_browser_on_startup": True
            },
            "voice": {
                "input_model": "browser",
                "input_provider": "browser"
            }
        }
    
    def save_settings(self) -> bool:
        """Save settings to file."""
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(self.settings, f, indent=2)
            logger.info("Settings saved successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return False
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get setting value by dot-separated path.
        
        Args:
            key_path: Dot-separated path (e.g., "retry.max_attempts")
            default: Default value if not found
            
        Returns:
            Setting value or default
        """
        keys = key_path.split('.')
        value = self.settings
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def set(self, key_path: str, value: Any) -> bool:
        """
        Set setting value by dot-separated path.
        
        Args:
            key_path: Dot-separated path (e.g., "retry.max_attempts")
            value: Value to set
            
        Returns:
            True if successful
        """
        keys = key_path.split('.')
        target = self.settings
        
        # Navigate to parent
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        
        # Set value
        target[keys[-1]] = value
        return self.save_settings()
    
    def get_min_content_length(self) -> int:
        """Get minimum expected content length for validation."""
        return self.get("output_validation.min_content_length", 50)


# Singleton instance
_settings_manager = None

def get_settings_manager() -> SettingsManager:
    """Get the singleton SettingsManager instance."""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager
