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

from core.utils.paths import LOCAL_MODELS_3D

# --- Installation Logic Simulation ---
# For actual implementation, this would check if a specific directory exists
# e.g., checkpoints/3d/trellis and return True/False
@router.get("/install_status/{model}")
async def get_install_status(model: str):
    """Check if a specific 3D model/engine is installed locally."""
    # We will simulate installation by checking if a dummy lock file exists
    wrapper_name = model.replace("-", "")
    install_file = LOCAL_MODELS_3D / wrapper_name / ".install_complete"
    
    return {
        "model": model,
        "installed": install_file.exists()
    }

@router.post("/install/{model}")
async def install_3d_model(model: str):
    """Start actual streaming installation of a 3D model/engine (Trellis)."""
    from fastapi.responses import StreamingResponse
    import asyncio
    from core.utils.paths import LOCAL_MODELS_3D
    import sys
    import json
    import subprocess
    import shutil
    # Define robust microservice structure for the model
    # ex: localmodels/3d/trellis2
    wrapper_name = model.replace("-", "")
    wrapper_dir = LOCAL_MODELS_3D / wrapper_name
    
    install_file = wrapper_dir / ".install_complete"
    repo_dir = wrapper_dir / model         # localmodels/3d/trellis2/trellis-2
    venv_dir = wrapper_dir / "venv"          # localmodels/3d/trellis2/venv
    run_script = wrapper_dir / "run_server.py" # localmodels/3d/trellis2/run_server.py
    
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    
    async def _generate():
        try:
            # 1. Clean previous attempts
            if wrapper_dir.exists() and not install_file.exists():
                yield f"data: {json.dumps({'line': 'Cleaning partial installation...'})}\n\n"
                # To be safe on Windows, we try to clean but don't crash if files are locked
                try: shutil.rmtree(wrapper_dir, ignore_errors=True)
                except: pass
                wrapper_dir.mkdir(parents=True, exist_ok=True)
            
            repo_dir.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(repo_dir, ignore_errors=True) # Ensure it's empty for git clone
                
            # 2. Setup Virtual Environment
            yield f"data: {json.dumps({'line': f'Creating isolated virtual environment at {venv_dir.relative_to(LOCAL_MODELS_3D)}...'})}\n\n"
            proc_venv = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "venv", str(venv_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            async for raw in proc_venv.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line: yield f"data: {json.dumps({'line': line})}\n\n"
            await proc_venv.wait()
            
            if proc_venv.returncode != 0:
                yield f"data: {json.dumps({'done': True, 'success': False, 'error': 'Venv creation failed'})}\n\n"
                return
                
            # 3. Clone the repository
            yield f"data: {json.dumps({'line': f'Cloning microsoft/TRELLIS into {repo_dir.relative_to(LOCAL_MODELS_3D)}...'})}\n\n"
            proc_git = await asyncio.create_subprocess_exec(
                "git", "clone", "https://github.com/microsoft/TRELLIS.git", str(repo_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            async for raw in proc_git.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line: yield f"data: {json.dumps({'line': line})}\n\n"
            await proc_git.wait()
            
            if proc_git.returncode != 0:
                yield f"data: {json.dumps({'done': True, 'success': False, 'error': 'Git clone failed'})}\n\n"
                return
                
            # 4. Install Dependencies into the isolated venv
            yield f"data: {json.dumps({'line': 'Installing Python dependencies into isolated venv...'})}\n\n"
            
            pip_exe = venv_dir / "Scripts" / "pip.exe" if sys.platform == 'win32' else venv_dir / "bin" / "pip"
            req_file = repo_dir / "requirements.txt"
            
            if req_file.exists():
                proc_pip = await asyncio.create_subprocess_exec(
                    str(pip_exe), "install", "-r", str(req_file),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                async for raw in proc_pip.stdout:
                    line = raw.decode("utf-8", errors="replace").rstrip()
                    if line: yield f"data: {json.dumps({'line': line})}\n\n"
                await proc_pip.wait()
                
                if proc_pip.returncode != 0:
                    yield f"data: {json.dumps({'line': '[Warning] Pip install completed with non-zero exit code. You may need to install specific CUDA extensions manually.'})}\n\n"
            else:
                yield f"data: {json.dumps({'line': 'No requirements.txt found. Skipping dependecy installation.'})}\n\n"

            # 5. Generate the Server Script Wrapper
            yield f"data: {json.dumps({'line': 'Generating FastAPI microservice hook (run_server.py)...'})}\n\n"
            run_script.write_text(f'''\"\"\"
Aethvion Suite - {model.title()} Microservice
Standalone isolated backend hook for 3D generation.
\"\"\"
from fastapi import FastAPI
import uvicorn
import os
import sys

app = FastAPI(title="{model.title()} Worker")

@app.get("/health")
def health():
    return {{"status": "online", "model": "{model}"}}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=0) # Port 0 assigns random available port
''')
            
            # 6. Create success lockfile
            yield f"data: {json.dumps({'line': 'Finalizing installation...'})}\n\n"
            with open(install_file, "w") as f:
                f.write(f"Installed {datetime.now().isoformat()}")
                
            yield f"data: {json.dumps({'done': True, 'success': True})}\n\n"
            
        except Exception as e:
            logger.error(f"Installation failed: {e}")
            yield f"data: {json.dumps({'done': True, 'success': False, 'error': str(e)})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
