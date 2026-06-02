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
from fastapi.responses import HTMLResponse, JSONResponse
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

def _import_remaining_routers():
    """Import all non-critical route modules. Runs in a thread pool so it
    does NOT block the event loop during startup."""
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
    from .overlay_routes import router as overlay_router
    from .schedule_routes import router as schedule_router
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
    from core.aethviondb.aethviondb_routes import router as aethviondb_router
    from core.aethviondb.api_v1.router import router as aethviondb_v1_router
    from core.automate.automate_routes import router as automate_router
    return [
        preferences_router, workspace_router, task_router, memory_router,
        registry_router, usage_router, arena_router, settings_router,
        photo_router, adv_aiconv_router, board_router, assistant_router,
        ollama_router, audio_router, corp_router, overlay_router,
        schedule_router, threed_router, agent_ws_router, notification_router,
        explained_router, ext_api_router, ext_api_mgmt_router,
        persistent_memory_router, discord_router, logs_router,
        documentation_router, companion_router, companion_creator_router,
        aethviondb_router, aethviondb_v1_router, automate_router,
    ]


async def register_all_routers(app: FastAPI):
    """Import remaining route modules in a thread (non-blocking), then register them.
    system_router is already registered synchronously in lifespan before this runs."""
    try:
        routers = await asyncio.to_thread(_import_remaining_routers)
        for router in routers:
            app.include_router(router)
        logger.debug("All routers included successfully.")
    except Exception as e:
        logger.error(f"Failed to register routers: {e}", exc_info=True)
        app.state.startup_status.update({"status": "Startup error: route registration failed.", "error": str(e)})
    finally:
        app.state.routes_ready.set()

async def _prewarm_memory():
    """Load ChromaDB + knowledge graph after the UI is declared ready.
    Runs in background so the first memory-touching user request doesn't stall."""
    try:
        def _load():
            from core.memory import get_episodic_memory, get_knowledge_graph
            get_episodic_memory()
            get_knowledge_graph()
        await asyncio.to_thread(_load)
        logger.info("Memory tier pre-warmed.")
    except Exception as e:
        logger.warning(f"Memory pre-warm failed (non-critical): {e}")


async def initialize_ai_engine(app: FastAPI):
    """Perform slow/blocking AI engine initialization in background."""
    try:
        # Blocking init (runs in thread pool — no ChromaDB/memory here anymore)
        await asyncio.to_thread(perform_blocking_init)

        # Wait for all routes to be registered before declaring the app ready.
        # Router imports run concurrently in a thread; this ensures no 404s on first use.
        try:
            await asyncio.wait_for(app.state.routes_ready.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning("Route registration timed out — proceeding anyway")

        # Post-init workers
        from core.orchestrator.task_queue import get_task_queue_manager
        task_manager = get_task_queue_manager(app.state.orchestrator)
        await task_manager.start()

        app.state.startup_status.update({"status": "Ready", "progress": 100, "initialized": True})
        logger.info("Aethvion Suite ready!")

        # Pre-warm ChromaDB + knowledge graph in the background after UI is visible
        asyncio.create_task(_prewarm_memory())

    except Exception as e:
        logger.error(f"AI Engine initialization failed: {e}", exc_info=True)
        app.state.startup_status.update({"status": "Something went wrong during AI initialization.", "error": str(e)})

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.main_event_loop = asyncio.get_running_loop()
    app.state.routes_ready = asyncio.Event()

    # Initialize log streaming
    ws_handler = WebSocketLogHandler()
    ws_handler.main_loop = app.state.main_event_loop
    ws_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(ws_handler)

    # Register system_router synchronously — provides /health and /startup-status
    # which the frontend and suite tester need before anything else is ready.
    from .routes.system_routes import router as system_router
    app.include_router(system_router)

    # Import + register remaining 31 routers in a thread (non-blocking).
    # AI engine init runs concurrently; it waits for routes_ready before
    # declaring initialized=True, so the frontend never hits a 404 on first use.
    asyncio.create_task(register_all_routers(app))
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

# Exception handlers
# Registered once here; covers every router in the application.

from core.exceptions import AethvionError  # noqa: E402

@app.exception_handler(AethvionError)
async def _handle_domain_error(request: Request, exc: AethvionError) -> JSONResponse:
    logger.error("[%s] %s: %s", request.url.path, type(exc).__name__, exc.message)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

@app.exception_handler(HTTPException)
async def _handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    if exc.status_code >= 500:
        # Log the real detail server-side; send a generic message to the client.
        logger.error("[%s] HTTP %d: %s", request.url.path, exc.status_code, exc.detail)
        return JSONResponse(status_code=exc.status_code, content={"detail": "Internal server error."})
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.exception_handler(Exception)
async def _handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.error("[%s] Unhandled %s: %s", request.url.path, type(exc).__name__, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})

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

# CORS — restricted to localhost origins only.
# Aethvion Suite is a local-first application; cross-origin credentials must
# never be sent to arbitrary third-party origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        # Allows file:// → fetch() calls (electron / webview / bat launcher)
        "null",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
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
INTERACTIVEDOCS_DIR = PROJECT_ROOT / "core" / "documentation" / "interactivedocs"
INTERACTIVEDOCS_DIR.mkdir(exist_ok=True)
app.mount("/interactivedocs", StaticFiles(directory=str(INTERACTIVEDOCS_DIR), html=True), name="interactivedocs")

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main dashboard page."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        content = index_path.read_text(encoding="utf-8")
        content = content.replace("__VERSION__", VERSION).replace("__VNUM__", VERSION)
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
