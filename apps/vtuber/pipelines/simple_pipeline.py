"""
Specter Simple Pipeline
Mode: Single image -> Vision AI bounding-box extraction -> Layer slice -> Rig
Background removal is NOT applied automatically - it's opt-in per layer via the Edit tab.
All originals are always saved.
"""
import os
import sys
import json
import shutil
from PIL import Image

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from .utils import create_part_entry, generate_rig, extract_bounding_boxes


VISION_PROMPT = """
Analyze this 2D character image for VTuber rigging.
Identify the bounding boxes [ymin, xmin, ymax, xmax] (normalized 0-1000) for the following parts:
1. head (the entire head including hair)
2. eye_left
3. eye_right
4. mouth
5. body (everything below the head)

Return the results strictly as a JSON object with the part names as keys and the box as value.
Example: {"head": [100, 200, 500, 600], ...}
"""


class SimplePipeline:
    """Rig a single pre-existing character image (no generation)."""

    def __init__(self, provider, model_id: str):
        self.provider = provider
        self.model_id = model_id

    def generate_rig_from_image(self, image_path: str, output_dir: str,
                                 output_name: str, instructions: str = None) -> str:
        """
        Analyze a single image, slice it, and generate the rig JSON.
        All originals are always saved. BG removal is a separate opt-in step.
        """
        os.makedirs(output_dir, exist_ok=True)
        textures_dir = os.path.join(output_dir, "textures")
        os.makedirs(textures_dir, exist_ok=True)

        # Always save original
        original_path = os.path.join(textures_dir, "original.png")
        shutil.copy2(image_path, original_path)

        # 1. Vision: extract bounding boxes
        print("Analysing image anatomy via Vision AI...")
        with open(image_path, "rb") as f:
            image_data = f.read()

        coords = extract_bounding_boxes(image_data, VISION_PROMPT, self.provider, self.model_id)

        if not coords:
            raise ValueError("Vision AI returned no bounding boxes. Cannot slice image.")

        print(f"Vision mapped {len(coords)} parts.")

        img = Image.open(image_path).convert("RGBA")
        width, height = img.size
        parts_config = []
        canvas_w, canvas_h = 1000, 1000

        for name, box in coords.items():
            if not box or len(box) != 4:
                print(f"Skipping {name}: invalid box.")
                continue

            left   = (box[1] / 1000) * width
            top    = (box[0] / 1000) * height
            right  = (box[3] / 1000) * width
            bottom = (box[2] / 1000) * height

            cropped = img.crop((left, top, right, bottom))

            raw_path = os.path.join(textures_dir, f"{name}_raw.png")
            tex_path = os.path.join(textures_dir, f"{name}.png")
            cropped.save(raw_path)
            shutil.copy2(raw_path, tex_path)

            parts_config.append(create_part_entry(name, f"textures/{name}.png",
                                                   left, top, right, bottom, canvas_w, canvas_h))
            print(f"Sliced: {name}")

        # 3. Generate rig
        print("Generating physics rig...")
        config = generate_rig(parts_config, self.provider, self.model_id, instructions)
        config["name"] = output_name.replace("_", " ").title()
        config["pipeline"] = "simple"

        rig_path = os.path.join(output_dir, "avatar.specter.json")
        with open(rig_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

        print(f"Simple Pipeline complete: {output_name}")
        return rig_path
