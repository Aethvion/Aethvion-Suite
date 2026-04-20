"""
Aethvion Suite - Image Generation Routes
API endpoints for image generation via LLM providers.

Supported backends:
  - DALL-E 3          (OpenAI)
  - Imagen 3          (Google AI)
  - Stable Diffusion  (local SD WebUI / AUTOMATIC1111 API at http://127.0.0.1:7860)
  - ComfyUI           (local, at http://127.0.0.1:8188)
"""

import base64
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from core.providers import ProviderManager
from core.workspace import get_workspace_manager
from core.utils import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/photo", tags=["photo"])

# ── Local SD backend defaults (configurable via env or settings) ───────────────
_SD_WEBUI_URL  = "http://127.0.0.1:7860"   # AUTOMATIC1111 / Forge
_COMFYUI_URL   = "http://127.0.0.1:8188"   # ComfyUI


def _is_local_sd_model(model: str) -> bool:
    """Return True if this model ID maps to the local Stable Diffusion WebUI."""
    m = model.lower()
    return m.startswith("sd:") or m.startswith("sdxl:") or m in {
        "stable-diffusion", "stable-diffusion-xl", "sdxl", "sd15", "sd21",
        "automatic1111", "sd-webui",
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
    """
    Call the AUTOMATIC1111 / SD-WebUI REST API and return raw PNG bytes.

    Endpoint used:
      txt2img: POST /sdapi/v1/txt2img
      img2img: POST /sdapi/v1/img2img  (when input_image_b64 is provided)
    """
    import urllib.request, urllib.error, json as _json

    # Strip model prefix if present (e.g. "sd:v1-5-pruned.ckpt" → "v1-5-pruned.ckpt")
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
    req  = urllib.request.Request(endpoint, data=body,
                                   headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
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
    import urllib.request, urllib.error, json as _json
    try:
        req = urllib.request.Request(f"{_SD_WEBUI_URL}/sdapi/v1/sd-models",
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return _json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []

# Global provider manager instance for this router
# Note: This creates a second instance if server.py also has one,
# but avoids circular imports.
_provider_manager = None

def get_provider_manager() -> ProviderManager:
    global _provider_manager
    if _provider_manager is None:
        _provider_manager = ProviderManager()
    return _provider_manager

class ImageGenerationRequest(BaseModel):
    prompt: str
    model: str
    n: int = 1
    size: str = "1024x1024"
    quality: str = "standard" # standard, hd
    style: str = "natural" # vivid, natural (DALL-E 3 specific)
    aspect_ratio: Optional[str] = None # 1:1, 16:9 (Imagen specific)
    negative_prompt: Optional[str] = None
    seed: Optional[int] = None
    action: str = "generate"
    input_image: Optional[str] = None  # base64 encoded string
    mask_image: Optional[str] = None   # base64 encoded string

class ImageGenerationResponse(BaseModel):
    success: bool
    images: List[Dict[str, Any]] # {url, path, filename}
    metadata: Dict[str, Any]
    error: Optional[str] = None

@router.post("/generate", response_model=ImageGenerationResponse)
async def generate_image(req: ImageGenerationRequest):
    """
    Generate images using the specified model.
    """
    trace_id = f"img-{uuid.uuid4().hex[:8]}"
    logger.info(f"[{trace_id}] Image generation request: {req.model} - {req.prompt[:50]}...")
    
    try:
        # ── Local SD WebUI path (bypasses ProviderManager entirely) ────────────
        if _is_local_sd_model(req.model):
            logger.info(f"[{trace_id}] Routing to local SD WebUI: {req.model}")

            # Parse width/height from size string (e.g. "512x512" or "1024x1024")
            width, height = 512, 512
            if req.size and "x" in req.size:
                try:
                    w, h = req.size.split("x", 1)
                    width, height = int(w), int(h)
                except ValueError:
                    pass

            raw_images = await _generate_via_sd_webui(
                prompt=req.prompt,
                model=req.model,
                negative_prompt=req.negative_prompt or "",
                width=width,
                height=height,
                steps=20,
                cfg_scale=7.0,
                seed=req.seed if req.seed is not None else -1,
                n=req.n,
                input_image_b64=req.input_image,
                mask_image_b64=req.mask_image,
            )

            workspace    = get_workspace_manager()
            date_str     = datetime.now().strftime("%Y-%m-%d")
            saved_images = []
            for idx, img_bytes in enumerate(raw_images):
                safe_model = req.model.replace(":", "-").replace("/", "-")
                filename   = f"{safe_model}-{trace_id}-{idx}.png"
                save_path  = workspace.save_file(img_bytes, filename, f"images/{date_str}")
                saved_images.append({
                    "url":      f"/api/photo/serve/{filename}",
                    "path":     str(save_path),
                    "filename": filename,
                })

            return ImageGenerationResponse(
                success=True,
                images=saved_images,
                metadata={"model": req.model, "backend": "sd-webui", "count": len(saved_images)},
            )

        manager = get_provider_manager()

        # Identify provider based on model dict or specific logic
        target_provider = None

        if "dall-e" in req.model.lower():
            target_provider = manager.providers.get("openai")
        elif "imagen" in req.model.lower():
            target_provider = manager.providers.get("google_ai")
        else:
            # Fallback: check if any provider is configured with this model
            for p_name, p in manager.providers.items():
                if p.config.model == req.model:
                    target_provider = p
                    break

            if not target_provider:
                if "gpt" in req.model or "dall" in req.model:
                    target_provider = manager.providers.get("openai")
                else:
                    target_provider = manager.providers.get("google_ai")

        if not target_provider:
            raise HTTPException(status_code=400, detail=f"No provider found for model {req.model}")

        # Prepare kwargs
        kwargs = {}
        if req.aspect_ratio:
            kwargs['aspect_ratio'] = req.aspect_ratio
        if req.style:
            kwargs['style'] = req.style
        if req.negative_prompt:
            kwargs['negative_prompt'] = req.negative_prompt
        if req.seed is not None:
             kwargs['seed'] = req.seed

        # Decode base64 images if present
        import base64
        input_image_bytes = None
        mask_image_bytes = None
        
        def decode_b64(b64_str: str) -> bytes:
            if "," in b64_str:
                # Remove data URI prefix (e.g., data:image/png;base64,...)
                b64_str = b64_str.split(",", 1)[1]
            return base64.b64decode(b64_str)

        if req.input_image:
            input_image_bytes = decode_b64(req.input_image)
        if req.mask_image:
            mask_image_bytes = decode_b64(req.mask_image)

        # Call generate_image
        # Note: generate_image is synchronous in our implementation (calls API blocking)
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
            logger.error(f"[{trace_id}] Generation failed: {response.error}")
            return ImageGenerationResponse(
                success=False,
                images=[],
                metadata={},
                error=response.error
            )
        
        # Process results
        # Provider returns raw image bytes in metadata['images']
        raw_images = response.metadata.get('images', [])
        if not raw_images:
             return ImageGenerationResponse(
                success=False,
                images=[],
                metadata={},
                error="Provider returned success but no images found."
            )

        workspace = get_workspace_manager()
        saved_images = []
        
        # Create output directory: outputfiles/images/YYYY-MM-DD
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        # Iterate and save
        for idx, img_bytes in enumerate(raw_images):
            # Filename: {model}-{trace_id}-{i}.png
            # Sanitize model name
            safe_model = req.model.replace(":", "-").replace("/", "-")
            filename = f"{safe_model}-{trace_id}-{idx}.png"
            
            # Save to 'images/YYYY-MM-DD' domain/folder
            # WorkspaceManager takes domain. We can use "Images/{date_str}" or just "Images"
            # WorkspaceManager structure is {root}/{domain}/{filename}
            # The user asked for "data/outputfiles".
            # workspace.get_output_path("Images", filename) -> outputfiles/Images/filename
            # We want outputfiles/images/... 
            # Let's use domain="images" (lowercase usually normalized)
            
            # To support subfolders in domain, we can hack the domain or filename.
            # WorkspaceManager normalizes domain.
            # Let's just use "images" domain.
            
            path = workspace.save_output(
                domain="images", 
                filename=filename, 
                content=img_bytes,
                trace_id=trace_id
            )
            
            # Use path relative to static mount for URL
            # stored at c:\...\outputfiles\images\filename
            # served at /outputfiles/... if mounted?
            # We need to ensure outputfiles is served statically.
            # Current static mount is /static -> web/static
            # We should verify if outputfiles is served.
            # For now assume /api/files/ serves it or we add one.
            
            # Let's return the absolute path and a guessed URL
            saved_images.append({
                "path": str(path),
                "filename": filename,
                "url": f"/api/photo/serve/{filename}" # Helper endpoint we might need
            })

        return ImageGenerationResponse(
            success=True,
            images=saved_images,
            metadata={
                "provider": response.provider,
                "model": response.model,
                "trace_id": trace_id
            }
        )

    except Exception as e:
        logger.error(f"[{trace_id}] Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/local/models")
async def list_local_image_models():
    """
    List models available from the local Stable Diffusion WebUI (AUTOMATIC1111/Forge).
    Returns an empty list if SD WebUI is not running.
    """
    models = await _get_sd_webui_models()
    return {
        "sd_webui_url": _SD_WEBUI_URL,
        "available": len(models) > 0,
        "models": [
            {
                "id":    f"sd:{m.get('model_name', m.get('title', 'unknown'))}",
                "name":  m.get("title", m.get("model_name", "?")),
                "hash":  m.get("hash", ""),
            }
            for m in models
        ],
    }


@router.get("/serve/{filename}")
async def serve_image(filename: str):
    """Serve a generated image."""
    workspace = get_workspace_manager()
    # Assume domain 'images'
    path = workspace.get_output_path(domain="images", filename=filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    
    from fastapi.responses import FileResponse
    return FileResponse(path)
