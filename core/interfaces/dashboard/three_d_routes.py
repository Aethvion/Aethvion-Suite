"""
Aethvion Suite - 3D Generation Routes
API endpoints for 3D model generation and asset management.
"""

import base64
import uuid
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
import subprocess
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

# Worker Management
_WORKER_PROCESS = {} # model -> subprocess.Popen
_WORKER_PORT = {}    # model -> port

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def _worker_paths(model: str):
    worker_dir = LOCAL_MODELS_3D / model.replace("-", "")
    venv_python = (worker_dir / "venv" / "Scripts" / "python.exe" if os.name == "nt"
                   else worker_dir / "venv" / "bin" / "python")
    return worker_dir, venv_python, worker_dir / "run_server.py"


def _worker_log_path(model: str) -> Path:
    return LOGS_SYSTEM / f"{model}-worker.log"


def _prepare_worker(model: str, worker_dir: Path) -> None:
    """Bring an installed worker up to date before it starts.

    Installs made by earlier versions can carry a stale run_server.py or (Trellis) source
    patches that do not parse.  Refreshing them here means a fix to the Suite reaches
    existing installs without a reinstall.  Never raises: a problem here is logged and
    the worker is started anyway so its own error shows up in the health check.
    """
    try:
        templates = Path(__file__).parent / "templates"
        if model == "triposr":
            wanted = (templates / "triposr_server.py").read_text(encoding="utf-8")
        else:
            wanted = ((templates / "tsr_server_template.py").read_text(encoding="utf-8")
                      .replace("{MODEL_NAME}", model.title()).replace("{MODEL_ID}", model))
        run_script = worker_dir / "run_server.py"
        current = run_script.read_text(encoding="utf-8") if run_script.exists() else ""
        if current.replace("\r\n", "\n") != wanted.replace("\r\n", "\n"):
            run_script.write_text(wanted, encoding="utf-8")
            logger.info(f"[3D] Updated {model} run_server.py to the current template")

        if model == "trellis-2":
            from . import trellis_patches  # noqa: PLC0415
            repo_dir = worker_dir / model
            if repo_dir.exists() and not trellis_patches.is_patched(repo_dir):
                for line in trellis_patches.apply_sdpa_patches(repo_dir):
                    logger.info(f"[3D] Trellis source patch: {line}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[3D] Could not prepare {model} worker: {exc}")


def _stop_worker_process(model: str) -> None:
    proc = _WORKER_PROCESS.pop(model, None)
    _WORKER_PORT.pop(model, None)
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except OSError:
            pass


def _start_worker_process(model: str):
    """Start the worker process if it is not running. Returns (port, error)."""
    if model in _WORKER_PROCESS and _WORKER_PROCESS[model].poll() is None:
        return _WORKER_PORT[model], None

    worker_dir, venv_python, server_script = _worker_paths(model)
    if not venv_python.exists():
        return None, f"{model} is not installed (no virtual environment). Install it from the 3D Models tab."
    _prepare_worker(model, worker_dir)
    if not server_script.exists():
        return None, f"{model}: run_server.py is missing. Reinstall the model from the 3D Models tab."

    port = get_free_port()
    try:
        LOGS_SYSTEM.mkdir(parents=True, exist_ok=True)
        log_file = open(_worker_log_path(model), "w", encoding="utf-8")
        proc = subprocess.Popen(
            [str(venv_python), str(server_script), str(port)],
            cwd=str(worker_dir),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            text=True,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"[3D] Failed to start {model} worker: {e}")
        return None, str(e)
    _WORKER_PROCESS[model] = proc
    _WORKER_PORT[model]    = port
    logger.info(f"[3D] {model} worker PID {proc.pid} started on port {port} (log: {_worker_log_path(model)})")
    return port, None


def _short_error(text: str) -> str:
    """The last meaningful line of a traceback, for one-line error messages."""
    lines = [ln.strip() for ln in (text or "").strip().splitlines() if ln.strip()]
    return lines[-1] if lines else "unknown error"


async def get_or_start_worker(model: str, wait_seconds: int = 600):
    """Make sure the worker is running AND its model is loaded. Returns (port, error).

    A worker left in the "failed" state by an earlier attempt is stopped and started
    again, so fixing the cause and retrying works without restarting the Suite.
    """
    for attempt in (1, 2):
        already_running = model in _WORKER_PROCESS and _WORKER_PROCESS[model].poll() is None
        port, err = _start_worker_process(model)
        if err:
            return None, err
        proc = _WORKER_PROCESS[model]

        failure = ""
        deadline = asyncio.get_event_loop().time() + wait_seconds
        async with httpx.AsyncClient() as client:
            while True:
                if asyncio.get_event_loop().time() > deadline:
                    return None, f"{model} did not finish loading within {wait_seconds}s (log: {_worker_log_path(model)})"
                if proc.poll() is not None:
                    try:
                        tail = _worker_log_path(model).read_text(errors="replace")[-1500:]
                    except OSError:
                        tail = ""
                    _stop_worker_process(model)
                    return None, f"{model} worker exited while starting: {_short_error(tail)}"
                try:
                    res = await client.get(f"http://127.0.0.1:{port}/health", timeout=2.0)
                    data = res.json() if res.status_code == 200 else {}
                except (httpx.HTTPError, ValueError, OSError):
                    data = {}
                status = data.get("status")
                if status == "online":
                    return port, None
                if status == "failed":
                    failure = data.get("error", "") or "unknown loading error"
                    logger.error("[3D] %s failed to load: %s", model, failure)
                    _stop_worker_process(model)
                    break
                await asyncio.sleep(1.5)

        # A worker that was already sitting in the failed state may predate a fix:
        # start a fresh one once. A worker we just started and saw fail is final.
        if not (already_running and attempt == 1):
            return None, f"{model} failed to load: {_short_error(failure)} (full log: {_worker_log_path(model)})"
    return None, f"{model} failed to load (log: {_worker_log_path(model)})"

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
        
        if not req.input_image:
            return ThreeDGenerationResponse(
                success=False,
                error=f"{req.model} builds a 3D model from a picture: connect a reference image "
                      "(an Image node or an image generation step). A text prompt alone is not enough.")

        # Start/Get worker
        port, err = await get_or_start_worker(req.model)
        if err:
            return ThreeDGenerationResponse(success=False, error=f"Worker Error: {err}")

        # 2. Call Worker for Generation
        logger.info(f"[{trace_id}] Routing request to worker on port {port}")
        
        async with httpx.AsyncClient(timeout=900.0) as client:
            worker_res = await client.post(
                f"http://127.0.0.1:{port}/generate",
                json={
                    "image_base64": req.input_image.split(",", 1)[1] if req.input_image.startswith("data:") else req.input_image,
                    "prompt": req.prompt,
                    "seed": req.seed or 1,
                    "action": req.action
                }
            )
            
            if worker_res.status_code != 200:
                try:
                    detail = worker_res.json().get("detail", "")
                except ValueError:
                    detail = worker_res.text[:300]
                return ThreeDGenerationResponse(
                    success=False, error=f"{req.model} worker returned HTTP {worker_res.status_code}: {detail}")

            result_data = worker_res.json()
            if not result_data.get("success"):
                full = result_data.get("error", "Unknown worker error")
                logger.error(f"[{trace_id}] {req.model} generation failed:\n{full}")
                return ThreeDGenerationResponse(success=False, error=f"{req.model} generation failed: {_short_error(full)}")
            if not result_data.get("glb_base64"):
                return ThreeDGenerationResponse(success=False, error=f"{req.model} returned no mesh")

        # 3. Save Logic: Nested structure (YYYY-MM/trace_id/...)
        now = datetime.now()
        month_dir = now.strftime("%Y-%m")
        # We'll use a standard filename inside the folder to keep it clean
        base_subpath = f"{month_dir}/{trace_id}"
        
        # Ensure the subdirectories exist within ThreeD domain
        threed_root = workspace.workspace_root / "ThreeD"
        gen_dir = threed_root / base_subpath
        gen_dir.mkdir(parents=True, exist_ok=True)

        # Save Real GLB
        glb_bytes = base64.b64decode(result_data["glb_base64"])
        glb_filename = f"{req.model}.glb"
        glb_subpath = f"{base_subpath}/{glb_filename}"
        
        # If the user provided an image, save it too
        if req.input_image:
            try:
                 img_data = req.input_image
                 if "," in img_data:
                     img_data = img_data.split(",", 1)[1]
                 img_bytes = base64.b64decode(img_data)
                 # Save as reference.png in the same folder
                 workspace.save_output(domain="ThreeD", filename=f"{base_subpath}/reference.png", content=img_bytes, trace_id=trace_id)
            except Exception as e:
                logger.warning(f"Failed to save reference image: {e}")

        # Save the REAL GLB
        path = workspace.save_output(
            domain="ThreeD",
            filename=glb_subpath,
            content=glb_bytes,
            trace_id=trace_id
        )
        
        stat = path.stat()
        asset = ThreeDAssetResponse(
            id=trace_id,
            name=req.prompt if req.prompt else f"3D {req.model}",
            url=f"/api/3d/serve/{glb_subpath}",
            path=str(path),
            model=req.model,
            size_bytes=stat.st_size,
            created_at=now.isoformat()
        )

        return ThreeDGenerationResponse(
            success=True,
            asset=asset
        )

    except Exception as e:
        logger.error(f"[{trace_id}] 3D generation failed: {str(e)}")
        return ThreeDGenerationResponse(success=False, error=str(e))

@router.get("/history")
async def get_3d_history(page: int = 1, limit: int = 10):
    """
    Get recent 3D generations with visual thumbnails.
    """
    workspace = get_workspace_manager()
    outputs = workspace.list_outputs()
    
    # 1. Filter all GLBs in ThreeD domain
    all_glbs = []
    for f in outputs.get('files', []):
        rel_path = f.get('path', '')
        if f.get('domain') == 'ThreeD' and rel_path.endswith('.glb'):
            all_glbs.append(f)

    # 2. Sort by creation (list_outputs is already sorted but we'll be safe)
    all_glbs.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    # 3. Paginate
    start = (page - 1) * limit
    end = start + limit
    paged_glbs = all_glbs[start:end]
    
    history = []
    for f in paged_glbs:
        rel_path = f.get('path', '')
        # remove "ThreeD/"
        serve_path = rel_path[7:] if rel_path.startswith('ThreeD/') else rel_path
        
        ref_image_url = None
        glp_path_obj = Path(rel_path)
        ref_path = glp_path_obj.parent / "reference.png"
        
        # Check if reference.png exists in the workspace
        full_ref_path = workspace.workspace_root / ref_path
        if full_ref_path.exists():
            # URL is relative to ThreeD domain
            ref_serve_path = str(ref_path).replace('\\', '/')
            if ref_serve_path.startswith('ThreeD/'):
                ref_serve_path = ref_serve_path[7:]
            ref_image_url = f"/api/3d/serve/{ref_serve_path}"

        history.append({
            "id": f.get('trace_id') or 'unknown',
            "name": f.get('filename'),
            "url": f"/api/3d/serve/{serve_path}",
            "thumbnail_url": ref_image_url,
            "path": rel_path,
            "size_bytes": f.get('size_bytes', 0),
            "created_at": f.get('created_at')
        })
            
    return {
        "assets": history,
        "total": len(all_glbs),
        "page": page,
        "limit": limit
    }

@router.get("/serve/{filename:path}")
async def serve_3d_asset(filename: str):
    """Serve a generated 3D file (supports nested paths)."""
    workspace = get_workspace_manager()
    # Normalize path to prevent directory traversal
    safe_filename = filename.replace("..", "")
    path = workspace.workspace_root / "ThreeD" / safe_filename
    
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    
    from fastapi.responses import FileResponse
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

# Installation Logic Simulation
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
                "name": "Trellis 2 (WIP)" if model_id == "trellis-2" else "TripoSR" if model_id == "triposr" else model_id.title(),
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
            except subprocess.TimeoutExpired:
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
    # A worker that is up but whose model failed to load is useless: replace it.
    if model in _WORKER_PROCESS and _WORKER_PROCESS[model].poll() is None:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"http://127.0.0.1:{_WORKER_PORT[model]}/health", timeout=1.5)
            if res.status_code == 200 and res.json().get("status") == "failed":
                _stop_worker_process(model)
            else:
                return {"success": True, "port": _WORKER_PORT[model], "message": "Already running"}
        except (httpx.HTTPError, ValueError, OSError):
            return {"success": True, "port": _WORKER_PORT[model], "message": "Already running"}

    port, err = await asyncio.to_thread(_start_worker_process, model)
    if err:
        return {"success": False, "error": err}
    return {"success": True, "port": port, "pid": _WORKER_PROCESS[model].pid,
            "message": "Worker started — loading model into VRAM"}

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
    from core.utils.paths import LOCAL_MODELS_3D
    
    wrapper_name = model.replace("-", "")
    wrapper_dir = LOCAL_MODELS_3D / wrapper_name
    weights_dir = wrapper_dir / "weights"
    weights_complete_file = wrapper_dir / ".install_weights_complete"
    
    weights_dir.mkdir(parents=True, exist_ok=True)
    
    async def _generate():
        try:
            yield f"data: {json.dumps({'line': f'Initializing weight download for {model} to {weights_dir.relative_to(LOCAL_MODELS_3D)}...'})}\n\n"
            
            # to keep the main event loop clean.
            if "trellis" in model:
                repo_id = "microsoft/TRELLIS-image-large"
            elif model == "triposr":
                repo_id = "stabilityai/TripoSR"
            else:
                repo_id = "unknown"
            
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
                try:
                    subprocess.run(f'cmd /c rmdir /s /q "{repo_dir}"', shell=True)
                except (subprocess.SubprocessError, OSError): pass
                wrapper_dir.mkdir(parents=True, exist_ok=True)

            # Ensure repo_dir is clean
            if repo_dir.exists():
                try: subprocess.run(f'cmd /c rmdir /s /q "{repo_dir}"', shell=True)
                except (subprocess.SubprocessError, OSError): pass
                
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

            pip_exe = venv_dir / "Scripts" / "pip.exe" if sys.platform == 'win32' else venv_dir / "bin" / "pip"

            # TripoSR install path — fast, ~6 GB VRAM, fully public weights
            if model == "triposr":
                # 1. Core deps
                triposr_reqs = [
                    "torch==2.6.0", "torchvision==0.21.0", "torchaudio==2.6.0",
                    "wheel", "fastapi", "uvicorn", "httpx",
                    "pillow==10.1.0", "huggingface_hub[cli]", "hf_transfer", "tqdm",
                    "einops==0.7.0", "omegaconf==2.3.0", "transformers==4.35.0",
                    "trimesh==4.0.5", "rembg[gpu]", "onnxruntime-gpu",
                    "imageio[ffmpeg]", "xatlas==0.0.9", "moderngl==5.10.0",
                    "scipy", "numpy<2.0", "scikit-image",
                ]
                yield f"data: {json.dumps({'line': 'Installing TripoSR dependencies (torch 2.6 cu124, numpy < 2.0, scikit-image)...'})}\n\n"
                proc_tr = await asyncio.create_subprocess_exec(
                    str(pip_exe), "install", *triposr_reqs,
                    "--index-url", "https://download.pytorch.org/whl/cu124",
                    "--extra-index-url", "https://pypi.org/simple",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                async for raw in proc_tr.stdout:
                    line = raw.decode("utf-8", errors="replace").rstrip()
                    if line: yield f"data: {json.dumps({'line': line})}\n\n"
                await proc_tr.wait()

                # 2. torchmcubes — CUDA marching-cubes extension (must build from source)
                yield f"data: {json.dumps({'line': 'Building torchmcubes (marching cubes CUDA ext) — needs MSVC, may take 3-5 min...'})}\n\n"
                mc_env = dict(os.environ)
                mc_env['TORCH_CUDA_ARCH_LIST'] = '8.0;8.6;8.9+PTX'
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
                                    mc_env[k] = v
                            yield f"data: {json.dumps({'line': 'MSVC environment configured for torchmcubes build.'})}\n\n"
                except Exception as _msvc_err:
                    yield f"data: {json.dumps({'line': f'Warning: MSVC setup failed: {_msvc_err}'})}\n\n"

                _cpp_ext_tsr = venv_dir / "lib" / "site-packages" / "torch" / "utils" / "cpp_extension.py"
                if _cpp_ext_tsr.exists():
                    try:
                        _ce_src = _cpp_ext_tsr.read_text(encoding='utf-8')
                        _ce_patched = _ce_src.replace(
                            "raise RuntimeError(CUDA_MISMATCH_MESSAGE.format(cuda_str_version, torch.version.cuda))",
                            "warnings.warn(f'[Aethvion] CUDA version mismatch ({cuda_str_version} vs {torch.version.cuda}) — proceeding.')"
                        )
                        if _ce_patched != _ce_src:
                            _cpp_ext_tsr.write_text(_ce_patched, encoding='utf-8')
                            yield f"data: {json.dumps({'line': 'PyTorch CUDA version check relaxed for cross-version build.'})}\n\n"
                    except Exception:
                        pass

                proc_mc = await asyncio.create_subprocess_exec(
                    str(pip_exe), "install", "--no-build-isolation",
                    "git+https://github.com/tatsy/torchmcubes.git",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=mc_env,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                async for raw in proc_mc.stdout:
                    line = raw.decode("utf-8", errors="replace").rstrip()
                    if line: yield f"data: {json.dumps({'line': line})}\n\n"
                await proc_mc.wait()
                if proc_mc.returncode != 0:
                    yield f"data: {json.dumps({'line': 'Note: torchmcubes could not be built (needs MSVC + CUDA toolkit). TripoSR will use the built-in CPU marching-cubes fallback instead.'})}\n\n"
                else:
                    yield f"data: {json.dumps({'line': 'torchmcubes installed successfully.'})}\n\n"

                # 3. Clone TripoSR repo (no setup.py — add to sys.path at runtime)
                yield f"data: {json.dumps({'line': 'Cloning VAST-AI-Research/TripoSR repository...'})}\n\n"
                if repo_dir.exists():
                    shutil.rmtree(repo_dir, ignore_errors=True)
                proc_git_tsr = await asyncio.create_subprocess_exec(
                    "git", "clone", "https://github.com/VAST-AI-Research/TripoSR.git", str(repo_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                async for raw in proc_git_tsr.stdout:
                    line = raw.decode("utf-8", errors="replace").rstrip()
                    if line: yield f"data: {json.dumps({'line': line})}\n\n"
                await proc_git_tsr.wait()
                if proc_git_tsr.returncode != 0:
                    yield f"data: {json.dumps({'done': True, 'success': False, 'error': 'TripoSR git clone failed'})}\n\n"
                    return

                # 4. Write run_server.py
                yield f"data: {json.dumps({'line': 'Generating TripoSR FastAPI microservice hook (run_server.py)...'})}\n\n"
                triposr_server = (Path(__file__).parent / 'templates' / 'triposr_server.py').read_text(encoding='utf-8')
                run_script.write_text(triposr_server, encoding="utf-8")

                # 5. Lockfile
                yield f"data: {json.dumps({'line': 'Finalizing TripoSR installation...'})}\n\n"
                install_file.write_text(f"Installed {datetime.now().isoformat()}", encoding="utf-8")
                yield f"data: {json.dumps({'done': True, 'success': True})}\n\n"
                return
            # end triposr branch — fall through to trellis-2 install

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

            # Windows Compatibility Hardening
            yield f"data: {json.dumps({'line': 'Fixing path normalization for Windows...'})}\n\n"
            try:
                loader_file = repo_dir / "trellis" / "models" / "__init__.py"
                if loader_file.exists():
                    code = loader_file.read_text(encoding='utf-8')
                    if 'path_norm = os.path.normpath(path)' not in code:
                        fragile_block = 'is_local = os.path.exists'
                        if fragile_block in code:
                            new_body = """
    # Aethvion Windows Path Patch (Directory-Aware)
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
    # End Patch
"""
                            s_idx = code.find(fragile_block)
                            e_idx = code.find('with open(config_file')
                            if s_idx != -1 and e_idx != -1:
                                patched_code = code[:s_idx] + new_body.strip() + "\n\n    " + code[e_idx:]
                                loader_file.write_text(patched_code, encoding='utf-8')
                                yield f"data: {json.dumps({'line': 'Path patch complete.'})}\n\n"

                # Attention Patches
                yield f"data: {json.dumps({'line': 'Patching attention modules for SDPA support...'})}\n\n"
                from . import trellis_patches  # noqa: PLC0415
                for _pl in trellis_patches.apply_sdpa_patches(repo_dir):
                    yield f"data: {json.dumps({'line': '  ' + _pl})}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'line': f'Warning: Attention patch failed: {e}'})}\n\n"

            # 6. Generate the Server Script Wrapper
            yield f"data: {json.dumps({'line': 'Generating FastAPI microservice hook (run_server.py)...'})}\n\n"

            # Clean server template — all dependencies are real installed packages.
            # {MODEL_NAME} and {MODEL_ID} are substituted below via .replace().
            server_template = (Path(__file__).parent / 'templates' / 'tsr_server_template.py').read_text(encoding='utf-8')
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
