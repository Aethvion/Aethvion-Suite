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
import httpx
import subprocess
import time
import socket
import asyncio
from pathlib import Path

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

# --- Worker Management ---
_WORKER_PROCESS = {} # model -> subprocess.Popen
_WORKER_PORT = {}    # model -> port

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

async def get_or_start_worker(model: str):
    global _WORKER_PROCESS, _WORKER_PORT
    
    """Start the 3D model worker if not running."""
    if model in _WORKER_PROCESS and _WORKER_PROCESS[model].poll() is None:
        return _WORKER_PORT[model], None
        
    worker_dir = LOCAL_MODELS_3D / model.replace("-", "")
    venv_python = worker_dir / "venv" / "Scripts" / "python.exe" if os.name == 'nt' else worker_dir / "venv" / "bin" / "python"
    server_script = worker_dir / "run_server.py"
    
    if not venv_python.exists():
        return None, f"Worker environment not found at {venv_python}"
        
    port = get_free_port()
    logger.info(f"[3D] Starting {model} worker on port {port}...")
    
    try:
        log_file_path = worker_dir / "worker.log"
        log_file = open(log_file_path, "w", encoding='utf-8')
        
        proc = subprocess.Popen(
            [str(venv_python), str(server_script), str(port)],
            cwd=str(worker_dir),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            text=True
        )
        _WORKER_PROCESS[model] = proc
        _WORKER_PORT[model] = port
        
        # Wait for health check (Heavy ML model can take 2-3 minutes to load VRAM)
        max_retries = 120
        async with httpx.AsyncClient() as client:
            for i in range(max_retries):
                try:
                    res = await client.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
                    if res.status_code == 200:
                        res_data = res.json()
                        status = res_data.get("status")
                        if status == "online":
                            logger.info(f"[3D] Worker {model} is ready.")
                            return port, None
                        elif status == "failed":
                            err_msg = res_data.get("error", "Unknown loading error")
                            logger.error(f"[3D] Worker {model} reported loading failure: {err_msg}")
                            return None, f"Model failed to load: {err_msg}"
                except:
                    pass
                
                await asyncio.sleep(2.0)
                
                if proc.poll() is not None:
                    log_file.close()
                    error_out = log_file_path.read_text(errors='replace')
                    logger.error(f"[3D] Worker {model} failed to start. Output:\n{error_out}")
                    return None, f"Worker failed to start. Check worker.log"
                    
        return port, None
    except Exception as e:
        logger.error(f"[3D] Exception starting worker: {e}")
        return None, str(e)

@router.post("/generate", response_model=ThreeDGenerationResponse)
async def generate_3d_asset(req: ThreeDGenerationRequest):
    """
    Generate a 3D asset using the specified model.
    """
    trace_id = f"3d-{uuid.uuid4().hex[:8]}"
    logger.info(f"[{trace_id}] 3D generation request: {req.model} ({req.action})")

    try:
        # 1. Prepare Workspace & Worker
        workspace = get_workspace_manager()
        
        # Start/Get worker
        port, err = await get_or_start_worker(req.model)
        if err:
            return ThreeDGenerationResponse(success=False, error=f"Worker Error: {err}")

        # 2. Call Worker for Generation
        logger.info(f"[{trace_id}] Routing request to worker on port {port}")
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            worker_res = await client.post(
                f"http://127.0.0.1:{port}/generate",
                json={
                    "image_base64": req.input_image,
                    "prompt": req.prompt,
                    "seed": req.seed or 1,
                    "action": req.action
                }
            )
            
            if worker_res.status_code != 200:
                return ThreeDGenerationResponse(success=False, error=f"Worker HTTP {worker_res.status_code}")
            
            result_data = worker_res.json()
            if not result_data.get("success"):
                return ThreeDGenerationResponse(success=False, error=result_data.get("error", "Unknown worker error"))

        # 3. Save Real GLB
        glb_bytes = base64.b64decode(result_data["glb_base64"])
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

        # Save the REAL GLB
        path = workspace.save_output(
            domain="ThreeD",
            filename=filename,
            content=glb_bytes,
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
                id=f.get('trace_id') or 'unknown',
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
@router.get("/active_services")
async def get_active_services():
    """Get a list of all currently running heavy models with their live stats."""
    services = []
    
    for model_id, proc in _WORKER_PROCESS.items():
        if proc.poll() is None:
            # Service is alive, get its live health/vram
            status = await get_worker_health(model_id)
            services.append({
                "id": model_id,
                "name": "Trellis 2" if model_id == "trellis-2" else model_id.title(),
                "status": status.get("status", "starting"),
                "vram_used": status.get("vram_used", 0),
                "vram_total": status.get("vram_total", 0),
                "port": _WORKER_PORT.get(model_id)
            })
            
    return services

@router.post("/stop/{model}")
async def stop_worker(model: str):
    """Gracefully shutdown a model worker."""
    if model in _WORKER_PROCESS:
        proc = _WORKER_PROCESS[model]
        if proc.poll() is None:
            logger.info(f"[3D] Stopping worker {model}...")
            proc.terminate()
            # Wait briefly or kill if stubborn
            try:
                proc.wait(timeout=2)
            except:
                proc.kill()
        
        del _WORKER_PROCESS[model]
        if model in _WORKER_PORT: del _WORKER_PORT[model]
        return {"success": True}
    return {"success": False, "error": "Service not running"}

@router.get("/launch/{model}")
async def launch_worker(model: str):
    """Manually trigger worker startup for a specific model."""
    # This will call get_or_start_worker and initiate the VRAM load
    port, err = await get_or_start_worker(model)
    if err:
        return {"success": False, "error": err}
    return {"success": True, "port": port}

@router.get("/health/{model}")
async def get_worker_health(model: str):
    """Check the live health of a specific 3D model worker."""
    if model not in _WORKER_PROCESS or _WORKER_PROCESS[model].poll() is not None:
        return {"status": "offline", "message": "Worker not started"}
        
    port = _WORKER_PORT.get(model)
    if not port:
        return {"status": "starting", "message": "Allocating resources..."}
        
    try:
        async with httpx.AsyncClient() as client:
            # Short timeout, we want frequent pings
            res = await client.get(f"http://127.0.0.1:{port}/health", timeout=0.8)
            if res.status_code == 200:
                return res.json()
            return {"status": "starting", "message": "Initializing server..."}
    except:
        return {"status": "starting", "message": "Establishing connection..."}

@router.get("/install_status/{model}")
async def get_install_status(model: str):
    """Check if a specific 3D model/engine and its weights are installed locally."""
    wrapper_name = model.replace("-", "")
    wrapper_dir = LOCAL_MODELS_3D / wrapper_name
    install_file = wrapper_dir / ".install_complete"
    weights_file = wrapper_dir / ".install_weights_complete"
    
    # Simple folder-based check (fast, no flickering)
    is_valid = (wrapper_dir / "venv").exists()
    
    return {
        "model": model,
        "installed": install_file.exists() and is_valid,
        "weights_installed": weights_file.exists()
    }

@router.post("/install_weights/{model}")
async def install_weights(model: str):
    """Start streaming download of 3D model weights from HuggingFace."""
    from fastapi.responses import StreamingResponse
    import asyncio
    import json
    import shutil
    from core.utils.paths import LOCAL_MODELS_3D
    
    wrapper_name = model.replace("-", "")
    wrapper_dir = LOCAL_MODELS_3D / wrapper_name
    weights_dir = wrapper_dir / "weights"
    weights_complete_file = wrapper_dir / ".install_weights_complete"
    
    weights_dir.mkdir(parents=True, exist_ok=True)
    
    async def _generate():
        try:
            yield f"data: {json.dumps({'line': f'Initializing weight download for {model} to {weights_dir.relative_to(LOCAL_MODELS_3D)}...'})}\n\n"
            
            # We use a subprocess to use the HuggingFace CLI or a small script to download
            # to keep the main event loop clean.
            # Repo: microsoft/TRELLIS-image-large
            repo_id = "microsoft/TRELLIS-image-large" if "trellis" in model else "unknown"
            
            if repo_id == "unknown":
                yield f"data: {json.dumps({'done': True, 'success': False, 'error': 'Unknown model repository for weights'})}\n\n"
                return

            yield f"data: {json.dumps({'line': f'Downloading from HF Repo: {repo_id}...'})}\n\n"
            
            # We'll use huggingface_hub cli if possible, or a python script
            download_script = f"""
import os
from huggingface_hub import snapshot_download
print(f'Starting download of {repo_id}...')
snapshot_download(
    repo_id='{repo_id}',
    local_dir=r'{weights_dir}',
    local_dir_use_symlinks=False
)
print('Download complete.')
"""
            temp_script = wrapper_dir / "tmp_download.py"
            temp_script.write_text(download_script)
            
            # Use the venv python if possible, or system python
            venv_python = wrapper_dir / "venv" / "Scripts" / "python.exe" if os.name == 'nt' else wrapper_dir / "venv" / "bin" / "python"
            if not venv_python.exists():
                venv_python = "python" # fallback
                
            proc = await asyncio.create_subprocess_exec(
                str(venv_python), str(temp_script),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "HF_HUB_DISABLE_SYMLINKS": "1", "HF_HUB_ENABLE_HF_TRANSFER": "1"},
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            async for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    # Handle carriage returns by splitting/replacing to ensure vertical stacking
                    cleanLine = line.replace('\r', '\n');
                    yield f"data: {json.dumps({'line': cleanLine})}\n\n"
                
            await proc.wait()
            
            if temp_script.exists(): os.remove(temp_script)
            
            if proc.returncode == 0:
                weights_complete_file.write_text(f"Downloaded {datetime.now().isoformat()}")
                yield f"data: {json.dumps({'line': 'Weight installation verified and complete.', 'done': True, 'success': True})}\n\n"
            else:
                yield f"data: {json.dumps({'done': True, 'success': False, 'error': f'Download process failed with exit code {proc.returncode}'})}\n\n"
                
        except Exception as e:
            logger.error(f"Weight download failed: {e}")
            yield f"data: {json.dumps({'done': True, 'success': False, 'error': str(e)})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

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
            if repo_dir.exists() and (repo_dir / ".git").exists():
                yield f"data: {json.dumps({'line': 'Existing engine found. Syncing repository...'})}\n\n"
                proc_git = await asyncio.create_subprocess_exec(
                    "git", "pull",
                    cwd=str(repo_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
            else:
                if repo_dir.exists(): shutil.rmtree(repo_dir, ignore_errors=True)
                yield f"data: {json.dumps({'line': f'Cloning microsoft/TRELLIS (with submodules) into {repo_dir.relative_to(LOCAL_MODELS_3D)}...'})}\n\n"
                proc_git = await asyncio.create_subprocess_exec(
                    "git", "clone", "--recurse-submodules", "https://github.com/microsoft/TRELLIS.git", str(repo_dir),
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
            yield f"data: {json.dumps({'line': 'Installing core scientific stack (torch, rembg, etc.)...'})}\n\n"
            
            pip_exe = venv_dir / "Scripts" / "pip.exe" if sys.platform == 'win32' else venv_dir / "bin" / "pip"
            
            # Full dependency list from Trellis official setup script
            core_reqs = [
                "torch", "torchvision", "easydict", "scipy", "tqdm", 
                "huggingface_hub[cli]", "hf_transfer", "fastapi", "uvicorn", "httpx", "pillow",
                "imageio", "imageio-ffmpeg", "opencv-python-headless", "rembg", "onnxruntime-gpu",
                "trimesh", "open3d", "xatlas", "pyvista", "pymeshfix", "igraph", "transformers", "ninja"
            ]
            
            proc_core = await asyncio.create_subprocess_exec(
                str(pip_exe), "install", *core_reqs,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            async for raw in proc_core.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line: yield f"data: {json.dumps({'line': line})}\n\n"
            await proc_core.wait()

            # Install custom utils3d as required by Trellis official
            yield f"data: {json.dumps({'line': 'Installing specialized 3D utility repository (utils3d)...'})}\n\n"
            proc_u3d = await asyncio.create_subprocess_exec(
                str(pip_exe), "install", "git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=0x08000000 if os.name == 'nt' else 0
            )
            async for raw in proc_u3d.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line: yield f"data: {json.dumps({'line': line})}\n\n"
            await proc_u3d.wait()

            # 5. Generate the Server Script Wrapper
            yield f"data: {json.dumps({'line': 'Generating FastAPI microservice hook (run_server.py)...'})}\n\n"
            run_script.write_text(f'''\"\"\"
Aethvion Suite - {model.title()} Operational Microservice
High-fidelity 3D generation backend with CUDA acceleration and nvdiffrast bypass.
\"\"\"
import os
import sys
import base64
import torch
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from unittest.mock import MagicMock

# --- The "Ghost Module" Shim ---
# Deep dependencies like utils3d import nvdiffrast at top-level. 
# We inject a mock before importing Trellis to prevent immediate crashes on Windows.
sys.modules["nvdiffrast"] = MagicMock()
sys.modules["nvdiffrast.torch"] = MagicMock()

# --- Trellis Core Imports ---
# These are added to path once everything is patched
repo_path = os.path.join(os.path.dirname(__file__), "{model}")
sys.path.append(repo_path)

try:
    from trellis.pipelines import TrellisImageTo3DPipeline
    from trellis.utils import postprocessing_utils
    LOADED = True
except Exception as e:
    print(f"Failed to load Trellis: {{e}}")
    LOADED = False

app = FastAPI(title="{model.title()} Worker")

class GenRequest(BaseModel):
    image_base64: str
    prompt: Optional[str] = None
    seed: int = 42
    action: str = "image23d"

# Global pipeline instance
pipeline = None

@app.on_event("startup")
async def startup_event():
    global pipeline
    if not LOADED: return
    
    weights_path = os.path.join(os.path.dirname(__file__), "weights")
    if not os.path.exists(weights_path):
        print("Weights not found!")
        return
        
    print(f"Loading Trellis pipeline from {{weights_path}}...")
    try:
        pipeline = TrellisImageTo3DPipeline.from_pretrained(weights_path)
        pipeline.cuda()
        print("Model loaded into VRAM successfully.")
    except Exception as e:
        print(f"Error loading model: {{e}}")

@app.get("/health")
def health():
    if not LOADED:
        return {{"status": "failed", "error": "Import error"}}
    if pipeline is None:
        return {{"status": "warming", "message": "Loading weights into VRAM..."}}
    return {{"status": "online", "model": "{model}"}}

@app.post("/generate")
async def generate(req: GenRequest):
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Model warming up")
        
    try:
        # 1. Decode Image
        from PIL import Image
        import io
        raw_b64 = req.image_base64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        img_bytes = base64.b64decode(raw_b64)
        image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        
        # 2. Run Inference
        print(f"Running inference (Seed: {{req.seed}})...")
        outputs = pipeline.run(image, seed=req.seed)
        
        # 3. Post-process to Mesh
        # We use a neutral post-processing that avoids nvdiffrast dependencies
        video = outputs['sample'] # Not used here, but available
        
        # Convert to GLB
        print("Converting to GLB...")
        glo_mesh = postprocessing_utils.to_glb(outputs['gaussian'][0], outputs['mesh'][0])
        
        # 4. Encode and return
        glb_b64 = base64.b64encode(glo_mesh).decode('utf-8')
        
        return {{"success": True, "glb_base64": glb_b64}}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {{"success": False, "error": str(e)}}

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run(app, host="127.0.0.1", port=port)
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
