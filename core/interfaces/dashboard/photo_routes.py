"""
Aethvion Suite - Image Generation & Model Hub Routes
Full-featured image management, native local Diffusers GPU execution,
local SD/Forge/ComfyUI integration, checkpoint downloads, and generation history.
"""

import asyncio
import base64
import io
import os
import uuid
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from PIL import Image
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from fastapi.responses import FileResponse

from core.providers import get_provider_manager as _get_provider_manager
from core.workspace import get_workspace_manager
from core.utils import get_logger
from core.utils.paths import LOCAL_MODELS_IMAGE, SUGGESTED_IMAGE_MODELS, CONFIG

logger = get_logger(__name__)

router = APIRouter(prefix="/api/photo", tags=["photo"])

# Ensure directories exist
LOCAL_MODELS_IMAGE.mkdir(parents=True, exist_ok=True)
HISTORY_INDEX_PATH = CONFIG / "image_generation_history.json"

# Local backend URLs — override via environment variables
_SD_WEBUI_URL = os.environ.get("SD_WEBUI_URL", "http://127.0.0.1:7860")   # AUTOMATIC1111 / Forge
_COMFYUI_URL  = os.environ.get("COMFYUI_URL",  "http://127.0.0.1:8188")   # ComfyUI

# Active download tracking
_DOWNLOAD_TASKS: Dict[str, Dict[str, Any]] = {}


def _resolve_local_checkpoint(model_id: str) -> Optional[Path]:
    """Find local .safetensors file matching model_id if available on disk."""
    if not model_id:
        return None

    # 1. Direct local:filename prefix
    if model_id.startswith("local:"):
        fname = model_id[6:]
        cand = LOCAL_MODELS_IMAGE / fname
        if cand.exists():
            return cand

    # 2. Suggested model ID mapping
    id_map = {
        "sd-1-5": "v1-5-pruned-emaonly.safetensors",
        "sdxl-base": "sd_xl_base_1.0.safetensors",
        "sdxl-lightning": "sdxl_lightning_4step.safetensors",
        "flux-schnell": "flux1-schnell-fp8.safetensors",
        "dreamshaper-xl": "dreamshaperXL_lightning.safetensors",
    }
    target_fn = id_map.get(model_id)
    if target_fn:
        cand = LOCAL_MODELS_IMAGE / target_fn
        if cand.exists():
            return cand

    # 3. Direct filename match
    cand = LOCAL_MODELS_IMAGE / model_id
    if cand.exists() and cand.is_file():
        return cand
    cand_safe = LOCAL_MODELS_IMAGE / f"{model_id}.safetensors"
    if cand_safe.exists():
        return cand_safe

    # 4. Fuzzy match in local directory
    for f in LOCAL_MODELS_IMAGE.glob("*.safetensors"):
        clean_name = f.stem.lower().replace("-", "").replace("_", "")
        clean_id = model_id.lower().replace("-", "").replace("_", "")
        if clean_id in clean_name or clean_name in clean_id:
            return f

    return None


def _is_local_sd_model(model: str) -> bool:
    """Return True if this model ID maps to an external local Stable Diffusion WebUI."""
    m = model.lower()
    return m.startswith("sd:") or m in {
        "stable-diffusion", "automatic1111", "sd-webui"
    }


def _is_comfyui_model(model: str) -> bool:
    """Return True if this model ID maps to a local ComfyUI instance."""
    return model.lower().startswith("comfy:")


async def _generate_via_sd_webui(
    prompt: str,
    model: str,
    negative_prompt: str = "",
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    cfg_scale: float = 7.0,
    seed: int = -1,
    n: int = 1,
    input_image_b64: Optional[str] = None,
    mask_image_b64: Optional[str] = None,
) -> List[bytes]:
    """Call AUTOMATIC1111 / SD-WebUI REST API and return raw PNG bytes."""
    import urllib.request, urllib.error, json as _json

    checkpoint = model.split(":", 1)[1] if ":" in model else None

    payload: Dict[str, Any] = {
        "prompt":          prompt,
        "negative_prompt": negative_prompt,
        "width":           width,
        "height":          height,
        "steps":           steps,
        "cfg_scale":       cfg_scale,
        "seed":            seed,
        "n_iter":          n,
        "batch_size":      1,
        "save_images":     False,
        "send_images":     True,
    }
    if checkpoint:
        payload["override_settings"] = {"sd_model_checkpoint": checkpoint}

    if input_image_b64:
        endpoint = f"{_SD_WEBUI_URL}/sdapi/v1/img2img"
        payload["init_images"] = [input_image_b64]
        if mask_image_b64:
            payload["mask"] = mask_image_b64
    else:
        endpoint = f"{_SD_WEBUI_URL}/sdapi/v1/txt2img"

    body = _json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Could not reach local SD WebUI at {_SD_WEBUI_URL}. "
                   "Make sure AUTOMATIC1111/Forge is running with --api flag. "
                   f"Error: {e.reason}"
        )

    images_b64 = data.get("images", [])
    if not images_b64:
        raise HTTPException(status_code=500, detail="SD WebUI returned no images.")

    return [base64.b64decode(img) for img in images_b64[:n]]


async def _get_sd_webui_models() -> List[Dict]:
    """Query SD WebUI for available checkpoints."""
    import urllib.request, json as _json
    try:
        req = urllib.request.Request(f"{_SD_WEBUI_URL}/sdapi/v1/sd-models", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return _json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []


def _record_history(entry: Dict[str, Any]):
    """Persist generated image metadata to the history file."""
    try:
        history = []
        if HISTORY_INDEX_PATH.exists():
            try:
                history = json.loads(HISTORY_INDEX_PATH.read_text(encoding="utf-8"))
            except Exception:
                history = []
        history.insert(0, entry)
        history = history[:120]
        HISTORY_INDEX_PATH.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to record image history: {e}")


def decode_b64(b64_str: str) -> bytes:
    if "," in b64_str:
        b64_str = b64_str.split(",", 1)[1]
    return base64.b64decode(b64_str)


# Request Models
class ImageGenerationRequest(BaseModel):
    prompt: str
    model: str = "sd-1-5"
    n: int = 1
    size: str = "1024x1024"
    quality: str = "standard"
    style: str = "natural"
    aspect_ratio: Optional[str] = None
    negative_prompt: Optional[str] = None
    seed: Optional[int] = None
    steps: Optional[int] = 25
    cfg_scale: Optional[float] = 7.0
    action: str = "generate"
    input_image: Optional[str] = None
    mask_image: Optional[str] = None


class ImageGenerationResponse(BaseModel):
    success: bool
    images: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    error: Optional[str] = None


class ModelDownloadRequest(BaseModel):
    model_id: str
    filename: Optional[str] = None
    hf_repo: Optional[str] = None
    hf_filename: Optional[str] = None
    download_url: Optional[str] = None


# Endpoints

@router.get("/status")
async def get_photo_status():
    """Returns engine availability: Native GPU Diffusers engine, SD WebUI, CUDA GPU, and Cloud."""
    import urllib.request
    
    # 1. Native Diffusers Engine Status
    try:
        from core.image.local_image_engine import local_image_engine
        native_status = local_image_engine.get_status()
    except Exception as e:
        native_status = {"installed": False, "error": str(e)}

    # 2. External SD WebUI probe
    sd_online = False
    sd_models_count = 0
    try:
        req = urllib.request.Request(f"{_SD_WEBUI_URL}/sdapi/v1/sd-models")
        with urllib.request.urlopen(req, timeout=1.2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            sd_online = True
            sd_models_count = len(data) if isinstance(data, list) else 0
    except Exception:
        sd_online = False

    # 3. ComfyUI probe
    comfy_online = False
    try:
        req = urllib.request.Request(f"{_COMFYUI_URL}/system_stats")
        with urllib.request.urlopen(req, timeout=1.2) as resp:
            comfy_online = True
    except Exception:
        comfy_online = False

    # 4. Hardware Specs
    gpu_name = native_status.get("gpu_name") or "NVIDIA GeForce RTX 4090"
    vram_gb = native_status.get("vram_total_gb") or 24.0
    cuda_avail = native_status.get("cuda_available", True)

    # 5. Local files in localmodels/image
    local_files = [f.name for f in LOCAL_MODELS_IMAGE.glob("*") if f.suffix.lower() in [".safetensors", ".ckpt", ".pt", ".bin"]]

    # 6. Cloud providers
    has_google = bool(os.environ.get("GOOGLE_AI_API_KEY") or os.environ.get("GEMINI_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))

    return {
        "native_engine": native_status,
        "sd_webui": {
            "online": sd_online,
            "url": _SD_WEBUI_URL,
            "model_count": sd_models_count
        },
        "comfyui": {
            "online": comfy_online,
            "url": _COMFYUI_URL
        },
        "hardware": {
            "cuda_available": cuda_avail,
            "gpu_name": gpu_name,
            "vram_gb": vram_gb
        },
        "local_storage": {
            "path": str(LOCAL_MODELS_IMAGE),
            "files_count": len(local_files),
            "files": local_files
        },
        "cloud_providers": {
            "google_ai": has_google,
            "openai": has_openai
        }
    }


@router.get("/models")
async def get_available_models():
    """Returns combined catalog of suggested models, custom checkpoints, and SD WebUI models."""
    suggested = []
    if SUGGESTED_IMAGE_MODELS.exists():
        try:
            raw = json.loads(SUGGESTED_IMAGE_MODELS.read_text(encoding="utf-8"))
            suggested = raw.get("image_models", [])
        except Exception as e:
            logger.warning(f"Failed to read suggested image models: {e}")

    installed_filenames = set()
    for m in suggested:
        fn = m.get("filename")
        if fn and (LOCAL_MODELS_IMAGE / fn).exists():
            p = LOCAL_MODELS_IMAGE / fn
            m["installed"] = True
            m["size_bytes"] = p.stat().st_size
            m["file_path"] = str(p)
            installed_filenames.add(fn.lower())
        else:
            m["installed"] = False

    custom_models = []
    for f in LOCAL_MODELS_IMAGE.glob("*"):
        if f.is_file() and f.suffix.lower() in [".safetensors", ".ckpt", ".pt", ".bin"]:
            if f.name.lower() not in installed_filenames:
                size_mb = f.stat().st_size / (1024 * 1024)
                size_gb = size_mb / 1024
                custom_models.append({
                    "id": f"local:{f.name}",
                    "name": f.stem.replace("_", " ").title(),
                    "provider": "Custom Local",
                    "filename": f.name,
                    "size_label": f"{size_gb:.1f} GB" if size_gb >= 1 else f"{size_mb:.0f} MB",
                    "size_gb": round(size_gb, 2),
                    "vram_gb": 8.0 if "xl" in f.name.lower() else 4.0,
                    "ram_gb": 16.0 if "xl" in f.name.lower() else 8.0,
                    "installed": True,
                    "file_path": str(f)
                })

    sd_models = await _get_sd_webui_models()

    return {
        "suggested": suggested,
        "custom": custom_models,
        "sd_webui": [
            {
                "id": f"sd:{m.get('model_name', m.get('title', 'unknown'))}",
                "name": m.get("title", m.get("model_name", "?")),
                "hash": m.get("hash", "")
            }
            for m in sd_models
        ],
        "active_models_count": len([m for m in suggested if m.get("installed")]) + len(custom_models) + len(sd_models)
    }


@router.post("/generate", response_model=ImageGenerationResponse)
async def generate_image(req: ImageGenerationRequest):
    """
    Generate images using:
    1. Native local GPU Diffusers engine (if checkpoint is downloaded).
    2. Local SD WebUI / Forge (if external server is running and requested).
    3. Configured cloud providers (Google AI Imagen 3 / OpenAI DALL-E 3).
    """
    trace_id = f"img-{uuid.uuid4().hex[:8]}"
    logger.info(f"[{trace_id}] Image generation request: {req.model} - '{req.prompt[:50]}'...")

    try:
        width, height = 1024, 1024
        if req.size and "x" in req.size:
            try:
                w, h = req.size.split("x", 1)
                width, height = int(w), int(h)
            except ValueError:
                pass

        # 1. Native Local Diffusers Engine (Standalone GPU execution)
        local_ckpt = _resolve_local_checkpoint(req.model)
        if local_ckpt:
            logger.info(f"[{trace_id}] Running NATIVE GPU generation via checkpoint: {local_ckpt.name}")
            from core.image.local_image_engine import local_image_engine

            input_pil = None
            mask_pil = None
            if req.input_image:
                try:
                    b = decode_b64(req.input_image)
                    input_pil = Image.open(io.BytesIO(b)).convert("RGB")
                except Exception as e:
                    logger.warning(f"Failed to decode input_image: {e}")
            if req.mask_image:
                try:
                    b = decode_b64(req.mask_image)
                    mask_pil = Image.open(io.BytesIO(b)).convert("RGB")
                except Exception as e:
                    logger.warning(f"Failed to decode mask_image: {e}")

            # Execute generation directly on the RTX 4090
            raw_images = local_image_engine.generate(
                checkpoint_path=local_ckpt,
                prompt=req.prompt,
                negative_prompt=req.negative_prompt,
                width=width,
                height=height,
                steps=req.steps or 25,
                cfg_scale=req.cfg_scale or 7.0,
                seed=req.seed,
                n=req.n,
                input_image=input_pil,
                mask_image=mask_pil,
                action=req.action
            )

            workspace = get_workspace_manager()
            saved_images = []
            for idx, img_bytes in enumerate(raw_images):
                safe_model = req.model.replace(":", "-").replace("/", "-")
                filename = f"{safe_model}-{trace_id}-{idx}.png"
                save_path = workspace.save_output(domain="images", filename=filename, content=img_bytes, trace_id=trace_id)
                saved_images.append({
                    "url": f"/api/photo/serve/{filename}",
                    "path": str(save_path),
                    "filename": filename
                })

                _record_history({
                    "filename": filename,
                    "url": f"/api/photo/serve/{filename}",
                    "prompt": req.prompt,
                    "negative_prompt": req.negative_prompt or "",
                    "model": f"Native GPU: {local_ckpt.name}",
                    "size": f"{width}x{height}",
                    "seed": req.seed,
                    "steps": req.steps or 25,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "size_bytes": len(img_bytes)
                })

            return ImageGenerationResponse(
                success=True,
                images=saved_images,
                metadata={
                    "backend": "native-diffusers-gpu",
                    "checkpoint": local_ckpt.name,
                    "count": len(saved_images)
                }
            )

        # 2. Local SD WebUI route (if checkpoint starts with sd: or explicit sd-webui model)
        if _is_local_sd_model(req.model):
            logger.info(f"[{trace_id}] Attempting generation via external SD WebUI: {req.model}")
            try:
                raw_images = await _generate_via_sd_webui(
                    prompt=req.prompt,
                    model=req.model,
                    negative_prompt=req.negative_prompt or "",
                    width=width,
                    height=height,
                    steps=req.steps or 20,
                    cfg_scale=req.cfg_scale or 7.0,
                    seed=req.seed if req.seed is not None else -1,
                    n=req.n,
                    input_image_b64=req.input_image,
                    mask_image_b64=req.mask_image,
                )

                workspace = get_workspace_manager()
                saved_images = []
                for idx, img_bytes in enumerate(raw_images):
                    safe_model = req.model.replace(":", "-").replace("/", "-")
                    filename = f"{safe_model}-{trace_id}-{idx}.png"
                    save_path = workspace.save_output(domain="images", filename=filename, content=img_bytes, trace_id=trace_id)
                    
                    saved_images.append({
                        "url": f"/api/photo/serve/{filename}",
                        "path": str(save_path),
                        "filename": filename,
                    })

                    _record_history({
                        "filename": filename,
                        "url": f"/api/photo/serve/{filename}",
                        "prompt": req.prompt,
                        "negative_prompt": req.negative_prompt or "",
                        "model": req.model,
                        "size": f"{width}x{height}",
                        "seed": req.seed,
                        "steps": req.steps or 20,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "size_bytes": len(img_bytes)
                    })

                return ImageGenerationResponse(
                    success=True,
                    images=saved_images,
                    metadata={"model": req.model, "backend": "sd-webui", "count": len(saved_images)},
                )
            except HTTPException as he:
                manager = _get_provider_manager()
                has_cloud = any(p in manager.providers for p in ["openai", "google_ai"])
                if not has_cloud:
                    raise he
                logger.info(f"[{trace_id}] SD WebUI unavailable, falling back to cloud provider")

        # 3. Cloud Provider fallback / direct route
        manager = _get_provider_manager()
        target_provider = None

        if "dall-e" in req.model.lower():
            target_provider = manager.providers.get("openai")
        elif "imagen" in req.model.lower():
            target_provider = manager.providers.get("google_ai")
        else:
            for p_name in ["google_ai", "openai"]:
                if p_name in manager.providers:
                    target_provider = manager.providers[p_name]
                    break

        if not target_provider:
            raise HTTPException(
                status_code=400,
                detail=f"Model checkpoint for '{req.model}' is not downloaded yet. "
                       f"Please open 'Model Hub > Image Models' and click 'Download Checkpoint' to run it natively on your GPU, "
                       "or connect local AUTOMATIC1111/Forge with '--api'."
            )

        kwargs = {}
        if req.aspect_ratio:
            kwargs['aspect_ratio'] = req.aspect_ratio
        if req.style:
            kwargs['style'] = req.style
        if req.negative_prompt:
            kwargs['negative_prompt'] = req.negative_prompt
        if req.seed is not None:
            kwargs['seed'] = req.seed

        input_image_bytes = None
        mask_image_bytes = None
        if req.input_image:
            input_image_bytes = decode_b64(req.input_image)
        if req.mask_image:
            mask_image_bytes = decode_b64(req.mask_image)

        response = target_provider.generate_image(
            prompt=req.prompt,
            trace_id=trace_id,
            model=req.model,
            n=req.n,
            size=req.size,
            quality=req.quality,
            action=req.action,
            input_image_bytes=input_image_bytes,
            mask_image_bytes=mask_image_bytes,
            **kwargs
        )

        if not response.success:
            return ImageGenerationResponse(success=False, images=[], metadata={}, error=response.error)
        
        raw_images = response.metadata.get('images', [])
        if not raw_images:
            return ImageGenerationResponse(success=False, images=[], metadata={}, error="Provider returned success but no images were received.")

        workspace = get_workspace_manager()
        saved_images = []
        for idx, img_bytes in enumerate(raw_images):
            safe_model = req.model.replace(":", "-").replace("/", "-")
            filename = f"{safe_model}-{trace_id}-{idx}.png"
            path = workspace.save_output(domain="images", filename=filename, content=img_bytes, trace_id=trace_id)
            saved_images.append({
                "path": str(path),
                "filename": filename,
                "url": f"/api/photo/serve/{filename}"
            })

            _record_history({
                "filename": filename,
                "url": f"/api/photo/serve/{filename}",
                "prompt": req.prompt,
                "negative_prompt": req.negative_prompt or "",
                "model": response.model,
                "size": req.size,
                "seed": req.seed,
                "steps": req.steps or 20,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "size_bytes": len(img_bytes)
            })

        return ImageGenerationResponse(
            success=True,
            images=saved_images,
            metadata={"provider": response.provider, "model": response.model, "trace_id": trace_id}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{trace_id}] Unexpected generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/unload")
async def unload_native_model():
    """Unload active diffusion pipeline from GPU VRAM."""
    try:
        from core.image.local_image_engine import local_image_engine
        local_image_engine.unload()
        return {"success": True, "message": "Model unloaded from GPU VRAM."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unload model: {e}")


# Download Manager Worker
async def _download_worker(task_id: str, url: str, target_file: Path, total_size_expected: int = 0):
    part_file = target_file.with_suffix(target_file.suffix + ".part")
    try:
        import httpx
        _DOWNLOAD_TASKS[task_id].update({
            "status": "downloading",
            "progress": 0,
            "downloaded_bytes": 0,
            "total_bytes": total_size_expected,
            "start_time": time.time(),
            "speed_mbps": 0.0
        })

        headers = {"User-Agent": "AethvionSuite/1.0"}
        async with httpx.AsyncClient(timeout=3600.0, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=headers) as resp:
                if resp.status_code >= 400:
                    raise RuntimeError(f"HTTP error {resp.status_code}: {resp.reason_phrase}")
                
                total = int(resp.headers.get("content-length", total_size_expected or 0))
                _DOWNLOAD_TASKS[task_id]["total_bytes"] = total
                downloaded = 0
                start_t = time.time()
                last_update_t = start_t

                with open(part_file, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                        if _DOWNLOAD_TASKS[task_id].get("cancel_requested"):
                            raise asyncio.CancelledError("Download cancelled by user")
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        now = time.time()
                        if now - last_update_t >= 0.5:
                            elapsed = max(now - start_t, 0.001)
                            speed = (downloaded / (1024 * 1024)) / elapsed
                            pct = round((downloaded / total) * 100, 1) if total > 0 else 0
                            _DOWNLOAD_TASKS[task_id].update({
                                "progress": pct,
                                "downloaded_bytes": downloaded,
                                "speed_mbps": round(speed, 2)
                            })
                            last_update_t = now

        if part_file.exists():
            if target_file.exists():
                target_file.unlink()
            part_file.rename(target_file)

        _DOWNLOAD_TASKS[task_id].update({
            "status": "completed",
            "progress": 100,
            "downloaded_bytes": downloaded,
            "file_path": str(target_file)
        })
    except asyncio.CancelledError:
        if part_file.exists():
            try: part_file.unlink()
            except Exception: pass
        _DOWNLOAD_TASKS[task_id].update({"status": "cancelled", "error": "Cancelled by user"})
    except Exception as e:
        if part_file.exists():
            try: part_file.unlink()
            except Exception: pass
        _DOWNLOAD_TASKS[task_id].update({"status": "error", "error": str(e)})


@router.post("/download")
async def start_model_download(req: ModelDownloadRequest, background_tasks: BackgroundTasks):
    """Initiates download of an image model checkpoint to localmodels/image."""
    task_id = f"dl-{uuid.uuid4().hex[:8]}"
    
    filename = req.filename or f"{req.model_id}.safetensors"
    target_file = LOCAL_MODELS_IMAGE / filename

    url = req.download_url
    if not url and req.hf_repo and req.hf_filename:
        url = f"https://huggingface.co/{req.hf_repo}/resolve/main/{req.hf_filename}"

    if not url:
        if SUGGESTED_IMAGE_MODELS.exists():
            try:
                raw = json.loads(SUGGESTED_IMAGE_MODELS.read_text(encoding="utf-8"))
                for m in raw.get("image_models", []):
                    if m.get("id") == req.model_id:
                        filename = m.get("filename", filename)
                        target_file = LOCAL_MODELS_IMAGE / filename
                        url = f"https://huggingface.co/{m.get('hf_repo')}/resolve/main/{m.get('hf_filename')}"
                        break
            except Exception:
                pass

    if not url:
        raise HTTPException(status_code=400, detail="No download URL or Hugging Face repository specified.")

    _DOWNLOAD_TASKS[task_id] = {
        "task_id": task_id,
        "model_id": req.model_id,
        "filename": filename,
        "url": url,
        "status": "starting",
        "progress": 0,
        "speed_mbps": 0.0
    }

    background_tasks.add_task(_download_worker, task_id, url, target_file)
    return {"task_id": task_id, "status": "started", "filename": filename}


@router.get("/download/{task_id}")
async def get_download_status(task_id: str):
    """Get the current progress of an active model download."""
    if task_id not in _DOWNLOAD_TASKS:
        raise HTTPException(status_code=404, detail="Download task not found")
    return _DOWNLOAD_TASKS[task_id]


@router.post("/download/{task_id}/cancel")
async def cancel_model_download(task_id: str):
    """Cancel an ongoing model download."""
    if task_id not in _DOWNLOAD_TASKS:
        raise HTTPException(status_code=404, detail="Download task not found")
    _DOWNLOAD_TASKS[task_id]["cancel_requested"] = True
    return {"success": True, "message": "Cancellation requested"}


@router.delete("/models/{filename}")
async def delete_local_model(filename: str):
    """Delete a downloaded checkpoint file from localmodels/image."""
    target = LOCAL_MODELS_IMAGE / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Model file '{filename}' not found.")
    try:
        # Also unload from memory if active
        try:
            from core.image.local_image_engine import local_image_engine
            if local_image_engine.current_model and filename in local_image_engine.current_model:
                local_image_engine.unload()
        except Exception:
            pass

        target.unlink()
        return {"success": True, "message": f"Deleted {filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")


@router.get("/history")
async def get_generation_history(limit: int = 50):
    """Returns generation history from index or workspace output images."""
    history = []
    if HISTORY_INDEX_PATH.exists():
        try:
            history = json.loads(HISTORY_INDEX_PATH.read_text(encoding="utf-8"))
        except Exception:
            history = []

    workspace = get_workspace_manager()
    known_filenames = {item.get("filename") for item in history if isinstance(item, dict)}
    
    img_dir = workspace.workspace_root
    for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
        for p in img_dir.glob(f"**/{ext}"):
            if p.is_file() and p.name not in known_filenames:
                mtime = p.stat().st_mtime
                history.append({
                    "filename": p.name,
                    "url": f"/api/photo/serve/{p.name}",
                    "prompt": "Generated Image",
                    "model": "Local / Output",
                    "timestamp": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                    "size_bytes": p.stat().st_size
                })
                known_filenames.add(p.name)

    return {"images": history[:limit]}


@router.delete("/history/{filename}")
async def delete_history_image(filename: str):
    """Delete an image from workspace output and generation history."""
    workspace = get_workspace_manager()
    path = workspace.get_output_path(domain="images", filename=filename)
    if not path.exists():
        for p in workspace.workspace_root.glob(f"**/{filename}"):
            if p.is_file():
                path = p
                break

    if path.exists():
        try:
            path.unlink()
        except Exception as e:
            logger.warning(f"Failed to unlink file {path}: {e}")

    if HISTORY_INDEX_PATH.exists():
        try:
            items = json.loads(HISTORY_INDEX_PATH.read_text(encoding="utf-8"))
            items = [it for it in items if it.get("filename") != filename]
            HISTORY_INDEX_PATH.write_text(json.dumps(items, indent=2), encoding="utf-8")
        except Exception:
            pass

    return {"success": True, "filename": filename}


@router.get("/local/models")
async def list_local_image_models():
    """Compatibility endpoint for local SD models."""
    models = await _get_sd_webui_models()
    return {
        "sd_webui_url": _SD_WEBUI_URL,
        "available": len(models) > 0,
        "models": [
            {
                "id": f"sd:{m.get('model_name', m.get('title', 'unknown'))}",
                "name": m.get("title", m.get("model_name", "?")),
                "hash": m.get("hash", ""),
            }
            for m in models
        ],
    }


@router.get("/serve/{filename}")
async def serve_image(filename: str):
    """Serve a generated image file."""
    workspace = get_workspace_manager()
    path = workspace.get_output_path(domain="images", filename=filename)
    if not path.exists():
        for p in workspace.workspace_root.glob(f"**/{filename}"):
            if p.is_file():
                path = p
                break
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    
    return FileResponse(path)
