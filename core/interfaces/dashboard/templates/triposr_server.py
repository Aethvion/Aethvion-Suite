"""
Aethvion Suite — TripoSR Worker
Fast single-image-to-3D (stabilityai/TripoSR, ~6 GB VRAM).
"""
import os
import sys
import base64
import traceback
import threading
import io
import datetime

# Global timestamped print
_original_print = print
def print(*args, **kwargs):
    ts = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    _original_print(ts, *args, **kwargs)

_HERE    = os.path.dirname(os.path.abspath(__file__))
_REPO    = os.path.join(_HERE, "triposr")
_WEIGHTS = os.path.join(_HERE, "weights")

if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

print(f"[triposr] Repo:    {_REPO}")
print(f"[triposr] Weights: {_WEIGHTS}")

_model      = None
_status     = "launching"
_load_error = None

import torch
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


def _vram():
    try:
        if torch.cuda.is_available():
            u = torch.cuda.memory_reserved(0) / 1024**3
            t = torch.cuda.get_device_properties(0).total_memory / 1024**3
            return round(u, 3), round(t, 3)
    except Exception:
        pass
    return 0.0, 0.0


def _load():
    global _model, _status, _load_error
    try:
        from tsr.system import TSR

        # Use local weights if already downloaded, otherwise auto-download from HuggingFace
        if os.path.exists(os.path.join(_WEIGHTS, "config.yaml")):
            model_src = _WEIGHTS
            print(f"[triposr] Using local weights: {_WEIGHTS}")
        else:
            model_src = "stabilityai/TripoSR"
            print("[triposr] Downloading weights from HuggingFace (1.7 GB, one-time)...")

        model = TSR.from_pretrained(
            model_src,
            config_name="config.yaml",
            weight_name="model.ckpt",
        )
        model.renderer.set_chunk_size(8192)

        if torch.cuda.is_available():
            dev = torch.cuda.get_device_properties(0)
            print(f"[triposr] CUDA: {dev.name}  ({dev.total_memory/1024**3:.1f} GB)")
            model = model.to("cuda")

        _model  = model
        _status = "online"
        u, t = _vram()
        print(f"[triposr] VRAM: {u:.2f}/{t:.2f} GB")
        print("[triposr] STATUS: online")
    except Exception:
        _load_error = traceback.format_exc()
        _status = "failed"
        print(f"[triposr] LOAD FAILED:\n{_load_error}")


@asynccontextmanager
async def _lifespan(app):
    t = threading.Thread(target=_load, daemon=True, name="triposr-loader")
    t.start()
    print("[triposr] Loader thread started")
    yield


app = FastAPI(title="TripoSR Worker", lifespan=_lifespan)


class GenRequest(BaseModel):
    image_base64: str
    seed: int = 42
    resolution: int = 256


@app.get("/health")
def health():
    u, t = _vram()
    r = {"status": _status, "vram_used": u, "vram_total": t, "model": "triposr"}
    if _status == "failed" and _load_error:
        r["error"] = _load_error[-2000:]
    return r


@app.post("/generate")
async def generate(req: GenRequest):
    if _status != "online" or _model is None:
        raise HTTPException(503, detail=f"Model not ready ({_status})")
    try:
        from PIL import Image

        raw = req.image_base64
        if "," in raw:
            raw = raw.split(",", 1)[1]
        image = Image.open(io.BytesIO(base64.b64decode(raw)))

        # Background removal — use rembg if available, fall back to white composite
        try:
            import rembg
            session = rembg.new_session()
            image = rembg.remove(image.convert("RGBA"), session=session)
            print("[triposr] Background removed via rembg")
        except Exception as rembg_err:
            print(f"[triposr] rembg skipped ({rembg_err.__class__.__name__}): {rembg_err}")
            image = image.convert("RGBA")

        # Composite onto white background for the model
        bg = Image.new("RGBA", image.size, (255, 255, 255, 255))
        if image.mode == "RGBA":
            bg.paste(image, mask=image.split()[3])
        else:
            bg.paste(image)
        image_rgb = bg.convert("RGB")

        print(f"[triposr] /generate resolution={req.resolution}")
        device = "cuda" if torch.cuda.is_available() else "cpu"

        with torch.no_grad():
            scene_codes = _model([image_rgb], device=device)

        print("[triposr] Extracting mesh...")
        meshes = _model.extract_mesh(scene_codes, has_vertex_color=True, resolution=req.resolution)

        # 90 degrees left rotation at creation level
        import numpy as np
        import trimesh
        matrix = trimesh.transformations.rotation_matrix(np.pi/2, [0, 1, 0])
        meshes[0].apply_transform(matrix)

        glb_bytes = meshes[0].export(file_type="glb")
        print(f"[triposr] GLB size: {len(glb_bytes)/1024:.1f} KB")

        return {"success": True, "glb_base64": base64.b64encode(glb_bytes).decode()}
    except Exception:
        tb = traceback.format_exc()
        print(f"[triposr] /generate failed:\n{tb}")
        return {"success": False, "error": tb}


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"[triposr] Starting on port {port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
