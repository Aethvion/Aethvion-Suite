"""
Specter Server — FastAPI backend for the Specter VTuber Engine (v2)
Standalone module, does not depend on Misaka Cipher chat/discord systems.
"""
import io
import json
import os
import sys
import uuid
import zipfile
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

# Add specter module dir and project root to sys.path
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(MODULE_DIR, "..", "..", ".."))
for p in (MODULE_DIR, PROJECT_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Literal

# Optional Misaka Cipher provider integration
try:
    from core.providers.provider_manager import ProviderManager
    pm = ProviderManager()
    HAS_PROVIDERS = True
except Exception:
    pm = None
    HAS_PROVIDERS = False

# Specter-local modules
from formats.specter_format import (
    SpecterFormat, SPECTER_VERSION, new_model, new_layer, new_bone,
    new_bone_param, new_physics_group, _migrate_v1_to_v2,
)
from rigging.auto_mesh import generate_mesh_for_layer
from rigging.auto_bones import suggest_bones, suggest_bone_params
from rigging.auto_weights import assign_weights, smooth_weights, normalize_weights
from pipelines.utils import remove_background

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Specter VTuber Engine", version="2.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
VIEWER_DIR = BASE_DIR / "viewer"
MODELS_DIR = BASE_DIR / "models"
SPECTER_DIR = BASE_DIR / "specter_files"   # .specter archives
MODELS_DIR.mkdir(exist_ok=True)
SPECTER_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Provider helpers
# ---------------------------------------------------------------------------

def _get_chat_provider(chat_model: Optional[str] = None):
    if not HAS_PROVIDERS or not pm:
        raise HTTPException(503, "AI providers not available. Check your .env configuration.")
    provider = pm.get_provider("google_ai") or pm.get_provider("openai")
    if not provider:
        raise HTTPException(503, "No chat provider available.")
    model_id = chat_model or provider.config.model
    return provider, model_id


def _get_image_provider(image_model: Optional[str] = None):
    if not HAS_PROVIDERS or not pm:
        raise HTTPException(503, "AI providers not available.")
    provider = pm.get_provider_for_capability("IMAGE") or pm.get_provider("openai") or pm.get_provider("google_ai")
    if not provider:
        raise HTTPException(503, "No image provider available.")
    model_id = image_model or "imagen-3.0-generate-002"
    return provider, model_id


# ---------------------------------------------------------------------------
# Provider / model info
# ---------------------------------------------------------------------------

@app.get("/api/providers")
async def get_providers():
    if not HAS_PROVIDERS or not pm:
        return JSONResponse({"chat_models": [], "image_models": [], "available": False})
    chat, image = [], []
    for model_id, info in pm.model_descriptor_map.items():
        caps = [c.upper() for c in info.get("capabilities", [])]
        entry = {"id": model_id, "provider": info.get("provider"), "description": info.get("description", "")}
        if "CHAT" in caps:
            chat.append(entry)
        if "IMAGE" in caps:
            image.append(entry)
    return JSONResponse({"chat_models": chat, "image_models": image, "available": True})


# ---------------------------------------------------------------------------
# Model listing & CRUD
# ---------------------------------------------------------------------------

@app.get("/api/models")
async def list_models():
    """List all saved .specter files and legacy model directories."""
    results = []

    # .specter archives
    for sf in SPECTER_DIR.glob("*.specter"):
        try:
            manifest_data = {}
            with zipfile.ZipFile(sf, "r") as zf:
                if "manifest.json" in zf.namelist():
                    manifest_data = json.loads(zf.read("manifest.json"))
            results.append({
                "id": sf.stem,
                "name": manifest_data.get("name", sf.stem),
                "format": "specter",
                "path": f"/specter-files/{sf.name}",
                "modified": manifest_data.get("modified", ""),
            })
        except Exception:
            pass

    # Legacy model directories
    for entry in MODELS_DIR.iterdir():
        if entry.is_dir():
            cfg = entry / "avatar.specter.json"
            if cfg.exists():
                try:
                    data = json.loads(cfg.read_text(encoding="utf-8"))
                    results.append({
                        "id": entry.name,
                        "name": data.get("name", entry.name),
                        "format": "legacy",
                        "path": f"/models/{entry.name}/avatar.specter.json",
                        "modified": "",
                    })
                except Exception:
                    pass

    return JSONResponse(results)


@app.get("/api/model/{model_id}")
async def get_model(model_id: str):
    """Return model JSON. Works for .specter archives and legacy dirs."""
    # Check .specter archive first
    sf = SPECTER_DIR / f"{model_id}.specter"
    if sf.exists():
        model = SpecterFormat.load_model_only(str(sf))
        return JSONResponse(model)

    # Legacy directory
    cfg = MODELS_DIR / model_id / "avatar.specter.json"
    if cfg.exists():
        data = json.loads(cfg.read_text(encoding="utf-8"))
        model = _migrate_v1_to_v2(data, model_id)
        return JSONResponse(model)

    raise HTTPException(404, f"Model '{model_id}' not found.")


@app.post("/api/model/new")
async def create_model(name: str = Form("Untitled")):
    """Create a new empty .specter model."""
    model_id = f"{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
    model = new_model(name)
    sf_path = SPECTER_DIR / f"{model_id}.specter"
    SpecterFormat.save(str(sf_path), model, {})
    return JSONResponse({"status": "success", "model_id": model_id, "model": model})


class SaveModelRequest(BaseModel):
    model: dict

@app.post("/api/model/{model_id}/save")
async def save_model(model_id: str, request: SaveModelRequest):
    """Save model data back to .specter file."""
    sf_path = SPECTER_DIR / f"{model_id}.specter"
    model = request.model
    if not model:
        raise HTTPException(400, "No model data provided.")

    if sf_path.exists():
        # Load existing textures and merge
        _, existing_textures = SpecterFormat.load(str(sf_path))
        SpecterFormat.save(str(sf_path), model, existing_textures)
    else:
        SpecterFormat.save(str(sf_path), model, {})

    return JSONResponse({"status": "success"})


@app.delete("/api/model/{model_id}")
async def delete_model(model_id: str):
    sf_path = SPECTER_DIR / f"{model_id}.specter"
    if sf_path.exists():
        sf_path.unlink()
        return JSONResponse({"status": "success"})

    model_dir = MODELS_DIR / model_id
    if model_dir.exists():
        import shutil
        shutil.rmtree(model_dir)
        return JSONResponse({"status": "success"})

    raise HTTPException(404, "Model not found.")


# ---------------------------------------------------------------------------
# Texture management
# ---------------------------------------------------------------------------

@app.get("/api/model/{model_id}/texture/{tex_path:path}")
async def get_texture(model_id: str, tex_path: str):
    """Serve a texture from a .specter archive or legacy directory."""
    sf_path = SPECTER_DIR / f"{model_id}.specter"
    if sf_path.exists():
        with zipfile.ZipFile(sf_path, "r") as zf:
            rel = f"textures/{tex_path}"
            if rel in zf.namelist():
                data = zf.read(rel)
                return Response(content=data, media_type="image/png",
                                headers={"Cache-Control": "no-cache"})
        raise HTTPException(404, "Texture not found in archive.")

    # Legacy path
    tex_file = MODELS_DIR / model_id / "textures" / tex_path
    if tex_file.exists():
        return FileResponse(str(tex_file))

    raise HTTPException(404, "Texture not found.")


@app.post("/api/model/{model_id}/add-layer")
async def add_layer(model_id: str, file: UploadFile = File(...),
                    layer_name: Optional[str] = Form(None)):
    """Upload an image and add it as a new layer to the model."""
    from PIL import Image

    data = await file.read()
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    w, h = img.size
    layer_n = layer_name or Path(file.filename).stem

    sf_path = SPECTER_DIR / f"{model_id}.specter"
    if not sf_path.exists():
        raise HTTPException(404, "Model not found.")

    model, textures = SpecterFormat.load(str(sf_path))

    tex_rel = f"textures/{uuid.uuid4().hex[:8]}.png"
    textures[tex_rel] = data

    layer = new_layer(layer_n, tex_rel, w, h,
                      model["canvas"]["width"], model["canvas"]["height"])
    model["layers"].append(layer)

    SpecterFormat.save(str(sf_path), model, textures)
    return JSONResponse({"status": "success", "layer": layer})


@app.post("/api/model/{model_id}/layer/{layer_id}/remove-bg")
async def remove_layer_bg(model_id: str, layer_id: str):
    """Remove background from a layer texture."""
    sf_path = SPECTER_DIR / f"{model_id}.specter"
    if not sf_path.exists():
        raise HTTPException(404, "Model not found.")

    model, textures = SpecterFormat.load(str(sf_path))
    layer = next((l for l in model["layers"] if l["id"] == layer_id), None)
    if not layer:
        raise HTTPException(404, "Layer not found.")

    tex_rel = layer["texture"]
    if tex_rel not in textures:
        raise HTTPException(404, "Texture data not found in archive.")

    raw_data = textures[tex_rel]

    # Save raw backup
    raw_rel = tex_rel.replace(".png", "_raw.png")
    textures[raw_rel] = raw_data
    if "original_texture" not in layer:
        layer["original_texture"] = tex_rel

    # Process
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_in:
        tmp_in.write(raw_data)
        tmp_in_path = tmp_in.name

    nobg_rel = tex_rel.replace(".png", "_nobg.png")
    tmp_out_path = tmp_in_path.replace(".png", "_nobg.png")

    try:
        remove_background(tmp_in_path, tmp_out_path)
        with open(tmp_out_path, "rb") as f:
            nobg_data = f.read()
        textures[nobg_rel] = nobg_data
        layer["texture"] = nobg_rel
    finally:
        Path(tmp_in_path).unlink(missing_ok=True)
        Path(tmp_out_path).unlink(missing_ok=True)

    SpecterFormat.save(str(sf_path), model, textures)
    return JSONResponse({"status": "success", "texture": nobg_rel})


@app.post("/api/model/{model_id}/layer/{layer_id}/restore-bg")
async def restore_layer_bg(model_id: str, layer_id: str):
    sf_path = SPECTER_DIR / f"{model_id}.specter"
    if not sf_path.exists():
        raise HTTPException(404, "Model not found.")

    model, textures = SpecterFormat.load(str(sf_path))
    layer = next((l for l in model["layers"] if l["id"] == layer_id), None)
    if not layer:
        raise HTTPException(404, "Layer not found.")

    orig = layer.pop("original_texture", None)
    if orig:
        layer["texture"] = orig

    SpecterFormat.save(str(sf_path), model, textures)
    return JSONResponse({"status": "success", "texture": layer["texture"]})


# ---------------------------------------------------------------------------
# Export / Import
# ---------------------------------------------------------------------------

@app.get("/api/model/{model_id}/export")
async def export_model(model_id: str):
    """Download the .specter file."""
    sf_path = SPECTER_DIR / f"{model_id}.specter"
    if sf_path.exists():
        return FileResponse(str(sf_path), media_type="application/octet-stream",
                            filename=f"{model_id}.specter")

    # Try to export from legacy directory
    model_dir = MODELS_DIR / model_id
    if model_dir.exists():
        out_path = SPECTER_DIR / f"{model_id}.specter"
        SpecterFormat.export_from_dir(str(model_dir), str(out_path))
        return FileResponse(str(out_path), media_type="application/octet-stream",
                            filename=f"{model_id}.specter")

    raise HTTPException(404, "Model not found.")


@app.post("/api/import")
async def import_model(file: UploadFile = File(...)):
    """Import an uploaded .specter file."""
    data = await file.read()
    name = Path(file.filename).stem
    model_id = f"{name}_{uuid.uuid4().hex[:6]}"
    sf_path = SPECTER_DIR / f"{model_id}.specter"
    sf_path.write_bytes(data)
    model = SpecterFormat.load_model_only(str(sf_path))
    return JSONResponse({"status": "success", "model_id": model_id, "model": model})


# ---------------------------------------------------------------------------
# AI Generation pipelines
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    prompt: str
    image_model: Optional[str] = None
    chat_model: Optional[str] = None
    pipeline: Literal["simple", "sheet", "local"] = "sheet"


@app.post("/api/generate/concept")
async def generate_concept(req: GenerateRequest):
    """Generate a character concept image."""
    uid = uuid.uuid4().hex[:8]
    model_name = f"concept_{uid}"
    output_dir = MODELS_DIR / model_name
    output_dir.mkdir(exist_ok=True)
    concept_path = output_dir / "concept.png"

    try:
        if req.pipeline == "local":
            provider, model_id = _get_chat_provider(req.chat_model)
            from pipelines.local_pipeline import LocalPipeline
            local_url = os.getenv("LOCAL_SD_URL", "http://127.0.0.1:7860")
            pip = LocalPipeline(provider, model_id, backend="a1111", base_url=local_url)
            if not pip.check_connection():
                raise HTTPException(503, f"Local SD not reachable at {local_url}")
            pip.generate_concept(req.prompt, str(concept_path))
        else:
            image_provider, image_model = _get_image_provider(req.image_model)
            chat_provider, chat_model = _get_chat_provider(req.chat_model)
            from pipelines.sheet_pipeline import SheetPipeline
            pip = SheetPipeline(chat_provider, image_provider, chat_model, image_model)
            pip.generate_concept(req.prompt, str(concept_path))

        return JSONResponse({
            "status": "success",
            "concept_id": model_name,
            "concept_url": f"/models/{model_name}/concept.png",
            "pipeline": req.pipeline,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


class RigConceptRequest(BaseModel):
    concept_id: str
    pipeline: Literal["simple", "sheet", "local"] = "sheet"
    chat_model: Optional[str] = None
    instructions: Optional[str] = None
    mesh_density: Literal["low", "medium", "high", "ai"] = "medium"
    bone_style: Literal["humanoid", "minimal", "custom"] = "humanoid"
    auto_weights: bool = True


@app.post("/api/generate/rig")
async def generate_rig(req: RigConceptRequest):
    """Convert a concept image into a fully rigged .specter model."""
    concept_dir = MODELS_DIR / req.concept_id
    concept_path = concept_dir / "concept.png"

    if not concept_path.exists():
        raise HTTPException(404, "Concept image not found.")

    try:
        provider, model_id = _get_chat_provider(req.chat_model)

        # Run pipeline to get layers
        if req.pipeline == "sheet":
            image_provider, image_model = _get_image_provider()
            from pipelines.sheet_pipeline import SheetPipeline
            pip = SheetPipeline(provider, image_provider, model_id, image_model)
            rig_path = pip.generate_rig_from_sheet(
                str(concept_path), str(concept_dir), req.concept_id, req.instructions)
        elif req.pipeline == "local":
            local_url = os.getenv("LOCAL_SD_URL", "http://127.0.0.1:7860")
            from pipelines.local_pipeline import LocalPipeline
            pip = LocalPipeline(provider, model_id, backend="a1111", base_url=local_url)
            rig_path = pip.generate_rig_from_concept(
                str(concept_path), str(concept_dir), req.concept_id, req.instructions)
        else:
            from pipelines.simple_pipeline import SimplePipeline
            pip = SimplePipeline(provider, model_id)
            rig_path = pip.generate_rig_from_image(
                str(concept_path), str(concept_dir), req.concept_id, req.instructions)

        # Upgrade to v2 and create .specter archive
        legacy_cfg = json.loads(Path(rig_path).read_text(encoding="utf-8"))
        model = _migrate_v1_to_v2(legacy_cfg, req.concept_id)

        # Generate better meshes
        for layer in model["layers"]:
            layer["mesh"] = generate_mesh_for_layer(
                layer, provider if req.mesh_density == "ai" else None,
                model_id, req.mesh_density)

        # Generate bones
        model["bones"] = suggest_bones(model["layers"], provider, model_id, req.bone_style)
        model["bone_params"] = suggest_bone_params(model["bones"], model["parameters"], provider, model_id)

        # Generate weights
        if req.auto_weights and model["bones"]:
            raw_weights = assign_weights(model["layers"], model["bones"])
            model["weights"] = smooth_weights(raw_weights, {l["id"]: l for l in model["layers"]})

        # Pack into .specter archive
        textures: dict[str, bytes] = {}
        tex_dir = concept_dir / "textures"
        if tex_dir.exists():
            for png in tex_dir.glob("*.png"):
                textures[f"textures/{png.name}"] = png.read_bytes()

        new_id = req.concept_id
        sf_path = SPECTER_DIR / f"{new_id}.specter"
        SpecterFormat.save(str(sf_path), model, textures)

        return JSONResponse({"status": "success", "model_id": new_id, "model": model})

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/generate/from-upload")
async def generate_from_upload(
    file: UploadFile = File(...),
    chat_model: Optional[str] = Form(None),
    instructions: Optional[str] = Form(None),
    mesh_density: str = Form("medium"),
    bone_style: str = Form("humanoid"),
):
    """Upload an image and auto-rig it into a .specter model."""
    uid = uuid.uuid4().hex[:8]
    model_id = f"upload_{Path(file.filename).stem}_{uid}"
    model_dir = MODELS_DIR / model_id
    model_dir.mkdir(exist_ok=True)

    upload_path = model_dir / "upload.png"
    data = await file.read()
    upload_path.write_bytes(data)

    try:
        provider, mid = _get_chat_provider(chat_model)
        from pipelines.simple_pipeline import SimplePipeline
        pip = SimplePipeline(provider, mid)
        rig_path = pip.generate_rig_from_image(str(upload_path), str(model_dir), model_id, instructions)

        legacy_cfg = json.loads(Path(rig_path).read_text(encoding="utf-8"))
        model = _migrate_v1_to_v2(legacy_cfg, model_id)

        for layer in model["layers"]:
            layer["mesh"] = generate_mesh_for_layer(layer, density=mesh_density)

        model["bones"] = suggest_bones(model["layers"], provider, mid, bone_style)
        model["bone_params"] = suggest_bone_params(model["bones"], model["parameters"], provider, mid)

        raw_weights = assign_weights(model["layers"], model["bones"])
        model["weights"] = smooth_weights(raw_weights, {l["id"]: l for l in model["layers"]})

        textures: dict[str, bytes] = {}
        tex_dir = model_dir / "textures"
        if tex_dir.exists():
            for png in tex_dir.glob("*.png"):
                textures[f"textures/{png.name}"] = png.read_bytes()

        sf_path = SPECTER_DIR / f"{model_id}.specter"
        SpecterFormat.save(str(sf_path), model, textures)

        return JSONResponse({"status": "success", "model_id": model_id, "model": model})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# AI Rigging helpers (called from editor)
# ---------------------------------------------------------------------------

class AutoMeshRequest(BaseModel):
    model_id: str
    layer_id: str
    density: Literal["low", "medium", "high", "ai"] = "medium"
    chat_model: Optional[str] = None


@app.post("/api/rig/auto-mesh")
async def auto_mesh(req: AutoMeshRequest):
    sf_path = SPECTER_DIR / f"{req.model_id}.specter"
    if not sf_path.exists():
        raise HTTPException(404, "Model not found.")

    model, textures = SpecterFormat.load(str(sf_path))
    layer = next((l for l in model["layers"] if l["id"] == req.layer_id), None)
    if not layer:
        raise HTTPException(404, "Layer not found.")

    provider, mid = (None, None)
    if req.density == "ai":
        provider, mid = _get_chat_provider(req.chat_model)

    layer["mesh"] = generate_mesh_for_layer(layer, provider, mid or "", req.density)
    SpecterFormat.save(str(sf_path), model, textures)
    return JSONResponse({"status": "success", "mesh": layer["mesh"]})


class AutoBonesRequest(BaseModel):
    model_id: str
    style: Literal["humanoid", "minimal", "custom"] = "humanoid"
    chat_model: Optional[str] = None


@app.post("/api/rig/auto-bones")
async def auto_bones_endpoint(req: AutoBonesRequest):
    sf_path = SPECTER_DIR / f"{req.model_id}.specter"
    if not sf_path.exists():
        raise HTTPException(404, "Model not found.")

    model, textures = SpecterFormat.load(str(sf_path))

    provider, mid = (None, "")
    if req.style == "custom":
        provider, mid = _get_chat_provider(req.chat_model)

    bones = suggest_bones(model["layers"], provider, mid, req.style)
    bone_params = suggest_bone_params(bones, model["parameters"], provider, mid)
    model["bones"] = bones
    model["bone_params"] = bone_params
    SpecterFormat.save(str(sf_path), model, textures)
    return JSONResponse({"status": "success", "bones": bones, "bone_params": bone_params})


class AutoWeightsRequest(BaseModel):
    model_id: str
    smooth: bool = True


@app.post("/api/rig/auto-weights")
async def auto_weights_endpoint(req: AutoWeightsRequest):
    sf_path = SPECTER_DIR / f"{req.model_id}.specter"
    if not sf_path.exists():
        raise HTTPException(404, "Model not found.")

    model, textures = SpecterFormat.load(str(sf_path))
    if not model.get("bones"):
        raise HTTPException(400, "No bones defined. Add bones before auto-weighting.")

    raw = assign_weights(model["layers"], model["bones"])
    if req.smooth:
        weights = smooth_weights(raw, {l["id"]: l for l in model["layers"]})
    else:
        weights = normalize_weights(raw)

    model["weights"] = weights
    SpecterFormat.save(str(sf_path), model, textures)
    return JSONResponse({"status": "success", "weights": weights})


class AutoRigAllRequest(BaseModel):
    model_id: str
    mesh_density: Literal["low", "medium", "high", "ai"] = "medium"
    bone_style: Literal["humanoid", "minimal", "custom"] = "humanoid"
    chat_model: Optional[str] = None


@app.post("/api/rig/auto-all")
async def auto_rig_all(req: AutoRigAllRequest):
    """One-click: generate meshes, bones, bone_params, and weights."""
    sf_path = SPECTER_DIR / f"{req.model_id}.specter"
    if not sf_path.exists():
        raise HTTPException(404, "Model not found.")

    model, textures = SpecterFormat.load(str(sf_path))

    provider, mid = (None, "")
    if req.mesh_density == "ai" or req.bone_style == "custom":
        provider, mid = _get_chat_provider(req.chat_model)

    for layer in model["layers"]:
        layer["mesh"] = generate_mesh_for_layer(layer, provider, mid, req.mesh_density)

    model["bones"] = suggest_bones(model["layers"], provider, mid, req.bone_style)
    model["bone_params"] = suggest_bone_params(model["bones"], model["parameters"], provider, mid)

    raw = assign_weights(model["layers"], model["bones"])
    model["weights"] = smooth_weights(raw, {l["id"]: l for l in model["layers"]})

    SpecterFormat.save(str(sf_path), model, textures)
    return JSONResponse({
        "status": "success",
        "layers": model["layers"],
        "bones": model["bones"],
        "bone_params": model["bone_params"],
        "weights": model["weights"],
    })


# ---------------------------------------------------------------------------
# Legacy v1 support
# ---------------------------------------------------------------------------

@app.post("/api/legacy/upload-and-rig")
async def legacy_upload(
    file: UploadFile = File(...),
    chat_model: Optional[str] = Form(None),
    instructions: Optional[str] = Form(None),
):
    """Legacy simple-pipeline upload, wraps result in .specter."""
    return await generate_from_upload(file, chat_model, instructions)


@app.get("/api/legacy/models")
async def legacy_list():
    """Legacy model listing (returns paths compatible with old viewer)."""
    results = []
    for entry in MODELS_DIR.iterdir():
        if entry.is_dir():
            cfg = entry / "avatar.specter.json"
            if cfg.exists():
                results.append({
                    "id": entry.name,
                    "path": f"/models/{entry.name}/avatar.specter.json",
                })
    return JSONResponse(results)


# ---------------------------------------------------------------------------
# Static files and root
# ---------------------------------------------------------------------------

app.mount("/viewer", StaticFiles(directory=str(VIEWER_DIR)), name="viewer")
app.mount("/models", StaticFiles(directory=str(MODELS_DIR)), name="models")
app.mount("/specter-files", StaticFiles(directory=str(SPECTER_DIR)), name="specter-files")


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse({"ok": True})


@app.get("/", response_class=HTMLResponse)
async def index():
    idx = VIEWER_DIR / "index.html"
    return idx.read_text(encoding="utf-8")


@app.get("/docs", response_class=HTMLResponse)
async def docs_page():
    """Serve the Specter documentation page (open alongside the editor)."""
    docs_path = VIEWER_DIR / "docs.html"
    return docs_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

def launch():
    from core.utils.port_manager import PortManager
    base_port = int(os.getenv("SPECTER_PORT", "8081"))
    port = PortManager.bind_port("Specter Engine", base_port)
    
    print(f"🎭 Specter VTuber Engine v{SPECTER_VERSION} → http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    launch()
