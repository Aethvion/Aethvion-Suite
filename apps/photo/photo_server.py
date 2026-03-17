import os
import sys
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import shutil
from datetime import datetime

# Add workspace root to path
WORKSPACE_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(WORKSPACE_ROOT))
from core.utils.port_manager import PortManager

from core.utils import get_logger

logger = get_logger("AethvionPhoto")

app = FastAPI(
    title="Aethvion Photo — Image Forge",
    description="Professional Image Editing Service",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
APP_DIR = Path(__file__).parent
DATA_DIR = WORKSPACE_ROOT / "data" / "apps" / "photo"
PROJECTS_DIR = DATA_DIR / "projects"
UPLOADS_DIR = DATA_DIR / "uploads"

for d in [PROJECTS_DIR, UPLOADS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Mount Viewer
VIEWER_DIR = APP_DIR / "viewer"
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = VIEWER_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Aethvion Photo</h1><p>Viewer not found.</p>", status_code=404)

if VIEWER_DIR.exists():
    app.mount("/css", StaticFiles(directory=str(VIEWER_DIR / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(VIEWER_DIR / "js")), name="js")
    app.mount("/assets", StaticFiles(directory=str(VIEWER_DIR / "assets")), name="assets")

# Mount Data for served files
app.mount("/api/files/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

class StatusResponse(BaseModel):
    status: str
    version: str
    uptime: str
    directories: Dict[str, bool]

@app.get("/api/status", response_model=StatusResponse)
async def get_status():
    return {
        "status": "online",
        "version": "1.0.0",
        "uptime": datetime.now().isoformat(),
        "directories": {
            "projects": PROJECTS_DIR.exists(),
            "uploads": UPLOADS_DIR.exists()
        }
    }

@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    """Upload an image to the workspace."""
    try:
        ext = Path(file.filename).suffix.lower()
        if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
            raise HTTPException(status_code=400, detail="Unsupported file format")
        
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        save_path = UPLOADS_DIR / filename
        
        with save_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        return {
            "filename": filename,
            "url": f"/api/files/uploads/{filename}",
            "size": save_path.stat().st_size
        }
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/process/remove-bg")
async def remove_background(filename: str = Form(...)):
    """Remove background using rembg."""
    try:
        input_path = UPLOADS_DIR / filename
        if not input_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        output_filename = f"nobg_{filename}"
        output_path = UPLOADS_DIR / output_filename
        
        # Integration with rembg
        try:
            from rembg import remove
            from PIL import Image
            import io
            
            with input_path.open("rb") as i:
                input_data = i.read()
                output_data = remove(input_data)
                
                with output_path.open("wb") as o:
                    o.write(output_data)
                    
            return {
                "success": True,
                "original": filename,
                "processed": output_filename,
                "url": f"/api/files/uploads/{output_filename}"
            }
        except ImportError:
            logger.warning("rembg not installed, skipping actual processing")
            return {"success": False, "error": "rembg not installed"}
            
    except Exception as e:
        logger.error(f"Background removal failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ProjectSave(BaseModel):
    name: str
    data: str # JSON string

@app.post("/api/save-project")
async def save_project(project: ProjectSave):
    """Save an .aethphoto project to the server."""
    try:
        # Sanitize filename
        filename = project.name.replace(" ", "_").replace("/", "_").replace("\\", "_")
        if not filename.endswith(".aethphoto"):
            filename += ".aethphoto"
        
        save_path = PROJECTS_DIR / filename
        save_path.write_text(project.data, encoding="utf-8")
        
        return {
            "success": True,
            "filename": filename,
            "path": str(save_path)
        }
    except Exception as e:
        logger.error(f"Save project failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects")
async def list_projects():
    """List all saved projects on the server."""
    try:
        projects = []
        for p in PROJECTS_DIR.glob("*.aethphoto"):
            stats = p.stat()
            projects.append({
                "name": p.stem,
                "filename": p.name,
                "size": stats.st_size,
                "modified": datetime.fromtimestamp(stats.st_mtime).isoformat()
            })
        return {"projects": sorted(projects, key=lambda x: x['modified'], reverse=True)}
    except Exception as e:
        logger.error(f"List projects failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/load-project/{filename}")
async def load_project(filename: str):
    """Load a specific project from the server."""
    try:
        path = PROJECTS_DIR / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail="Project not found")
        return {"data": path.read_text(encoding="utf-8")}
    except Exception as e:
        logger.error(f"Load project failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def launch():
    base_port = int(os.getenv("PHOTO_PORT", "8086"))
    port = PortManager.bind_port("Aethvion Photo", base_port)
    logger.info(f"🎨 Aethvion Photo Service → http://localhost:{port}")
    try:
        from core.utils.browser import open_app_window
        open_app_window(f"http://localhost:{port}", delay=1.5)
    except Exception:
        pass
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    launch()
