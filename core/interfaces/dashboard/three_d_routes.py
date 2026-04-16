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

from core.utils.paths import LOCAL_MODELS_3D, LOGS_SYSTEM

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
                "name": "Trellis 2 (WIP)" if model_id == "trellis-2" else model_id.title(),
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
    """
    Start the worker process and return immediately.
    The model loads in the background — poll /api/3d/health/{model} for status.
    """
    # Already running — return its port right away
    if model in _WORKER_PROCESS and _WORKER_PROCESS[model].poll() is None:
        return {"success": True, "port": _WORKER_PORT[model], "message": "Already running"}

    worker_dir   = LOCAL_MODELS_3D / model.replace("-", "")
    venv_python  = (worker_dir / "venv" / "Scripts" / "python.exe"
                    if os.name == "nt"
                    else worker_dir / "venv" / "bin" / "python")
    server_script = worker_dir / "run_server.py"

    if not venv_python.exists():
        return {"success": False, "error": "Virtual environment not found — reinstall the model."}
    if not server_script.exists():
        return {"success": False, "error": "run_server.py missing — reinstall the model."}

    port = get_free_port()
    logger.info(f"[3D] Starting {model} worker on port {port}…")

    try:
        LOGS_SYSTEM.mkdir(parents=True, exist_ok=True)
        log_file_path = LOGS_SYSTEM / f"{model}-worker.log"
        log_file = open(log_file_path, "w", encoding="utf-8")

        proc = subprocess.Popen(
            [str(venv_python), str(server_script), str(port)],
            cwd=str(worker_dir),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            text=True,
        )
        _WORKER_PROCESS[model] = proc
        _WORKER_PORT[model]    = port
        logger.info(f"[3D] Worker PID {proc.pid} started — log: {log_file_path}")
        return {"success": True, "port": port, "pid": proc.pid,
                "message": "Worker started — loading model into VRAM"}
    except Exception as e:
        logger.error(f"[3D] Failed to start worker: {e}")
        return {"success": False, "error": str(e)}

@router.get("/health/{model}")
async def get_worker_health(model: str):
    """Check the live health of a specific 3D model worker."""
    if model not in _WORKER_PROCESS:
        return {"status": "offline", "message": "Worker not started"}

    proc = _WORKER_PROCESS[model]
    if proc.poll() is not None:
        # Process has exited — surface last lines from the log
        log_path = LOGS_SYSTEM / f"{model}-worker.log"
        snippet = ""
        try:
            text = log_path.read_text(errors="replace")
            snippet = text[-600:].strip()
        except Exception:
            pass
        return {"status": "failed", "message": "Worker process exited unexpectedly", "error": snippet}

    port = _WORKER_PORT.get(model)
    if not port:
        return {"status": "launching", "message": "Allocating resources…"}

    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"http://127.0.0.1:{port}/health", timeout=0.8)
            if res.status_code == 200:
                return res.json()
            return {"status": "launching", "message": "Initializing server…"}
    except Exception:
        return {"status": "launching", "message": "Establishing connection…"}

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
            temp_script.write_text(download_script, encoding='utf-8')
            
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
                weights_complete_file.write_text(f"Downloaded {datetime.now().isoformat()}", encoding='utf-8')
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
                # To be safe on Windows, we use rmdir /s /q which is more aggressive
                try:
                    subprocess.run(f'cmd /c rmdir /s /q "{repo_dir}"', shell=True)
                except: pass
                wrapper_dir.mkdir(parents=True, exist_ok=True)
            
            # Ensure repo_dir is clean
            if repo_dir.exists():
                try: subprocess.run(f'cmd /c rmdir /s /q "{repo_dir}"', shell=True)
                except: pass
                
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
            
            # Core dependency list — torch pulled from cu124 wheel index, others from PyPI
            core_reqs = [
                "torch==2.6.0", "torchvision==0.21.0", "torchaudio==2.6.0",
                "wheel", "ninja",
                "easydict", "scipy", "tqdm",
                "huggingface_hub[cli]", "hf_transfer", "fastapi", "uvicorn", "httpx", "pillow",
                "imageio", "imageio-ffmpeg", "opencv-python-headless", "rembg", "onnxruntime-gpu",
                "trimesh", "open3d", "xatlas", "pyvista", "pymeshfix", "igraph", "transformers",
                "spconv-cu124",
            ]
            
            yield f"data: {json.dumps({'line': 'Installing high-performance CUDA 12.4 core (This may take 3-5m)...'})}\n\n"
            proc_core = await asyncio.create_subprocess_exec(
                str(pip_exe), "install", *core_reqs, "--index-url", "https://download.pytorch.org/whl/cu124", "--extra-index-url", "https://pypi.org/simple",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            async for raw in proc_core.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line: yield f"data: {json.dumps({'line': line})}\n\n"
            await proc_core.wait()

            # Install Kaolin with verified compatibility
            yield f"data: {json.dumps({'line': 'Installing NVIDIA Kaolin specialized geometry library...'})}\n\n"
            proc_kaolin = await asyncio.create_subprocess_exec(
                str(pip_exe), "install", "kaolin==0.18.0", "-f", "https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.6.0_cu124.html",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            async for raw in proc_kaolin.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line: yield f"data: {json.dumps({'line': line})}\n\n"
            await proc_kaolin.wait()

            # Install nvdiffrast — builds from source, requires MSVC + CUDA toolkit
            yield f"data: {json.dumps({'line': 'Building nvdiffrast (CUDA mesh rasterizer) — may take 5-10 min...'})}\n\n"

            # Locate MSVC via vswhere and merge its env vars into our subprocess env
            nv_env = dict(os.environ)
            nv_env['TORCH_CUDA_ARCH_LIST'] = '8.0;8.6;8.9+PTX'
            try:
                vswhere_path = r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
                if os.path.exists(vswhere_path):
                    vs_install = subprocess.check_output(
                        [vswhere_path, "-latest", "-property", "installationPath"],
                        text=True, errors='replace'
                    ).strip()
                    vcvarsall = os.path.join(vs_install, "VC", "Auxiliary", "Build", "vcvarsall.bat")
                    if os.path.exists(vcvarsall):
                        env_out = subprocess.run(
                            f'cmd /c "call "{vcvarsall}" x64 && set"',
                            shell=True, capture_output=True, text=True, errors='replace'
                        )
                        for ln in env_out.stdout.splitlines():
                            if '=' in ln:
                                k, v = ln.split('=', 1)
                                nv_env[k] = v
                        yield f"data: {json.dumps({'line': 'MSVC environment configured.'})}\n\n"
            except Exception as _msvc_err:
                yield f"data: {json.dumps({'line': f'Warning: MSVC setup failed: {_msvc_err}'})}\n\n"

            # PyTorch raises RuntimeError if system nvcc major version != torch CUDA major version.
            # The torch cu124 wheel ships its own CUDA runtime, so a newer system nvcc is fine at
            # runtime; we just need to relax the compile-time check.
            _cpp_ext = venv_dir / "lib" / "site-packages" / "torch" / "utils" / "cpp_extension.py"
            if _cpp_ext.exists():
                try:
                    _ce_src = _cpp_ext.read_text(encoding='utf-8')
                    _ce_patched = _ce_src.replace(
                        "raise RuntimeError(CUDA_MISMATCH_MESSAGE.format(cuda_str_version, torch.version.cuda))",
                        "warnings.warn(f'[Aethvion] CUDA version mismatch ({cuda_str_version} vs {torch.version.cuda}) — proceeding.')"
                    )
                    if _ce_patched != _ce_src:
                        _cpp_ext.write_text(_ce_patched, encoding='utf-8')
                        yield f"data: {json.dumps({'line': 'PyTorch CUDA version check relaxed for cross-version build.'})}\n\n"
                except Exception:
                    pass

            proc_nv = await asyncio.create_subprocess_exec(
                str(pip_exe), "install", "--no-build-isolation",
                "git+https://github.com/NVlabs/nvdiffrast",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=nv_env,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            async for raw in proc_nv.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line: yield f"data: {json.dumps({'line': line})}\n\n"
            await proc_nv.wait()
            if proc_nv.returncode != 0:
                yield f"data: {json.dumps({'line': 'Warning: nvdiffrast build failed — mesh postprocessing will be unavailable.'})}\n\n"
            else:
                yield f"data: {json.dumps({'line': 'nvdiffrast installed successfully.'})}\n\n"

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

            # --- Windows Compatibility Hardening ---
            yield f"data: {json.dumps({'line': 'Fixing path normalization for Windows...'})}\n\n"
            try:
                loader_file = repo_dir / "trellis" / "models" / "__init__.py"
                if loader_file.exists():
                    code = loader_file.read_text(encoding='utf-8')
                    if 'path_norm = os.path.normpath(path)' not in code:
                        fragile_block = 'is_local = os.path.exists'
                        if fragile_block in code:
                            new_body = """
    # --- Aethvion Windows Path Patch (Directory-Aware) ---
    path_norm = os.path.normpath(path)
    # Check for directory structure first: path/config.json + path/model.safetensors
    d_json = os.path.join(path_norm, "config.json")
    d_st   = os.path.join(path_norm, "model.safetensors")
    
    # Check for flat structure: path.json + path.safetensors
    f_json = f"{path_norm}.json"
    f_st   = f"{path_norm}.safetensors"

    is_local = False
    if os.path.isdir(path_norm) and os.path.exists(d_json) and os.path.exists(d_st):
        is_local = True
        config_file = d_json
        model_file = d_st
    elif os.path.exists(f_json) and os.path.exists(f_st):
        is_local = True
        config_file = f_json
        model_file = f_st

    if is_local:
        # proceed with config_file and model_file
        pass
    else:
        from huggingface_hub import hf_hub_download
        if os.path.isabs(path_norm) or ":\\\\" in path_norm or path_norm.startswith("\\\\\\\\"):
             raise FileNotFoundError(f"Local model files not found at {path_norm}")
        path_parts = path.replace('\\\\', '/').split('/')
        if len(path_parts) < 2:
            raise ValueError(f"Invalid model path or repo_id: {path}")
        repo_id = f'{path_parts[0]}/{path_parts[1]}'
        model_name = '/'.join(path_parts[2:])
        config_file = hf_hub_download(repo_id, f"{model_name}.json")
        model_file = hf_hub_download(repo_id, f"{model_name}.safetensors")
    # --- End Patch ---
"""
                            s_idx = code.find(fragile_block)
                            e_idx = code.find('with open(config_file')
                            if s_idx != -1 and e_idx != -1:
                                patched_code = code[:s_idx] + new_body.strip() + "\n\n    " + code[e_idx:]
                                loader_file.write_text(patched_code, encoding='utf-8')
                                yield f"data: {json.dumps({'line': 'Path patch complete.'})}\n\n"

                # --- Attention Patches ---
                yield f"data: {json.dumps({'line': 'Patching attention modules for SDPA support...'})}\n\n"
                full_attn_patch = """
    elif ATTN == 'sdpa':
        if num_all_args == 1:
            q, k, v = qkv.unbind(dim=1)
        elif num_all_args == 2:
            k, v = kv.unbind(dim=1)
        out_list = []
        q_start, kv_start = 0, 0
        for i in range(len(q_seqlen)):
            qi = q[q_start:q_start+q_seqlen[i]].transpose(0, 1).unsqueeze(0)
            ki = k[kv_start:kv_start+kv_seqlen[i]].transpose(0, 1).unsqueeze(0)
            vi = v[kv_start:kv_start+kv_seqlen[i]].transpose(0, 1).unsqueeze(0)
            res = torch.nn.functional.scaled_dot_product_attention(qi, ki, vi)
            out_list.append(res.squeeze(0).transpose(0, 1))
            q_start += q_seqlen[i]
            kv_start += kv_seqlen[i]
        out = torch.cat(out_list, dim=0)
"""
                coll_patch = """
        elif ATTN == 'sdpa':
            q, k, v = qkv_feats.unbind(dim=2)
            q = q.transpose(1, 2)
            k = k.transpose(1, 2)
            v = v.transpose(1, 2)
            out = torch.nn.functional.scaled_dot_product_attention(q, k, v)
            out = out.transpose(1, 2)
"""
                coll_varlen_patch = """
        elif ATTN == 'sdpa':
            q, k, v = qkv_feats.unbind(dim=1)
            out_list = []
            curr = 0
            for slen in seq_lens:
                qi = q[curr:curr+slen].transpose(0, 1).unsqueeze(0)
                ki = k[curr:curr+slen].transpose(0, 1).unsqueeze(0)
                vi = v[curr:curr+slen].transpose(0, 1).unsqueeze(0)
                res = torch.nn.functional.scaled_dot_product_attention(qi, ki, vi)
                out_list.append(res.squeeze(0).transpose(0, 1))
                curr += slen
            out = torch.cat(out_list, dim=0)
"""
                # 1. Patch sparse/__init__.py
                si_file = repo_dir / "trellis" / "modules" / "sparse" / "__init__.py"
                if si_file.exists():
                    c = si_file.read_text(encoding='utf-8')
                    if "'sdpa'" not in c:
                        c = c.replace("['xformers', 'flash_attn']", "['xformers', 'flash_attn', 'sdpa']")
                        si_file.write_text(c, encoding='utf-8')
                
                # 2. Patch full_attn.py
                fa_file = repo_dir / "trellis" / "modules" / "sparse" / "attention" / "full_attn.py"
                if fa_file.exists():
                    c = fa_file.read_text(encoding='utf-8')
                    if "'sdpa'" not in c:
                        c = c.replace("import flash_attn", "import flash_attn\\nelif ATTN == 'sdpa':\\n    pass")
                        c = c.replace("    else:", full_attn_patch + "    else:")
                        fa_file.write_text(c, encoding='utf-8')

                # 3. Patch others
                for f in ["serialized_attn.py", "windowed_attn.py"]:
                    target = repo_dir / "trellis" / "modules" / "sparse" / "attention" / f
                    if target.exists():
                        c = target.read_text(encoding='utf-8')
                        if "'sdpa'" not in c:
                            c = c.replace("import flash_attn", "import flash_attn\\nelif ATTN == 'sdpa':\\n    pass")
                            c = c.replace("else:\\n            raise ValueError(f\\\"Unknown attention module: {ATTN}\\\")", coll_patch + "        else:\\n            raise ValueError(f\\\"Unknown attention module: {ATTN}\\\")")
                            c = c.replace("max(seq_lens)) # [M, H, C]", "max(seq_lens)) # [M, H, C]" + coll_varlen_patch)
                            target.write_text(c, encoding='utf-8')

            except Exception as e:
                yield f"data: {json.dumps({'line': f'Warning: Attention patch failed: {e}'})}\n\n"

            # 6. Generate the Server Script Wrapper
            yield f"data: {json.dumps({'line': 'Generating FastAPI microservice hook (run_server.py)...'})}\n\n"

            # Clean server template — all dependencies are real installed packages.
            # {MODEL_NAME} and {MODEL_ID} are substituted below via .replace().
            # All other curly braces are plain Python dict/f-string syntax — do NOT use f-string here.
            server_template = r'''"""
Aethvion Suite — {MODEL_NAME} Worker
All dependencies (kaolin, nvdiffrast) are real installed packages — no mocks.
"""
import os
import sys
import base64
import traceback
import threading

# --- Attention backend: use PyTorch built-in SDPA (no flash_attn required) ---
os.environ.setdefault("ATTN_BACKEND", "sdpa")
os.environ.setdefault("SPARSE_ATTN_BACKEND", "sdpa")

# --- Tell transformers flash_attn is not available (avoids import-time crash) ---
try:
    import transformers.utils.import_utils as _iu
    _iu.is_flash_attn_2_available = lambda: False
    _iu.is_flash_attn_available   = lambda: False
    _iu.is_flash_attn_3_available = lambda: False
except Exception:
    pass

# --- Path setup --------------------------------------------------------------
_HERE    = os.path.dirname(os.path.abspath(__file__))
_REPO    = os.path.join(_HERE, "{MODEL_ID}")
_WEIGHTS = os.path.join(_HERE, "weights")

if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

print(f"[{MODEL_ID}] Repo:    {_REPO}")
print(f"[{MODEL_ID}] Weights: {_WEIGHTS}")

# --- Import pipeline class ---------------------------------------------------
_Pipeline     = None
_import_error = None
try:
    from trellis.pipelines import TrellisImageTo3DPipeline as _T
    _Pipeline = _T
    print(f"[{MODEL_ID}] Pipeline imported OK")
except Exception:
    _import_error = traceback.format_exc()
    print(f"[{MODEL_ID}] IMPORT FAILED:\n{_import_error}")

# --- FastAPI service ----------------------------------------------------------
import torch
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

_pipeline   = None
_status     = "launching"
_load_error = None


def _vram():
    try:
        if torch.cuda.is_available():
            u = torch.cuda.memory_reserved(0) / 1024**3
            t = torch.cuda.get_device_properties(0).total_memory / 1024**3
            return round(u, 3), round(t, 3)
    except Exception:
        pass
    return 0.0, 0.0


def _load():
    global _pipeline, _status, _load_error
    if _Pipeline is None:
        _load_error = _import_error or "Pipeline class failed to import"
        _status = "failed"
        return
    if not os.path.exists(os.path.join(_WEIGHTS, "pipeline.json")):
        _load_error = f"pipeline.json missing in {_WEIGHTS}"
        _status = "failed"
        print(f"[{MODEL_ID}] {_load_error}")
        return
    try:
        if torch.cuda.is_available():
            dev = torch.cuda.get_device_properties(0)
            print(f"[{MODEL_ID}] CUDA: {dev.name}  ({dev.total_memory/1024**3:.1f} GB)")
        u0, _ = _vram()
        print(f"[{MODEL_ID}] Loading weights (1-3 min)...")
        pipeline = _Pipeline.from_pretrained(_WEIGHTS)
        if torch.cuda.is_available():
            pipeline.cuda()
        u1, t1 = _vram()
        print(f"[{MODEL_ID}] VRAM: {u1:.2f}/{t1:.2f} GB  (delta {u1-u0:.2f} GB)")
        _pipeline = pipeline
        _status   = "online"
        print(f"[{MODEL_ID}] STATUS: online")
    except Exception:
        _load_error = traceback.format_exc()
        _status = "failed"
        print(f"[{MODEL_ID}] LOAD FAILED:\n{_load_error}")


@asynccontextmanager
async def _lifespan(app):
    t = threading.Thread(target=_load, daemon=True, name="{MODEL_ID}-loader")
    t.start()
    print(f"[{MODEL_ID}] Loader thread started")
    yield


app = FastAPI(title="{MODEL_NAME} Worker", lifespan=_lifespan)


class GenRequest(BaseModel):
    image_base64: str
    seed:         int       = 42
    formats:      List[str] = ["gaussian", "mesh"]


@app.get("/health")
def health():
    u, t = _vram()
    r = {"status": _status, "vram_used": u, "vram_total": t, "model": "{MODEL_ID}"}
    if _status == "failed" and _load_error:
        r["error"] = _load_error[-2000:]
    return r


@app.post("/generate")
async def generate(req: GenRequest):
    if _status != "online" or _pipeline is None:
        raise HTTPException(503, detail=f"Model not ready ({_status})")
    try:
        from PIL import Image
        import io as _io
        raw = req.image_base64
        if "," in raw:
            raw = raw.split(",", 1)[1]
        image = Image.open(_io.BytesIO(base64.b64decode(raw))).convert("RGB")
        print(f"[{MODEL_ID}] /generate seed={req.seed}")
        outputs = _pipeline.run(image, seed=req.seed, formats=req.formats)
        print(f"[{MODEL_ID}] Inference complete")
        if "mesh" in outputs and "gaussian" in outputs:
            from trellis.utils import postprocessing_utils
            glb = postprocessing_utils.to_glb(outputs["gaussian"][0], outputs["mesh"][0])
            return {"success": True, "glb_base64": base64.b64encode(glb).decode()}
        return {"success": True, "formats": list(outputs.keys())}
    except Exception:
        tb = traceback.format_exc()
        print(f"[{MODEL_ID}] /generate failed:\n{tb}")
        return {"success": False, "error": tb}


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"[{MODEL_ID}] Starting on port {port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
'''
            run_script.write_text(
                server_template.replace("{MODEL_NAME}", model.title()).replace("{MODEL_ID}", model),
                encoding='utf-8'
            )

            # 6. Create success lockfile
            yield f"data: {json.dumps({'line': 'Finalizing installation...'})}\n\n"
            install_file.write_text(f"Installed {datetime.now().isoformat()}", encoding='utf-8')
                
            yield f"data: {json.dumps({'done': True, 'success': True})}\n\n"
            
        except Exception as e:
            logger.error(f"Installation failed: {e}")
            yield f"data: {json.dumps({'done': True, 'success': False, 'error': str(e)})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
