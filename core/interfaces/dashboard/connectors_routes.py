"""
Aethvion Suite — Global Connectors & Connector Profiles Routes
Manage global bridges/connectors, live-test commands, slash triggers, and permission profiles.
"""
import asyncio
import re
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.bridges import bridge_manager
from core.workspace.preferences_manager import get_preferences_manager
from core.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/connectors", tags=["connectors"])


class ToggleConnectorRequest(BaseModel):
    enabled: bool


class ConnectorSettingsRequest(BaseModel):
    settings: Dict[str, Any]


class TestConnectorRequest(BaseModel):
    command: Optional[str] = None
    args: Optional[Dict[str, Any]] = None
    profile_id: Optional[str] = None


class SlashCommandRequest(BaseModel):
    message: str
    profile_id: Optional[str] = None


class ConnectorProfileRequest(BaseModel):
    id: Optional[str] = None
    name: str
    description: str = ""
    privacy_badge: str = "Custom"
    icon: str = "fas fa-sliders"
    allowed_connectors: List[str] = []


@router.get("/registry")
async def get_connectors_registry():
    """Return all global connectors with their saved settings and all connector profiles."""
    reg = bridge_manager.get_registry()
    modules = reg.get("modules", [])
    pm = get_preferences_manager()
    nexus_prefs = pm.get("nexus", {}) if pm else {}

    enriched_modules = []
    for mod in modules:
        m_copy = dict(mod)
        mod_id = m_copy.get("id", "")
        saved_cfg = nexus_prefs.get(mod_id, {}) if isinstance(nexus_prefs, dict) else {}
        # Mask secret fields in response while providing non-secret values
        values = {}
        for s_key in m_copy.get("settings", []):
            val = saved_cfg.get(s_key, "") if isinstance(saved_cfg, dict) else ""
            if "secret" in s_key.lower() or "key" in s_key.lower() or "token" in s_key.lower():
                values[s_key] = "••••••••" if val else ""
            else:
                values[s_key] = val
        m_copy["saved_settings"] = values
        enriched_modules.append(m_copy)

    profiles = bridge_manager.get_profiles()
    return {
        "modules": enriched_modules,
        "profiles": profiles
    }


@router.post("/{module_id}/toggle")
async def toggle_connector(module_id: str, req: ToggleConnectorRequest):
    """Enable or disable a connector globally."""
    updated = bridge_manager.set_module_enabled(module_id, req.enabled)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Connector '{module_id}' not found.")
    return {"success": True, "module": updated}


@router.post("/{module_id}/settings")
async def save_connector_settings(module_id: str, req: ConnectorSettingsRequest):
    """Save configuration settings for a connector module."""
    pm = get_preferences_manager()
    for key, val in (req.settings or {}).items():
        if val == "••••••••":
            continue
        pm.set(f"nexus.{module_id}.{key}", val)
    return {"success": True, "module_id": module_id}


@router.post("/{module_id}/test")
async def test_connector(module_id: str, req: TestConnectorRequest):
    """Execute a connector command in the background thread and return output + any attachments."""
    output = await asyncio.to_thread(
        bridge_manager.call_module,
        module_id,
        req.command or "",
        req.args or {},
        req.profile_id
    )
    attachments = []
    try:
        from core.companions.engine.tools import extract_peripheral_captures
        _, attachments = extract_peripheral_captures([output], [])
    except Exception:
        pass
    is_error = output.startswith("Bridge Error:") or output.startswith("Bridge Blocked:") or output.startswith("Nexus Error:")
    return {
        "success": not is_error,
        "module_id": module_id,
        "output": output,
        "attachments": attachments
    }


@router.post("/slash")
async def execute_slash_command(req: SlashCommandRequest):
    """Parse and execute a slash command (e.g. '/screen_capture explain this') and return context."""
    result = await asyncio.to_thread(
        bridge_manager.parse_and_execute_slash_commands,
        req.message,
        req.profile_id
    )
    return result


@router.get("/profiles")
async def list_connector_profiles():
    """Return all saved Connector Profiles."""
    return {"profiles": bridge_manager.get_profiles()}


@router.post("/profiles")
async def save_connector_profile(req: ConnectorProfileRequest):
    """Create or update a Connector Profile."""
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Profile name is required.")

    slug = re.sub(r"[^a-z0-9_]+", "_", (req.id or name).lower()).strip("_")
    if not slug:
        slug = "custom_profile"

    profiles = bridge_manager.get_profiles()
    existing_idx = next((i for i, p in enumerate(profiles) if p.get("id") == slug), None)

    new_prof = {
        "id": slug,
        "name": name,
        "description": req.description.strip(),
        "privacy_badge": req.privacy_badge.strip() or "Custom",
        "icon": req.icon.strip() or "fas fa-sliders",
        "builtin": profiles[existing_idx].get("builtin", False) if existing_idx is not None else False,
        "allowed_connectors": list(dict.fromkeys(req.allowed_connectors or []))
    }

    if existing_idx is not None:
        profiles[existing_idx] = new_prof
    else:
        profiles.append(new_prof)

    bridge_manager.save_profiles(profiles)
    return {"success": True, "profile": new_prof, "profiles": profiles}


@router.delete("/profiles/{profile_id}")
async def delete_connector_profile(profile_id: str):
    """Delete a custom Connector Profile."""
    profiles = bridge_manager.get_profiles()
    target = next((p for p in profiles if p.get("id") == profile_id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found.")
    if target.get("builtin"):
        raise HTTPException(status_code=400, detail="Built-in security profiles cannot be deleted (you can edit their allowed connectors instead).")

    updated = [p for p in profiles if p.get("id") != profile_id]
    bridge_manager.save_profiles(updated)
    return {"success": True, "profiles": updated}


@router.get("/reminders/due")
async def get_due_reminders():
    """Poll and pop any co-working tasks/reminders whose timer has expired."""
    try:
        from core.bridges import tasks_bridge
        due = await asyncio.to_thread(tasks_bridge.pop_due_reminders)
        return {"due": due}
    except Exception as e:
        logger.debug(f"[Connectors] Reminder check error: {e}")
        return {"due": []}
