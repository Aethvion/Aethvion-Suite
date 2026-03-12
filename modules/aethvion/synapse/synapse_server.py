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

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Synapse Tracking Engine", version="1.0.0")
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

@app.post("/api/trackers/start/{tracker_name}")
async def start_tracker(tracker_name: str):
    """Start a specific tracking backend."""
    success = synapse_core.start_tracker(tracker_name, config={"name": tracker_name})
    if success:
        return JSONResponse({"status": "success", "message": f"Started {tracker_name}"})
    return JSONResponse({"status": "error", "message": f"Failed to start {tracker_name}"}, status_code=400)

@app.post("/api/trackers/stop")
async def stop_tracker():
    """Stop the current tracking backend."""
    synapse_core.stop_tracker()
    return JSONResponse({"status": "success", "message": "Tracker stopped"})

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
    port = int(os.getenv("SYNAPSE_PORT", "8002"))
    print(f"👁️ Synapse Tracking Engine → http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    launch()
