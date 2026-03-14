"""
Specter Shared Pipeline Utilities
Shared functions used by all three generation pipelines.
"""
import os
import sys
import json
from typing import Dict, Any, List

# Add project root to sys.path for core imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from google.genai import types


def create_part_entry(name: str, tex_filename: str, left: float, top: float,
                       right: float, bottom: float, canvas_w: float, canvas_h: float) -> Dict[str, Any]:
    """Create a part entry with initial Mesh grid data."""
    w = right - left
    h = bottom - top

    vertices = []
    uvs = []
    for row in range(3):
        for col in range(3):
            vertices.extend([col * 0.5 - 0.5, row * 0.5 - 0.5])
            uvs.extend([col * 0.5, row * 0.5])

    indices = [
        0, 1, 3, 1, 4, 3, 1, 2, 4, 2, 5, 4,
        3, 4, 6, 4, 7, 6, 4, 5, 7, 5, 8, 7
    ]

    return {
        "id": name,
        "texture": tex_filename,
        "x": (left + right) / 2 - (canvas_w / 2),
        "y": (top + bottom) / 2 - (canvas_h / 2),
        "z": get_default_z(name),
        "mesh": {
            "vertices": vertices,
            "uvs": uvs,
            "indices": indices,
            "width": w,
            "height": h
        }
    }


def get_default_z(part_name: str) -> int:
    z_map = {
        "body": 5,
        "head": 10,
        "hair_back": 8,
        "mouth": 15,
        "eye_left": 15,
        "eye_right": 15,
        "hair_front": 20,
        "accessories": 25,
    }
    return z_map.get(part_name, 10)


def remove_background(image_path: str, output_path: str) -> bool:
    """Attempt to remove background using rembg if installed."""
    try:
        from rembg import remove

        print(f"🧹 Removing background for {os.path.basename(image_path)}...")
        with open(image_path, "rb") as f:
            input_data = f.read()

        output_data = remove(input_data)

        with open(output_path, "wb") as f:
            f.write(output_data)

        return True
    except ImportError:
        print("⚠️ 'rembg' is not installed. Skipping background removal.")
        import shutil
        shutil.copy2(image_path, output_path)
        return False
    except Exception as e:
        print(f"❌ Background removal failed: {e}")
        import shutil
        shutil.copy2(image_path, output_path)
        return False


def generate_rig(parts: List[Dict[str, Any]], provider, model_id: str,
                 instructions: str = None) -> Dict[str, Any]:
    """Ask the LLM to write the physics mappings and parameters based on the parts list."""
    print("🧠 Asking AI to generate physics mappings...")

    base_config = {
        "name": "AI Avatar",
        "version": "1.2.0",
        "parts": parts,
        "params": {
            "ParamBreath": {"name": "Breathing", "min": 0, "max": 1, "default": 0, "value": 0},
            "ParamEyeOpenL": {"name": "Eye Open L", "min": 0, "max": 1, "default": 1, "value": 1},
            "ParamEyeOpenR": {"name": "Eye Open R", "min": 0, "max": 1, "default": 1, "value": 1},
            "ParamMouthOpenY": {"name": "Mouth Open", "min": 0, "max": 1, "default": 0, "value": 0}
        },
        "animations": {
            "idle": {
                "ParamBreath": {"type": "sine", "speed": 1.0, "amplitude": 0.5}
            }
        },
        "mappings": [
            {"param": "ParamBreath", "layer": "body", "type": "mesh_deform", "vertex_index": 4, "axis": "y", "multiplier": 0.1},
            {"param": "ParamMouthOpenY", "layer": "mouth", "type": "mesh_deform", "vertex_index": 7, "axis": "y", "multiplier": 0.3},
            {"param": "ParamEyeOpenL", "layer": "eye_left", "type": "scale", "base": 0, "multiplier": 1.0},
            {"param": "ParamEyeOpenR", "layer": "eye_right", "type": "scale", "base": 0, "multiplier": 1.0}
        ]
    }

    # Check if provider is usable — any provider with a .client is fine
    client = getattr(provider, 'client', None) if provider else None
    if not client:
        print("No AI provider client available. Using default physics.")
        return base_config

    prompt = f"""
You are the core logic engine for a VTuber rigging platform.
I have generated the following bodily components for a 2D avatar. Each component is a 3x3 mesh grid (indices 0 to 8, where 4 is center).
Parts array:
{json.dumps([{{'id': p['id'], 'z': p['z']}} for p in parts], indent=2)}

Please output a JSON object containing EXACTLY three root keys: "params", "animations", and "mappings".
1. "params": Define one or more logic parameters per part. Name them after the part, e.g. Param{{part_id.title()}}X, Param{{part_id.title()}}Y, ParamBreath, etc.
2. "animations": Give me an "idle" animation that oscillates ParamBreath using type "sine". You can add more animations.
3. "mappings": Wire params to parts using the part IDs from the list above.

Mapping Types:
- "mesh_deform": Needs param, layer (part id), vertex_index (0-8), axis ("x" or "y"), multiplier.
- "scale": Needs param, layer, base (offset), multiplier.
- "position_x" or "position_y": Needs param, layer, base, multiplier.
- "rotation": Needs param, layer, base, multiplier.

User specific rig instructions: {instructions or "Make a standard VTuber rig that breathes and blinks."}

Return ONLY valid JSON covering the "params", "animations", and "mappings". Do NOT include Markdown formatting like ```json.
"""

    try:
        response = client.models.generate_content(
            model=model_id,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        ai_logic = json.loads(response.text)

        final_config = {
            "name": "AI Avatar",
            "version": "1.2.0",
            "parts": parts,
            "params": ai_logic.get("params", base_config["params"]),
            "animations": ai_logic.get("animations", base_config["animations"]),
            "mappings": ai_logic.get("mappings", base_config["mappings"])
        }
        return final_config

    except Exception as e:
        print(f"❌ Error generating AI rig logic: {e}. Using defaults.")
        return base_config


def extract_bounding_boxes(image_data: bytes, prompt: str, provider, model_id: str) -> Dict[str, List]:
    """Use Google Vision to extract bounding boxes from an image."""
    try:
        client = getattr(provider, 'client', None)
        if not client:
            return {}

        response = client.models.generate_content(
            model=model_id,
            contents=[
                types.Part.from_bytes(data=image_data, mime_type="image/png"),
                prompt
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"❌ Vision extraction failed: {e}")
        return {}
