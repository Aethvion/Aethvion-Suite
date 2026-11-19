"""
Aethvion Suite — TRELLIS.2-4B Worker (with automatic TRELLIS v1 fallback)
Supports microsoft/TRELLIS.2-4B (O-Voxel full PBR) as well as existing TRELLIS v1 installs.
"""
import io
import os
import sys
import base64
import inspect
import threading
import traceback
from contextlib import asynccontextmanager
from typing import List, Optional

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("ATTN_BACKEND", "sdpa")
if "SPARSE_ATTN_BACKEND" not in os.environ:
    try:
        import xformers  # noqa: F401
        os.environ["SPARSE_ATTN_BACKEND"] = "xformers"
    except Exception:
        os.environ["SPARSE_ATTN_BACKEND"] = "flash_attn"

# Prevent transformers from crashing on Windows when flash_attn is absent
try:
    import transformers.utils.import_utils as _iu
    _iu.is_flash_attn_2_available = lambda: False
    _iu.is_flash_attn_available = lambda: False
    _iu.is_flash_attn_3_available = lambda: False
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.join(_HERE, "trellis-2")
_WEIGHTS = os.path.join(_HERE, "weights")

if os.path.isdir(_REPO) and _REPO not in sys.path:
    sys.path.insert(0, _REPO)

print(f"[trellis-2] Repo:    {_REPO}")
print(f"[trellis-2] Weights: {_WEIGHTS}")

_IS_TRELLIS2 = os.path.isdir(os.path.join(_REPO, "trellis2"))
_IS_TRELLIS1 = os.path.isdir(os.path.join(_REPO, "trellis"))

_Pipeline = None
_OVoxel = None
_import_error = None
_engine_version = "trellis-2-4b"

if _IS_TRELLIS2:
    try:
        from trellis2.pipelines import Trellis2ImageTo3DPipeline as _T2
        _Pipeline = _T2
        try:
            import o_voxel as _ov
            _OVoxel = _ov
        except Exception as _ov_exc:
            print(f"[trellis-2] o_voxel optional import warning: {_ov_exc}")
        print("[trellis-2] TRELLIS.2 pipeline imported OK")
    except Exception:
        _import_error = traceback.format_exc()
        print(f"[trellis-2] TRELLIS.2 IMPORT FAILED:\n{_import_error}")
elif _IS_TRELLIS1:
    _engine_version = "trellis-v1-legacy"
    try:
        from trellis.pipelines import TrellisImageTo3DPipeline as _T1
        _Pipeline = _T1
        print("[trellis-2] Legacy TRELLIS v1 pipeline imported OK")
    except Exception:
        _import_error = traceback.format_exc()
        print(f"[trellis-2] TRELLIS v1 IMPORT FAILED:\n{_import_error}")
else:
    _engine_version = "missing-repo"
    _import_error = f"Neither trellis2/ nor trellis/ package found inside {_REPO}"
    print(f"[trellis-2] {_import_error}")

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

_pipeline = None
_status = "launching"
_load_error = None
_gpu_lock = threading.Lock()


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

    weights_src = _WEIGHTS if os.path.exists(os.path.join(_WEIGHTS, "pipeline.json")) else None
    if not weights_src:
        if _engine_version == "trellis-2-4b":
            weights_src = "microsoft/TRELLIS.2-4B"
            print("[trellis-2] Local weights missing pipeline.json; loading HF repo microsoft/TRELLIS.2-4B")
        else:
            _load_error = f"pipeline.json missing in {_WEIGHTS}"
            _status = "failed"
            print(f"[trellis-2] {_load_error}")
            return

    try:
        if torch.cuda.is_available():
            dev = torch.cuda.get_device_properties(0)
            print(f"[trellis-2] CUDA: {dev.name} ({dev.total_memory / 1024**3:.1f} GB)")
        u0, _ = _vram()
        print(f"[trellis-2] Loading {_engine_version} from {weights_src}...")
        pipeline = _Pipeline.from_pretrained(weights_src)
        if torch.cuda.is_available():
            pipeline.cuda()
        u1, t1 = _vram()
        print(f"[trellis-2] VRAM: {u1:.2f}/{t1:.2f} GB (delta {u1 - u0:.2f} GB)")
        _pipeline = pipeline
        _status = "online"
        print("[trellis-2] STATUS: online")
    except Exception as exc:
        tb = traceback.format_exc()
        msg = f"{exc}\n{tb}".lower()
        if any(k in msg for k in ("gatedrepoerror", "gated repo", "401 client error", "403 client error", "cannot access gated repo")):
            _load_error = (
                "Hugging Face authentication required for gated dependency (e.g. facebook/dinov3-vitl16-pretrain-lvd1689m or briaai/RMBG-2.0). "
                "Accept the repository terms on Hugging Face, then run `huggingface-cli login` or set the HF_TOKEN environment variable and restart Aethvion Suite."
            )
        else:
            _load_error = tb
        _status = "failed"
        print(f"[trellis-2] LOAD FAILED:\n{tb}")


@asynccontextmanager
async def _lifespan(app):
    t = threading.Thread(target=_load, daemon=True, name="trellis2-loader")
    t.start()
    print("[trellis-2] Loader thread started")
    yield


app = FastAPI(title="TRELLIS.2-4B Worker", lifespan=_lifespan)


class GenRequest(BaseModel):
    image_base64: str
    prompt: Optional[str] = None
    seed: int = 42
    resolution: str = "1024"
    quality: Optional[str] = None
    formats: List[str] = ["gaussian", "mesh"]
    simplify: float = 0.95
    decimation_target: int = 100000
    texture_size: int = 2048
    remesh: bool = True
    textured: bool = True
    pbr: bool = True


@app.get("/health")
def health():
    u, t = _vram()
    r = {
        "status": _status,
        "vram_used": u,
        "vram_total": t,
        "model": "trellis-2",
        "engine_version": _engine_version,
    }
    if _status == "failed" and _load_error:
        r["error"] = _load_error[-2000:]
    return r


def _export_trellis2_glb(outputs, req: GenRequest):
    import numpy as np
    import trimesh

    mesh = outputs[0] if isinstance(outputs, (list, tuple)) else outputs
    if hasattr(mesh, "simplify"):
        try:
            mesh.simplify(16777216)
        except Exception as exc:
            print(f"[trellis-2] mesh.simplify skipped: {exc}")

    if _OVoxel is not None and req.textured:
        try:
            glb = _OVoxel.postprocess.to_glb(
                vertices=mesh.vertices,
                faces=mesh.faces,
                attr_volume=mesh.attrs,
                coords=mesh.coords,
                attr_layout=mesh.layout,
                voxel_size=mesh.voxel_size,
                aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
                decimation_target=int(req.decimation_target or 100000),
                texture_size=int(req.texture_size or 2048),
                remesh=bool(req.remesh),
                remesh_band=1,
                remesh_project=0,
                verbose=False,
            )
            buf = io.BytesIO()
            try:
                glb.export(buf, file_type="glb", extension_webp=True)
            except TypeError:
                glb.export(buf, file_type="glb")
            return buf.getvalue(), True, ""
        except Exception as exc:
            print(f"[trellis-2] o_voxel.postprocess.to_glb failed ({exc}), falling back to trimesh export")

    # Fallback: export geometry + vertex colors if o_voxel isn't compiled
    verts = mesh.vertices.detach().float().cpu().numpy() if torch.is_tensor(mesh.vertices) else np.asarray(mesh.vertices)
    faces = mesh.faces.detach().cpu().numpy() if torch.is_tensor(mesh.faces) else np.asarray(mesh.faces)
    out = trimesh.Trimesh(verts, faces, process=False)
    return out.export(file_type="glb"), False, "o_voxel texture baking unavailable; exported raw geometry"


def _export_trellis1_glb(outputs, req: GenRequest):
    import numpy as np
    import trimesh

    mesh = outputs["mesh"][0]
    rotate = trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])
    why = ""
    if req.textured and "gaussian" in outputs:
        try:
            from trellis.utils import postprocessing_utils
            glb = postprocessing_utils.to_glb(
                outputs["gaussian"][0],
                mesh,
                simplify=req.simplify,
                texture_size=min(int(req.texture_size or 1024), 2048),
                verbose=False,
            )
            glb.apply_transform(rotate)
            return glb.export(file_type="glb"), True, ""
        except (ImportError, ModuleNotFoundError) as exc:
            why = f"texture baking unavailable ({exc})"

    vertices = mesh.vertices.detach().float().cpu().numpy()
    faces = mesh.faces.detach().cpu().numpy()
    colours = None
    if getattr(mesh, "vertex_attrs", None) is not None:
        colours = mesh.vertex_attrs[:, :3].detach().float().cpu().numpy().clip(0.0, 1.0)
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
    except Exception:
        pass
    vertices = vertices @ np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])
    out = trimesh.Trimesh(vertices, faces, process=False)
    if colours is not None and len(colours) == len(vertices):
        rgba = np.concatenate([colours, np.ones((len(colours), 1))], axis=1)
        out.visual = trimesh.visual.ColorVisuals(out, vertex_colors=(rgba * 255).astype(np.uint8))
    out.apply_transform(rotate)
    return out.export(file_type="glb"), False, (why or "mesh only") + "; vertex colours"


def _run_trellis2_pipeline(image, req: GenRequest):
    res_str = str(req.quality or req.resolution or "1024")
    res_val = "1024" if res_str not in ("512", "1024", "1536") else res_str
    kwargs = {"seed": int(req.seed)}
    try:
        sig = inspect.signature(_pipeline.run)
        if "pipeline_type" in sig.parameters:
            kwargs["pipeline_type"] = f"{res_val}_cascade"
        elif "resolution" in sig.parameters:
            kwargs["resolution"] = int(res_val)
    except Exception:
        pass
    try:
        return _pipeline.run(image, **kwargs)
    except TypeError:
        return _pipeline.run(image, seed=int(req.seed))


@app.post("/generate")
async def generate(req: GenRequest):
    if _status != "online" or _pipeline is None:
        raise HTTPException(503, detail=f"Model not ready ({_status})")
    try:
        from PIL import Image
        raw = req.image_base64
        if "," in raw:
            raw = raw.split(",", 1)[1]
        img_bytes = base64.b64decode(raw)
        image = Image.open(io.BytesIO(img_bytes))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA")

        with _gpu_lock:
            if _engine_version == "trellis-2-4b":
                print(f"[trellis-2] /generate (TRELLIS.2-4B) seed={req.seed} res={req.quality or req.resolution}")
                outputs = _run_trellis2_pipeline(image, req)
                data, textured, note = _export_trellis2_glb(outputs, req)
            else:
                print(f"[trellis-2] /generate (legacy v1) seed={req.seed}")
                outputs = _pipeline.run(image.convert("RGB"), seed=int(req.seed), formats=req.formats)
                if "mesh" not in outputs:
                    return {"success": False, "error": "TRELLIS v1 returned no mesh"}
                data, textured, note = _export_trellis1_glb(outputs, req)

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        print(f"[trellis-2] GLB size: {len(data) / 1024:.1f} KB textured={textured}")
        return {
            "success": True,
            "glb_base64": base64.b64encode(data).decode(),
            "textured": textured,
            "note": note,
            "engine_version": _engine_version,
        }
    except Exception:
        tb = traceback.format_exc()
        print(f"[trellis-2] /generate failed:\n{tb}")
        return {"success": False, "error": tb}


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"[trellis-2] Starting on port {port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
