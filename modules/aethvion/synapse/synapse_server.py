import os
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Add module dir and project root to sys.path
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(MODULE_DIR, "..", "..", ".."))
for p in (MODULE_DIR, PROJECT_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from modules.aethvion.synapse.synapse_core import synapse_core
from modules.aethvion.synapse.trackers.capture_manager import capture_manager
from modules.aethvion.synapse.osf_manager import osf_manager

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Synapse Tracking Engine", version="1.0.0")
app.state.preview_active = False
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
VIEWER_DIR = BASE_DIR / "viewer"

app.mount("/viewer", StaticFiles(directory=str(VIEWER_DIR)), name="viewer")

# ---------------------------------------------------------------------------
# REST API (Control Trackers)
# ---------------------------------------------------------------------------

@app.get("/api/trackers")
async def list_trackers():
    """List available trackers and current status."""
    active = synapse_core.active_tracker.config.get("name", "mediapipe") if synapse_core.active_tracker else None
    return JSONResponse({
        "available": synapse_core.get_supported_trackers(),
        "active": active,
        "is_running": synapse_core.active_tracker.is_running if synapse_core.active_tracker else False
    })

@app.get("/api/trackers/debug")
async def tracker_debug():
    """Return debug stats from the active tracker (especially useful for OpenSeeFace)."""
    tracker = synapse_core.active_tracker
    if not tracker:
        return JSONResponse({"active": False})
    name = tracker.config.get("name", "unknown")
    stats = getattr(tracker, "stats", {})
    return JSONResponse({
        "active":      True,
        "name":        name,
        "is_running":  tracker.is_running,
        "stats":       stats,
    })

from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

class StartConfig(BaseModel):
    source: str   = "webcam:0"
    osf_host: str = "127.0.0.1"
    osf_port: int = 11573

@app.post("/api/trackers/start/{tracker_name}")
async def start_tracker(tracker_name: str, config: StartConfig):
    """Start a specific tracking backend with source and optional OSF config."""
    success = synapse_core.start_tracker(tracker_name, config={
        "name":     tracker_name,
        "source":   config.source,
        "osf_host": config.osf_host,
        "osf_port": config.osf_port,
    })
    if success:
        src = f"UDP {config.osf_host}:{config.osf_port}" if tracker_name == "openseeface" else config.source
        return JSONResponse({"status": "success", "message": f"Started {tracker_name} on {src}"})
    return JSONResponse({"status": "error", "message": f"Failed to start {tracker_name}"}, status_code=400)

@app.post("/api/trackers/stop")
async def stop_tracker():
    """Stop the current tracking backend."""
    # OpenSeeFace tracker owns no camera — don't touch CaptureManager for it
    tracker_name = (synapse_core.active_tracker.config.get("name", "") if synapse_core.active_tracker else "")
    synapse_core.stop_tracker()
    if not app.state.preview_active and tracker_name != "openseeface":
        capture_manager.stop()
    return JSONResponse({"status": "success", "message": "Tracker stopped"})

# ---------------------------------------------------------------------------
# OSF Process Management
# ---------------------------------------------------------------------------

@app.get("/api/osf/status")
async def osf_status():
    """Return install + process status for the bundled OpenSeeFace binary."""
    return JSONResponse(osf_manager.get_status())


@app.post("/api/osf/install")
async def osf_install():
    """Download and extract OpenSeeFace; streams SSE progress to the client."""
    async def _stream():
        async for chunk in osf_manager.install():
            yield chunk
    return StreamingResponse(_stream(), media_type="text/event-stream")


class OsfLaunchConfig(BaseModel):
    camera_index: int = 0
    port: int         = 11573
    host: str         = "127.0.0.1"


@app.post("/api/osf/launch")
async def osf_launch(config: OsfLaunchConfig):
    """Start the OpenSeeFace facetracker process."""
    result = osf_manager.launch(config.camera_index, config.port, config.host)
    return JSONResponse(result, status_code=200 if result["success"] else 400)


@app.post("/api/osf/stop-process")
async def osf_stop_process():
    """Terminate the OpenSeeFace facetracker process."""
    return JSONResponse(osf_manager.stop_process())


@app.post("/api/osf/uninstall")
async def osf_uninstall():
    """Remove the bundled OpenSeeFace installation."""
    return JSONResponse(osf_manager.uninstall())


@app.get("/api/osf/log")
async def osf_log():
    """Return the last 40 lines of the facetracker process output."""
    return JSONResponse({"log": osf_manager.get_log_tail(40)})


@app.get("/api/osf/files")
async def osf_files():
    """List all files in the OpenSeeFace install directory (for diagnostics)."""
    from modules.aethvion.synapse.osf_manager import OSF_DIR
    if not OSF_DIR.exists():
        return JSONResponse({"error": "Not installed", "files": []})
    files = [str(p.relative_to(OSF_DIR)) for p in sorted(OSF_DIR.rglob("*")) if p.is_file()]
    return JSONResponse({"dir": str(OSF_DIR), "count": len(files), "files": files})


@app.post("/api/preview/start")
async def start_preview(config: StartConfig):
    """Start the raw video preview."""
    capture_manager.start(config.source)
    app.state.preview_active = True
    return JSONResponse({"status": "success", "message": f"Preview started on {config.source}"})

@app.post("/api/preview/stop")
async def stop_preview():
    """Stop the raw video preview."""
    app.state.preview_active = False
    # If tracker is not active, we can release hardware
    if not (synapse_core.active_tracker and synapse_core.active_tracker.is_running):
        capture_manager.stop()
    return JSONResponse({"status": "success", "message": "Preview stopped"})

@app.get("/video_feed")
async def video_feed():
    """MJPEG streaming endpoint for Synapse (Tracker processed OR Raw Preview)."""
    import asyncio
    import cv2
    async def frame_generator():
        while True:
            frame = None
            
            # 1. Try tracker processed frame first (mesh overlay)
            if synapse_core.active_tracker and hasattr(synapse_core.active_tracker, 'latest_frame'):
                frame = synapse_core.active_tracker.latest_frame
                
            # 2. Fallback to raw frame from CaptureManager if preview is enabled
            if frame is None and app.state.preview_active:
                raw = capture_manager.get_frame()
                if raw is not None:
                    ret, buffer = cv2.imencode('.jpg', raw, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                    if ret:
                        frame = buffer.tobytes()
            
            if frame:
                yield (b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            
            await asyncio.sleep(1/30.0)
            
    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")

# ---------------------------------------------------------------------------
# WebSocket (Stream Tracking Data)
# ---------------------------------------------------------------------------

@app.websocket("/ws/tracking")
async def websocket_tracking_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint that streams tracking parameters to clients (e.g. Specter/Dashboard).
    """
    await websocket.accept()
    
    # Callback to push data from SynapseBridge to the socket
    def on_new_data(tracking_data: dict):
        # We must push to the asyncio event loop safely, but since we are in 
        # a synchronous callback invoked by a thread, we use a simple queue or push sync
        # Note: FastAPI WebSockets in async usually require async handling.
        # For simplicity in this bridge, we'll poll inside the async loop.
        pass

    synapse_core.bridge.subscribe(on_new_data)
    
    try:
        import asyncio
        while True:
            # Instead of a complex thread-safe queue for this example, we poll the bridge 
            # at ~30 FPS limit to ensure stable streaming to the dashboard.
            data = synapse_core.bridge.get_last_frame()
            if data:
                payload = {
                    "type": "params",
                    "params": data
                }
                await websocket.send_json(payload)
            await asyncio.sleep(1/30.0)
    except WebSocketDisconnect:
        print("[Synapse WebSocket] Client disconnected.")
    except Exception as e:
        print(f"[Synapse WebSocket] Error: {e}")
    finally:
        synapse_core.bridge.unsubscribe(on_new_data)


# ---------------------------------------------------------------------------
# Front-end View
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    idx = VIEWER_DIR / "index.html"
    return idx.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

def launch():
    from core.utils.port_manager import PortManager
    base_port = int(os.getenv("SYNAPSE_PORT", "8082"))
    port = PortManager.bind_port("Synapse Tracking", base_port)
    
    print(f"👁️ Synapse Tracking Engine → http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    launch()
