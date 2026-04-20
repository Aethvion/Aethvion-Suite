"""
Specter Local Pipeline
Mode: Local Stable Diffusion (via Automatic1111 or ComfyUI API) → Vision AI slice → Rig

This pipeline is designed for users who run a local image generation server.
It connects to a local SD instance for consistent, controlnet-guided part generation.

STATUS: Foundation ready. Connect your local endpoints below.
"""
import os
import sys
import json
import uuid
import shutil
import requests
from PIL import Image
from typing import Dict, Any, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from .utils import create_part_entry, remove_background, generate_rig, extract_bounding_boxes


# Configuration — these can be overridden via the UI or .env
DEFAULT_A1111_URL = "http://127.0.0.1:7860"
DEFAULT_COMFYUI_URL = "http://127.0.0.1:8188"


SHEET_PROMPT_VISION = """
Analyze this Concept Art image. It may contain a full character or multiple separated parts.
Identify the bounding boxes [ymin, xmin, ymax, xmax] (normalized 0-1000) for these parts:
1. body
2. head
3. hair_front
4. eye_left
5. eye_right
6. mouth

Return the results strictly as JSON. Example: {"head": [100, 200, 500, 600], ...}
"""


class LocalPipeline:
    """Generate a VTuber model using a local SD/ComfyUI server."""

    def __init__(self, provider, model_id: str,
                 backend: str = "a1111",
                 base_url: str = None):
        """
        Args:
            provider: Google AI provider for Vision + Chat (always required for Vision parsing)
            model_id: Gemini model to use for Vision + Chat
            backend: "a1111" or "comfyui"
            base_url: Local server URL (default: 127.0.0.1:7860)
        """
        self.provider = provider
        self.model_id = model_id
        self.backend = backend
        self.base_url = base_url or (DEFAULT_A1111_URL if backend == "a1111" else DEFAULT_COMFYUI_URL)

    def check_connection(self) -> bool:
        """Verify the local server is running."""
        try:
            r = requests.get(f"{self.base_url}/sdapi/v1/sd-models", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def generate_concept(self, prompt: str, output_path: str,
                         negative_prompt: str = None,
                         steps: int = 30, cfg_scale: float = 7.0) -> str:
        """
        Generate a sprite sheet using the local SD server (txt2img).

        Args:
            prompt: Character design prompt
            output_path: Where to save the generated image
            negative_prompt: SD negative prompt
            steps: Sampling steps
            cfg_scale: CFG scale
        """
        if self.backend == "a1111":
            return self._generate_a1111(prompt, output_path, negative_prompt, steps, cfg_scale)
        elif self.backend == "comfyui":
            raise NotImplementedError("ComfyUI support is coming soon. Use A1111 for now.")
        else:
            raise ValueError(f"Unknown backend: {self.backend}")

    def _generate_a1111(self, prompt: str, output_path: str,
                         negative_prompt: str, steps: int, cfg_scale: float) -> str:
        """POST to A1111 /sdapi/v1/txt2img."""
        import base64

        sheet_prompt = (
            "sprite sheet, character sheet, VTuber parts layout, white background, "
            "top half complete character A-pose, bottom half isolated parts: "
            "headless body, head, front bangs, left eye, right eye, mouth, "
            f"{prompt}"
        )

        neg = negative_prompt or (
            "nsfw, bad anatomy, extra limbs, background, gradient, text, watermark"
        )

        payload = {
            "prompt": sheet_prompt,
            "negative_prompt": neg,
            "steps": steps,
            "cfg_scale": cfg_scale,
            "width": 1024,
            "height": 1024,
            "sampler_name": "DPM++ 2M Karras",
            "restore_faces": False,
        }

        print(f"🖥️ Local Pipeline: Sending txt2img to {self.base_url}...")
        r = requests.post(f"{self.base_url}/sdapi/v1/txt2img", json=payload, timeout=120)
        r.raise_for_status()

        result = r.json()
        if not result.get("images"):
            raise ValueError("Local SD server returned no images.")

        image_bytes = base64.b64decode(result["images"][0])
        with open(output_path, "wb") as f:
            f.write(image_bytes)

        print(f"✅ Local concept generated.")
        return output_path

    def generate_rig_from_concept(self, concept_path: str, output_dir: str,
                                   output_name: str, instructions: str = None) -> str:
        """Vision-AI slice the local image and generate the rig JSON."""
        print(f"🚀 Local Pipeline: Rigging {output_name}...")
        os.makedirs(output_dir, exist_ok=True)
        textures_dir = os.path.join(output_dir, "textures")
        os.makedirs(textures_dir, exist_ok=True)

        shutil.copy2(concept_path, os.path.join(textures_dir, "original_local.png"))

        # Vision extraction — always uses cloud Google AI for parsing
        with open(concept_path, "rb") as f:
            image_data = f.read()

        coords = extract_bounding_boxes(image_data, SHEET_PROMPT_VISION, self.provider, self.model_id)

        if not coords:
            raise ValueError("Vision AI returned no bounding boxes.")

        img = Image.open(concept_path).convert("RGBA")
        width, height = img.size
        parts_config = []
        canvas_w, canvas_h = 1000, 1000

        for name, box in coords.items():
            if not box or len(box) != 4:
                continue

            left  = (box[1] / 1000) * width
            top   = (box[0] / 1000) * height
            right = (box[3] / 1000) * width
            bottom= (box[2] / 1000) * height

            cropped = img.crop((left, top, right, bottom))
            raw_path = os.path.join(textures_dir, f"{name}_raw.png")
            cropped.save(raw_path)

            nobg_part = os.path.join(textures_dir, f"{name}.png")
            remove_background(raw_path, nobg_part)

            tex_filename = f"textures/{name}.png"
            parts_config.append(create_part_entry(name, tex_filename, left, top, right, bottom, canvas_w, canvas_h))

        # Rig
        config = generate_rig(parts_config, self.provider, self.model_id, instructions)
        config["name"] = output_name.replace("_", " ").title()
        config["pipeline"] = "local"

        rig_path = os.path.join(output_dir, "avatar.specter.json")
        with open(rig_path, "w") as f:
            json.dump(config, f, indent=4)

        print(f"✅ Local Pipeline complete: {output_name}")
        return rig_path
