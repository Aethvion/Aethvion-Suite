"""
core/interfaces/dashboard/routes/preferences_routes.py
══════════════════════════════════════════════════════
API routes for user preferences and settings.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from core.utils import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/preferences", tags=["preferences"])

class PreferenceUpdate(BaseModel):
    key: Optional[str] = None
    value: Any = None

@router.get("")
async def get_preferences():
    """Get all user preferences."""
    try:
        from core.workspace.preferences_manager import get_preferences_manager
        prefs = get_preferences_manager()
        return prefs.get_all()
    except Exception as e:
        logger.error(f"Failed to get preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get")
async def get_preference_value(key: str):
    """Get a specific preference value."""
    try:
        from core.workspace.preferences_manager import get_preferences_manager
        prefs = get_preferences_manager()
        value = prefs.get(key)
        return {"key": key, "value": value}
    except Exception as e:
        logger.error(f"Failed to get preference {key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
async def update_preferences(updates: Dict[str, Any]):
    """Update multiple preferences."""
    try:
        from core.workspace.preferences_manager import get_preferences_manager
        prefs = get_preferences_manager()
        prefs.update(updates)
        return {"status": "success", "preferences": prefs.get_all()}
    except Exception as e:
        logger.error(f"Failed to update preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{key}")
async def set_preference(key: str, update: PreferenceUpdate):
    """Set a specific preference key."""
    try:
        from core.workspace.preferences_manager import get_preferences_manager
        prefs = get_preferences_manager()
        prefs.set(key, update.value)
        return {"status": "success", "key": key, "value": update.value}
    except Exception as e:
        logger.error(f"Failed to set preference {key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))