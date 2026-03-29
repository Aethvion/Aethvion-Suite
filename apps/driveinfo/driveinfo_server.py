"""
Aethvion Drive Info — FastAPI Server
"""

import subprocess as _sp
import sys
from pathlib import Path

# Ensure both the project root and this app's directory are importable
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))                          # for driveinfo_core
sys.path.insert(0, str(_HERE.parent.parent))            # project root for core.*

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from core.utils import fastapi_utils

from driveinfo_core import (
    DATA_DIR,
    scan_state,
    start_scan,
    cancel_scan,
    list_scans,
    load_scan,
    delete_scan,
    list_drives,
    generate_display_scan,
    _display_path,
)

# ---------------------------------------------------------------------------
app = FastAPI(title="Aethvion Drive Info", version="1.0.0")
fastapi_utils.add_dev_cache_control(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VIEWER_DIR = Path(__file__).parent / "viewer"
app.mount("/viewer", StaticFiles(directory=str(VIEWER_DIR), html=True), name="viewer")

# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------

from fastapi import Request

@app.get("/")
async def root(request: Request):
    query = f"?{request.query_params}" if request.query_params else ""
    return RedirectResponse(url=f"/viewer/index.html{query}")

# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    path: str

@app.post("/api/scan")
async def api_start_scan(req: ScanRequest):
    ok = start_scan(req.path.strip())
    if not ok:
        raise HTTPException(status_code=409, detail="A scan is already running")
    return {"started": True, "path": req.path}

@app.get("/api/scan/status")
async def api_scan_status():
    return scan_state.to_dict()

@app.get("/api/scan/result")
async def api_scan_result():
    if scan_state.running:
        raise HTTPException(status_code=409, detail="Scan still running")
    if scan_state.error:
        raise HTTPException(status_code=500, detail=scan_state.error)
    if not scan_state.save_path or not Path(scan_state.save_path).exists():
        raise HTTPException(status_code=404, detail="No scan result available")
    full_path    = Path(scan_state.save_path)
    display_path = _display_path(full_path)
    serve_path   = display_path if display_path.exists() else full_path
    return FileResponse(
        path=str(serve_path),
        media_type="application/json",
        filename=serve_path.name,
    )

@app.post("/api/scan/cancel")
async def api_cancel_scan():
    cancel_scan()
    return {"cancelled": True}

# ---------------------------------------------------------------------------
# Saved scans
# ---------------------------------------------------------------------------

@app.get("/api/scans")
async def api_list_scans():
    return list_scans()

@app.get("/api/scans/{filename}")
def api_load_scan(filename: str):
    # Sync endpoint → FastAPI runs it in a thread pool so blocking I/O is fine.
    path = DATA_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Scan file not found")

    display_path = _display_path(path)

    # Generate display version on-demand for pre-existing large scans that
    # were saved before the display-scan feature existed.
    if not display_path.exists():
        file_size = path.stat().st_size
        if file_size > 20 * 1024 * 1024:   # > 20 MB → generate pruned view
            generate_display_scan(path)     # blocking but runs in thread pool

    serve_path = display_path if display_path.exists() else path
    return FileResponse(
        path=str(serve_path),
        media_type="application/json",
        filename=serve_path.name,
    )

@app.delete("/api/scans/{filename}")
async def api_delete_scan(filename: str):
    delete_scan(filename)
    return {"deleted": filename}

# ---------------------------------------------------------------------------
# Drives
# ---------------------------------------------------------------------------

@app.get("/api/drives")
async def api_drives():
    return list_drives()

# ---------------------------------------------------------------------------
# Open in Explorer
# ---------------------------------------------------------------------------

class ExplorerRequest(BaseModel):
    path: str

@app.post("/api/open-explorer")
async def api_open_explorer(req: ExplorerRequest):
    """Open *path* in the OS file manager (Windows Explorer, macOS Finder, etc.)."""
    path = req.path.strip()
    if not path:
        raise HTTPException(status_code=400, detail="No path provided")
    try:
        if sys.platform == "win32":
            # Use explorer.exe — works for both files and directories
            _sp.Popen(["explorer", path], shell=False)
        elif sys.platform == "darwin":
            _sp.Popen(["open", path])
        else:
            _sp.Popen(["xdg-open", path])
        return {"opened": True, "path": path}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def api_health():
    return {"status": "ok", "module": "driveinfo"}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def launch():
    import uvicorn
    import os
    from core.utils.port_manager import PortManager
    base_port = int(os.getenv("DRIVEINFO_PORT", "8088"))
    port = PortManager.bind_port("Aethvion Drive Info", base_port)
    print(f"  Aethvion Drive Info  →  http://localhost:{port}")
    try:
        from core.utils.browser import open_app_window
        open_app_window(f"http://localhost:{port}", delay=1.5)
    except Exception:
        pass
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    launch()
