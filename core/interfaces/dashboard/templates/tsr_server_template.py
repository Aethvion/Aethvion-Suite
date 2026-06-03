"""
Aethvion Suite — {MODEL_NAME} Worker
All dependencies (kaolin, nvdiffrast) are real installed packages — no mocks.
"""
import os
import sys
import base64
import traceback
import threading

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


@app.get("/health")
def health():
    u, t = _vram()
    r = {"status": _status, "vram_used": u, "vram_total": t, "model": "{MODEL_ID}"}
    if _status == "failed" and _load_error:
        r["error"] = _load_error[-2000:]
    return r


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
        if "mesh" in outputs and "gaussian" in outputs:
            # 90 degrees left rotation at creation level
            import numpy as np
            import trimesh
            matrix = trimesh.transformations.rotation_matrix(np.pi/2, [0, 1, 0])
            outputs["mesh"][0].apply_transform(matrix)

            from trellis.utils import postprocessing_utils
            glb = postprocessing_utils.to_glb(outputs["gaussian"][0], outputs["mesh"][0])
            return {"success": True, "glb_base64": base64.b64encode(glb).decode()}
        return {"success": True, "formats": list(outputs.keys())}
    except Exception:
        tb = traceback.format_exc()
        print(f"[{MODEL_ID}] /generate failed:\n{tb}")
        return {"success": False, "error": tb}


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"[{MODEL_ID}] Starting on port {port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
