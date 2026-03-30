"""
Aethvion Suite - Settings Routes
API endpoints for managing system settings (config/settings.json)
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from core.config.settings_manager import get_settings_manager
from core.utils import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

@router.get("")
async def get_settings():
    """Get the full system settings (settings.json)."""
    try:
        sm = get_settings_manager()
        return sm.settings
    except Exception as e:
        logger.error(f"Failed to get settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
async def update_settings(updates: Dict[str, Any]):
    """Update settings in settings.json."""
    try:
        sm = get_settings_manager()
        for key_path, value in updates.items():
            # sm.set handles dot notation and persistence
            sm.set(key_path, value)
        return {"status": "success", "settings": sm.settings}
    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))
