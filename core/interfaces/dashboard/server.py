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
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.version import VERSION
from core.utils import get_logger, fastapi_utils, utcnow_iso

# Extraction modules
from .ws_manager import manager, WebSocketLogHandler

logger = get_logger(__name__)
aether = None
orchestrator = None
factory = None

async def register_all_routers(app: FastAPI):
    """Register all API routes. Must be called during startup."""
    try:
        # Import routers here to avoid circular dependencies
        from .routes.system_routes import router as system_router
        from .routes.preferences_routes import router as preferences_router
        from .routes.workspace_routes import router as workspace_router
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
        from .ollama_routes import router as ollama_router
        from .audio_models_routes import router as audio_router
        from .corp_routes import router as corp_router
        from .games_routes import router as games_router
        from .overlay_routes import router as overlay_router
        from .schedule_routes import router as schedule_router
        from .smarter_than_ai_routes import router as smarter_router
        from .three_d_routes import router as threed_router
        from .agent_workspace_routes import router as agent_ws_router
        from .notification_routes import router as notification_router
        from .explained_routes import router as explained_router
        from .external_api_routes import router as ext_api_router, mgmt_router as ext_api_mgmt_router
        from .persistent_memory_routes import router as persistent_memory_router
        from .discord_routes import router as discord_router
        from .logs_routes import router as logs_router
        from .documentation_routes import router as documentation_router
        
        from core.companions.companion_routes import router as companion_router
        from core.companions.companion_creator_routes import router as companion_creator_router
        
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
        app.include_router(ollama_router)
        app.include_router(audio_router)
        app.include_router(corp_router)
        app.include_router(games_router)
        app.include_router(overlay_router)
        app.include_router(schedule_router)
        app.include_router(smarter_router)
        app.include_router(threed_router)
        app.include_router(agent_ws_router)
        app.include_router(notification_router)
        app.include_router(explained_router)
        app.include_router(ext_api_router)
        app.include_router(ext_api_mgmt_router)
        app.include_router(persistent_memory_router)
        app.include_router(discord_router)
        app.include_router(logs_router)
        app.include_router(documentation_router)
        app.include_router(companion_router)
        app.include_router(companion_creator_router)
        
        logger.debug("All routers included successfully.")
    except Exception as e:
        logger.error(f"Failed to register routers: {e}", exc_info=True)
        raise

async def initialize_ai_engine(app: FastAPI):
    """Perform slow/blocking AI engine initialization in background."""
    try:
        # Blocking init
        await asyncio.to_thread(perform_blocking_init)
        
        # Post-init workers
        from core.orchestrator.task_queue import get_task_queue_manager
        task_manager = get_task_queue_manager(app.state.orchestrator)
        await task_manager.start()
        
        app.state.startup_status.update({"status": "Ready", "progress": 100, "initialized": True})
        logger.info("Aethvion Suite ready!")
    except Exception as e:
        logger.error(f"AI Engine initialization failed: {e}", exc_info=True)
        app.state.startup_status.update({"status": "Something went wrong during AI initialization.", "error": str(e)})

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.main_event_loop = asyncio.get_running_loop()
    
    # 1. Initialize log streaming
    ws_handler = WebSocketLogHandler()
    ws_handler.main_loop = app.state.main_event_loop
    ws_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(ws_handler)
    
    await register_all_routers(app)
    
    # 3. Start AI engine initialization in background
    asyncio.create_task(initialize_ai_engine(app))
    
    yield
    
    # Shutdown logic
    logger.info("Shutting down Aethvion Suite...")
    for pid in list(app.state.RUNNING_APPS.values()):
        try:
            import psutil
            p = psutil.Process(pid)
            for child in p.children(recursive=True): child.kill()
            p.kill()
        except Exception:
            pass

# Initialize FastAPI app
app = FastAPI(
    title="Aethvion Suite",
    description="Intelligent AI Assistant Suite",
    version=str(VERSION),
    lifespan=lifespan
)
fastapi_utils.add_dev_cache_control(app)

# Global State
app.state.RUNNING_APPS = {}
app.state.startup_status = {
    "initialized": False,
    "status": "Starting Aethvion...",
    "progress": 0,
    "error": None
}
app.state.orchestrator = None
app.state.aether = None
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

def perform_blocking_init():
    from core.aether_core import AetherCore
    from core.factory import AgentFactory
    from core.orchestrator import MasterOrchestrator

    global aether, orchestrator, factory
    app.state.startup_status.update({"status": "Starting AI engine...", "progress": 20})
    aether = AetherCore()
    aether.initialize()
    
    app.state.startup_status.update({"status": "Preparing AI agents...", "progress": 50})
    factory = AgentFactory(aether)
    
    app.state.startup_status.update({"status": "Connecting components...", "progress": 70})
    orchestrator = MasterOrchestrator(aether, factory)
    
    app.state.aether = aether
    app.state.factory = factory
    app.state.orchestrator = orchestrator
    
    orchestrator.set_step_callback(
        lambda data: asyncio.run_coroutine_threadsafe(manager.broadcast(data, "chat"), app.state.main_event_loop)
    )

# Models
class ChatMessage(BaseModel):
    message: str
    thread_id: Optional[str] = "default"

@app.post("/api/chat")
async def chat(message: ChatMessage):
    if not app.state.orchestrator: 
        raise HTTPException(503, "Still starting up \u2014 try again in a moment.")
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
                cid = data.get("companionId")
                result = await app.state.orchestrator.process_message(data["message"], companion_id=cid)
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

@app.websocket("/ws/agents")
async def websocket_agents(websocket: WebSocket):
    await manager.connect(websocket, "agents")
    try:
        while True:
            await asyncio.sleep(10)
            await websocket.send_json({"type": "heartbeat", "timestamp": utcnow_iso()})
    except (WebSocketDisconnect, RuntimeError): pass
    finally: manager.disconnect(websocket, "agents")
