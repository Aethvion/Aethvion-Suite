"""
Aethvion Suite - FastAPI Web Server (Thin Wiring)
REST API and WebSocket server for web dashboard
"""
import os
import sys
import asyncio
import logging
import uuid
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.version import VERSION
from core.utils import get_logger, fastapi_utils, utcnow_iso

# Extraction modules
from .ws_manager import manager, WebSocketLogHandler
from .routes.system_routes import router as system_router
from .routes.preferences_routes import router as preferences_router
from .routes.workspace_routes import router as workspace_router

logger = get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Aethvion Suite - Nexus Portal",
    description="Autonomous AI Orchestration System",
    version=str(VERSION)
)
fastapi_utils.add_dev_cache_control(app)

# Global State (Stored on app.state for modular access)
app.state.RUNNING_APPS = {}
app.state.startup_status = {
    "initialized": False,
    "status": "Starting Server...",
    "progress": 0,
    "error": None
}
app.state.orchestrator = None
app.state.nexus = None
app.state.factory = None
app.state.discord_worker = None
app.state.main_event_loop = None

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
STATIC_DIR = Path(__file__).parent / "static"
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main dashboard page."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        content = index_path.read_text(encoding="utf-8")
        content = content.replace("__VERSION__", f"v{VERSION}").replace("__VNUM__", str(VERSION))
        return HTMLResponse(content, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return HTMLResponse("<h1>Aethvion Suite</h1><p>index.html not found</p>")

@app.on_event("startup")
async def startup_event():
    app.state.main_event_loop = asyncio.get_running_loop()
    
    # Initialize log streaming
    ws_handler = WebSocketLogHandler()
    ws_handler.main_loop = app.state.main_event_loop
    ws_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(ws_handler)
    
    asyncio.create_task(initialize_system_background())

async def initialize_system_background():
    try:
        # Import and include routers
        from .task_routes import router as task_router
        from .memory_routes import router as memory_router
        from .registry_routes import router as registry_router
        from .usage_routes import router as usage_router
        from .arena_routes import router as arena_router
        from .settings_routes import router as settings_router
        from .photo_routes import router as photo_router
        from .advanced_aiconv_routes import router as adv_aiconv_router
        from .research_board_routes import router as board_router
        from .assistant_routes import router as assistant_router
        from core.companions.companion_routes import router as companion_router
        from core.companions.companion_creator_routes import router as companion_creator_router
        from .documentation_routes import router as documentation_router
        from .logs_routes import router as logs_router
        
        app.include_router(system_router)
        app.include_router(preferences_router)
        app.include_router(workspace_router)
        app.include_router(task_router)
        app.include_router(memory_router)
        app.include_router(registry_router)
        app.include_router(usage_router)
        app.include_router(arena_router)
        app.include_router(settings_router)
        app.include_router(photo_router)
        app.include_router(adv_aiconv_router)
        app.include_router(board_router)
        app.include_router(assistant_router)
        app.include_router(companion_router)
        app.include_router(companion_creator_router)
        app.include_router(documentation_router)
        app.include_router(logs_router)

        # Blocking init
        await asyncio.to_thread(perform_blocking_init)
        
        # Post-init workers
        from core.orchestrator.task_queue import get_task_queue_manager
        task_manager = get_task_queue_manager(app.state.orchestrator)
        await task_manager.start()
        
        app.state.startup_status.update({"status": "All systems operational", "progress": 100, "initialized": True})
        logger.info("Aethvion Suite (Thin) ready!")
    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        app.state.startup_status.update({"status": "Startup Failed", "error": str(e)})

def perform_blocking_init():
    from core.nexus_core import NexusCore
    from core.factory import AgentFactory
    from core.orchestrator import MasterOrchestrator

    app.state.nexus = NexusCore()
    app.state.nexus.initialize()
    app.state.factory = AgentFactory(app.state.nexus)
    app.state.orchestrator = MasterOrchestrator(app.state.nexus, app.state.factory)
    
    app.state.orchestrator.set_step_callback(
        lambda data: asyncio.run_coroutine_threadsafe(manager.broadcast(data, "chat"), app.state.main_event_loop)
    )

# Models
class ChatMessage(BaseModel):
    message: str
    thread_id: Optional[str] = "default"

@app.post("/api/chat")
async def chat(message: ChatMessage):
    if not app.state.orchestrator: raise HTTPException(503, "Not initialized")
    from core.orchestrator.task_queue import get_task_queue_manager
    task_id = await get_task_queue_manager().submit_task(message.message, thread_id=message.thread_id)
    return {"task_id": task_id}

# WebSockets
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await manager.connect(websocket, "chat")
    try:
        while True:
            data = await websocket.receive_json()
            if "message" in data:
                result = await asyncio.to_thread(app.state.orchestrator.process_message, data["message"])
                await websocket.send_json({"type": "response", "response": result.response, "success": result.success})
    except (WebSocketDisconnect, RuntimeError): pass
    finally: manager.disconnect(websocket, "chat")

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await manager.connect(websocket, "logs")
    try:
        while True:
            await asyncio.sleep(10)
            await websocket.send_json({"type": "heartbeat", "timestamp": utcnow_iso()})
    except (WebSocketDisconnect, RuntimeError): pass
    finally: manager.disconnect(websocket, "logs")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Aethvion Suite...")
    for pid in list(app.state.RUNNING_APPS.values()):
        try:
            import psutil
            p = psutil.Process(pid)
            for child in p.children(recursive=True): child.kill()
            p.kill()
        except: pass
