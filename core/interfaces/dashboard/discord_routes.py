"""
Aethvion Suite - Discord Routes
API endpoints for managing the Discord bot integration.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging

from core.utils import get_logger
from core.workspace.preferences_manager import get_preferences_manager

logger = get_logger(__name__)
router = APIRouter(prefix="/api/discord", tags=["discord"])

# Global worker reference (injected from server.py)
discord_worker = None

class DiscordStatus(BaseModel):
    status: str
    user: Optional[str] = None
    guilds: int = 0
    error: Optional[str] = None

@router.get("/status", response_model=DiscordStatus)
async def get_status():
    """Get the current status of the Discord worker."""
    if not discord_worker:
        return DiscordStatus(status="offline")
        
    if discord_worker.is_closed():
        return DiscordStatus(status="offline")
        
    if not discord_worker.is_ready():
        return DiscordStatus(status="connecting")
        
    try:
        return DiscordStatus(
            status="online",
            user=str(discord_worker.user),
            guilds=len(discord_worker.guilds)
        )
    except Exception as e:
        return DiscordStatus(status="error", error=str(e))

@router.post("/start")
async def start_worker():
    """Start the Discord worker service."""
    # Lazy imports to avoid circular deps
    import core.interfaces.dashboard.server as server
    from core.workers.discord_worker import start_discord_service
    from core.orchestrator.task_queue import get_task_queue_manager
    
    if discord_worker and not discord_worker.is_closed():
        return {"status": "already_running"}
        
    prefs = get_preferences_manager()
    bot_token = prefs.get('nexus.discord_link.bot_token')
    
    if not bot_token or not bot_token.strip():
        raise HTTPException(status_code=400, detail="Discord Bot Token not configured in settings.")
        
    try:
        # We need the orchestrator and task_manager from the main server
        orchestrator = getattr(server, 'orchestrator', None)
        task_manager = get_task_queue_manager() # Should return the singleton
        
        if not orchestrator:
            raise HTTPException(status_code=500, detail="Master Orchestrator not initialized.")
            
        new_worker = start_discord_service(orchestrator, task_manager, bot_token)
        server.discord_worker = new_worker # Update global on server
        globals()['discord_worker'] = new_worker # Update local global
        
        import asyncio
        asyncio.create_task(new_worker.run_worker())
        
        return {"status": "starting"}
    except Exception as e:
        logger.error(f"Failed to start Discord worker: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop")
async def stop_worker():
    """Stop the Discord worker service."""
    if not discord_worker:
        return {"status": "not_running"}
        
    try:
        if hasattr(discord_worker, 'stop_worker'):
            discord_worker.stop_worker()
        else:
            await discord_worker.close()
            
        return {"status": "stopped"}
    except Exception as e:
        logger.error(f"Failed to stop Discord worker: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def set_worker_instance(instance):
    """Set the worker instance for this router module."""
    global discord_worker
    discord_worker = instance
