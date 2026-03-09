"""
Misaka Cipher - FastAPI Web Server
REST API and WebSocket server for web dashboard
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
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
from datetime import datetime

from core.utils import get_logger
from core.config.settings_manager import get_settings_manager

logger = get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Misaka Cipher - Nexus Portal",
    description="Autonomous AI Orchestration System",
    version="1.0.0"
)

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

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main dashboard page instantly."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        content = index_path.read_text(encoding="utf-8")
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        return HTMLResponse(content=content, headers=headers)
    return HTMLResponse("<h1>Misaka Cipher Dashboard</h1><p>index.html not found</p>")

# Mount static files immediately
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Global instances (initialized on startup in background)
orchestrator = None
nexus = None
factory = None
forge = None
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
        from .package_routes import router as package_router
        from .task_routes import router as task_router
        from .tool_routes import router as tool_router
        from .memory_routes import router as memory_router
        from .registry_routes import router as registry_router
        from .usage_routes import router as usage_router
        from .arena_routes import router as arena_router
        from .settings_routes import router as settings_router
        from .image_routes import router as image_router
        from .advanced_aiconv_routes import router as adv_aiconv_router
        from .assistant_routes import router as assistant_router
        from .misaka_cipher_routes import router as misaka_cipher_router
        from .documentation_routes import router as documentation_router
        from .games_routes import router as games_router
        
        # Immediate Router Inclusion (Sync but fast)
        app.include_router(package_router)
        app.include_router(task_router)
        app.include_router(tool_router)
        app.include_router(memory_router)
        app.include_router(registry_router)
        app.include_router(usage_router)
        app.include_router(arena_router)
        app.include_router(settings_router)
        app.include_router(image_router)
        app.include_router(adv_aiconv_router)
        app.include_router(assistant_router)
        app.include_router(misaka_cipher_router)
        app.include_router(documentation_router)
        app.include_router(games_router)

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
        
        startup_status["status"] = "All systems operational"
        startup_status["progress"] = 95
        
        # Ensure system-metrics.json exists on startup
        metrics_path = Path(__file__).parent / "static" / "assets" / "system-metrics.json"
        if not metrics_path.exists():
            startup_status["status"] = "Generating System Metrics..."
            await _perform_telemetry_sync()
            
        startup_status["progress"] = 100
        startup_status["initialized"] = True
        logger.info("Misaka Cipher Web Server ready!")
        
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
        logger.info("Initializing Misaka Cipher Web Server...")
        
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
    logger.info("Shutting down Misaka Cipher Web Server...")


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


@app.get("/api/system/status")
async def get_system_status():
    """Get lightweight system status."""
    if not nexus:
        raise HTTPException(status_code=503, detail="System not initialized")
    
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
            "forge": {"total_tools": len(forge.registry.list_tools()) if forge else 0},
            "vitals": vitals,
            "usage_today": usage_today
        }
    except Exception as e:
        logger.error(f"System status error: {str(e)}", exc_info=True)
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

    metrics = {
        "system": {
            "project_size_bytes": project_size,
            "db_size_bytes": db_size,
            "last_sync": datetime.now().isoformat()
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
async def list_workspace_files(category: str = 'output'):
    """List files recursively based on category."""
    try:
        from core.workspace.workspace_manager import WorkspaceManager
        project_root = Path(__file__).parent.parent.parent.parent
        
        # We use project_root as the manager root so that 'path' is relative to project root
        # and works across all categories for 'serve' and 'explorer'
        # Crucial: set create_dirs=False to prevent scanning from polluting the root with domain folders
        manager = WorkspaceManager(workspace_root=project_root, create_dirs=False)
        
        # Determine target subdirectory relative to project root
        sub_dir = ""
        if category in ['files', 'output']:
            sub_dir = "data/outputfiles"
        elif category == 'screenshots':
            sub_dir = "data/workspace/media/screenshots"
        elif category == 'camera':
            sub_dir = "data/workspace/media/webcam"
        elif category == 'uploads':
            sub_dir = "data/workspace/uploads"
        else:
            sub_dir = "data/outputfiles"
            
        # Get all outputs from the project root
        all_data = manager.list_outputs()
        
        # Filter files that belong to the target sub_dir
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
            "stats": stats_percentages
        }
        
    except Exception as e:
        logger.error(f"Workspace file listing error for category {category}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

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
            
            # Identify provider/model
            # If model is specified, find the provider for it
            target_provider = None
            if req.model:
                target_provider = manager.model_to_provider_map.get(req.model)
            
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
            
            # Identify provider/model
            target_provider = None
            if req.model:
                target_provider = manager.model_to_provider_map.get(req.model)
            
            # Get voice/format from kwargs if we had them, otherwise defaults
            # For now use defaults or simple extraction from prompt/model
            voice = "alloy"
            
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
                
            # Return as base64 for the frontend player
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
