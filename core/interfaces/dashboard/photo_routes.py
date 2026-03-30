"""
Aethvion Suite - Image Generation Routes
API endpoints for image generation via LLM providers
"""

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
        manager = get_provider_manager()
        
        # Identify provider based on model dict or specific logic
        # ProviderManager usually selects provider by config, but we need to find 
        # which provider owns this model.
        # Simple heuristic: look for provider that supports this model, or use mapped names.
        
        target_provider = None
        
        # Check explicit mapping or iterate providers
        # Since ProviderManager doesn't natively map arbitrary model names to providers easily in its current public API
        # (it mostly does failover), we'll do a quick check.
        
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
            
            # If still not found, default to google (primary) or openai if model looks like theirs
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
        # We should ideally run this in a threadpool if it blocks, but for now direct call.
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
            # Let's use "Images" domain, and filename includes date or we put it in folder.
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
            # If not, we might need to add a mount in server.py or use an API to serve it.
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
