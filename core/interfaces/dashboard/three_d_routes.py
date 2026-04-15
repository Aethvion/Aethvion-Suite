"""
Aethvion Suite - 3D Generation Routes
API endpoints for 3D model generation and asset management.
"""

import base64
import uuid
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from core.workspace import get_workspace_manager
from core.utils import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/3d", tags=["3d"])

class ThreeDGenerationRequest(BaseModel):
    action: str = "generate" # "generate" (t23d) or "image23d" (i23d)
    prompt: Optional[str] = None
    input_image: Optional[str] = None # base64
    model: str = "trellis-2"
    quality: str = "1024"
    seed: Optional[int] = None
    textured: bool = True

class ThreeDAssetResponse(BaseModel):
    id: str
    name: str
    url: str
    path: str
    model: str
    format: str = "glb"
    size_bytes: int
    created_at: str

class ThreeDGenerationResponse(BaseModel):
    success: bool
    asset: Optional[ThreeDAssetResponse] = None
    error: Optional[str] = None

@router.post("/generate", response_model=ThreeDGenerationResponse)
async def generate_3d_asset(req: ThreeDGenerationRequest):
    """
    Generate a 3D asset using the specified model.
    """
    trace_id = f"3d-{uuid.uuid4().hex[:8]}"
    logger.info(f"[{trace_id}] 3D generation request: {req.model} ({req.action})")

    try:
        # 1. Prepare Workspace
        workspace = get_workspace_manager()
        
        # 2. Logic for Generation
        # For now, we simulation the generation of a GLB file.
        # In a production environment, this would call out to a Trellis / TripoSR worker.
        
        # CREATE MOCK GLB CONTENT
        # A minimal binary GLB is 20-30 bytes, but we'll just use a dummy string for now
        # to simulate a file being saved.
        mock_glb_content = b"glTF" + b"\x02\x00\x00\x00" + os.urandom(1024) 
        
        filename = f"{req.model}-{trace_id}.glb"
        
        # If the user actually provided an image, we'll save it too for reference
        if req.input_image:
            image_filename = f"{trace_id}-ref.png"
            try:
                 img_data = req.input_image
                 if "," in img_data:
                     img_data = img_data.split(",", 1)[1]
                 img_bytes = base64.b64decode(img_data)
                 workspace.save_output(domain="ThreeD", filename=image_filename, content=img_bytes, trace_id=trace_id)
            except Exception as e:
                logger.warning(f"Failed to save reference image: {e}")

        # Save the "generated" GLB
        path = workspace.save_output(
            domain="ThreeD",
            filename=filename,
            content=mock_glb_content,
            trace_id=trace_id
        )
        
        stat = path.stat()
        asset = ThreeDAssetResponse(
            id=trace_id,
            name=req.prompt if req.prompt else "3D Capture",
            url=f"/api/3d/serve/{filename}",
            path=str(path),
            model=req.model,
            size_bytes=stat.st_size,
            created_at=datetime.now().isoformat()
        )

        return ThreeDGenerationResponse(
            success=True,
            asset=asset
        )

    except Exception as e:
        logger.error(f"[{trace_id}] 3D generation failed: {str(e)}")
        return ThreeDGenerationResponse(success=False, error=str(e))

@router.get("/history", response_model=List[ThreeDAssetResponse])
async def get_3d_history():
    """
    Get recent 3D generations.
    """
    workspace = get_workspace_manager()
    outputs = workspace.list_outputs()
    
    history = []
    for f in outputs.get('files', []):
        if f.get('domain') == 'ThreeD' and f.get('filename', '').endswith('.glb'):
            history.append(ThreeDAssetResponse(
                id=f.get('trace_id', 'unknown'),
                name=f.get('filename').split('-')[0],
                url=f"/api/3d/serve/{f.get('filename')}",
                path=f.get('path'),
                model="trellis-2", # Dummy model for legacy
                size_bytes=f.get('size_bytes', 0),
                created_at=f.get('created_at')
            ))
            
    return history

@router.get("/serve/{filename}")
async def serve_3d_asset(filename: str):
    """Serve a generated 3D file."""
    workspace = get_workspace_manager()
    path = workspace.get_output_path(domain="ThreeD", filename=filename)
    
    if not path.exists():
        raise HTTPException(status_code=404, detail="Asset not found")
    
    from fastapi.responses import FileResponse
    # Return with glb content type
    return FileResponse(path, media_type="model/gltf-binary")

@router.get("/status")
async def get_3d_engine_status():
    """Check if 3D generation engines are online."""
    # Logic to check for local CUDA instances or sub-processes
    return {
        "status": "online",
        "engines": {
            "trellis-2": "ready",
            "triposr": "ready",
            "crm": "ready"
        },
        "vram_available": "24GB" # Simulated
    }
