"""
Aethvion Suite - FastAPI Web Server
REST API and WebSocket server for web dashboard
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from pathlib import Path
import asyncio
import json
import logging
import sys
import os
import subprocess
import platform
from datetime import datetime

from core.version import VERSION
from core.utils import get_logger, fastapi_utils
from core.config.settings_manager import get_settings_manager
from core.utils.paths import WS_OUTPUTS, WS_MEDIA, WS_UPLOADS
import psutil

# Windows window suppression
CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

logger = get_logger(__name__)

# Track dynamically started apps: { module_name: pid }
RUNNING_APPS: Dict[str, int] = {}

# Initialize FastAPI app
app = FastAPI(
    title="Aethvion Suite - Nexus Portal",
    description="Autonomous AI Orchestration System",
    version=str(VERSION)
)
fastapi_utils.add_dev_cache_control(app)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- INSTANT ACCESSIBILITY SECTION ---
STATIC_DIR = Path(__file__).parent / "static"
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main dashboard page instantly."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        content = index_path.read_text(encoding="utf-8")
        # Centralized version injection
        content = content.replace("__VERSION__", f"v{VERSION}")
        content = content.replace("__VNUM__", str(VERSION))
        
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        return HTMLResponse(content=content, headers=headers)
    return HTMLResponse("<h1>Aethvion Suite Dashboard</h1><p>index.html not found</p>")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up dynamically started apps on server shutdown."""
    if not RUNNING_APPS:
        return
        
    logger.info(f"Shutting down {len(RUNNING_APPS)} dynamic apps...")
    for name, pid in list(RUNNING_APPS.items()):
        try:
            if psutil.pid_exists(pid):
                parent = psutil.Process(pid)
                # Kill children first
                for child in parent.children(recursive=True):
                    child.kill()
                parent.kill()
                logger.info(f"Terminated {name} (PID {pid})")
        except Exception as e:
            logger.error(f"Failed to terminate {name} (PID {pid}): {e}")
    RUNNING_APPS.clear()

# Mount static files immediately
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

# Global instances (initialized on startup in background)
orchestrator = None
nexus = None
factory = None
forge = None
discord_worker = None
main_event_loop = None

# Startup tracking
startup_status = {
    "initialized": False,
    "status": "Starting Server...",
    "progress": 0,
    "error": None
}

# WebSocket connection manager
class ConnectionManager:
    """Manages WebSocket connections."""
    
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {
            'chat': [],
            'logs': [],
            'agents': []
        }
    
    async def connect(self, websocket: WebSocket, channel: str):
        """Connect a new WebSocket client."""
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = []
        self.active_connections[channel].append(websocket)
    
    def disconnect(self, websocket: WebSocket, channel: str):
        """Disconnect a WebSocket client."""
        if channel in self.active_connections and websocket in self.active_connections[channel]:
            self.active_connections[channel].remove(websocket)
    
    async def broadcast(self, message: dict, channel: str):
        """Broadcast message to all clients on a channel."""
        if channel not in self.active_connections:
            return
        
        disconnected = []
        for connection in self.active_connections[channel]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to {channel}: {type(e).__name__}: {e}")
                disconnected.append(connection)
        
        for conn in disconnected:
            self.disconnect(conn, channel)

manager = ConnectionManager()

# Global cache for workspace files to avoid redundant disk scans
# Format: { 'timestamp': float, 'data': { 'files': [], 'stats': {}, 'count': 0 } }
FILES_CACHE = {}


# WebSocket Log Handler
class WebSocketLogHandler(logging.Handler):
    """Custom handler to pipe logs to WebSocket."""
    
    def emit(self, record):
        try:
            msg = self.format(record)
            if "GET /api/system/status" in msg or "GET /api/workspace/files" in msg:
                return
                
            log_entry = {
                "type": "log",
                "level": record.levelname,
                "message": msg,
                "source": record.name,
                "timestamp": datetime.now().isoformat()
            }
            
            if main_event_loop and main_event_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast(log_entry, "logs"),
                    main_event_loop
                )
        except Exception:
            self.handleError(record)


# Request/Response models
class ChatMessage(BaseModel):
    """Chat message from user."""
    message: str
    trace_id: Optional[str] = None
    thread_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat response from orchestrator."""
    response: str
    trace_id: str
    actions_taken: List[str]
    tools_forged: List[str]
    agents_spawned: List[str]
    execution_time: float
    success: bool
    model_id: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None


class MemorySearchRequest(BaseModel):
    """Memory search request."""
    query: str
    domain: Optional[str] = None
    limit: int = 10

class SemanticSearchRequest(BaseModel):
    """Semantic file search request."""
    query: str
    limit: int = 10
    domain: Optional[str] = None

class AudioProcessRequest(BaseModel):
    """Audio processing request."""
    prompt: str
    model: str
    mode: str
    provider: Optional[str] = None
    voice: Optional[str] = None
    input_audio: Optional[str] = None


# Startup/Shutdown events
@app.on_event("startup")
async def startup_event():
    """Trigger background initialization."""
    global main_event_loop
    main_event_loop = asyncio.get_running_loop()
    
    # Initialize logging streamer immediately
    root_logger = logging.getLogger()
    ws_handler = WebSocketLogHandler()
    ws_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(message)s')
    ws_handler.setFormatter(formatter)
    root_logger.addHandler(ws_handler)
    
    # Start background initialization
    asyncio.create_task(initialize_system_background())

async def initialize_system_background():
    """Heavy initialization of components in the background."""
    # No global keywords needed here as we only mutate startup_status
    # and delegate assignments to perform_blocking_init.
    
    try:
        # Step 1: Resource Imports (CPU bound, moved to thread later if needed, but routers are fast)
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
        from .misaka_cipher_routes import router as misaka_cipher_router
        from .documentation_routes import router as documentation_router
        from .games_routes import router as games_router
        from .smarter_than_ai_routes import router as smarter_than_ai_router
        from .discord_routes import router as discord_router
        from .audio_models_routes import router as audio_models_router
        from .ollama_routes import router as ollama_router
        from .agent_workspace_routes import router as agent_workspace_router
        from .corp_routes import router as corp_router

        # Immediate Router Inclusion (Sync but fast)
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
        app.include_router(misaka_cipher_router)
        app.include_router(documentation_router)
        app.include_router(games_router)
        app.include_router(smarter_than_ai_router)
        app.include_router(discord_router)
        app.include_router(audio_models_router)
        app.include_router(ollama_router)
        app.include_router(agent_workspace_router)
        app.include_router(corp_router)

        # Step 2: Offload Heavy Component Initialization to a Thread
        # This keeps the FastAPI event loop free to serve requests.
        await asyncio.to_thread(perform_blocking_init)
        
        # Step 3: Start Workers (Must happen on event loop for async workers)
        startup_status["status"] = "Connecting Workers..."
        startup_status["progress"] = 80
        from workers.package_installer import get_installer_worker
        installer_worker = get_installer_worker()
        installer_worker.start()
        
        from core.orchestrator.task_queue import get_task_queue_manager
        task_manager = get_task_queue_manager(orchestrator, max_workers=4)
        await task_manager.start()
        
        # Step 4: Bootstrap Persistent Discord Worker
        try:
            from core.workspace.preferences_manager import get_preferences_manager
            prefs = get_preferences_manager()
            bot_token = prefs.get('nexus.discord_link.bot_token')
            discord_enabled = prefs.get('nexus.discord_link.enabled', False)
            
            if discord_enabled and bot_token and bot_token.strip():
                startup_status["status"] = "Bootstrapping Discord Service..."
                from core.workers.discord_worker import start_discord_service
                new_discord_worker = start_discord_service(orchestrator, task_manager, bot_token)
                
                # Store globally for API access
                global discord_worker
                discord_worker = new_discord_worker
                
                # Update router reference
                from .discord_routes import set_worker_instance
                set_worker_instance(new_discord_worker)
                
                # Run in background event loop
                asyncio.create_task(new_discord_worker.run_worker())
                logger.info("✓ Discord Persistent Worker bootstrapped")
            else:
                logger.info("Discord Bot Token not found in settings. Discord service skipped.")
        except Exception as e:
            logger.error(f"Failed to bootstrap Discord service: {e}")
        
        startup_status["status"] = "All systems operational"
        startup_status["progress"] = 95
        
        # Ensure system-metrics.json exists on startup
        metrics_path = Path(__file__).parent / "static" / "assets" / "system-metrics.json"
        if not metrics_path.exists():
            startup_status["status"] = "Generating System Metrics..."
            await _perform_telemetry_sync()
            
        startup_status["progress"] = 100
        startup_status["initialized"] = True
        logger.info("Aethvion Suite Web Server ready!")
        
        # Final console visibility block
        print("\n" + "=" * 66)
        print(f"  SYSTEM ONLINE: http://localhost:{os.environ.get('PORT', 8080)}")
        print("=" * 66 + "\n")
        
    except Exception as e:
        logger.error(f"Startup failed: {str(e)}", exc_info=True)
        startup_status["error"] = str(e)
        startup_status["status"] = "Startup Failed"

def perform_blocking_init():
    """Perform CPU-heavy synchronous initializations."""
    global nexus, factory, forge, orchestrator
    
    try:
        # Lazy imports for heavy core components
        from core.nexus_core import NexusCore
        from core.factory import AgentFactory
        from core.forge import ToolForge
        from core.orchestrator import MasterOrchestrator

        startup_status["status"] = "Initializing Nexus Core..."
        startup_status["progress"] = 15
        logger.info("Initializing Aethvion Suite Web Server...")
        
        nexus = NexusCore()
        nexus.initialize()
        app.state.nexus = nexus
        startup_status["status"] = "Nexus Core Ready"
        startup_status["progress"] = 40
        logger.info("✓ Nexus Core initialized")
        
        startup_status["status"] = "Spawning Agent Factory..."
        startup_status["progress"] = 50
        factory = AgentFactory(nexus)
        logger.info("✓ Factory initialized")
        
        startup_status["status"] = "Assembling Tool Forge..."
        startup_status["progress"] = 60
        forge = ToolForge(nexus)
        logger.info("✓ Forge initialized")
        
        startup_status["status"] = "Synchronizing Orchestrator..."
        startup_status["progress"] = 70
        orchestrator = MasterOrchestrator(nexus, factory, forge)
        
        def broadcast_step_callback(step_data: Dict):
            if main_event_loop:
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast(step_data, "chat"),
                    main_event_loop
                )
        
        orchestrator.set_step_callback(broadcast_step_callback)
        logger.info("✓ Master Orchestrator initialized")
        
    except Exception as e:
        logger.error(f"Blocking init failed: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down Aethvion Suite Web Server...")


# Static mounting moved to Instant Accessibility section


# Preferences API
class PreferenceUpdate(BaseModel):
    key: Optional[str] = None
    value: Any = None

@app.get("/api/preferences")
async def get_preferences():
    """Get all user preferences."""
    try:
        from core.workspace.preferences_manager import get_preferences_manager
        prefs = get_preferences_manager()
        return prefs.get_all()
    except Exception as e:
        logger.error(f"Failed to get preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/preferences/get")
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

@app.post("/api/preferences")
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

@app.post("/api/preferences/{key}")
async def set_preference(key: str, update: PreferenceUpdate):
    """Set a specific preference key."""
    try:
        from core.workspace.preferences_manager import get_preferences_manager
        prefs = get_preferences_manager()
        # Use key from URL path, value from body (or None)
        prefs.set(key, update.value)
        return {"status": "success", "key": key, "value": update.value}
    except Exception as e:
        logger.error(f"Failed to set preference {key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Routes
# Root route already defined in Instant Accessibility section


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "orchestrator": orchestrator is not None,
            "nexus": nexus is not None and nexus._initialized,
            "factory": factory is not None,
            "forge": forge is not None
        }
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(message: ChatMessage):
    """Send message to Master Orchestrator."""
    if not orchestrator:
        raise HTTPException(status_code=53, detail="Orchestrator not initialized")
    
    try:
        from core.orchestrator.task_queue import get_task_queue_manager
        task_manager = get_task_queue_manager()
        thread_id = message.thread_id or "default"
        
        task_id = await task_manager.submit_task(
            prompt=message.message,
            thread_id=thread_id
        )
        
        start_time = datetime.now()
        while (datetime.now() - start_time).total_seconds() < 60:
            task = task_manager.get_task(task_id)
            if task and task.status == "completed":
                result_dict = task.result
                return ChatResponse(
                    response=result_dict.get('response'),
                    trace_id=task.id,
                    actions_taken=result_dict.get('actions_taken', []),
                    tools_forged=result_dict.get('tools_forged', []),
                    agents_spawned=result_dict.get('agents_spawned', []),
                    execution_time=result_dict.get('execution_time', 0),
                    success=result_dict.get('success', True),
                    model_id=result_dict.get('model_id'),
                    usage=result_dict.get('usage')
                )
            elif task and task.status == "failed":
                raise HTTPException(status_code=500, detail=f"Task execution failed: {task.error}")
            await asyncio.sleep(0.5)
            
        raise HTTPException(status_code=504, detail="Task execution timed out")
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        logger.error(f"Chat endpoint error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/system/startup-status")
async def get_startup_status():
    """Get system initialization status."""
    return startup_status

@app.get("/api/system/ports")
async def get_system_ports():
    """Get dynamically registered system ports."""
    from core.utils.port_manager import PortManager
    return PortManager.get_registered_ports()


@app.post("/api/system/ports/{port}/terminate")
async def terminate_app_by_port(port: int):
    """
    Force-close any application listening on a specific local port.
    Useful for 'Closing' apps from the Port Manager UI.
    """
    # 1. Find the process listening on this port
    target_pid = None
    try:
        for proc in psutil.process_iter(['pid', 'name', 'connections']):
            try:
                for conn in proc.connections(kind='inet'):
                    if conn.laddr.port == port and conn.status == 'LISTEN':
                        target_pid = proc.pid
                        break
                if target_pid:
                    break
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
    except Exception as e:
        logger.error(f"Error scanning for process on port {port}: {e}")
        raise HTTPException(status_code=500, detail="Failed to scan processes")

    if not target_pid:
        # Check if it's just in the registry but not actually listening
        from core.utils.port_manager import PortManager
        PortManager.release_port(port)
        return {"status": "success", "message": f"Port {port} registry entry cleared (no active process found)."}

    # 2. Terminate the process
    try:
        proc = psutil.Process(target_pid)
        name = proc.name()
        
        # Kill logic: Try terminate first, then kill
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except psutil.TimeoutExpired:
            proc.kill()
        
        # 3. Clean up from our local tracking and the port registry
        from core.utils.port_manager import PortManager
        PortManager.release_port(port)
        
        # Scrub from RUNNING_APPS if it matches
        for app_name, pid in list(RUNNING_APPS.items()):
            if pid == target_pid:
                del RUNNING_APPS[app_name]
                break

        logger.info(f"Terminated application '{name}' on PID {target_pid} (Port {port})")
        return {"status": "success", "message": f"Terminated {name} (PID {target_pid}) on port {port}"}

    except psutil.NoSuchProcess:
        return {"status": "success", "message": "Process already stopped."}
    except Exception as e:
        logger.error(f"Failed to terminate process {target_pid}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to terminate process: {str(e)}")


@app.post("/api/system/shutdown")
async def shutdown_system():
    """Gracefully shut down the entire Aethvion Suite."""
    logger.info("Manual shutdown requested via API.")
    # Short delay to allow the response to reach the client
    asyncio.create_task(delayed_exit())
    return {"status": "success", "message": "System shutting down..."}

async def delayed_exit():
    await asyncio.sleep(1.0)
    logger.info("Exiting dashboard process (graceful).")
    os._exit(0)

@app.post("/api/system/modules/run")
async def run_module_script(request: dict):
    """Execute or stop a module startup script (.bat)."""
    module_name = request.get("module")
    action = request.get("action")
    
    if not module_name:
        raise HTTPException(status_code=400, detail="Module name required")

    # Map module names to their startup scripts (relative to project root)
    module_map = {
        "vtuber":    "apps/vtuber/Start_VTuber.bat",
        "tracking":  "apps/tracking/Start_Tracking.bat",
        "photo":     "apps/photo/Start_Photo.bat",
        "audio":     "apps/audio/Start_Audio.bat",
        "driveinfo": "apps/driveinfo/Start_DriveInfo.bat",
        "finance":   "apps/finance/Start_Finance.bat",
        "code":      "apps/code/Start_Code.bat",
        "hardwareinfo": "apps/hardwareinfo/Start_HardwareInfo.bat",
        "linkmap":      "apps/linkmap/Start_LinkMap.bat",
    }
    
    if module_name not in module_map:
        raise HTTPException(status_code=404, detail=f"Module {module_name} not found in registry")
        
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    script_path = root_dir / module_map[module_name]
    
    if not script_path.exists():
        script_path = Path(os.getcwd()) / module_map[module_name]
        if not script_path.exists():
            raise HTTPException(status_code=404, detail=f"Startup script not found at {script_path}")
        
    try:
        if action == "run":
            # Check if already running
            existing_pid = RUNNING_APPS.get(module_name)
            if existing_pid and psutil.pid_exists(existing_pid):
                return {"status": "success", "message": f"{module_name} is already running"}

            # For Windows, we use 'cmd /c' to run the batch file.
            # We use /k only for internal debugging if needed, /c is safer for general use.
            cmd = f'cmd /c "{script_path}"'
            
            logger.info(f"[Modules] Launching {module_name} via: {cmd}")
            
            import subprocess
            CREATE_NEW_CONSOLE = 0x00000010
            
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(script_path.parent),
                    creationflags=CREATE_NEW_CONSOLE,
                    shell=True,
                    env=os.environ.copy()
                )
                RUNNING_APPS[module_name] = proc.pid
                logger.info(f"[Modules] Started {module_name} with PID {proc.pid}")
                return {"status": "success", "message": f"Started {module_name} service", "pid": proc.pid}
            except Exception as launch_err:
                logger.error(f"[Modules] Failed to Popen {module_name}: {launch_err}")
                raise launch_err
            
        elif action == "stop":
            pid = RUNNING_APPS.get(module_name)
            if not pid or not psutil.pid_exists(pid):
                # If not in our PID map, try to find it by name as fallback
                found = False
                for p in psutil.process_iter(['pid', 'cmdline']):
                    try:
                        cmd = " ".join(p.info.get('cmdline') or [])
                        if module_name in cmd.lower() and ("python" in cmd.lower() or "bat" in cmd.lower()):
                            pid = p.info['pid']
                            found = True
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                if not found:
                    return {"status": "success", "message": f"{module_name} is not running"}

            # Kill tree
            try:
                parent = psutil.Process(pid)
                for child in parent.children(recursive=True):
                    child.kill()
                parent.kill()
                if module_name in RUNNING_APPS:
                    del RUNNING_APPS[module_name]
                return {"status": "success", "message": f"Stopped {module_name} service"}
            except psutil.NoSuchProcess:
                if module_name in RUNNING_APPS:
                    del RUNNING_APPS[module_name]
                return {"status": "success", "message": f"{module_name} was already terminated"}
        else:
            raise HTTPException(status_code=400, detail="Unsupported action")
    except Exception as e:
        logger.error(f"Module action {action} failed for {module_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/system/modules/open-folder")
async def open_module_folder(request: dict):
    """Open a module folder in Windows Explorer."""
    folder_path = request.get("path")
    if not folder_path:
        raise HTTPException(status_code=400, detail="Path required")
        
    import subprocess
    import os
    
    full_path = os.path.abspath(os.path.join(os.getcwd(), folder_path))
    
    if not os.path.exists(full_path):
         raise HTTPException(status_code=404, detail=f"Folder not found at {full_path}")
         
    try:
        os.startfile(full_path)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/system/status")
async def get_system_status():
    """Get full system status including nexus, orchestrator, firewall."""
    if not startup_status.get("initialized", False) or not nexus:
        raise HTTPException(status_code=503, detail="System not fully initialized")
    
    try:
        status = nexus.get_status()
        vitals = {"cpu_percent": 0, "ram_percent": 0, "ram_used_gb": 0, "ram_total_gb": 0}
        
        try:
            import psutil
            vitals["cpu_percent"] = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            vitals["ram_percent"] = mem.percent
            vitals["ram_used_gb"] = round(mem.used / (1024**3), 1)
            vitals["ram_total_gb"] = round(mem.total / (1024**3), 1)
        except ImportError: pass
            
        try:
            from core.workspace.usage_tracker import get_usage_tracker
            tracker = get_usage_tracker()
            usage_today = tracker.get_today_summary()
        except ImportError:
            usage_today = {"tokens": 0, "cost": 0.0}
        
        return {
            "nexus": status,
            "factory": {
                "active_agents": factory.registry.get_active_count() if factory else 0,
                "total_agents": len(factory.registry.get_all_agents()) if factory else 0
            },

            "vitals": vitals,
            "usage_today": usage_today
        }
    except Exception as e:
        logger.error(f"System status error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _get_git_remote_head(root_dir):
    """Fetch the latest commit hash from the remote repository."""
    try:
        output = subprocess.check_output(
            ['git', 'ls-remote', 'origin', 'HEAD'],
            cwd=str(root_dir),
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW
        )
        if output:
            return output.split()[0][:7]  # Short hash
    except Exception:
        pass
    return None

@app.get("/api/system/version-info")
async def get_version_info():
    """Get detailed local and remote version/commit information."""
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    
    # 1. Local Version
    from core.version import VERSION
    
    # 2. Current Commit (Local HEAD)
    current_commit = "Unknown"
    try:
        current_commit = subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=str(root_dir),
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW
        ).strip()
    except Exception: pass
    
    # 3. Full System Metadata (including last_update_commit and changelog)
    last_update_commit = "Unknown"
    changelog = []
    status_path = Path(__file__).parent / "static" / "assets" / "system-status.json"
    if status_path.exists():
        try:
            with open(status_path, 'r') as f:
                data = json.load(f)
                sys_data = data.get("system", {})
                last_update_commit = sys_data.get("last_update_commit", "Unknown")
                changelog = sys_data.get("changelog", [])
        except Exception: pass
        
    # 4. Remote Commit (latest on GitHub)
    remote_commit = await asyncio.to_thread(_get_git_remote_head, root_dir)
    
    return {
        "local": {
            "version": str(VERSION),
            "commit": current_commit,
            "last_update_commit": last_update_commit,
            "changelog": changelog
        },
        "remote": {
            "commit": remote_commit
        }
    }


@app.post("/api/system/update")
async def trigger_self_update():
    """Trigger the self-update process and shutdown with restart code."""
    import subprocess as _sp
    logger.info("Self-Update triggered via API")

    try:
        root_dir      = Path(__file__).resolve().parent.parent.parent.parent
        updater_script = root_dir / "core" / "updater.py"

        if not updater_script.exists():
            raise HTTPException(status_code=404, detail="Updater script not found")

        logger.info(f"Launching updater: {updater_script}")

        # Run in a thread so the event loop stays alive.
        # stdin=DEVNULL prevents git from hanging waiting for a credential
        # prompt when the server has no terminal attached (the main cause of
        # the previous 500 — asyncio.create_subprocess_exec left stdin open,
        # git stalled, the client request timed out).
        def _run_updater():
            return _sp.run(
                [sys.executable, str(updater_script)],
                cwd=str(root_dir),
                capture_output=True,
                text=True,
                timeout=180,          # hard cap: 3 min
                stdin=_sp.DEVNULL,    # ← no terminal; never block on input
                env={**os.environ},   # pass full PATH so git is always found
                creationflags=CREATE_NO_WINDOW
            )

        result = await asyncio.to_thread(_run_updater)

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "unknown error").strip()
            logger.error(f"Update failed (exit {result.returncode}): {err}")
            raise HTTPException(status_code=500, detail=f"Update failed: {err}")

        logger.info("Updater finished. Scheduling restart in 1.5 s...")

        # After successful update, we should capture the NEW commit hash and save it
        # so the UI knows what the 'last installed' commit is.
        try:
            new_commit = subprocess.check_output(
                ['git', 'rev-parse', '--short', 'HEAD'],
                cwd=str(root_dir),
                text=True,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW
            ).strip()
            
            status_path = Path(__file__).parent / "static" / "assets" / "system-status.json"
            if status_path.exists():
                with open(status_path, 'r') as f:
                    status_data = json.load(f)
                
                status_data["system"]["last_update_commit"] = new_commit
                status_data["system"]["last_sync"] = datetime.now().strftime("%Y-%m-%d")
                
                with open(status_path, 'w') as f:
                    json.dump(status_data, f, indent=4)
                logger.info(f"Updated system-status.json with new commit: {new_commit}")
        except Exception as e:
            logger.warning(f"Failed to update last_update_commit in JSON: {e}")

        async def _delayed_exit():
            await asyncio.sleep(1.5)
            logger.info("Exiting with code 42 for launcher restart.")
            os._exit(42)

        asyncio.create_task(_delayed_exit())

        return {
            "status":  "success",
            "message": "Update completed. Restarting system...",
            "output":  result.stdout,
        }

    except HTTPException:
        raise
    except TimeoutError:
        logger.error("Update timed out after 180 s")
        raise HTTPException(status_code=500, detail="Update timed out — check your network connection")
    except Exception as e:
        logger.error(f"Update error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/system/telemetry/sync")
async def sync_system_telemetry():
    """Sync system telemetry."""
    try:
        return await _perform_telemetry_sync()
    except Exception as e:
        logger.error(f"Telemetry sync error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def _perform_telemetry_sync() -> Dict[str, Any]:
    """Helper to calculate and save system metrics."""
    project_size = 0
    db_size = 0
    try:
        # Use project root (top-level)
        root_dir = Path(__file__).parent.parent.parent.parent
        for path in root_dir.rglob('*'):
            if path.is_file():
                try:
                    size = path.stat().st_size
                    project_size += size
                    # Heuristic for DB files
                    if 'chroma' in str(path) or '.db' in path.name:
                        db_size += size
                except (PermissionError, OSError):
                    continue
    except Exception as e:
        logger.warning(f"Error calculating project size: {e}")

    episodic_count = 0
    if orchestrator and hasattr(orchestrator, 'episodic_memory') and hasattr(orchestrator.episodic_memory, 'collection'):
        try:
            episodic_count = orchestrator.episodic_memory.collection.count()
        except Exception: pass

    # 4. Gather Git Info
    git_commit = "Unknown"
    try:
        git_commit = subprocess.check_output(
            ['git', 'log', '-1', '--format=%h - %s (%cr)'],
            cwd=str(root_dir),
            text=True,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW
        ).strip()
    except Exception:
        pass

    # 5. Count GGUF Models
    model_count = 0
    try:
        models_dir = root_dir / "localmodels" / "gguf"
        if models_dir.exists():
            model_count = len([f for f in models_dir.iterdir() if f.is_file()])
    except Exception:
        pass

    metrics = {
        "system": {
            "project_size_bytes": project_size,
            "db_size_bytes": db_size,
            "last_sync": datetime.now().isoformat(),
            "git_commit": git_commit,
            "model_count": model_count,
            "python_version": sys.version.split()[0],
            "platform": f"{platform.system()} {platform.release()}"
        },
        "memory": {"episodic_count": episodic_count}
    }

    metrics_path = Path(__file__).parent / "static" / "assets" / "system-metrics.json"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Use thread for file writing to avoid blocking event loop
    def save_json():
        with open(metrics_path, 'w') as f:
            json.dump(metrics, f, indent=2)
            
    await asyncio.to_thread(save_json)
    return metrics


@app.get("/api/agents/active")
async def get_active_agents():
    """Get active agents."""
    if not factory:
        raise HTTPException(status_code=503, detail="Factory not initialized")
    agents = factory.registry.get_all_agents()
    return {"count": len(agents), "agents": agents}


@app.post("/api/memory/search")
async def search_memory(request: MemorySearchRequest):
    """Search episodic memory."""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    try:
        results = orchestrator.query_memory(query=request.query, trace_id="WEB_SEARCH", domain=request.domain)
        serialized_results = []
        for r in results[:request.limit]:
            serialized_results.append({
                "memory_id": getattr(r, 'memory_id', str(r)),
                "summary": getattr(r, 'summary', str(r)),
                "domain": getattr(r, 'domain', "unknown"),
                "timestamp": getattr(r, 'timestamp', datetime.now().isoformat()),
                "event_type": getattr(r, 'event_type', "unknown")
            })
        return {"count": len(serialized_results), "results": serialized_results}
    except Exception as e:
        logger.error(f"Memory search error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workspace/files")
async def list_workspace_files(category: str = 'output', refresh: bool = False):
    """List files recursively based on category with optional caching."""
    global FILES_CACHE
    try:
        from core.workspace.workspace_manager import WorkspaceManager
        project_root = Path(__file__).parent.parent.parent.parent
        
        # Check cache if not refreshing
        if not refresh and FILES_CACHE:
            # We filter the cached data by category even if it's cached
            all_data = FILES_CACHE.get('data')
            if all_data:
                # Re-apply filtering logic to the cached data
                sub_dir = _get_subdir_for_category(category)
                filtered_files = [
                    f for f in all_data.get('files', []) 
                    if f['path'].startswith(sub_dir) or f['path'].startswith(sub_dir.replace('/', '\\'))
                ]
                
                # Recalculate stats for the filtered set
                total_files = sum(1 for f in filtered_files if not f.get('is_dir'))
                stats = {}
                for f in filtered_files:
                    if not f.get('is_dir'):
                        ext = f.get('file_type', 'txt')
                        stats[ext] = stats.get(ext, 0) + 1
                
                stats_percentages = {}
                if total_files > 0:
                    for ext, count in stats.items():
                        stats_percentages[ext] = round((count / total_files) * 100, 1)
                        
                return {
                    "count": len(filtered_files),
                    "files": filtered_files,
                    "stats": stats_percentages,
                    "cached": True
                }

        # Perform a fresh scan
        manager = WorkspaceManager(workspace_root=project_root, create_dirs=False)
        all_data = manager.list_outputs()
        
        # Update global cache
        FILES_CACHE = {
            'timestamp': datetime.now().timestamp(),
            'data': all_data
        }
        
        # Filter for the requested category
        sub_dir = _get_subdir_for_category(category)
        filtered_files = [
            f for f in all_data.get('files', []) 
            if f['path'].startswith(sub_dir) or f['path'].startswith(sub_dir.replace('/', '\\'))
        ]
        
        # Recalculate stats for the filtered set
        total_files = sum(1 for f in filtered_files if not f.get('is_dir'))
        stats = {}
        for f in filtered_files:
            if not f.get('is_dir'):
                ext = f.get('file_type', 'txt')
                stats[ext] = stats.get(ext, 0) + 1
        
        stats_percentages = {}
        if total_files > 0:
            for ext, count in stats.items():
                stats_percentages[ext] = round((count / total_files) * 100, 1)
                
        return {
            "count": len(filtered_files),
            "files": filtered_files,
            "stats": stats_percentages,
            "cached": False
        }
        
    except Exception as e:
        logger.error(f"Workspace file listing error for category {category}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def _get_subdir_for_category(category: str) -> str:
    """Helper to map categories to subdirectories."""
    if category in ['files', 'output']:
        return str(WS_OUTPUTS)
    elif category == 'screenshots':
        return str(WS_MEDIA / "screenshots")
    elif category == 'camera':
        return str(WS_MEDIA / "webcam")
    elif category == 'uploads':
        return str(WS_UPLOADS)
    return str(WS_OUTPUTS)

@app.post("/api/workspace/files/search")
async def search_workspace_files(req: SemanticSearchRequest):
    """Semantically search workspace files."""
    try:
        from core.memory.file_vector_store import get_file_vector_store
        from core.workspace import get_workspace_manager
        
        store = get_file_vector_store()
        workspace = get_workspace_manager()
        
        # Check if we need to index (first time)
        if store.collection.count() == 0:
            logger.info("Semantic index is empty, performing initial index...")
            all_files_data = workspace.list_outputs()
            all_files = all_files_data.get('files', [])
            for f in all_files:
                if not f.get('is_dir'):
                    path = workspace.workspace_root / f['path']
                    if path.exists():
                        try:
                            content = path.read_text(encoding='utf-8', errors='ignore')
                            store.index_file(f['path'], content, {"domain": f['domain']})
                        except: continue
        
        results = store.search(req.query, limit=req.limit, domain=req.domain)
        
        # Enrich results with full file info from WorkspaceManager
        all_metadata_data = workspace.list_outputs()
        all_metadata = all_metadata_data.get('files', [])
        meta_map = {f['path']: f for f in all_metadata}
        
        enriched_results = []
        for r in results:
            path = r['path']
            if path in meta_map:
                enriched_results.append({
                    **meta_map[path],
                    "relevance": round(1.0 - (r['score'] / 2.0), 3), # Convert distance to rough score
                    "excerpt": r['excerpt']
                })
        
        return {"results": enriched_results, "count": len(enriched_results)}
    except Exception as e:
        logger.error(f"Semantic file search error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/audio/process")
async def process_audio(req: AudioProcessRequest):
    """Process audio requests (TTS, STT, Edit, Music)."""
    trace_id = f"aud-{datetime.now().strftime('%H%M%S')}"
    try:
        from core.providers import ProviderManager
        manager = ProviderManager() # Initialize locally to avoid circular imports if needed
        
        import base64
        def decode_b64(b64_str: str) -> bytes:
            if "," in b64_str:
                b64_str = b64_str.split(",", 1)[1]
            return base64.b64decode(b64_str)

        if req.mode == 'stt':
            if not req.input_audio:
                raise HTTPException(status_code=400, detail="Input audio is required for transcription.")

            audio_bytes = decode_b64(req.input_audio)

            # Route local audio_models provider through tts_manager
            if req.provider == 'audio_models' or req.model == 'whisper':
                try:
                    import asyncio
                    from apps.audio.tts_manager import tts_manager
                    text = await asyncio.to_thread(tts_manager.transcribe, audio_bytes, req.model or 'whisper')
                    return {"success": True, "text": text, "model": req.model, "provider": "audio_models"}
                except Exception as local_err:
                    logger.warning(f"Local STT failed, falling back to provider: {local_err}")

            # API provider path
            target_provider = manager.model_to_provider_map.get(req.model) if req.model else None
            response = manager.transcribe(
                audio_bytes=audio_bytes,
                trace_id=trace_id,
                provider=target_provider,
                model=req.model if req.model else None
            )
            if not response.success:
                return {"success": False, "error": response.error}
            return {
                "success": True,
                "text": response.content,
                "model": response.model,
                "provider": response.provider
            }

        elif req.mode == 'tts':
            if not req.prompt:
                raise HTTPException(status_code=400, detail="Prompt text is required for speech generation.")

            # Route local audio_models provider through tts_manager
            if req.provider == 'audio_models':
                try:
                    import asyncio
                    from apps.audio.tts_manager import tts_manager
                    audio_bytes = await asyncio.to_thread(
                        tts_manager.generate_tts,
                        req.prompt, req.model, req.voice or None
                    )
                    audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
                    return {
                        "success": True,
                        "audio": f"data:audio/wav;base64,{audio_b64}",
                        "model": req.model,
                        "provider": "audio_models",
                        "format": "wav"
                    }
                except Exception as local_err:
                    logger.warning(f"Local TTS failed: {local_err}")
                    return {"success": False, "error": f"Local TTS error: {local_err}"}

            # API provider path
            target_provider = manager.model_to_provider_map.get(req.model) if req.model else None
            voice = req.voice or "alloy"
            response = manager.generate_speech(
                text=req.prompt,
                trace_id=trace_id,
                provider=target_provider,
                model=req.model if req.model else None,
                voice=voice
            )
            if not response.success:
                return {"success": False, "error": response.error}
            audio_bytes = response.metadata.get('audio')
            if not audio_bytes:
                return {"success": False, "error": "Provider returned success but no audio data found."}
            audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
            mime_type = f"audio/{response.metadata.get('format', 'mp3')}"
            return {
                "success": True,
                "audio": f"data:{mime_type};base64,{audio_b64}",
                "model": response.model,
                "provider": response.provider
            }
            
        else:
            return {
                "success": False,
                "error": f"Mode '{req.mode}' is not yet implemented in the backend."
            }
            
    except Exception as e:
        logger.error(f"Audio processing error: {str(e)}", exc_info=True)
        return {"success": False, "error": str(e)}


@app.post("/api/voice/transcribe")
async def voice_transcribe(request: Request):
    """
    Transcribe voice input for the chat interface.

    Accepts base64-encoded audio and returns the transcribed text using
    the voice input model configured in global settings.
    """
    trace_id = f"voice-{datetime.now().strftime('%H%M%S')}"
    try:
        body = await request.json()
        audio_b64: str = body.get("audio", "")
        model: Optional[str] = body.get("model")
        provider_name: Optional[str] = body.get("provider")

        if not audio_b64:
            return {"success": False, "error": "No audio data provided"}

        import base64
        # Strip data URI prefix if present
        if "," in audio_b64:
            audio_b64 = audio_b64.split(",", 1)[1]
        audio_bytes = base64.b64decode(audio_b64)

        # Resolve model/provider from settings if not provided
        if not model:
            from core.config.settings_manager import get_settings_manager
            sm = get_settings_manager()
            model = sm.get("voice.input_model", "browser")
            provider_name = sm.get("voice.input_provider", "browser")

        # "browser" means Web Speech API - should not reach here, but handle gracefully
        if model == "browser" or provider_name == "browser":
            return {"success": False, "error": "Browser voice model is handled client-side"}

        from core.providers import ProviderManager
        manager = ProviderManager()

        # Look up provider from model map if not specified
        if not provider_name and model:
            provider_name = manager.model_to_provider_map.get(model)

        response = manager.transcribe(
            audio_bytes=audio_bytes,
            trace_id=trace_id,
            provider=provider_name,
            model=model
        )

        if not response.success:
            return {"success": False, "error": response.error}

        return {
            "success": True,
            "text": response.content,
            "model": response.model,
            "provider": response.provider
        }

    except Exception as e:
        logger.error(f"Voice transcription error: {str(e)}", exc_info=True)
        return {"success": False, "error": str(e)}

@app.post("/api/workspace/files/reindex")
async def reindex_workspace_files():
    """Manually trigger a full re-index of workspace files."""
    try:
        from core.memory.file_vector_store import get_file_vector_store
        from core.workspace import get_workspace_manager
        
        store = get_file_vector_store()
        workspace = get_workspace_manager()
        
        # Clear existing
        store.client.delete_collection("workspace_files")
        store.collection = store.client.create_collection("workspace_files")
        
        all_files_data = workspace.list_outputs()
        all_files = all_files_data.get('files', [])
        indexed_count = 0
        for f in all_files:
            if not f.get('is_dir'):
                path = workspace.workspace_root / f['path']
                if path.exists():
                    try:
                        content = path.read_text(encoding='utf-8', errors='ignore')
                        if store.index_file(f['path'], content, {"domain": f['domain']}):
                            indexed_count += 1
                    except: continue
        
        return {"status": "success", "indexed_count": indexed_count}
    except Exception as e:
        logger.error(f"Re-indexing error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class ExplorerOpenRequest(BaseModel):
    path: str

@app.post("/api/workspace/explorer/open")
async def open_in_explorer(req: ExplorerOpenRequest):
    """Open a file or folder in the system's external explorer."""
    try:
        # Resolve full path relative to project root
        project_root = Path(__file__).parent.parent.parent.parent
        target_path = project_root / req.path
        if not target_path.exists():
            raise HTTPException(status_code=404, detail=f"Path not found: {req.path}")
            
        target_str = str(target_path.resolve())
        
        # Windows specific explorer command
        if os.name == 'nt':
            if target_path.is_file():
                # Open explorer and select the file
                subprocess.Popen(f'explorer /select,"{target_str}"')
            else:
                # Open directory
                os.startfile(target_str)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', '-R', target_str] if target_path.is_file() else ['open', target_str])
        else:
            # Linux fallback
            subprocess.Popen(['xdg-open', target_str if target_path.is_dir() else str(target_path.parent)])
            
        return {"status": "success", "opened": req.path}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        logger.error(f"Explorer open error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workspace/files/{domain}/{filename}")
async def download_workspace_file(domain: str, filename: str):
    """Download workspace file."""
    try:
        from core.workspace import get_workspace_manager
        workspace = get_workspace_manager()
        file_path = workspace.get_output_path(domain, filename)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {domain}/{filename}")
        return FileResponse(path=str(file_path), filename=filename, media_type="application/octet-stream")
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        logger.error(f"File download error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workspace/files/serve")
async def serve_workspace_file(path: str):
    """Serve a workspace file directly (useful for image previews)."""
    try:
        project_root = Path(__file__).parent.parent.parent.parent
        file_path = project_root / path
        
        # Security check: ensure the path resolves within the project root
        try:
            resolved_path = file_path.resolve()
            project_resolved = project_root.resolve()
            if not str(resolved_path).startswith(str(project_resolved)):
                raise HTTPException(status_code=403, detail="Access denied")
        except (Exception, ValueError):
            raise HTTPException(status_code=403, detail="Invalid path")

        if not resolved_path.exists() or not resolved_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
            
        return FileResponse(path=str(resolved_path))
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        logger.error(f"File serve error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workspace/files/content")
async def get_workspace_file_content(path: str):
    """
    Serve the content of a file from the workspace data directory.
    This is used to render captured screenshots, webcam images, and uploads in the UI.
    Supports absolute paths if they are within the project data directory.
    """
    try:
        requested_path = Path(path).resolve()
        # Define project root relative to this file: core/interfaces/dashboard/server.py
        project_root = Path(__file__).parent.parent.parent.parent.resolve()
        data_parent = (project_root / "data").resolve()
        
        # Security check: Ensure the path is within the data directory
        if not str(requested_path).startswith(str(data_parent)):
            logger.warning(f"Unauthorized path access attempt: {path}")
            raise HTTPException(status_code=403, detail="Unauthorized: Path outside of workspace data.")

        if not requested_path.exists() or not requested_path.is_file():
            logger.warning(f"File not found: {path}")
            raise HTTPException(status_code=404, detail="File not found.")

        import mimetypes
        mime_type, _ = mimetypes.guess_type(str(requested_path))
        if not mime_type:
            mime_type = "application/octet-stream"

        return FileResponse(str(requested_path), media_type=mime_type)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving file content: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/traces/{trace_id}")
async def get_trace_details(trace_id: str):
    """Get trace details."""
    try:
        from core.memory import get_episodic_memory
        episodic = get_episodic_memory()
        memories = episodic.get_by_trace_id(trace_id)
        if not memories:
            raise HTTPException(status_code=404, detail=f"No data found for trace {trace_id}")
        return {
            "trace_id": trace_id,
            "memory_count": len(memories),
            "memories": [{"memory_id": m.memory_id, "summary": m.summary, "event_type": m.event_type, "timestamp": m.timestamp, "domain": m.domain} for m in memories]
        }
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        logger.error(f"Trace details error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket endpoints
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await manager.connect(websocket, "chat")
    try:
        while True:
            data = await websocket.receive_json()
            if "message" in data:
                user_message = data["message"]
                # Prepend any attached file context before sending to orchestrator
                attached_context = data.get("attached_context")
                if attached_context:
                    user_message = f"{attached_context}\n\n{user_message}"
                result = await asyncio.to_thread(orchestrator.process_message, user_message)
                await websocket.send_json({"type": "response", "trace_id": result.trace_id, "response": result.response, "actions": result.actions_taken, "success": result.success})
    except (WebSocketDisconnect, RuntimeError):
        pass # Client disconnected or connection closed
    except Exception as e:
        logger.error(f"WebSocket chat error: {e}")
    finally:
        manager.disconnect(websocket, "chat")

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await manager.connect(websocket, "logs")
    try:
        while True:
            await asyncio.sleep(10)
            await websocket.send_json({"type": "heartbeat", "timestamp": datetime.now().isoformat()})
    except (WebSocketDisconnect, RuntimeError):
        pass # Client disconnected or connection closed
    except Exception as e:
        logger.error(f"WebSocket logs error: {e}")
    finally:
        manager.disconnect(websocket, "logs")

@app.websocket("/ws/agents")
async def websocket_agents(websocket: WebSocket):
    await manager.connect(websocket, "agents")
    try:
        while True:
            agents = factory.registry.get_all_agents()
            await websocket.send_json({"type": "agents_update", "count": len(agents), "agents": agents, "timestamp": datetime.now().isoformat()})
            await asyncio.sleep(2)
    except (WebSocketDisconnect, RuntimeError):
        pass # Client disconnected or connection closed
    except Exception as e:
        logger.error(f"WebSocket agents error: {e}")
    finally:
        manager.disconnect(websocket, "agents")

async def broadcast_log(message: str, level: str = "info"):
    await manager.broadcast({"type": "log", "level": level, "message": message, "timestamp": datetime.now().isoformat()}, "logs")
