"""
Aethvion Suite - Companion Creator Routes
API endpoints for creating, listing, editing, exporting, and importing companions.

Custom companions are stored in data/companions/<id>/config.json.
Built-in companions (axiom, lyra) can have their personality overridden here.
Registry is hot-reloaded after every mutation — no server restart required.
"""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.utils import get_logger, utcnow_iso, atomic_json_write
from core.utils.paths import COMPANIONS
from core.companions.registry import CompanionRegistry

logger = get_logger(__name__)
router = APIRouter(prefix="/api/companion-creator", tags=["companion-creator"])

_CUSTOM_DIR = COMPANIONS
_CUSTOM_DIR.mkdir(parents=True, exist_ok=True)

# Built-in companions managed by core/companions/configs/ — view-only, not editable
# Actual companion IDs (as in config "id" field, not filenames)
_BUILTIN_IDS = {"misakacipher", "axiom", "lyra"}
_CORE_CONFIG_DIR = Path(__file__).parent / "configs"

_ALLOWED_ICON_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_MAX_ICON_BYTES    = 2 * 1024 * 1024   # 2 MB


# ── Schema ─────────────────────────────────────────────────────────────────────

class BehaviorConfig(BaseModel):
    temperature: float = 0.85
    initiate_temperature: float = 0.80
    change_susceptibility: float = 0.70
    default_mood: str = "calm"


class CapabilitiesConfig(BaseModel):
    tools_enabled: bool = False
    workspace_access: bool = False
    memory_updates_enabled: bool = True
    internet_search: bool = False


class PromptsConfig(BaseModel):
    chat_system: str = ""
    initiate_system: str = ""


class CompanionCreateRequest(BaseModel):
    name: str
    description: str
    personality: str
    speech_style: str = ""
    quirks: list[str] = []
    likes: list[str] = []
    dislikes: list[str] = []
    default_model: str = "gemini-1.5-flash"
    accent_color: str = "#6366f1"
    avatar_symbol: str = "✦"
    default_expression: str = "default"
    expressions: list[str] = []
    moods: list[str] = []
    icon_mode: bool = False
    behavior: BehaviorConfig = BehaviorConfig()
    capabilities: CapabilitiesConfig = CapabilitiesConfig()
    prompts: PromptsConfig = PromptsConfig()


class CompanionUpdateRequest(CompanionCreateRequest):
    pass


class BuiltinUpdateRequest(BaseModel):
    """Only personality fields can be changed for built-in companions."""
    personality: str
    speech_style: str = ""
    quirks: list[str] = []
    likes: list[str] = []
    dislikes: list[str] = []
    accent_color: str = ""
    avatar_symbol: str = ""
    behavior: BehaviorConfig = BehaviorConfig()
    capabilities: CapabilitiesConfig = CapabilitiesConfig()
    prompts: PromptsConfig = PromptsConfig()


class ImportRequest(BaseModel):
    config: dict  # full exported companion config


# ── Helpers ────────────────────────────────────────────────────────────────────

_SAFE_ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def _validate_companion_id(companion_id: str) -> None:
    if not _SAFE_ID_RE.match(companion_id):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid companion ID {companion_id!r}. "
                "IDs must contain only lowercase letters, digits, and underscores."
            ),
        )




def _slug(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "companion"


def _augment_icon_status(data: dict, companion_dir: Path) -> dict:
    """Ensure has_icon reflects the actual file on disk (repairs missing flag)."""
    if not data.get("has_icon"):
        icon = _find_icon(companion_dir)
        if icon:
            data["has_icon"] = True
    return data


def _get_last_ts(companion_dir: Path) -> str | None:
    """Return the timestamp string of the most recent chat message, or None."""
    history_dir = companion_dir / "history"
    if not history_dir.exists():
        return None
    # glob across all month subdirs, pick the newest file
    files = sorted(history_dir.glob("**/chat_*.json"), reverse=True)
    if not files:
        return None
    try:
        msgs = json.loads(files[0].read_text(encoding="utf-8"))
        for m in reversed(msgs):
            ts = m.get("timestamp")
            if ts:
                return ts
    except Exception:
        pass
    return None


def _list_custom_companions() -> list[dict]:
    configs = []
    for config_file in sorted(_CUSTOM_DIR.glob("*/config.json")):
        try:
            data = json.loads(config_file.read_text(encoding="utf-8"))
            # Skip built-ins that may have override configs in the data dir
            if data.get("id") not in _BUILTIN_IDS:
                _augment_icon_status(data, config_file.parent)
                data["last_interaction_ts"] = _get_last_ts(config_file.parent)
                configs.append(data)
        except Exception as e:
            logger.warning(f"Could not read {config_file}: {e}")
    return configs


def _list_builtin_companions() -> list[dict]:
    """Return built-in companion configs (data/ override takes priority).
    Uses the companion's actual id (from the JSON 'id' field) to locate the
    data-dir override — avoids the misaka_cipher vs misakacipher slug mismatch.
    """
    builtins = []
    for filename in ("axiom", "lyra", "misaka_cipher"):
        core = _CORE_CONFIG_DIR / f"{filename}.json"
        if not core.exists():
            continue
        try:
            # Read core config to get the canonical id (e.g. "misakacipher")
            core_data = json.loads(core.read_text(encoding="utf-8"))
            cid = core_data.get("id", filename)
            # Data-dir override uses the canonical id, not the filename slug
            override = _CUSTOM_DIR / cid / "config.json"
            if override.exists():
                data = json.loads(override.read_text(encoding="utf-8"))
            else:
                data = core_data
            data["_builtin"] = True
            _augment_icon_status(data, _CUSTOM_DIR / cid)
            data["last_interaction_ts"] = _get_last_ts(_CUSTOM_DIR / cid)
            builtins.append(data)
        except Exception as e:
            logger.warning(f"Could not read builtin config {filename}: {e}")
    return builtins


def _load_config(companion_id: str) -> dict:
    _validate_companion_id(companion_id)
    # Check data dir first, then core configs
    data_path = _CUSTOM_DIR / companion_id / "config.json"
    core_path = _CORE_CONFIG_DIR / f"{companion_id}.json"
    if data_path.exists():
        return json.loads(data_path.read_text(encoding="utf-8"))
    if core_path.exists():
        return json.loads(core_path.read_text(encoding="utf-8"))
    # Scan core configs by internal "id" field — handles cases where filename ≠ id
    # (e.g. misaka_cipher.json has id="misakacipher")
    if _CORE_CONFIG_DIR.exists():
        for cfg_file in _CORE_CONFIG_DIR.glob("*.json"):
            try:
                data = json.loads(cfg_file.read_text(encoding="utf-8"))
                if data.get("id") == companion_id:
                    return data
            except Exception:
                pass
    raise HTTPException(status_code=404, detail=f"Companion '{companion_id}' not found")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/all")
async def list_all_companions():
    """Return all companions: built-ins first, then custom."""
    builtins = _list_builtin_companions()
    custom = _list_custom_companions()
    return {"companions": builtins + custom}


@router.get("/list")
async def list_companions():
    """Return only custom companion configs (backward-compatible)."""
    return {"companions": _list_custom_companions()}


@router.get("/export/{companion_id}")
async def export_companion(companion_id: str):
    """Return an exportable (shareable) copy of a companion config."""
    config = _load_config(companion_id)
    if companion_id in _BUILTIN_IDS:
        raise HTTPException(status_code=403, detail="Built-in companions cannot be exported.")
    # Strip internal/server-specific fields before export
    exportable = {k: v for k, v in config.items() if k not in ("route_prefix", "call_source", "prefs_key")}
    exportable["_exported_from"] = "Aethvion Suite"
    exportable["_export_date"] = datetime.now().strftime("%Y-%m-%d")
    return exportable


@router.post("/import")
async def import_companion(req: ImportRequest):
    """Import a shared companion config. Generates a fresh ID to avoid collisions."""
    data = req.config
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="Imported config must include a 'name' field.")

    base_slug = _slug(data["name"])
    companion_id = base_slug

    # Always generate a fresh ID for imports to avoid collisions
    if companion_id in _BUILTIN_IDS or (_CUSTOM_DIR / companion_id).exists():
        companion_id = f"{base_slug}_{uuid.uuid4().hex[:4]}"

    companion_dir = _CUSTOM_DIR / companion_id
    companion_dir.mkdir(parents=True, exist_ok=True)
    (companion_dir / "history").mkdir(exist_ok=True)

    config = {
        "id":            companion_id,
        "name":          data.get("name", "Imported Companion"),
        "description":   data.get("description", ""),
        "personality":   data.get("personality", ""),
        "speech_style":  data.get("speech_style", ""),
        "quirks":        data.get("quirks", []),
        "likes":         data.get("likes", []),
        "dislikes":      data.get("dislikes", []),
        "default_model": data.get("default_model", "gemini-1.5-flash"),
        "accent_color":  data.get("accent_color", "#6366f1"),
        "avatar_symbol": data.get("avatar_symbol", "✦"),
        "expressions":   data.get("expressions", ["default", "happy", "thinking", "focused", "error"]),
        "moods":         data.get("moods", ["calm", "happy", "reflective"]),
        "route_prefix":  f"/api/custom/{companion_id}",
        "type":          "custom",
        "_imported": True,
    }
    atomic_json_write(companion_dir / "config.json", config)
    atomic_json_write(companion_dir / "base_info.json", {
        "name":          config["name"],
        "core_identity": config["description"],
        "personality":   config["personality"],
        "speech_style":  config["speech_style"],
        "quirks":        config["quirks"],
        "likes":         config["likes"],
        "dislikes":      config["dislikes"],
        "autonomy_level": "Medium",
    })
    atomic_json_write(companion_dir / "memory.json", {
        "user_info": {},
        "recent_observations": [],
        "synthesis_notes": [],
        "last_updated": utcnow_iso(),
    })

    CompanionRegistry.force_reload()
    logger.info(f"Companion imported: {companion_id} ({config['name']})")
    return {"success": True, "id": companion_id, "name": config["name"],
            "message": f"'{config['name']}' imported successfully."}


@router.put("/builtin/{companion_id}")
async def update_builtin_companion(companion_id: str, req: BuiltinUpdateRequest):
    """Deprecated — use PUT /{companion_id} instead. Built-in edits are now supported there."""
    raise HTTPException(
        status_code=410,
        detail="Use PUT /api/companion-creator/{id} to edit any companion, including built-ins.",
    )


# ── Icon endpoints (must come before /{companion_id} catch-all) ───────────────

def _find_icon(companion_dir: Path) -> Path | None:
    """Return the icon file path if one exists, else None."""
    for ext in _ALLOWED_ICON_EXTS:
        p = companion_dir / f"icon{ext}"
        if p.exists():
            return p
    return None


@router.get("/{companion_id}/icon")
async def get_companion_icon(companion_id: str):
    """Serve the companion's icon image, or 404 if none uploaded."""
    _validate_companion_id(companion_id)
    companion_dir = _CUSTOM_DIR / companion_id
    icon = _find_icon(companion_dir)
    if not icon:
        raise HTTPException(status_code=404, detail="No icon found for this companion.")
    return FileResponse(str(icon))


@router.post("/{companion_id}/icon")
async def upload_companion_icon(companion_id: str, file: UploadFile = File(...)):
    """Upload or replace a companion's icon image (PNG/JPG/GIF/WebP, max 2 MB)."""
    _validate_companion_id(companion_id)
    companion_dir = _CUSTOM_DIR / companion_id
    # Built-ins: create override dir on first write; custom: must already exist
    if not companion_dir.exists():
        if companion_id in _BUILTIN_IDS:
            companion_dir.mkdir(parents=True, exist_ok=True)
        else:
            raise HTTPException(status_code=404, detail=f"Companion '{companion_id}' not found.")

    suffix = Path(file.filename or "").suffix.lower() or ".png"
    if suffix not in _ALLOWED_ICON_EXTS:
        raise HTTPException(status_code=400,
            detail=f"Unsupported image type '{suffix}'. Use: PNG, JPG, GIF or WebP.")

    data = await file.read()
    if len(data) > _MAX_ICON_BYTES:
        raise HTTPException(status_code=400, detail="Icon too large — maximum is 2 MB.")

    # Remove any existing icon before writing the new one
    for ext in _ALLOWED_ICON_EXTS:
        old = companion_dir / f"icon{ext}"
        if old.exists():
            old.unlink()

    icon_path = companion_dir / f"icon{suffix}"
    icon_path.write_bytes(data)

    # Record in config so list endpoints can expose has_icon without a file scan
    config_path = companion_dir / "config.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        # Built-in without an override yet — seed from base config
        try:
            cfg = _load_config(companion_id)
        except Exception:
            cfg = {}
    cfg["has_icon"] = True
    cfg["icon_ext"] = suffix
    atomic_json_write(config_path, cfg)

    CompanionRegistry.force_reload()
    logger.info(f"[CompanionCreator] Icon uploaded for {companion_id} ({suffix}, {len(data)} bytes)")
    return {"success": True, "icon_url": f"/api/companion-creator/{companion_id}/icon"}


@router.delete("/{companion_id}/icon")
async def delete_companion_icon(companion_id: str):
    """Remove a companion's icon image."""
    _validate_companion_id(companion_id)
    companion_dir = _CUSTOM_DIR / companion_id
    removed = False
    for ext in _ALLOWED_ICON_EXTS:
        p = companion_dir / f"icon{ext}"
        if p.exists():
            p.unlink()
            removed = True

    config_path = companion_dir / "config.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        cfg.pop("has_icon", None)
        cfg.pop("icon_ext",  None)
        atomic_json_write(config_path, cfg)

    CompanionRegistry.force_reload()
    return {"success": True, "removed": removed}


# ── Expression image endpoints ────────────────────────────────────────────────

_SAFE_EXPR_RE = re.compile(r"^[a-z0-9_]{1,32}$")
_MAX_EXPR_BYTES = 5 * 1024 * 1024   # 5 MB


def _validate_expression_name(name: str) -> None:
    if not _SAFE_EXPR_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid expression name {name!r}. Use only lowercase letters, digits, and underscores.",
        )


def _find_expression_image(companion_dir: Path, expression: str) -> Path | None:
    """Return the expression image path if one exists, else None."""
    for ext in _ALLOWED_ICON_EXTS:
        p = companion_dir / "expressions" / f"{expression}{ext}"
        if p.exists():
            return p
    return None


@router.get("/{companion_id}/expression/{expression_name}")
async def get_expression_image(companion_id: str, expression_name: str):
    """Serve a companion expression image."""
    _validate_companion_id(companion_id)
    _validate_expression_name(expression_name)
    img = _find_expression_image(_CUSTOM_DIR / companion_id, expression_name)
    if not img:
        raise HTTPException(status_code=404, detail="No image for this expression.")
    return FileResponse(str(img))


@router.post("/{companion_id}/expression/{expression_name}")
async def upload_expression_image(companion_id: str, expression_name: str, file: UploadFile = File(...)):
    """Upload or replace an expression image (PNG/JPG/GIF/WebP, max 5 MB)."""
    _validate_companion_id(companion_id)
    _validate_expression_name(expression_name)

    companion_dir = _CUSTOM_DIR / companion_id
    companion_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "").suffix.lower() or ".png"
    if suffix not in _ALLOWED_ICON_EXTS:
        raise HTTPException(status_code=400,
            detail=f"Unsupported image type '{suffix}'. Use: PNG, JPG, GIF or WebP.")

    data = await file.read()
    if len(data) > _MAX_EXPR_BYTES:
        raise HTTPException(status_code=400, detail="Image too large — maximum is 5 MB.")

    expr_dir = companion_dir / "expressions"
    expr_dir.mkdir(exist_ok=True)

    # Remove any existing image for this expression name
    for ext in _ALLOWED_ICON_EXTS:
        old = expr_dir / f"{expression_name}{ext}"
        if old.exists():
            old.unlink()

    (expr_dir / f"{expression_name}{suffix}").write_bytes(data)

    # Record in config
    config_path = companion_dir / "config.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        try:
            cfg = _load_config(companion_id)
        except Exception:
            cfg = {}
    cfg.setdefault("expression_images", {})[expression_name] = suffix
    cfg["icon_mode"] = True
    atomic_json_write(config_path, cfg)

    CompanionRegistry.force_reload()
    logger.info(f"[CompanionCreator] Expression image uploaded: {companion_id}/{expression_name}{suffix}")
    return {"success": True, "expression": expression_name, "ext": suffix}


@router.delete("/{companion_id}/expression/{expression_name}")
async def delete_expression_image(companion_id: str, expression_name: str):
    """Delete a companion expression image."""
    _validate_companion_id(companion_id)
    _validate_expression_name(expression_name)

    companion_dir = _CUSTOM_DIR / companion_id
    expr_dir = companion_dir / "expressions"
    removed = False
    for ext in _ALLOWED_ICON_EXTS:
        p = expr_dir / f"{expression_name}{ext}"
        if p.exists():
            p.unlink()
            removed = True

    config_path = companion_dir / "config.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        cfg.get("expression_images", {}).pop(expression_name, None)
        atomic_json_write(config_path, cfg)

    CompanionRegistry.force_reload()
    return {"success": True, "removed": removed}


@router.get("/{companion_id}/memory")
async def get_companion_memory(companion_id: str):
    """Return the base_info.json and memory.json for a companion."""
    _validate_companion_id(companion_id)
    companion_dir = _CUSTOM_DIR / companion_id
    if not companion_dir.exists():
        raise HTTPException(status_code=404, detail=f"Companion '{companion_id}' not found in data dir.")

    base_info_path = companion_dir / "base_info.json"
    memory_path    = companion_dir / "memory.json"

    base_info = {}
    if base_info_path.exists():
        with open(base_info_path, "r", encoding="utf-8") as f:
            base_info = json.load(f)

    memory = {}
    if memory_path.exists():
        with open(memory_path, "r", encoding="utf-8") as f:
            memory = json.load(f)

    return {"base_info": base_info, "memory": memory}


@router.get("/{companion_id}")
async def get_companion(companion_id: str):
    """Return a single companion config."""
    return _load_config(companion_id)


@router.post("/create")
async def create_companion(req: CompanionCreateRequest):
    """Create a new custom companion. Active immediately — no restart needed."""
    base_slug = _slug(req.name)
    companion_id = base_slug

    if companion_id in _BUILTIN_IDS or (_CUSTOM_DIR / companion_id).exists():
        companion_id = f"{base_slug}_{uuid.uuid4().hex[:4]}"

    companion_dir = _CUSTOM_DIR / companion_id
    companion_dir.mkdir(parents=True, exist_ok=True)
    (companion_dir / "history").mkdir(exist_ok=True)

    expressions = req.expressions or ["default", "happy", "thinking", "focused", "error"]
    moods       = req.moods       or ["calm", "happy", "reflective", "intense"]

    config = {
        "id":               companion_id,
        "name":             req.name,
        "description":      req.description,
        "personality":      req.personality,
        "speech_style":     req.speech_style,
        "quirks":           req.quirks,
        "likes":            req.likes,
        "dislikes":         req.dislikes,
        "default_model":    req.default_model,
        "accent_color":     req.accent_color,
        "avatar_symbol":    req.avatar_symbol,
        "default_expression": req.default_expression,
        "expressions":      expressions,
        "moods":            moods,
        "behavior": {
            "temperature":           req.behavior.temperature,
            "initiate_temperature":  req.behavior.initiate_temperature,
            "change_susceptibility": req.behavior.change_susceptibility,
            "default_mood":          req.behavior.default_mood,
        },
        "capabilities": {
            "tools_enabled":          req.capabilities.tools_enabled,
            "workspace_access":       req.capabilities.workspace_access,
            "memory_updates_enabled": req.capabilities.memory_updates_enabled,
            "internet_search":        req.capabilities.internet_search,
        },
        "prompts": {
            "chat_system":    req.prompts.chat_system,
            "initiate_system": req.prompts.initiate_system,
        },
        "route_prefix":  f"/api/custom/{companion_id}",
        "type":          "custom",
        "icon_mode":     req.icon_mode,
    }

    atomic_json_write(companion_dir / "config.json", config)
    atomic_json_write(companion_dir / "base_info.json", {
        "name":          req.name,
        "core_identity": req.description,
        "personality":   req.personality,
        "speech_style":  req.speech_style,
        "quirks":        req.quirks,
        "likes":         req.likes,
        "dislikes":      req.dislikes,
        "autonomy_level": "Medium",
    })
    atomic_json_write(companion_dir / "memory.json", {
        "user_info": {},
        "recent_observations": [],
        "synthesis_notes": [],
        "last_updated": utcnow_iso(),
    })

    CompanionRegistry.force_reload()
    logger.info(f"Custom companion created: {companion_id} ({req.name})")
    return {
        "success": True,
        "id":      companion_id,
        "name":    req.name,
        "message": f"Companion '{req.name}' created successfully.",
    }


@router.put("/{companion_id}")
async def update_companion(companion_id: str, req: CompanionUpdateRequest):
    """Update a companion's config. Built-in edits are stored as data-dir overrides."""
    existing = _load_config(companion_id)
    companion_dir = _CUSTOM_DIR / companion_id
    companion_dir.mkdir(parents=True, exist_ok=True)   # creates override dir for built-ins

    expressions = req.expressions or existing.get("expressions", ["default", "happy", "thinking"])
    moods       = req.moods       or existing.get("moods", ["calm", "happy", "reflective"])

    config = {
        **existing,
        "name":             req.name,
        "description":      req.description,
        "personality":      req.personality,
        "speech_style":     req.speech_style,
        "quirks":           req.quirks,
        "likes":            req.likes,
        "dislikes":         req.dislikes,
        "default_model":    req.default_model,
        "accent_color":     req.accent_color,
        "avatar_symbol":    req.avatar_symbol,
        "default_expression": req.default_expression,
        "expressions":      expressions,
        "moods":            moods,
        "behavior": {
            "temperature":           req.behavior.temperature,
            "initiate_temperature":  req.behavior.initiate_temperature,
            "change_susceptibility": req.behavior.change_susceptibility,
            "default_mood":          req.behavior.default_mood,
        },
        "capabilities": {
            "tools_enabled":          req.capabilities.tools_enabled,
            "workspace_access":       req.capabilities.workspace_access,
            "memory_updates_enabled": req.capabilities.memory_updates_enabled,
            "internet_search":        req.capabilities.internet_search,
        },
        "prompts": {
            "chat_system":    req.prompts.chat_system,
            "initiate_system": req.prompts.initiate_system,
        },
        # icon_mode from the form; expression_images preserved via **existing spread above
        "icon_mode": req.icon_mode,
    }
    atomic_json_write(companion_dir / "config.json", config)

    base_info_path = companion_dir / "base_info.json"
    base_info = json.loads(base_info_path.read_text(encoding="utf-8")) if base_info_path.exists() else {}
    base_info.update({
        "name":          req.name,
        "core_identity": req.description,
        "personality":   req.personality,
        "speech_style":  req.speech_style,
        "quirks":        req.quirks,
        "likes":         req.likes,
        "dislikes":      req.dislikes,
    })
    atomic_json_write(base_info_path, base_info)

    CompanionRegistry.force_reload()
    return {"success": True, "id": companion_id, "message": f"'{req.name}' updated successfully."}


@router.delete("/{companion_id}")
async def delete_companion(companion_id: str):
    """Delete a custom companion (cannot delete built-ins)."""
    _validate_companion_id(companion_id)
    if companion_id in _BUILTIN_IDS:
        raise HTTPException(status_code=403, detail="Cannot delete built-in companions.")

    companion_dir = _CUSTOM_DIR / companion_id
    if not companion_dir.exists():
        raise HTTPException(status_code=404, detail=f"Companion '{companion_id}' not found.")

    import shutil
    shutil.rmtree(companion_dir)
    CompanionRegistry.force_reload()
    logger.info(f"Custom companion deleted: {companion_id}")
    return {"success": True, "message": f"Companion '{companion_id}' deleted."}
