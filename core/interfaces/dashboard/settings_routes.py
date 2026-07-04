"""
Aethvion Suite - Settings Routes
API endpoints for managing system settings (config/settings.json)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from core.config.settings_manager import get_settings_manager
from core.utils import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class PrivacyModeRequest(BaseModel):
    enabled: bool

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
            sm.set(key_path, value)
        return {"status": "success", "settings": sm.settings}
    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ActiveProfileRequest(BaseModel):
    profile: str


@router.get("/active-profile")
async def get_active_profile_endpoint():
    """Return the active data profile ('standard' | 'private')."""
    from core.config.profiles import get_active_profile
    return {"profile": get_active_profile()}


@router.post("/active-profile")
async def set_active_profile_endpoint(req: ActiveProfileRequest):
    """Switch the active data profile. New threads and memories are tagged with it."""
    try:
        from core.config.profiles import set_active_profile
        applied = set_active_profile(req.profile)
        return {"success": True, "profile": applied}
    except Exception as e:
        logger.error(f"Failed to set active profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/privacy-mode")
async def get_privacy_mode():
    """Return current privacy mode state."""
    sm = get_settings_manager()
    return {"enabled": bool(sm.settings.get("privacy_mode", False))}


@router.post("/privacy-mode")
async def set_privacy_mode_endpoint(req: PrivacyModeRequest):
    """Enable or disable privacy mode (local-only LLM routing)."""
    try:
        sm = get_settings_manager()
        sm.set("privacy_mode", req.enabled)
        state = "enabled" if req.enabled else "disabled"
        logger.info(f"Privacy mode {state} via API")
        return {
            "success": True,
            "enabled": req.enabled,
            "message": (
                "Privacy mode enabled. All LLM calls now route to local models only."
                if req.enabled else
                "Privacy mode disabled. Normal provider routing restored."
            ),
        }
    except Exception as e:
        logger.error(f"Failed to set privacy mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))
