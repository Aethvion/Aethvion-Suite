import os
import sys
import json
import base64
import numpy as np
import io
from PIL import Image, ImageDraw
from typing import Dict, Any, List

# Add project root to sys.path for core imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from core.providers.provider_manager import ProviderManager
import uuid
from google.genai import types

class AutoRigger:
    def __init__(self):
        # Use Misaka Cipher's centralized Provider Manager
        self.pm = ProviderManager()
        self.provider = self.pm.get_provider("google_ai")
        
        if not self.provider:
            raise ValueError("Google AI provider not initialized in Misaka Cipher.")
            
        # Access the underlying genai.Client from the provider
        if hasattr(self.provider, 'client'):
            self.client = self.provider.client
        else:
            self.client = None
        # Default fallback
        self.model_id = self.provider.config.model if self.provider else "gemini-1.5-flash"
        
        print(f"👻 Specter AutoRigger linked to Misaka Core (Provider: {self.provider.config.name}, Model: {self.model_id})")

    def analyze_avatar(self, image_path: str, chat_model: str = None) -> Dict[str, Any]:
        """Analyze an avatar image and return coordinates for features."""
        with open(image_path, "rb") as f:
            image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')

        prompt = """
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
        
        # Force Google AI for Vision (since it uses genai types)
        vision_provider = self.provider
        vision_model = self.model_id
        
        target_model = chat_model or self.model_id
        if target_model:
            provider_name = self.pm.model_to_provider_map.get(target_model)
            if provider_name == "google_ai":
                vision_provider = self.pm.get_provider(provider_name)
                vision_model = target_model
                
        if not vision_provider:
             print("Warning: Google AI Provider is not available for Vision extraction.")
             return {}
             
        try:
            # Use generating client if it exists (Gemini specifically)
            client = getattr(vision_provider, 'client', self.client)
            response = client.models.generate_content(
                model=vision_model,
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
            print(f"Error parsing Google AI response: {e}")
            return {}



    def generate_avatar(self, prompt: str, output_path: str, image_model: str = None) -> bool:
        """Generate a character image from a design prompt."""
        print(f"🎨 Generating avatar from design: {prompt}")
        
        # Determine image capability
        image_provider = None
        target_model = None
        
        if image_model:
            provider_name = self.pm.model_to_provider_map.get(image_model)
            if provider_name:
                image_provider = self.pm.get_provider(provider_name)
                target_model = image_model
        
        if not image_provider:
             image_provider = self.pm.get_provider_for_capability("IMAGE")
             
        if not image_provider:
            # Fallback
            image_provider = self.pm.get_provider("openai") or self.pm.get_provider("google_ai")

        if not image_provider:
            raise ValueError("No viable image provider found.")

        full_prompt = (
            "A VTuber character design sprite sheet on a pure white background. "
            "The top half should show the complete character design (A-pose, front-facing, simple flat colors). "
            "The bottom half MUST strictly contain clearly separated, floating modular parts laid out individually: "
            "an isolated headless body, an isolated head with back-hair, isolated front hair bangs, isolated left and right eyes, and an isolated mouth. "
            f"Character design reference: {prompt}"
        )

        trace_id = f"specter-gen-{uuid.uuid4().hex[:8]}"
        
        if not target_model:
             target_model = "imagen-3.0-generate-002" if image_provider.config.name == "google_ai" else "dall-e-3"

        response = image_provider.generate_image(
            prompt=full_prompt,
            trace_id=trace_id,
            model=target_model,
            size="1024x1024"
        )

        if response.success and response.metadata and 'images' in response.metadata:
            image_bytes = response.metadata['images'][0]
            with open(output_path, "wb") as f:
                f.write(image_bytes)
            print("✅ Avatar image generated successfully.")
            return True
        else:
            print(f"❌ Avatar generation failed: {response.error}")
            raise Exception(f"Image generation failed: {response.error}")

    def extract_layers(self, source_image: str, coords: Dict[str, List[int]], output_dir: str) -> List[Dict[str, Any]]:
        """Crop the image into layers and 'cut out' holes in the body to prevent ghosting."""
        os.makedirs(os.path.join(output_dir, "textures"), exist_ok=True)
        img = Image.open(source_image).convert("RGBA")
        width, height = img.size
        
        # Create a copy of the image to 'cut holes' into (the body/base layer)
        base_img = img.copy()
        
        parts_config = []
        
        # Process specific features first so we can 'cut' them from the base
        features = {k: v for k, v in coords.items() if k != 'body'}
        
        for name, box in features.items():
            left = (box[1] / 1000) * width
            top = (box[0] / 1000) * height
            right = (box[3] / 1000) * width
            bottom = (box[2] / 1000) * height
            
            # Crop feature
            cropped = img.crop((left, top, right, bottom))
            tex_filename = f"textures/{name}.png"
            cropped.save(os.path.join(output_dir, tex_filename))
            
            # ERASE feature from base image to prevent double-rendering
            # (Filling with transparent pixels)
            from PIL import ImageDraw
            draw = ImageDraw.Draw(base_img)
            draw.rectangle([left, top, right, bottom], fill=(0, 0, 0, 0))
            
            parts_config.append(self._create_part_entry(name, tex_filename, left, top, right, bottom, width, height))

        # Save the 'cleaned' body
        body_box = coords.get('body', [0, 0, 1000, 1000])
        left = (body_box[1] / 1000) * width
        top = (body_box[0] / 1000) * height
        right = (body_box[3] / 1000) * width
        bottom = (body_box[2] / 1000) * height
        
        body_cropped = base_img.crop((left, top, right, bottom))
        body_tex = "textures/body.png"
        body_cropped.save(os.path.join(output_dir, body_tex))
        
        parts_config.append(self._create_part_entry("body", body_tex, left, top, right, bottom, width, height))
            
        return parts_config

    def _create_part_entry(self, name, tex_filename, left, top, right, bottom, canvas_w, canvas_h) -> Dict[str, Any]:
        """Create a part entry with initial Mesh grid data."""
        w = right - left
        h = bottom - top
        
        # Simple 3x3 grid mesh for deformation
        vertices = []
        uvs = []
        for row in range(3):
            for col in range(3):
                # Normalized vertex positions (-0.5 to 0.5 relative to center)
                vertices.extend([col * 0.5 - 0.5, row * 0.5 - 0.5])
                # UV coordinates (0 to 1)
                uvs.extend([col * 0.5, row * 0.5])
        
        # Triangulation indices for 2x2 grid (8 triangles)
        indices = [
            0, 1, 3, 1, 4, 3, 1, 2, 4, 2, 5, 4,
            3, 4, 6, 4, 7, 6, 4, 5, 7, 5, 8, 7
        ]

        return {
            "id": name,
            "texture": tex_filename,
            "x": (left + right) / 2 - (canvas_w / 2),
            "y": (top + bottom) / 2 - (canvas_h / 2),
            "z": self._get_default_z(name),
            "mesh": {
                "vertices": vertices,
                "uvs": uvs,
                "indices": indices,
                "width": w,
                "height": h
            }
        }

    def _get_default_z(self, part_name: str) -> int:
        z_map = {
            "body": 5,
            "head": 10,
            "mouth": 15,
            "eye_left": 15,
            "eye_right": 15
        }
        return z_map.get(part_name, 10)

    def generate_rig(self, parts: List[Dict[str, Any]], chat_model: str = None, instructions: str = None) -> Dict[str, Any]:
        """Ask the LLM to write the physics mappings and parameters based on the parts list."""
        print(f"🧠 Asking AI to wire up the physics mappings...")
        
        # Base fallback config if LLM fails or is missing
        base_config = {
            "name": "AI Modular Avatar",
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
        
        target_model = chat_model or self.model_id
        target_provider = None
        if target_model:
            provider_name = self.pm.model_to_provider_map.get(target_model)
            if provider_name:
                target_provider = self.pm.get_provider(provider_name)
        
        if not target_provider:
             target_provider = self.provider

        if not target_provider or target_provider.config.name != "google_ai":
            print("⚠️ Chat provider is not Google AI or unavailable. Using default physics.")
            return base_config

        prompt = f"""
You are the core logic engine for a VTuber rigging platform.
I have generated the following bodily components for a 2D avatar. Each component is a 3x3 mesh grid (indices 0 to 8, where 4 is center).
Parts array:
{json.dumps([{'id': p['id'], 'z': p['z']} for p in parts], indent=2)}

Please output a JSON object containing EXACTLY three root keys: "params", "animations", and "mappings".
1. "params": Define logic parameters (min, max, default). (e.g. ParamBreath, ParamFaceAngleX).
2. "animations": Give me an "idle" animation that oscillates ParamBreath using type "sine". You can add more animations if you want.
3. "mappings": The physical wiring. Map your params to the parts!

Mapping Types:
- "mesh_deform": Needs param, layer (part id), vertex_index (0-8), axis ("x" or "y"), multiplier.
- "scale": Needs param, layer, base (offset), multiplier.
- "position_x" or "position_y": Needs param, layer, base, multiplier.
- "rotation": Needs param, layer, base, multiplier.

User specific rig instructions: {instructions or "Make a standard VTuber rig that breathes and blinks."}

Return ONLY valid JSON covering the "params", "animations", and "mappings". Match the JSON structure I need. Do NOT include Markdown formatting like ```json.
"""

        try:
            client = getattr(target_provider, 'client', self.client)
            response = client.models.generate_content(
                model=target_model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            ai_logic = json.loads(response.text)
            
            # Merge with parts
            final_config = {
                "name": "AI Modular Avatar",
                "version": "1.2.0",
                "parts": parts,
                "params": ai_logic.get("params", base_config["params"]),
                "animations": ai_logic.get("animations", base_config["animations"]),
                "mappings": ai_logic.get("mappings", base_config["mappings"])
            }
            return final_config
            
        except Exception as e:
            print(f"Error parsing AI Rigging Logic: {e}. Falling back to default physics.")
            return base_config

    def remove_background(self, image_path: str, output_path: str) -> bool:
        """Attempt to remove background using rembg if installed."""
        try:
            from rembg import remove
            from PIL import Image
            
            print(f"🧹 Removing background for {os.path.basename(image_path)}...")
            with open(image_path, "rb") as input_file:
                input_data = input_file.read()
                
            output_data = remove(input_data)
            
            with open(output_path, "wb") as output_file:
                output_file.write(output_data)
                
            return True
        except ImportError:
            print("⚠️ 'rembg' is not installed. Skipping background removal. (Run 'pip install rembg onnxruntime' to enable)")
            return False
        except Exception as e:
            print(f"❌ Background removal failed: {e}")
            return False

    def process_model(self, image_path: str, output_name: str, chat_model: str = None):
        """Full pipeline: Analyze -> Extract -> Rig."""
        output_dir = os.path.join(os.path.dirname(image_path), output_name)
        os.makedirs(output_dir, exist_ok=True)
        
        # Optional: Remove background
        processed_image_path = image_path
        nobg_path = os.path.join(output_dir, f"{output_name}_nobg.png")
        if self.remove_background(image_path, nobg_path):
            processed_image_path = nobg_path
            
        print(f"🔍 Analyzing {processed_image_path}...")
        
        # Save original and processed backups to the textures folder
        textures_dir = os.path.join(output_dir, "textures")
        os.makedirs(textures_dir, exist_ok=True)
        
        import shutil
        shutil.copy2(image_path, os.path.join(textures_dir, "original.png"))
        if processed_image_path != image_path:
             shutil.copy2(processed_image_path, os.path.join(textures_dir, "nobg.png"))
        
        coords = self.analyze_avatar(processed_image_path, chat_model=chat_model)
        
        print(f"✂️ Extracting layers to {output_dir}...")
        parts = self.extract_layers(processed_image_path, coords, output_dir)
        
        print(f"✨ Generating rig...")
        config = self.generate_rig(parts)
        config["name"] = output_name.replace("_", " ").title()
        
        with open(os.path.join(output_dir, "avatar.specter.json"), "w") as f:
            json.dump(config, f, indent=4)
            
        print(f"✅ Auto-rigging complete for {output_name}")

    def process_model_modular(self, concept_path: str, output_name: str, image_model: str = None, chat_model: str = None, instructions: str = None):
        """Phase 2 Pipeline: Interpret Sprite Sheet Concept -> Extract Parts -> Assemble -> Rig."""
        print(f"🚀 Starting Sprite Sheet Modular Rigging for {output_name}...")
        
        output_dir = os.path.join(os.path.dirname(concept_path))
        os.makedirs(output_dir, exist_ok=True)
        textures_dir = os.path.join(output_dir, "textures")
        os.makedirs(textures_dir, exist_ok=True)
        
        # 1. Analyze Sprite Sheet
        print(f"🔍 Analyzing Sprite Sheet: {concept_path}...")
        # We need a new prompt to extract the sliced parts from the concept
        with open(concept_path, "rb") as f:
            image_data = f.read()

        prompt = """
        Analyze this Concept Art Sprite Sheet. It contains a full character design AND disassembled modular parts floating separately.
        Identify the bounding boxes [ymin, xmin, ymax, xmax] (normalized 0-1000) for ONLY the ISOLATED parts (ignore the fully assembled character).
        I need the precise bounding boxes for these floating pieces:
        1. body (the headless torso/arms/legs)
        2. head (the head base with ears and back hair)
        3. hair_front (the front bangs)
        4. eye_left
        5. eye_right
        6. mouth

        Return the results strictly as a JSON object with the part names as keys and the box as value.
        Example: {"head": [100, 200, 500, 600], ...}
        """
        
        # Force Google AI for Vision (since it uses genai types)
        vision_provider = self.provider
        vision_model = self.model_id
        
        target_model = chat_model or self.model_id
        if target_model:
            provider_name = self.pm.model_to_provider_map.get(target_model)
            if provider_name == "google_ai":
                vision_provider = self.pm.get_provider(provider_name)
                vision_model = target_model
                
        if not vision_provider:
             raise ValueError("Google AI Provider is not available for Vision extraction.")

        coords = {}
        try:
            client = getattr(vision_provider, 'client', self.client)
            response = client.models.generate_content(
                model=vision_model,
                contents=[
                    types.Part.from_bytes(data=image_data, mime_type="image/png"),
                    prompt
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            coords = json.loads(response.text)
            print(f"✅ Vision extraction mapped {len(coords)} isolated parts.")
        except Exception as e:
            print(f"Error parsing Sprite Sheet response: {e}")
            raise ValueError(f"Failed to extract sprite sheet bounding boxes: {e}")

        # 2. Extract Layers and Remove Backgrounds
        print(f"✂️ Slicing Sprite Sheet layers to {textures_dir}...")
        os.makedirs(os.path.join(output_dir, "textures"), exist_ok=True)
        img = Image.open(concept_path).convert("RGBA")
        width, height = img.size
        
        parts_config = []
        canvas_w = 1000
        canvas_h = 1000
        
        import shutil
        shutil.copy2(concept_path, os.path.join(textures_dir, "original_spritesheet.png"))

        for name, box in coords.items():
            print(f"   -> Processing: {name} (Box: {box})...")
            
            # Skip if the Vision Model failed to locate this piece
            if not box or len(box) != 4:
                print(f"      ⚠️ Skipping {name}: Invalid bounding box detected.")
                continue
                
            left = (box[1] / 1000) * width
            top = (box[0] / 1000) * height
            right = (box[3] / 1000) * width
            bottom = (box[2] / 1000) * height
            
            # Crop feature
            cropped = img.crop((left, top, right, bottom))
            raw_path = os.path.join(textures_dir, f"{name}_raw.png")
            cropped.save(raw_path)
            
            # Remove Background
            nobg_path = os.path.join(textures_dir, f"{name}.png")
            self.remove_background(raw_path, nobg_path)
            
            tex_filename = f"textures/{name}.png"
            parts_config.append(self._create_part_entry(name, tex_filename, left, top, right, bottom, canvas_w, canvas_h))

        print(f"✨ Orchestrating dynamic Physics Engine mappings...")
        config = self.generate_rig(parts_config, chat_model=chat_model, instructions=instructions)
        config["name"] = output_name.replace("_", " ").title()
        
        with open(os.path.join(output_dir, "avatar.specter.json"), "w") as f:
            json.dump(config, f, indent=4)
            
        print(f"✅ Modular Rigging complete for {output_name}")
