"""
Aethvion Suite — {MODEL_NAME} Worker
All dependencies (kaolin, nvdiffrast) are real installed packages — no mocks.
"""
import os
import sys
import base64
import traceback
import threading

# Placeholders defined for Python syntax validation/linting
MODEL_ID = "{MODEL_ID}"
MODEL_NAME = "{MODEL_NAME}"

# Attention backend: use PyTorch built-in SDPA (no flash_attn required)
os.environ.setdefault("ATTN_BACKEND", "sdpa")
os.environ.setdefault("SPARSE_ATTN_BACKEND", "sdpa")

# Tell transformers flash_attn is not available (avoids import-time crash)
try:
    import transformers.utils.import_utils as _iu
    _iu.is_flash_attn_2_available = lambda: False
    _iu.is_flash_attn_available   = lambda: False
    _iu.is_flash_attn_3_available = lambda: False
except Exception:
    pass

# Path setup
_HERE    = os.path.dirname(os.path.abspath(__file__))
_REPO    = os.path.join(_HERE, "{MODEL_ID}")
_WEIGHTS = os.path.join(_HERE, "weights")

if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

print(f"[{MODEL_ID}] Repo:    {_REPO}")
print(f"[{MODEL_ID}] Weights: {_WEIGHTS}")

# Import pipeline class
_Pipeline     = None
_import_error = None
try:
    from trellis.pipelines import TrellisImageTo3DPipeline as _T
    _Pipeline = _T
    print(f"[{MODEL_ID}] Pipeline imported OK")
except Exception:
    _import_error = traceback.format_exc()
    print(f"[{MODEL_ID}] IMPORT FAILED:\n{_import_error}")

# FastAPI service
import torch
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

_pipeline   = None
_status     = "launching"
_load_error = None


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
    global _pipeline, _status, _load_error
    if _Pipeline is None:
        _load_error = _import_error or "Pipeline class failed to import"
        _status = "failed"
        return
    if not os.path.exists(os.path.join(_WEIGHTS, "pipeline.json")):
        _load_error = f"pipeline.json missing in {_WEIGHTS}"
        _status = "failed"
        print(f"[{MODEL_ID}] {_load_error}")
        return
    try:
        if torch.cuda.is_available():
            dev = torch.cuda.get_device_properties(0)
            print(f"[{MODEL_ID}] CUDA: {dev.name}  ({dev.total_memory/1024**3:.1f} GB)")
        u0, _ = _vram()
        print(f"[{MODEL_ID}] Loading weights (1-3 min)...")
        pipeline = _Pipeline.from_pretrained(_WEIGHTS)
        if torch.cuda.is_available():
            pipeline.cuda()
        u1, t1 = _vram()
        print(f"[{MODEL_ID}] VRAM: {u1:.2f}/{t1:.2f} GB  (delta {u1-u0:.2f} GB)")
        _pipeline = pipeline
        _status   = "online"
        print(f"[{MODEL_ID}] STATUS: online")
    except Exception:
        _load_error = traceback.format_exc()
        _status = "failed"
        print(f"[{MODEL_ID}] LOAD FAILED:\n{_load_error}")


@asynccontextmanager
async def _lifespan(app):
    t = threading.Thread(target=_load, daemon=True, name="{MODEL_ID}-loader")
    t.start()
    print(f"[{MODEL_ID}] Loader thread started")
    yield


app = FastAPI(title="{MODEL_NAME} Worker", lifespan=_lifespan)


class GenRequest(BaseModel):
    image_base64: str
    seed:         int       = 42
    formats:      List[str] = ["gaussian", "mesh"]
    simplify:     float     = 0.95   # fraction of triangles removed (0.95 = keep 5%)
    texture_size: int       = 1024


@app.get("/health")
def health():
    u, t = _vram()
    r = {"status": _status, "vram_used": u, "vram_total": t, "model": "{MODEL_ID}"}
    if _status == "failed" and _load_error:
        r["error"] = _load_error[-2000:]
    return r


def _export_glb(outputs, req):
    """Turn pipeline outputs into GLB bytes. Returns (bytes, textured, note).

    Preferred path: TRELLIS' own to_glb, which simplifies the mesh and bakes a texture
    by rendering the Gaussians. That needs two compiled extensions (nvdiffrast and
    diff_gaussian_rasterization). When either is missing the mesh is still exported,
    simplified and coloured per vertex, so the model is usable instead of failing.
    """
    import numpy as np
    import trimesh

    mesh = outputs["mesh"][0]
    rotate = trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])   # face the viewer

    why = ""
    if "gaussian" in outputs:
        try:
            from trellis.utils import postprocessing_utils
            glb = postprocessing_utils.to_glb(
                outputs["gaussian"][0], mesh,
                simplify=req.simplify, texture_size=req.texture_size, verbose=False,
            )
            glb.apply_transform(rotate)
            return glb.export(file_type="glb"), True, ""
        except (ImportError, ModuleNotFoundError) as exc:
            why = f"texture baking unavailable ({exc})"
            print(f"[{MODEL_ID}] {why}: exporting with vertex colours instead")

    vertices = mesh.vertices.detach().float().cpu().numpy()
    faces    = mesh.faces.detach().cpu().numpy()
    colours  = None
    if getattr(mesh, "vertex_attrs", None) is not None:
        colours = mesh.vertex_attrs[:, :3].detach().float().cpu().numpy().clip(0.0, 1.0)

    # Simplify (the raw mesh has hundreds of thousands of triangles), then carry the
    # colours over from the nearest original vertex.
    try:
        from trellis.utils import postprocessing_utils
        new_v, new_f = postprocessing_utils.postprocess_mesh(
            vertices, faces, simplify=req.simplify > 0, simplify_ratio=req.simplify,
            fill_holes=False, verbose=False,
        )
        if colours is not None and len(new_v):
            from scipy.spatial import cKDTree
            colours = colours[cKDTree(vertices).query(new_v)[1]]
        vertices, faces = new_v, new_f
    except Exception as exc:
        print(f"[{MODEL_ID}] mesh simplification skipped: {exc}")

    vertices = vertices @ np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])      # z-up -> y-up, as to_glb does
    out = trimesh.Trimesh(vertices, faces, process=False)
    if colours is not None and len(colours) == len(vertices):
        rgba = np.concatenate([colours, np.ones((len(colours), 1))], axis=1)
        out.visual = trimesh.visual.ColorVisuals(out, vertex_colors=(rgba * 255).astype(np.uint8))
    out.apply_transform(rotate)
    return out.export(file_type="glb"), False, (why or "mesh only") + "; colours are stored per vertex"


@app.post("/generate")
async def generate(req: GenRequest):
    if _status != "online" or _pipeline is None:
        raise HTTPException(503, detail=f"Model not ready ({_status})")
    try:
        from PIL import Image
        import io as _io
        raw = req.image_base64
        if "," in raw:
            raw = raw.split(",", 1)[1]
        image = Image.open(_io.BytesIO(base64.b64decode(raw))).convert("RGB")
        print(f"[{MODEL_ID}] /generate seed={req.seed}")
        outputs = _pipeline.run(image, seed=req.seed, formats=req.formats)
        print(f"[{MODEL_ID}] Inference complete")
        if "mesh" in outputs:
            data, textured, note = _export_glb(outputs, req)
            print(f"[{MODEL_ID}] GLB size: {len(data) / 1024:.1f} KB  textured={textured}")
            return {"success": True, "glb_base64": base64.b64encode(data).decode(),
                    "textured": textured, "note": note}
        return {"success": True, "formats": list(outputs.keys())}
    except Exception:
        tb = traceback.format_exc()
        print(f"[{MODEL_ID}] /generate failed:\n{tb}")
        return {"success": False, "error": tb}


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"[{MODEL_ID}] Starting on port {port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
