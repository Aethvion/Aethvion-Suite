"""
Aethvion Suite — Hunyuan3D 2.1 Worker
VRAM-safe two-stage pipeline (Shape ~10 GB -> unload -> PBR Paint ~21 GB) for 24 GB GPUs.
"""
import gc
import io
import os
import sys
import types
import base64
import tempfile
import threading
import traceback
from contextlib import asynccontextmanager
from typing import Optional

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.join(_HERE, "hunyuan3d")
_WEIGHTS = os.path.join(_HERE, "weights")

for _sub in (os.path.join(_REPO, "hy3dshape"), os.path.join(_REPO, "hy3dpaint"), _REPO):
    if os.path.isdir(_sub) and _sub not in sys.path:
        sys.path.insert(0, _sub)

try:
    from torchvision_fix import apply_fix as _apply_tv_fix
    _apply_tv_fix()
except Exception:
    pass

print(f"[hunyuan3d] Repo:    {_REPO}")
print(f"[hunyuan3d] Weights: {_WEIGHTS}")

_ShapePipeline = None
_BackgroundRemover = None
_PaintPipeline = None
_PaintConfig = None
_import_error = None
_HAS_REAL_BPY = False


def _obj_to_glb_with_pbr(obj_path: str, glb_path: str, *args, **kwargs) -> bool:
    """Convert a Hunyuan3D painted OBJ mesh + PBR maps into a binary GLB without Blender."""
    try:
        import trimesh
        from PIL import Image

        mesh = trimesh.load(obj_path, force="mesh", process=False)
        base = os.path.splitext(obj_path)[0]
        albedo_path = f"{base}.jpg"
        metallic_path = f"{base}_metallic.jpg"
        roughness_path = f"{base}_roughness.jpg"
        normal_path = f"{base}_normal.jpg"

        albedo_img = Image.open(albedo_path).convert("RGB") if os.path.exists(albedo_path) else None
        metallic_img = Image.open(metallic_path).convert("L") if os.path.exists(metallic_path) else None
        roughness_img = Image.open(roughness_path).convert("L") if os.path.exists(roughness_path) else None
        normal_img = Image.open(normal_path).convert("RGB") if os.path.exists(normal_path) else None

        mr_img = None
        if metallic_img is not None or roughness_img is not None:
            ref_size = (metallic_img or roughness_img).size
            r_chan = roughness_img.resize(ref_size, Image.BILINEAR) if roughness_img is not None else Image.new("L", ref_size, 255)
            m_chan = metallic_img.resize(ref_size, Image.BILINEAR) if metallic_img is not None else Image.new("L", ref_size, 0)
            mr_img = Image.merge("RGB", (Image.new("L", ref_size, 0), r_chan, m_chan))

        mat = trimesh.visual.material.PBRMaterial(
            baseColorTexture=albedo_img,
            metallicRoughnessTexture=mr_img,
            normalTexture=normal_img,
            metallicFactor=1.0 if metallic_img is not None else 0.0,
            roughnessFactor=1.0 if roughness_img is not None else 0.85,
        )
        uv = getattr(getattr(mesh, "visual", None), "uv", None)
        mesh.visual = trimesh.visual.TextureVisuals(uv=uv, material=mat)
        mesh.export(glb_path)
        return os.path.exists(glb_path) and os.path.getsize(glb_path) > 0
    except Exception as exc:
        print(f"[hunyuan3d] OBJ->GLB PBR conversion failed: {exc}")
        return False


try:
    from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline as _SP
    _ShapePipeline = _SP
    try:
        from hy3dshape.rembg import BackgroundRemover as _BR
        _BackgroundRemover = _BR
    except Exception:
        pass
    try:
        try:
            import bpy  # noqa: F401
            _HAS_REAL_BPY = True
        except ImportError:
            _HAS_REAL_BPY = False
            sys.modules["bpy"] = types.ModuleType("bpy")

        from textureGenPipeline import Hunyuan3DPaintPipeline as _PP, Hunyuan3DPaintConfig as _PC
        _PaintPipeline = _PP
        _PaintConfig = _PC
        if not _HAS_REAL_BPY:
            import textureGenPipeline as _tgp_mod
            import DifferentiableRenderer.mesh_utils as _mu_mod
            _tgp_mod.convert_obj_to_glb = _obj_to_glb_with_pbr
            _mu_mod.convert_obj_to_glb = _obj_to_glb_with_pbr
    except Exception as _pe:
        print(f"[hunyuan3d] Paint pipeline unavailable (shape-only mode): {_pe}")
    print("[hunyuan3d] Shape pipeline imported OK")
except Exception:
    _import_error = traceback.format_exc()
    print(f"[hunyuan3d] IMPORT FAILED:\n{_import_error}")

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

_shape_pipeline = None
_rembg = None
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


def _free_cuda():
    gc.collect()
    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass


def _move_pipeline(pipe, device: str):
    if pipe is None:
        return
    try:
        pipe.to(device)
    except Exception:
        pass


def _weights_source() -> str:
    if os.path.isdir(_WEIGHTS) and os.path.exists(os.path.join(_WEIGHTS, "hunyuan3d-dit-v2-1")):
        return _WEIGHTS
    if os.path.isdir(_WEIGHTS) and any(
        f.endswith(".safetensors") or f.endswith(".ckpt") or f == "config.json"
        for f in os.listdir(_WEIGHTS)
    ):
        return _WEIGHTS
    return "tencent/Hunyuan3D-2.1"


def _load():
    global _shape_pipeline, _rembg, _status, _load_error
    if _ShapePipeline is None:
        _load_error = _import_error or "Hunyuan3D shape pipeline failed to import"
        _status = "failed"
        return

    try:
        if torch.cuda.is_available():
            dev = torch.cuda.get_device_properties(0)
            print(f"[hunyuan3d] CUDA: {dev.name} ({dev.total_memory / 1024**3:.1f} GB)")
        src = _weights_source()
        print(f"[hunyuan3d] Loading shape pipeline from {src}...")
        _shape_pipeline = _ShapePipeline.from_pretrained(src)
        # Keep shape pipeline off GPU until generation starts so Paint stage has full 24 GB
        _move_pipeline(_shape_pipeline, "cpu")
        if _BackgroundRemover is not None:
            try:
                _rembg = _BackgroundRemover()
            except Exception:
                _rembg = None
        _status = "online"
        print("[hunyuan3d] STATUS: online (VRAM staged)")
    except Exception:
        _load_error = traceback.format_exc()
        _status = "failed"
        print(f"[hunyuan3d] LOAD FAILED:\n{_load_error}")


@asynccontextmanager
async def _lifespan(app):
    t = threading.Thread(target=_load, daemon=True, name="hunyuan3d-loader")
    t.start()
    print("[hunyuan3d] Loader thread started")
    yield


app = FastAPI(title="Hunyuan3D 2.1 Worker", lifespan=_lifespan)


class GenRequest(BaseModel):
    image_base64: str
    prompt: Optional[str] = None
    seed: int = 42
    steps: int = 50
    textured: bool = True
    pbr: bool = True
    max_num_view: int = 6
    texture_resolution: int = 512
    remove_bg: bool = True


class TextureRequest(BaseModel):
    mesh_base64: str
    image_base64: Optional[str] = None
    max_num_view: int = 6
    texture_resolution: int = 512
    seed: int = 42


@app.get("/health")
def health():
    u, t = _vram()
    r = {
        "status": _status,
        "vram_used": u,
        "vram_total": t,
        "model": "hunyuan3d",
        "paint_available": _PaintPipeline is not None,
    }
    if _status == "failed" and _load_error:
        r["error"] = _load_error[-2000:]
    return r


def _build_paint_config(max_num_view: int, resolution: int):
    conf = _PaintConfig(int(max_num_view), int(resolution))
    realesrgan_ckpt = os.path.join(_REPO, "hy3dpaint", "ckpt", "RealESRGAN_x4plus.pth")
    mv_cfg = os.path.join(_REPO, "hy3dpaint", "cfgs", "hunyuan-paint-pbr.yaml")
    custom_pipe = os.path.join(_REPO, "hy3dpaint", "hunyuanpaintpbr")
    if os.path.exists(os.path.join(_WEIGHTS, "hunyuan3d-paintpbr-v2-1")):
        conf.multiview_pretrained_path = _weights_source()
    if os.path.exists(realesrgan_ckpt):
        conf.realesrgan_ckpt_path = realesrgan_ckpt
    if os.path.exists(mv_cfg):
        conf.multiview_cfg_path = mv_cfg
    if os.path.exists(custom_pipe):
        conf.custom_pipeline = custom_pipe
    return conf


def _has_meaningful_alpha(im) -> bool:
    if im.mode != "RGBA":
        return False
    ext = im.getchannel("A").getextrema()
    return bool(ext and ext[0] < 250)


@app.post("/generate")
async def generate(req: GenRequest):
    if _status != "online" or _shape_pipeline is None:
        raise HTTPException(503, detail=f"Model not ready ({_status})")
    try:
        from PIL import Image
        raw = req.image_base64
        if "," in raw:
            raw = raw.split(",", 1)[1]
        img = Image.open(io.BytesIO(base64.b64decode(raw)))
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        if req.remove_bg and not _has_meaningful_alpha(img) and _rembg is not None:
            try:
                img = _rembg(img.convert("RGB")).convert("RGBA")
            except Exception as exc:
                print(f"[hunyuan3d] rembg warning: {exc}")

        with _gpu_lock, tempfile.TemporaryDirectory() as tmpdir:
            ref_path = os.path.join(tmpdir, "ref.png")
            shape_path = os.path.join(tmpdir, "shape.glb")
            tex_obj_path = os.path.join(tmpdir, "textured.obj")
            tex_glb_path = tex_obj_path.replace(".obj", ".glb")
            img.save(ref_path)

            # Stage 1: Shape generation (~10 GB VRAM)
            if torch.cuda.is_available():
                _move_pipeline(_shape_pipeline, "cuda")
            gen = None
            try:
                dev = "cuda" if torch.cuda.is_available() else "cpu"
                gen = torch.Generator(device=dev).manual_seed(int(req.seed))
            except Exception:
                gen = None

            try:
                mesh = _shape_pipeline(
                    image=img,
                    num_inference_steps=int(req.steps or 50),
                    generator=gen,
                )[0]
            except TypeError:
                mesh = _shape_pipeline(image=img)[0]

            mesh.export(shape_path)

            # Offload Shape stage before Paint stage (~21 GB VRAM)
            _move_pipeline(_shape_pipeline, "cpu")
            _free_cuda()

            final_path = shape_path
            textured_ok = False
            note = ""

            if req.textured:
                if _PaintPipeline is None or _PaintConfig is None:
                    note = "PBR paint pipeline unavailable (missing custom_rasterizer/DifferentiableRenderer); returning untextured mesh"
                else:
                    try:
                        conf = _build_paint_config(req.max_num_view, req.texture_resolution)
                        paint_pipe = _PaintPipeline(conf)
                        out_path = paint_pipe(
                            mesh_path=shape_path,
                            image_path=ref_path,
                            output_mesh_path=tex_obj_path,
                            save_glb=True,
                        )
                        if not os.path.exists(tex_glb_path) and os.path.exists(tex_obj_path):
                            _obj_to_glb_with_pbr(tex_obj_path, tex_glb_path)
                        if os.path.exists(tex_glb_path):
                            final_path = tex_glb_path
                            textured_ok = True
                        elif out_path and out_path.endswith(".glb") and os.path.exists(out_path):
                            final_path = out_path
                            textured_ok = True
                        del paint_pipe
                        _free_cuda()
                    except Exception as exc:
                        note = f"PBR paint stage failed ({exc}); returning shape mesh"
                        print(f"[hunyuan3d] {note}")
                        _free_cuda()

            with open(final_path, "rb") as f:
                data = f.read()

        print(f"[hunyuan3d] GLB size: {len(data) / 1024:.1f} KB textured={textured_ok}")
        return {
            "success": True,
            "glb_base64": base64.b64encode(data).decode(),
            "textured": textured_ok,
            "note": note,
        }
    except Exception:
        _move_pipeline(_shape_pipeline, "cpu")
        _free_cuda()
        tb = traceback.format_exc()
        print(f"[hunyuan3d] /generate failed:\n{tb}")
        return {"success": False, "error": tb}


@app.post("/texture")
async def texture_mesh(req: TextureRequest):
    if _status != "online":
        raise HTTPException(503, detail=f"Model not ready ({_status})")
    if _PaintPipeline is None or _PaintConfig is None:
        return {"success": False, "error": "Hunyuan3D Paint pipeline is unavailable (custom_rasterizer not installed)"}
    try:
        from PIL import Image
        with _gpu_lock, tempfile.TemporaryDirectory() as tmpdir:
            mesh_raw = req.mesh_base64.split(",", 1)[1] if "," in req.mesh_base64 else req.mesh_base64
            mesh_path = os.path.join(tmpdir, "input.glb")
            with open(mesh_path, "wb") as f:
                f.write(base64.b64decode(mesh_raw))

            ref_path = os.path.join(tmpdir, "ref.png")
            if req.image_base64:
                img_raw = req.image_base64.split(",", 1)[1] if "," in req.image_base64 else req.image_base64
                Image.open(io.BytesIO(base64.b64decode(img_raw))).convert("RGBA").save(ref_path)
            else:
                Image.new("RGBA", (512, 512), (200, 200, 200, 255)).save(ref_path)

            _move_pipeline(_shape_pipeline, "cpu")
            _free_cuda()

            tex_obj_path = os.path.join(tmpdir, "textured.obj")
            tex_glb_path = tex_obj_path.replace(".obj", ".glb")
            conf = _build_paint_config(req.max_num_view, req.texture_resolution)
            paint_pipe = _PaintPipeline(conf)
            out_path = paint_pipe(
                mesh_path=mesh_path,
                image_path=ref_path,
                output_mesh_path=tex_obj_path,
                save_glb=True,
            )
            if not os.path.exists(tex_glb_path) and os.path.exists(tex_obj_path):
                _obj_to_glb_with_pbr(tex_obj_path, tex_glb_path)
            if os.path.exists(tex_glb_path):
                final_path = tex_glb_path
            elif out_path and out_path.endswith(".glb") and os.path.exists(out_path):
                final_path = out_path
            else:
                del paint_pipe
                _free_cuda()
                return {"success": False, "error": "PBR paint pipeline did not produce a GLB output"}
            del paint_pipe
            _free_cuda()

            with open(final_path, "rb") as f:
                data = f.read()

        return {"success": True, "glb_base64": base64.b64encode(data).decode(), "textured": True}
    except Exception:
        _free_cuda()
        tb = traceback.format_exc()
        print(f"[hunyuan3d] /texture failed:\n{tb}")
        return {"success": False, "error": tb}


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"[hunyuan3d] Starting on port {port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
