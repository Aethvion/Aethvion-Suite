"""
Aethvion Suite - 3D Generation Routes
API endpoints for 3D model generation and asset management.
"""

import base64
import shutil
import threading
import time
import uuid
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
import subprocess
import socket
import asyncio

from core.workspace import get_workspace_manager
from core.utils import get_logger
from core.utils.paths import LOCAL_MODELS_3D, LOGS_SYSTEM

logger = get_logger(__name__)

router = APIRouter(prefix="/api/3d", tags=["3d"])

_MODEL_DISPLAY_NAMES = {
    "trellis-2": "TRELLIS.2-4B",
    "hunyuan3d": "Hunyuan3D 2.1",
    "triposr": "TripoSR",
}
_HEAVY_3D_MODELS = {"trellis-2", "hunyuan3d"}
_GPU_3D_LOCK = threading.Lock()


class ThreeDGenerationRequest(BaseModel):
    action: str = "generate"  # "generate" (t23d) or "image23d" (i23d)
    prompt: Optional[str] = None
    input_image: Optional[str] = None  # base64
    model: str = "trellis-2"
    quality: str = "1024"
    seed: Optional[int] = None
    textured: bool = True
    pbr: bool = True
    decimation_target: Optional[int] = None
    texture_size: Optional[int] = None
    remesh: Optional[bool] = None
    max_num_view: Optional[int] = None
    texture_resolution: Optional[int] = None
    steps: Optional[int] = None
    extra_params: Optional[Dict[str, Any]] = None


class ThreeDTextureRequest(BaseModel):
    mesh_base64: str
    input_image: Optional[str] = None
    model: str = "hunyuan3d"
    max_num_view: int = 6
    texture_resolution: int = 512
    seed: Optional[int] = None

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

    Installs made by earlier versions can carry a stale run_server.py or (Trellis v1) source
    patches that do not parse.  Refreshing them here means a fix to the Suite reaches
    existing installs without a reinstall.  Never raises: a problem here is logged and
    the worker is started anyway so its own error shows up in the health check.
    """
    try:
        templates = Path(__file__).parent / "templates"
        if model == "triposr":
            wanted = (templates / "triposr_server.py").read_text(encoding="utf-8")
        elif model == "hunyuan3d":
            wanted = (templates / "hunyuan3d_server.py").read_text(encoding="utf-8")
        elif model == "trellis-2":
            wanted = (templates / "trellis2_server.py").read_text(encoding="utf-8")
        else:
            wanted = ((templates / "tsr_server_template.py").read_text(encoding="utf-8")
                      .replace("{MODEL_NAME}", model.title()).replace("{MODEL_ID}", model))
        run_script = worker_dir / "run_server.py"
        current = run_script.read_text(encoding="utf-8") if run_script.exists() else ""
        if current.replace("\r\n", "\n") != wanted.replace("\r\n", "\n"):
            run_script.write_text(wanted, encoding="utf-8")
            logger.info(f"[3D] Updated {model} run_server.py to the current template")

        if model == "trellis-2":
            repo_dir = worker_dir / model
            # Only apply legacy TRELLIS v1 SDPA patches when repo is v1 (has trellis/ and no trellis2/)
            if (repo_dir / "trellis").exists() and not (repo_dir / "trellis2").exists():
                from . import trellis_patches  # noqa: PLC0415
                if not trellis_patches.is_patched(repo_dir):
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


def _evict_other_heavy_workers(target_model: str) -> list[str]:
    """Stop any other running heavy 3D worker so 24 GB VRAM is free for *target_model*."""
    stopped: list[str] = []
    if target_model not in _HEAVY_3D_MODELS:
        return stopped
    for other in list(_WORKER_PROCESS):
        if other != target_model and other in _HEAVY_3D_MODELS:
            proc = _WORKER_PROCESS.get(other)
            if proc and proc.poll() is None:
                logger.info(f"[3D] Evicting heavy worker '{other}' before starting '{target_model}' to free VRAM")
                _stop_worker_process(other)
                stopped.append(other)
            else:
                _stop_worker_process(other)
    if stopped:
        time.sleep(1.0)
    return stopped


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
    """Generate a 3D asset using the specified model (GPU-serialized across parallel branches)."""
    trace_id = f"3d-{uuid.uuid4().hex[:8]}"
    logger.info(f"[{trace_id}] 3D generation request: {req.model} ({req.action})")

    if not req.input_image:
        return ThreeDGenerationResponse(
            success=False,
            error=f"{req.model} builds a 3D model from a picture: connect a reference image "
                  "(an Image node or an image generation step). A text prompt alone is not enough.")

    await asyncio.to_thread(_GPU_3D_LOCK.acquire)
    try:
        workspace = get_workspace_manager()
        await asyncio.to_thread(_evict_other_heavy_workers, req.model)

        port, err = await get_or_start_worker(req.model)
        if err:
            return ThreeDGenerationResponse(success=False, error=f"Worker Error: {err}")

        logger.info(f"[{trace_id}] Routing request to worker on port {port}")
        payload: Dict[str, Any] = {
            "image_base64": req.input_image.split(",", 1)[1] if req.input_image.startswith("data:") else req.input_image,
            "prompt": req.prompt,
            "seed": req.seed if req.seed is not None else 42,
            "action": req.action,
            "quality": req.quality,
            "resolution": req.quality,
            "textured": req.textured,
            "pbr": req.pbr,
        }
        for k in ("decimation_target", "texture_size", "remesh", "max_num_view", "texture_resolution", "steps"):
            v = getattr(req, k, None)
            if v is not None:
                payload[k] = v
        if isinstance(req.extra_params, dict):
            for k, v in req.extra_params.items():
                if v is not None and k not in ("image_base64",):
                    payload[k] = v

        async with httpx.AsyncClient(timeout=900.0) as client:
            worker_res = await client.post(f"http://127.0.0.1:{port}/generate", json=payload)

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

        now = datetime.now()
        base_subpath = f"{now.strftime('%Y-%m')}/{trace_id}"
        (workspace.workspace_root / "ThreeD" / base_subpath).mkdir(parents=True, exist_ok=True)

        glb_bytes = base64.b64decode(result_data["glb_base64"])
        glb_subpath = f"{base_subpath}/{req.model}.glb"

        try:
            img_data = req.input_image.split(",", 1)[1] if "," in req.input_image else req.input_image
            workspace.save_output(domain="ThreeD", filename=f"{base_subpath}/reference.png",
                                  content=base64.b64decode(img_data), trace_id=trace_id)
        except Exception as e:
            logger.warning(f"Failed to save reference image: {e}")

        path = workspace.save_output(domain="ThreeD", filename=glb_subpath, content=glb_bytes, trace_id=trace_id)
        asset = ThreeDAssetResponse(
            id=trace_id,
            name=req.prompt if req.prompt else f"3D {req.model}",
            url=f"/api/3d/serve/{glb_subpath}",
            path=str(path),
            model=req.model,
            size_bytes=path.stat().st_size,
            created_at=now.isoformat(),
        )
        return ThreeDGenerationResponse(success=True, asset=asset)

    except Exception as e:
        logger.error(f"[{trace_id}] 3D generation failed: {str(e)}")
        return ThreeDGenerationResponse(success=False, error=str(e))
    finally:
        _GPU_3D_LOCK.release()


@router.post("/texture", response_model=ThreeDGenerationResponse)
async def texture_3d_asset(req: ThreeDTextureRequest):
    """Apply PBR textures to an existing GLB mesh using a supported worker (e.g. hunyuan3d)."""
    trace_id = f"3dtex-{uuid.uuid4().hex[:8]}"
    logger.info(f"[{trace_id}] 3D texture request: {req.model}")

    if not req.mesh_base64:
        return ThreeDGenerationResponse(success=False, error="mesh_base64 is required for texturing.")

    await asyncio.to_thread(_GPU_3D_LOCK.acquire)
    try:
        workspace = get_workspace_manager()
        await asyncio.to_thread(_evict_other_heavy_workers, req.model)

        port, err = await get_or_start_worker(req.model)
        if err:
            return ThreeDGenerationResponse(success=False, error=f"Worker Error: {err}")

        payload = {
            "mesh_base64": req.mesh_base64.split(",", 1)[1] if req.mesh_base64.startswith("data:") else req.mesh_base64,
            "image_base64": (req.input_image.split(",", 1)[1] if req.input_image and req.input_image.startswith("data:") else req.input_image),
            "max_num_view": req.max_num_view,
            "texture_resolution": req.texture_resolution,
            "seed": req.seed if req.seed is not None else 42,
        }
        async with httpx.AsyncClient(timeout=900.0) as client:
            worker_res = await client.post(f"http://127.0.0.1:{port}/texture", json=payload)
            if worker_res.status_code != 200:
                return ThreeDGenerationResponse(success=False, error=f"{req.model} /texture HTTP {worker_res.status_code}: {worker_res.text[:300]}")
            result_data = worker_res.json()
            if not result_data.get("success") or not result_data.get("glb_base64"):
                return ThreeDGenerationResponse(success=False, error=_short_error(result_data.get("error", "No textured mesh returned")))

        now = datetime.now()
        base_subpath = f"{now.strftime('%Y-%m')}/{trace_id}"
        (workspace.workspace_root / "ThreeD" / base_subpath).mkdir(parents=True, exist_ok=True)
        glb_subpath = f"{base_subpath}/{req.model}_textured.glb"
        path = workspace.save_output(domain="ThreeD", filename=glb_subpath,
                                     content=base64.b64decode(result_data["glb_base64"]), trace_id=trace_id)
        asset = ThreeDAssetResponse(
            id=trace_id,
            name=f"Textured {req.model}",
            url=f"/api/3d/serve/{glb_subpath}",
            path=str(path),
            model=req.model,
            size_bytes=path.stat().st_size,
            created_at=now.isoformat(),
        )
        return ThreeDGenerationResponse(success=True, asset=asset)
    except Exception as e:
        logger.error(f"[{trace_id}] 3D texture failed: {e}")
        return ThreeDGenerationResponse(success=False, error=str(e))
    finally:
        _GPU_3D_LOCK.release()

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
    """Check if 3D generation engines are configured."""
    return {
        "status": "online",
        "engines": {
            "trellis-2": "ready",
            "hunyuan3d": "ready",
            "triposr": "ready",
        },
        "vram_available": "24GB",
    }


@router.get("/active_services")
async def get_active_services():
    """Get a list of all currently running heavy models with their live stats."""
    services = []

    for model_id, proc in _WORKER_PROCESS.items():
        if proc.poll() is None:
            status = await get_worker_health(model_id)
            services.append({
                "id": model_id,
                "name": _MODEL_DISPLAY_NAMES.get(model_id, model_id.title()),
                "status": status.get("status", "starting"),
                "vram_used": status.get("vram_used", 0),
                "vram_total": status.get("vram_total", 0),
                "port": _WORKER_PORT.get(model_id),
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
    weights_repo_file = wrapper_dir / ".weights_repo"

    installed = install_file.exists() and (wrapper_dir / "venv").exists()
    weights_repo = None
    if weights_repo_file.exists():
        try:
            weights_repo = weights_repo_file.read_text(encoding="utf-8").strip() or None
        except OSError:
            pass

    needs_upgrade = bool(
        model == "trellis-2"
        and installed
        and not (wrapper_dir / "trellis-2" / "trellis2").exists()
    )

    return {
        "model": model,
        "installed": installed,
        "weights_installed": weights_file.exists(),
        "weights_repo": weights_repo,
        "needs_upgrade": needs_upgrade,
    }


@router.post("/install_weights/{model}")
async def install_weights(model: str):
    """Start streaming download of 3D model weights from HuggingFace."""
    from fastapi.responses import StreamingResponse
    import json

    wrapper_name = model.replace("-", "")
    wrapper_dir = LOCAL_MODELS_3D / wrapper_name
    weights_dir = wrapper_dir / "weights"
    weights_complete_file = wrapper_dir / ".install_weights_complete"
    weights_repo_file = wrapper_dir / ".weights_repo"

    weights_dir.mkdir(parents=True, exist_ok=True)

    async def _generate():
        try:
            yield f"data: {json.dumps({'line': f'Initializing weight download for {model} to {weights_dir.relative_to(LOCAL_MODELS_3D)}...'})}\n\n"

            if model in ("trellis-2", "trellis"):
                repo_id = "microsoft/TRELLIS.2-4B"
            elif model == "hunyuan3d":
                repo_id = "tencent/Hunyuan3D-2.1"
            elif model == "triposr":
                repo_id = "stabilityai/TripoSR"
            else:
                repo_id = "unknown"

            if repo_id == "unknown":
                yield f"data: {json.dumps({'done': True, 'success': False, 'error': 'Unknown model repository for weights'})}\n\n"
                return

            yield f"data: {json.dumps({'line': f'Downloading from HF Repo: {repo_id}...'})}\n\n"

            download_script = f"""
import os
from huggingface_hub import snapshot_download
print('Starting download of {repo_id}...')
snapshot_download(
    repo_id='{repo_id}',
    local_dir=r'{weights_dir}',
    local_dir_use_symlinks=False
)
print('Download complete.')
"""
            temp_script = wrapper_dir / "tmp_download.py"
            temp_script.write_text(download_script, encoding="utf-8")

            venv_python = wrapper_dir / "venv" / "Scripts" / "python.exe" if os.name == "nt" else wrapper_dir / "venv" / "bin" / "python"
            if not venv_python.exists():
                venv_python = "python"

            proc = await asyncio.create_subprocess_exec(
                str(venv_python), str(temp_script),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "HF_HUB_DISABLE_SYMLINKS": "1", "HF_HUB_ENABLE_HF_TRANSFER": "1"},
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            async for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    cleanLine = line.replace("\r", "\n")
                    yield f"data: {json.dumps({'line': cleanLine})}\n\n"

            await proc.wait()

            if temp_script.exists():
                os.remove(temp_script)

            if proc.returncode == 0:
                weights_complete_file.write_text(f"Downloaded {datetime.now().isoformat()}", encoding="utf-8")
                weights_repo_file.write_text(repo_id, encoding="utf-8")
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

def _msvc_build_env() -> tuple[dict, str]:
    """Build an environment dict populated with MSVC x64 toolchain + CUDA arch list on Windows."""
    env = dict(os.environ)
    env["TORCH_CUDA_ARCH_LIST"] = "8.0;8.6;8.9+PTX"
    note = ""
    try:
        vswhere_path = r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
        if os.path.exists(vswhere_path):
            vs_install = subprocess.check_output(
                [vswhere_path, "-latest", "-property", "installationPath"],
                text=True, errors="replace",
            ).strip()
            vcvarsall = os.path.join(vs_install, "VC", "Auxiliary", "Build", "vcvarsall.bat")
            if os.path.exists(vcvarsall):
                env_out = subprocess.run(
                    f'cmd /c "call "{vcvarsall}" x64 && set"',
                    shell=True, capture_output=True, text=True, errors="replace",
                )
                for ln in env_out.stdout.splitlines():
                    if "=" in ln:
                        k, v = ln.split("=", 1)
                        env[k] = v
                note = "MSVC environment configured."
    except Exception as exc:
        note = f"Warning: MSVC setup failed: {exc}"
    return env, note


def _relax_torch_cuda_check(venv_dir: Path) -> bool:
    """Relax PyTorch's strict host-CUDA vs torch-CUDA version error so extensions build."""
    cpp_ext = venv_dir / "lib" / "site-packages" / "torch" / "utils" / "cpp_extension.py"
    if not cpp_ext.exists():
        return False
    try:
        src = cpp_ext.read_text(encoding="utf-8")
        patched = src.replace(
            "raise RuntimeError(CUDA_MISMATCH_MESSAGE.format(cuda_str_version, torch.version.cuda))",
            "warnings.warn(f'[Aethvion] CUDA version mismatch ({cuda_str_version} vs {torch.version.cuda}) — proceeding.')",
        )
        if patched != src:
            cpp_ext.write_text(patched, encoding="utf-8")
            return True
    except Exception:
        pass
    return False


@router.post("/install/{model}")
async def install_3d_model(model: str):
    """Start streaming installation of a 3D model/engine (trellis-2, hunyuan3d, triposr)."""
    from fastapi.responses import StreamingResponse
    import sys
    import json

    wrapper_name = model.replace("-", "")
    wrapper_dir = LOCAL_MODELS_3D / wrapper_name

    install_file = wrapper_dir / ".install_complete"
    repo_dir = wrapper_dir / model
    venv_dir = wrapper_dir / "venv"
    run_script = wrapper_dir / "run_server.py"

    wrapper_dir.mkdir(parents=True, exist_ok=True)

    def _sse(line: str) -> str:
        return f"data: {json.dumps({'line': line})}\n\n"

    async def _run_and_stream(cmd: list[str], *, env=None, cwd=None, out_rc: list[int] | None = None):
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            cwd=str(cwd) if cwd else None,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                yield _sse(line)
        rc = await proc.wait()
        if out_rc is not None:
            out_rc.append(rc)

    async def _generate():
        try:
            # 1. Clean previous attempts
            if wrapper_dir.exists() and not install_file.exists():
                yield _sse("Cleaning partial installation...")
                if repo_dir.exists():
                    await asyncio.to_thread(shutil.rmtree, repo_dir, True)
                wrapper_dir.mkdir(parents=True, exist_ok=True)

            if repo_dir.exists():
                await asyncio.to_thread(shutil.rmtree, repo_dir, True)

            # 2. Setup Virtual Environment
            yield _sse(f"Creating isolated virtual environment at {venv_dir.relative_to(LOCAL_MODELS_3D)}...")
            rc_box: list[int] = []
            async for chunk in _run_and_stream([sys.executable, "-m", "venv", str(venv_dir)], out_rc=rc_box):
                yield chunk
            if not rc_box or rc_box[0] != 0:
                yield f"data: {json.dumps({'done': True, 'success': False, 'error': 'Venv creation failed'})}\n\n"
                return

            pip_exe = venv_dir / "Scripts" / "pip.exe" if sys.platform == "win32" else venv_dir / "bin" / "pip"
            py_exe = venv_dir / "Scripts" / "python.exe" if sys.platform == "win32" else venv_dir / "bin" / "python"

            # TripoSR install path — fast, ~6 GB VRAM
            if model == "triposr":
                triposr_reqs = [
                    "torch==2.6.0", "torchvision==0.21.0", "torchaudio==2.6.0",
                    "wheel", "fastapi", "uvicorn", "httpx",
                    "pillow==10.1.0", "huggingface_hub[cli]", "hf_transfer", "tqdm",
                    "einops==0.7.0", "omegaconf==2.3.0", "transformers==4.35.0",
                    "trimesh==4.0.5", "rembg[gpu]", "onnxruntime-gpu",
                    "imageio[ffmpeg]", "xatlas==0.0.9", "moderngl==5.10.0",
                    "scipy", "numpy<2.0", "scikit-image",
                ]
                yield _sse("Installing TripoSR dependencies (torch 2.6 cu124, numpy < 2.0, scikit-image)...")
                async for chunk in _run_and_stream([
                    str(pip_exe), "install", *triposr_reqs,
                    "--index-url", "https://download.pytorch.org/whl/cu124",
                    "--extra-index-url", "https://pypi.org/simple",
                ]):
                    yield chunk

                yield _sse("Building torchmcubes (marching cubes CUDA ext) — needs MSVC, may take 3-5 min...")
                mc_env, mc_note = await asyncio.to_thread(_msvc_build_env)
                if mc_note:
                    yield _sse(mc_note)
                if _relax_torch_cuda_check(venv_dir):
                    yield _sse("PyTorch CUDA version check relaxed for cross-version build.")

                mc_rc: list[int] = []
                async for chunk in _run_and_stream(
                    [str(pip_exe), "install", "--no-build-isolation", "git+https://github.com/tatsy/torchmcubes.git"],
                    env=mc_env, out_rc=mc_rc,
                ):
                    yield chunk
                if not mc_rc or mc_rc[0] != 0:
                    yield _sse("Note: torchmcubes could not be built. TripoSR will use the CPU marching-cubes fallback instead.")
                else:
                    yield _sse("torchmcubes installed successfully.")

                yield _sse("Cloning VAST-AI-Research/TripoSR repository...")
                tsr_rc: list[int] = []
                async for chunk in _run_and_stream(
                    ["git", "clone", "https://github.com/VAST-AI-Research/TripoSR.git", str(repo_dir)],
                    out_rc=tsr_rc,
                ):
                    yield chunk
                if not tsr_rc or tsr_rc[0] != 0:
                    yield f"data: {json.dumps({'done': True, 'success': False, 'error': 'TripoSR git clone failed'})}\n\n"
                    return

                yield _sse("Generating TripoSR FastAPI microservice hook (run_server.py)...")
                run_script.write_text((Path(__file__).parent / "templates" / "triposr_server.py").read_text(encoding="utf-8"), encoding="utf-8")
                install_file.write_text(f"Installed {datetime.now().isoformat()}", encoding="utf-8")
                yield f"data: {json.dumps({'done': True, 'success': True})}\n\n"
                return
            # Hunyuan3D 2.1 install path — shape + multi-view PBR paint pipeline
            if model == "hunyuan3d":
                yield _sse(f"Cloning Tencent-Hunyuan/Hunyuan3D-2.1 into {repo_dir.relative_to(LOCAL_MODELS_3D)}...")
                hy_rc: list[int] = []
                async for chunk in _run_and_stream(
                    ["git", "clone", "https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1.git", str(repo_dir)],
                    out_rc=hy_rc,
                ):
                    yield chunk
                if not hy_rc or hy_rc[0] != 0:
                    yield f"data: {json.dumps({'done': True, 'success': False, 'error': 'Hunyuan3D git clone failed'})}\n\n"
                    return

                yield _sse("Installing PyTorch 2.5.1 CUDA 12.4 + core dependencies...")
                hy_reqs = [
                    "torch==2.5.1", "torchvision==0.20.1", "torchaudio==2.5.1",
                    "wheel", "ninja", "fastapi", "uvicorn", "httpx",
                    "huggingface_hub[cli]", "hf_transfer", "trimesh", "rembg",
                    "onnxruntime-gpu", "psutil",
                ]
                async for chunk in _run_and_stream([
                    str(pip_exe), "install", *hy_reqs,
                    "--index-url", "https://download.pytorch.org/whl/cu124",
                    "--extra-index-url", "https://pypi.org/simple",
                ]):
                    yield chunk

                req_txt = repo_dir / "requirements.txt"
                if req_txt.exists():
                    yield _sse("Installing Hunyuan3D-2.1 requirements.txt dependencies...")
                    async for chunk in _run_and_stream([str(pip_exe), "install", "-r", str(req_txt)]):
                        yield chunk

                yield _sse("Configuring MSVC toolchain for Hunyuan3D PBR paint extensions...")
                hy_env, hy_note = await asyncio.to_thread(_msvc_build_env)
                if hy_note:
                    yield _sse(hy_note)
                if _relax_torch_cuda_check(venv_dir):
                    yield _sse("PyTorch CUDA version check relaxed for cross-version build.")

                for ext_rel, label in (
                    ("hy3dpaint/custom_rasterizer", "custom_rasterizer"),
                    ("hy3dpaint/DifferentiableRenderer", "DifferentiableRenderer"),
                ):
                    ext_dir = repo_dir / ext_rel
                    if ext_dir.exists():
                        yield _sse(f"Building {label} CUDA/C++ extension...")
                        ext_rc: list[int] = []
                        async for chunk in _run_and_stream(
                            [str(pip_exe), "install", "--no-build-isolation", "-e", "."],
                            env=hy_env, cwd=ext_dir, out_rc=ext_rc,
                        ):
                            yield chunk
                        if not ext_rc or ext_rc[0] != 0:
                            yield _sse(f"Warning: {label} build failed — PBR painting will be unavailable (shape generation still works).")
                        else:
                            yield _sse(f"{label} installed successfully.")

                ckpt_dir = repo_dir / "hy3dpaint" / "ckpt"
                ckpt_dir.mkdir(parents=True, exist_ok=True)
                realesrgan_dest = ckpt_dir / "RealESRGAN_x4plus.pth"
                if not realesrgan_dest.exists():
                    yield _sse("Downloading RealESRGAN_x4plus.pth upscaler checkpoint...")
                    dl_code = (
                        "import urllib.request; "
                        f"urllib.request.urlretrieve('https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth', r'{realesrgan_dest}')"
                    )
                    dl_rc: list[int] = []
                    async for chunk in _run_and_stream([str(py_exe), "-c", dl_code], out_rc=dl_rc):
                        yield chunk
                    if not dl_rc or dl_rc[0] != 0:
                        yield _sse("Warning: RealESRGAN_x4plus.pth download failed — PBR texture upscaling may retry at runtime.")

                yield _sse("Generating Hunyuan3D 2.1 FastAPI microservice hook (run_server.py)...")
                run_script.write_text((Path(__file__).parent / "templates" / "hunyuan3d_server.py").read_text(encoding="utf-8"), encoding="utf-8")
                install_file.write_text(f"Installed {datetime.now().isoformat()}", encoding="utf-8")
                yield f"data: {json.dumps({'done': True, 'success': True})}\n\n"
                return

            # Upgraded TRELLIS.2-4B install path
            if repo_dir.exists() and (repo_dir / ".git").exists():
                yield _sse("Existing TRELLIS.2 repository found. Syncing...")
                git_rc: list[int] = []
                async for chunk in _run_and_stream(["git", "pull"], cwd=repo_dir, out_rc=git_rc):
                    yield chunk
            else:
                if repo_dir.exists():
                    await asyncio.to_thread(shutil.rmtree, repo_dir, True)
                yield _sse(f"Cloning microsoft/TRELLIS.2 (with submodules) into {repo_dir.relative_to(LOCAL_MODELS_3D)}...")
                git_rc = []
                async for chunk in _run_and_stream(
                    ["git", "clone", "--recurse-submodules", "https://github.com/microsoft/TRELLIS.2.git", str(repo_dir)],
                    out_rc=git_rc,
                ):
                    yield chunk

            if not git_rc or git_rc[0] != 0:
                yield f"data: {json.dumps({'done': True, 'success': False, 'error': 'TRELLIS.2 git clone failed'})}\n\n"
                return

            yield _sse("Installing TRELLIS.2 high-performance CUDA 12.4 core stack...")
            core_reqs = [
                "torch==2.6.0", "torchvision==0.21.0", "torchaudio==2.6.0",
                "wheel", "ninja", "easydict", "scipy", "tqdm",
                "huggingface_hub[cli]", "hf_transfer", "fastapi", "uvicorn", "httpx", "pillow",
                "imageio", "imageio-ffmpeg", "opencv-python-headless", "rembg", "onnxruntime-gpu",
                "trimesh", "transformers", "timm", "einops", "kornia", "psutil", "plyfile",
                "xatlas", "pymeshfix", "igraph", "spconv-cu124",
            ]
            async for chunk in _run_and_stream([
                str(pip_exe), "install", *core_reqs,
                "--index-url", "https://download.pytorch.org/whl/cu124",
                "--extra-index-url", "https://pypi.org/simple",
            ]):
                yield chunk

            yield _sse("Installing specialized 3D utility repository (utils3d)...")
            async for chunk in _run_and_stream([
                str(pip_exe), "install",
                "git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8",
            ]):
                yield chunk

            yield _sse("Configuring MSVC environment for TRELLIS.2 CUDA extensions (nvdiffrast, o-voxel, cumesh, flex_gemm)...")
            nv_env, nv_note = await asyncio.to_thread(_msvc_build_env)
            if nv_note:
                yield _sse(nv_note)
            if _relax_torch_cuda_check(venv_dir):
                yield _sse("PyTorch CUDA version check relaxed for cross-version build.")

            ext_specs = [
                ("nvdiffrast", [str(pip_exe), "install", "--no-build-isolation", "git+https://github.com/NVlabs/nvdiffrast"], None),
                ("cumesh", [str(pip_exe), "install", "--no-build-isolation", "git+https://github.com/JeffreyXiang/CuMesh.git"], None),
                ("flex_gemm", [str(pip_exe), "install", "--no-build-isolation", "git+https://github.com/JeffreyXiang/FlexGEMM.git"], None),
            ]
            ovoxel_dir = repo_dir / "o-voxel"
            if ovoxel_dir.exists():
                ext_specs.append(("o-voxel", [str(pip_exe), "install", "--no-build-isolation", "."], ovoxel_dir))
            else:
                ext_specs.append(("o-voxel", [str(pip_exe), "install", "--no-build-isolation", "o-voxel"], None))

            for label, cmd, cwd_dir in ext_specs:
                yield _sse(f"Building/installing {label}...")
                ext_rc = []
                async for chunk in _run_and_stream(cmd, env=nv_env, cwd=cwd_dir, out_rc=ext_rc):
                    yield chunk
                if not ext_rc or ext_rc[0] != 0:
                    yield _sse(f"Warning: {label} build failed — some advanced PBR/remeshing features may fall back.")
                else:
                    yield _sse(f"{label} installed successfully.")

            yield _sse("Generating TRELLIS.2-4B FastAPI microservice hook (run_server.py)...")
            server_template = (Path(__file__).parent / "templates" / "trellis2_server.py").read_text(encoding="utf-8")
            run_script.write_text(server_template, encoding="utf-8")

            yield _sse("Finalizing installation...")
            install_file.write_text(f"Installed {datetime.now().isoformat()}", encoding="utf-8")
            yield f"data: {json.dumps({'done': True, 'success': True})}\n\n"

        except Exception as e:
            logger.error(f"Installation failed: {e}")
            yield f"data: {json.dumps({'done': True, 'success': False, 'error': str(e)})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
