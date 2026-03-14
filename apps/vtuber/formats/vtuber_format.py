"""
.vtuber file format — ZIP-based package containing model.json + textures/
"""
import io
import json
import time
import uuid
import zipfile
from pathlib import Path
from typing import Optional

VTUBER_VERSION = "2.0.0"


# ---------------------------------------------------------------------------
# Default schema factories
# ---------------------------------------------------------------------------

def new_model(name: str = "Untitled") -> dict:
    return {
        "version": VTUBER_VERSION,
        "name": name,
        "author": "",
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "modified": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "canvas": {"width": 2048, "height": 2048},
        "layers": [],
        "bones": [],
        "weights": {},
        "parameters": {
            "ParamAngleX":  {"name": "Head Angle X",  "min": -30, "max": 30, "default": 0, "value": 0},
            "ParamAngleY":  {"name": "Head Angle Y",  "min": -30, "max": 30, "default": 0, "value": 0},
            "ParamAngleZ":  {"name": "Head Angle Z",  "min": -30, "max": 30, "default": 0, "value": 0},
            "ParamBreath":  {"name": "Breathing",     "min": 0,   "max": 1,  "default": 0, "value": 0},
            "ParamEyeOpenL":{"name": "Eye Open L",    "min": 0,   "max": 1,  "default": 1, "value": 1},
            "ParamEyeOpenR":{"name": "Eye Open R",    "min": 0,   "max": 1,  "default": 1, "value": 1},
            "ParamMouthOpenY":{"name": "Mouth Open",  "min": 0,   "max": 1,  "default": 0, "value": 0},
            "ParamMouthForm":{"name": "Mouth Form",   "min": -1,  "max": 1,  "default": 0, "value": 0},
            "ParamBrowLY":  {"name": "Brow L Y",      "min": -1,  "max": 1,  "default": 0, "value": 0},
            "ParamBrowRY":  {"name": "Brow R Y",      "min": -1,  "max": 1,  "default": 0, "value": 0},
        },
        "bone_params": [],
        "physics_groups": [],
        "animations": {
            "idle": {
                "name": "Idle",
                "duration": 3.0,
                "loop": True,
                "tracks": {
                    "ParamBreath": {"type": "sine", "speed": 0.4, "amplitude": 1.0, "offset": 0},
                    "ParamEyeOpenL": {"type": "blink", "speed": 1.0, "interval": 4.0},
                    "ParamEyeOpenR": {"type": "blink", "speed": 1.0, "interval": 4.0},
                }
            }
        },
        "metadata": {}
    }


def new_layer(name: str, texture_path: str, width: int, height: int,
              canvas_w: int = 2048, canvas_h: int = 2048) -> dict:
    """Create a default layer with a simple quad mesh."""
    # Center the layer on canvas
    cx = canvas_w / 2
    cy = canvas_h / 2
    hw = width / 2
    hh = height / 2

    vertices = [
        [cx - hw, cy - hh],
        [cx + hw, cy - hh],
        [cx + hw, cy + hh],
        [cx - hw, cy + hh],
    ]
    uvs = [[0, 0], [1, 0], [1, 1], [0, 1]]
    triangles = [[0, 1, 2], [0, 2, 3]]

    return {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "type": "mesh",
        "texture": texture_path,
        "visible": True,
        "locked": False,
        "order": 0,
        "parent": None,
        "transform": {"x": 0, "y": 0, "scaleX": 1, "scaleY": 1, "rotation": 0, "pivotX": 0, "pivotY": 0},
        "mesh": {"vertices": vertices, "uvs": uvs, "triangles": triangles},
        "texture_size": {"width": width, "height": height},
        "clipping_mask": None,
        "blend_mode": "normal",
        "opacity": 1.0,
    }


def new_bone(name: str, parent_id: Optional[str] = None,
             x: float = 0, y: float = 0, rotation: float = 0, length: float = 100) -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "parentId": parent_id,
        "position": {"x": x, "y": y},
        "rotation": rotation,
        "length": length,
        "color": "#7c6ff7",
        "visible": True,
    }


def new_bone_param(bone_id: str, param_id: str, prop: str = "rotation",
                   keyframes: Optional[list] = None) -> dict:
    if keyframes is None:
        keyframes = [
            {"param_value": -1.0, "bone_value": -30.0},
            {"param_value": 0.0,  "bone_value": 0.0},
            {"param_value": 1.0,  "bone_value": 30.0},
        ]
    return {
        "id": uuid.uuid4().hex[:12],
        "boneId": bone_id,
        "paramId": param_id,
        "property": prop,
        "keyframes": keyframes,
    }


def new_physics_group(name: str, input_param: str, bone_ids: list) -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "input": input_param,
        "bones": bone_ids,
        "settings": {"gravity": 0.3, "momentum": 0.8, "damping": 0.15, "wind": 0.0},
    }


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

class VTuberFormat:
    """Read and write .vtuber files (ZIP archives)."""

    MANIFEST_FILE = "manifest.json"
    MODEL_FILE = "model.json"
    TEXTURES_DIR = "textures/"

    # ------------------------------------------------------------------ read

    @staticmethod
    def load(path: str) -> tuple[dict, dict[str, bytes]]:
        """
        Load a .vtuber file.
        Returns (model_dict, textures_dict) where textures_dict maps
        relative paths (e.g. 'textures/head.png') to raw bytes.
        """
        textures: dict[str, bytes] = {}
        with zipfile.ZipFile(path, "r") as zf:
            with zf.open(VTuberFormat.MODEL_FILE) as f:
                model = json.load(f)
            for name in zf.namelist():
                if name.startswith(VTuberFormat.TEXTURES_DIR) and name != VTuberFormat.TEXTURES_DIR:
                    textures[name] = zf.read(name)
        return model, textures

    @staticmethod
    def load_model_only(path: str) -> dict:
        """Load only the model JSON without reading textures into memory."""
        with zipfile.ZipFile(path, "r") as zf:
            with zf.open(VTuberFormat.MODEL_FILE) as f:
                return json.load(f)

    # ----------------------------------------------------------------- write

    @staticmethod
    def save(path: str, model: dict, textures: dict[str, bytes]) -> None:
        """
        Save a .vtuber file.
        textures: dict mapping relative path → raw PNG bytes
        """
        model["modified"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        manifest = {
            "version": model.get("version", VTUBER_VERSION),
            "name": model.get("name", "Untitled"),
            "author": model.get("author", ""),
            "created": model.get("created", ""),
            "modified": model["modified"],
        }
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(VTuberFormat.MANIFEST_FILE, json.dumps(manifest, indent=2))
            zf.writestr(VTuberFormat.MODEL_FILE, json.dumps(model, indent=2))
            for rel_path, data in textures.items():
                zf.writestr(rel_path, data)

    # -------------------------------------------------------- directory ↔ .vtuber

    @staticmethod
    def export_from_dir(model_dir: str, output_path: str) -> None:
        """
        Pack a legacy model directory (avatar.vtuber.json + textures/) into a
        .vtuber archive. Also migrates old v1 format to v2 automatically.
        """
        model_dir = Path(model_dir)
        old_json = model_dir / "avatar.vtuber.json"
        if not old_json.exists():
            raise FileNotFoundError(f"No avatar.vtuber.json found in {model_dir}")

        with open(old_json, "r", encoding="utf-8") as f:
            old = json.load(f)

        model = _migrate_v1_to_v2(old, model_dir.name)
        textures: dict[str, bytes] = {}

        tex_dir = model_dir / "textures"
        if tex_dir.exists():
            for png in tex_dir.glob("*.png"):
                rel = f"textures/{png.name}"
                textures[rel] = png.read_bytes()

        VTuberFormat.save(output_path, model, textures)

    @staticmethod
    def extract_to_dir(specter_path: str, output_dir: str) -> str:
        """Extract a .vtuber archive to a directory. Returns the model dir path."""
        specter_path = Path(specter_path)
        output_dir = Path(output_dir)
        name = specter_path.stem
        model_dir = output_dir / name
        model_dir.mkdir(parents=True, exist_ok=True)

        model, textures = VTuberFormat.load(str(specter_path))

        with open(model_dir / "model.json", "w", encoding="utf-8") as f:
            json.dump(model, f, indent=2)

        for rel_path, data in textures.items():
            dest = model_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)

        return str(model_dir)

    # -------------------------------------------------------------- utilities

    @staticmethod
    def list_textures(path: str) -> list[str]:
        """Return relative texture paths inside a .vtuber file."""
        with zipfile.ZipFile(path, "r") as zf:
            return [n for n in zf.namelist()
                    if n.startswith(VTuberFormat.TEXTURES_DIR) and not n.endswith("/")]

    @staticmethod
    def add_texture(specter_path: str, rel_path: str, data: bytes) -> None:
        """Add or replace a texture inside an existing .vtuber file."""
        with zipfile.ZipFile(specter_path, "a", zipfile.ZIP_DEFLATED) as zf:
            if rel_path in zf.namelist():
                # zipfile doesn't support in-place replacement easily — rebuild
                pass
            zf.writestr(rel_path, data)


# ---------------------------------------------------------------------------
# Migration: v1 (avatar.vtuber.json) → v2 model dict
# ---------------------------------------------------------------------------

def _migrate_v1_to_v2(old: dict, model_name: str) -> dict:
    """Convert a v1 avatar.vtuber.json to a v2 model dict."""
    model = new_model(model_name)
    model["version"] = VTUBER_VERSION

    # Migrate parts → layers
    for part in old.get("parts", []):
        pid = part.get("id", uuid.uuid4().hex[:12])
        tex = part.get("texture", f"textures/{pid}.png")
        w = part.get("mesh", {}).get("width", 200)
        h = part.get("mesh", {}).get("height", 200)

        # Convert old 3x3 grid mesh to triangle list
        old_verts = part.get("mesh", {}).get("vertices", [])
        old_uvs = part.get("mesh", {}).get("uvs", [])
        old_indices = part.get("mesh", {}).get("indices", [])

        if old_verts and old_indices:
            verts_2d = [[old_verts[i], old_verts[i + 1]] for i in range(0, len(old_verts), 2)]
            uvs_2d = [[old_uvs[i], old_uvs[i + 1]] for i in range(0, len(old_uvs), 2)]
            tris = [[old_indices[i], old_indices[i + 1], old_indices[i + 2]]
                    for i in range(0, len(old_indices), 3)]
        else:
            cx, cy = 1024, 1024
            hw, hh = w / 2, h / 2
            verts_2d = [[cx - hw, cy - hh], [cx + hw, cy - hh],
                        [cx + hw, cy + hh], [cx - hw, cy + hh]]
            uvs_2d = [[0, 0], [1, 0], [1, 1], [0, 1]]
            tris = [[0, 1, 2], [0, 2, 3]]

        layer = {
            "id": pid,
            "name": pid.replace("_", " ").title(),
            "type": "mesh",
            "texture": tex,
            "visible": True,
            "locked": False,
            "order": part.get("z", 0),
            "parent": None,
            "transform": {
                "x": part.get("x", 0), "y": part.get("y", 0),
                "scaleX": 1, "scaleY": 1,
                "rotation": 0, "pivotX": 0, "pivotY": 0,
            },
            "mesh": {"vertices": verts_2d, "uvs": uvs_2d, "triangles": tris},
            "texture_size": {"width": w, "height": h},
            "clipping_mask": None,
            "blend_mode": "normal",
            "opacity": 1.0,
        }
        model["layers"].append(layer)

    # Migrate params
    for param_id, pval in old.get("params", {}).items():
        model["parameters"][param_id] = {
            "name": pval.get("name", param_id),
            "min": pval.get("min", -1),
            "max": pval.get("max", 1),
            "default": pval.get("default", 0),
            "value": pval.get("value", 0),
        }

    # Migrate animations
    model["animations"] = old.get("animations", model["animations"])

    return model
