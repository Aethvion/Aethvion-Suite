"""
Aethvion Suite - Native Local Diffusion Engine
Direct GPU-accelerated local execution of .safetensors checkpoints
using PyTorch and HuggingFace Diffusers on NVIDIA CUDA hardware.
"""

import gc
import io
import os
import time
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from PIL import Image

from core.utils import get_logger

logger = get_logger(__name__)

# Check CUDA device
_DEVICE = "cuda"


class LocalDiffusersEngine:
    """
    Singleton engine managing local diffusion pipelines in VRAM.
    Loads single-file .safetensors checkpoints on demand and caches the active model.
    """

    def __init__(self):
        self._current_model_path: Optional[str] = None
        self._current_model_type: Optional[str] = None
        self._pipeline = None
        self._last_used: float = 0.0

    @property
    def is_loaded(self) -> bool:
        return self._pipeline is not None

    @property
    def current_model(self) -> Optional[str]:
        return self._current_model_path

    def get_status(self) -> Dict[str, Any]:
        """Return real-time GPU and VRAM utilization status."""
        try:
            import torch
            cuda_avail = torch.cuda.is_available()
            vram_alloc = 0.0
            vram_total = 0.0
            gpu_name = "None"

            if cuda_avail:
                gpu_name = torch.cuda.get_device_name(0)
                vram_alloc = round(torch.cuda.memory_allocated(0) / (1024 ** 3), 2)
                vram_total = round(torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 1)

            return {
                "installed": True,
                "cuda_available": cuda_avail,
                "gpu_name": gpu_name,
                "vram_allocated_gb": vram_alloc,
                "vram_total_gb": vram_total,
                "loaded_model": Path(self._current_model_path).name if self._current_model_path else None,
                "is_active": self.is_loaded
            }
        except Exception as e:
            return {
                "installed": False,
                "error": str(e)
            }

    def unload(self):
        """Unload the active model from GPU VRAM and release memory."""
        if self._pipeline is not None:
            logger.info("[ImageEngine] Unloading active model from VRAM...")
            del self._pipeline
            self._pipeline = None
            self._current_model_path = None
            self._current_model_type = None

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            gc.collect()
            logger.info("[ImageEngine] VRAM successfully freed.")
        except Exception as e:
            logger.warning(f"[ImageEngine] Error clearing cache: {e}")

    def _detect_model_type(self, path: Path) -> str:
        """Infer model architecture (sdxl vs sd15 vs flux) from file metadata and name."""
        name = path.name.lower()
        if "flux" in name:
            return "flux"
        if "xl" in name or "sdxl" in name:
            return "sdxl"
        return "sd15"

    def load_model(self, checkpoint_path: Path, force_reload: bool = False):
        """
        Load a .safetensors checkpoint into GPU memory with FP16 precision.
        Reuses currently cached model if already loaded.
        """
        checkpoint_path = Path(checkpoint_path).resolve()
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint file not found: {checkpoint_path}")

        path_str = str(checkpoint_path)
        if not force_reload and self.is_loaded and self._current_model_path == path_str:
            logger.info(f"[ImageEngine] Checkpoint {checkpoint_path.name} already loaded in VRAM.")
            return

        # Unload previous model
        self.unload()

        import torch
        from diffusers import (
            StableDiffusionPipeline,
            StableDiffusionXLPipeline,
            DPMSolverMultistepScheduler,
            EulerDiscreteScheduler
        )

        model_type = self._detect_model_type(checkpoint_path)
        logger.info(f"[ImageEngine] Loading {checkpoint_path.name} (type: {model_type}) into GPU VRAM (FP16)...")
        start_t = time.time()

        try:
            if model_type == "sdxl":
                pipe = StableDiffusionXLPipeline.from_single_file(
                    path_str,
                    torch_dtype=torch.float16,
                    use_safetensors=True
                )
                # Optimize scheduler based on lightning vs standard
                if "lightning" in checkpoint_path.name.lower():
                    pipe.scheduler = EulerDiscreteScheduler.from_config(
                        pipe.scheduler.config,
                        timestep_spacing="trailing"
                    )
                else:
                    pipe.scheduler = DPMSolverMultistepScheduler.from_config(
                        pipe.scheduler.config,
                        use_karras_sigmas=True
                    )
            else:
                # Default SD 1.5
                pipe = StableDiffusionPipeline.from_single_file(
                    path_str,
                    torch_dtype=torch.float16,
                    use_safetensors=True
                )
                pipe.scheduler = DPMSolverMultistepScheduler.from_config(
                    pipe.scheduler.config,
                    use_karras_sigmas=True
                )

            # Move to CUDA
            pipe.to(_DEVICE)

            # Enable attention slicing for safety
            try:
                pipe.enable_attention_slicing()
            except Exception:
                pass

            self._pipeline = pipe
            self._current_model_path = path_str
            self._current_model_type = model_type
            self._last_used = time.time()

            load_sec = round(time.time() - start_t, 2)
            alloc_gb = round(torch.cuda.memory_allocated(0) / (1024 ** 3), 2)
            logger.info(f"[ImageEngine] Checkpoint loaded in {load_sec}s. Active VRAM: {alloc_gb} GB.")

        except Exception as e:
            self.unload()
            logger.error(f"[ImageEngine] Failed to load checkpoint {checkpoint_path.name}: {e}")
            raise RuntimeError(f"Failed to load checkpoint: {e}")

    def generate(
        self,
        checkpoint_path: Path,
        prompt: str,
        negative_prompt: Optional[str] = None,
        width: int = 1024,
        height: int = 1024,
        steps: int = 25,
        cfg_scale: float = 7.0,
        seed: Optional[int] = None,
        n: int = 1,
        input_image: Optional[Image.Image] = None,
        mask_image: Optional[Image.Image] = None,
        action: str = "generate"
    ) -> List[bytes]:
        """
        Execute generation directly on the GPU.
        Returns a list of raw PNG bytes.
        """
        import torch

        # Ensure model is in VRAM
        self.load_model(checkpoint_path)

        generator = None
        if seed is not None and seed >= 0:
            generator = torch.Generator(device=_DEVICE).manual_seed(seed)

        logger.info(f"[ImageEngine] Generating {n} image(s) [{width}x{height}] with {steps} steps, CFG={cfg_scale}...")
        start_t = time.time()

        pipe = self._pipeline

        with torch.inference_mode():
            # If img2img or inpainting requested
            if input_image is not None and action in ["edit", "upscale", "expand"]:
                from diffusers import (
                    AutoPipelineForImage2Image,
                    AutoPipelineForInpainting
                )
                if mask_image is not None and action in ["edit", "expand"]:
                    inpaint_pipe = AutoPipelineForInpainting.from_pipe(pipe)
                    output = inpaint_pipe(
                        prompt=prompt,
                        negative_prompt=negative_prompt or "",
                        image=input_image,
                        mask_image=mask_image,
                        num_inference_steps=steps,
                        guidance_scale=cfg_scale,
                        generator=generator,
                        num_images_per_prompt=n
                    )
                else:
                    img2img_pipe = AutoPipelineForImage2Image.from_pipe(pipe)
                    output = img2img_pipe(
                        prompt=prompt,
                        negative_prompt=negative_prompt or "",
                        image=input_image,
                        strength=0.75 if action == "edit" else 0.4,
                        num_inference_steps=steps,
                        guidance_scale=cfg_scale,
                        generator=generator,
                        num_images_per_prompt=n
                    )
            else:
                # Text to Image
                output = pipe(
                    prompt=prompt,
                    negative_prompt=negative_prompt or "",
                    width=width,
                    height=height,
                    num_inference_steps=steps,
                    guidance_scale=cfg_scale,
                    generator=generator,
                    num_images_per_prompt=n
                )

        elapsed = round(time.time() - start_t, 2)
        logger.info(f"[ImageEngine] Generation finished in {elapsed}s.")
        self._last_used = time.time()

        # Convert PIL outputs to PNG bytes
        results = []
        for img in output.images:
            buf = io.BytesIO()
            img.save(buf, format="PNG", quality=95)
            results.append(buf.getvalue())

        return results


# Global singleton instance
local_image_engine = LocalDiffusersEngine()
