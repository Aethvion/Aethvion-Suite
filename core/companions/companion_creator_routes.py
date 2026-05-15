"""
Aethvion Suite - Companion Creator Routes
API endpoints for creating, listing, editing, exporting, and importing companions.

Custom companions are stored in data/companions/<id>/config.json.
Built-in companions (axiom, lyra) can have their personality overridden here.
Registry is hot-reloaded after every mutation — no server restart required.
"""

import json
import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.utils.logger import get_logger
from core.utils.paths import COMPANIONS
from core.companions.registry import CompanionRegistry

logger = get_logger(__name__)
router = APIRouter(prefix="/api/companion-creator", tags=["companion-creator"])

_CUSTOM_DIR = COMPANIONS
_CUSTOM_DIR.mkdir(parents=True, exist_ok=True)

# Built-in companions managed by core/companions/configs/ — editable but not deletable
_BUILTIN_IDS = {"misaka_cipher", "axiom", "lyra"}
_CORE_CONFIG_DIR = Path(__file__).parent / "configs"


# ── Schema ─────────────────────────────────────────────────────────────────────

class CompanionCreateRequest(BaseModel):
    name: str
    description: str
    personality: str
    speech_style: str
    quirks: list[str] = []
    likes: list[str] = []
    dislikes: list[str] = []
    default_model: str = "gemini-1.5-flash"
    accent_color: str = "#6366f1"
    avatar_symbol: str = "✦"
    expressions: list[str] = []
    moods: list[str] = []


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


def _atomic_write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _slug(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "companion"


def _list_custom_companions() -> list[dict]:
    configs = []
    for config_file in sorted(_CUSTOM_DIR.glob("*/config.json")):
        try:
            data = json.loads(config_file.read_text(encoding="utf-8"))
            # Skip built-ins that may have override configs in the data dir
            if data.get("id") not in _BUILTIN_IDS:
                configs.append(data)
        except Exception as e:
            logger.warning(f"Could not read {config_file}: {e}")
    return configs


def _list_builtin_companions() -> list[dict]:
    """Return built-in companion configs (data/ override takes priority)."""
    builtins = []
    for cid in ("axiom", "lyra", "misaka_cipher"):
        # Data override takes priority
        override = _CUSTOM_DIR / cid / "config.json"
        core = _CORE_CONFIG_DIR / f"{cid}.json"
        src = override if override.exists() else core
        if src.exists():
            try:
                data = json.loads(src.read_text(encoding="utf-8"))
                data["_builtin"] = True
                builtins.append(data)
            except Exception as e:
                logger.warning(f"Could not read builtin config {cid}: {e}")
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
    _atomic_write_json(companion_dir / "config.json", config)
    _atomic_write_json(companion_dir / "base_info.json", {
        "name":          config["name"],
        "core_identity": config["description"],
        "personality":   config["personality"],
        "speech_style":  config["speech_style"],
        "quirks":        config["quirks"],
        "likes":         config["likes"],
        "dislikes":      config["dislikes"],
        "autonomy_level": "Medium",
    })
    _atomic_write_json(companion_dir / "memory.json", {
        "user_info": {},
        "recent_observations": [],
        "synthesis_notes": [],
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    CompanionRegistry.force_reload()
    logger.info(f"Companion imported: {companion_id} ({config['name']})")
    return {"success": True, "id": companion_id, "name": config["name"],
            "message": f"'{config['name']}' imported successfully."}


@router.put("/builtin/{companion_id}")
async def update_builtin_companion(companion_id: str, req: BuiltinUpdateRequest):
    """
    Override personality fields for a built-in companion.
    Writes a merged config to data/companions/{id}/config.json so the
    registry picks it up on force_reload() — no restart needed.
    """
    _validate_companion_id(companion_id)
    if companion_id not in _BUILTIN_IDS:
        raise HTTPException(status_code=400, detail=f"'{companion_id}' is not a built-in companion.")
    if companion_id == "misaka_cipher":
        raise HTTPException(status_code=403, detail="Misaka Cipher's config cannot be edited here.")

    # Load the canonical core config as base
    core_path = _CORE_CONFIG_DIR / f"{companion_id}.json"
    if not core_path.exists():
        raise HTTPException(status_code=404, detail=f"Core config for '{companion_id}' not found.")
    base = json.loads(core_path.read_text(encoding="utf-8"))

    # Merge editable fields
    if req.personality:
        base["personality"] = req.personality
    if req.speech_style:
        base["speech_style"] = req.speech_style
    if req.quirks is not None:
        base["quirks"] = req.quirks
    if req.likes is not None:
        base["likes"] = req.likes
    if req.dislikes is not None:
        base["dislikes"] = req.dislikes
    if req.accent_color:
        base["accent_color"] = req.accent_color
    if req.avatar_symbol:
        base["avatar_symbol"] = req.avatar_symbol

    companion_dir = _CUSTOM_DIR / companion_id
    companion_dir.mkdir(parents=True, exist_ok=True)
    (companion_dir / "history").mkdir(exist_ok=True)

    _atomic_write_json(companion_dir / "config.json", base)

    # Also update base_info.json
    base_info_path = companion_dir / "base_info.json"
    base_info = json.loads(base_info_path.read_text(encoding="utf-8")) if base_info_path.exists() else {}
    base_info.update({
        "name":          base["name"],
        "core_identity": base.get("description", ""),
        "personality":   req.personality or base.get("personality", ""),
        "speech_style":  req.speech_style or base.get("speech_style", ""),
        "quirks":        req.quirks,
        "likes":         req.likes,
        "dislikes":      req.dislikes,
    })
    _atomic_write_json(base_info_path, base_info)

    CompanionRegistry.force_reload()
    logger.info(f"Built-in companion updated: {companion_id}")
    return {"success": True, "id": companion_id, "message": f"'{base['name']}' updated successfully."}


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
        "id":            companion_id,
        "name":          req.name,
        "description":   req.description,
        "personality":   req.personality,
        "speech_style":  req.speech_style,
        "quirks":        req.quirks,
        "likes":         req.likes,
        "dislikes":      req.dislikes,
        "default_model": req.default_model,
        "accent_color":  req.accent_color,
        "avatar_symbol": req.avatar_symbol,
        "expressions":   expressions,
        "moods":         moods,
        "route_prefix":  f"/api/custom/{companion_id}",
        "type":          "custom",
    }

    _atomic_write_json(companion_dir / "config.json", config)
    _atomic_write_json(companion_dir / "base_info.json", {
        "name":          req.name,
        "core_identity": req.description,
        "personality":   req.personality,
        "speech_style":  req.speech_style,
        "quirks":        req.quirks,
        "likes":         req.likes,
        "dislikes":      req.dislikes,
        "autonomy_level": "Medium",
    })
    _atomic_write_json(companion_dir / "memory.json", {
        "user_info": {},
        "recent_observations": [],
        "synthesis_notes": [],
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
    """Update an existing custom companion's config."""
    if companion_id in _BUILTIN_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"Use PUT /builtin/{companion_id} to edit built-in companions."
        )
    existing = _load_config(companion_id)
    companion_dir = _CUSTOM_DIR / companion_id

    expressions = req.expressions or existing.get("expressions", ["default", "happy", "thinking"])
    moods       = req.moods       or existing.get("moods", ["calm", "happy", "reflective"])

    config = {
        **existing,
        "name":          req.name,
        "description":   req.description,
        "personality":   req.personality,
        "speech_style":  req.speech_style,
        "quirks":        req.quirks,
        "likes":         req.likes,
        "dislikes":      req.dislikes,
        "default_model": req.default_model,
        "accent_color":  req.accent_color,
        "avatar_symbol": req.avatar_symbol,
        "expressions":   expressions,
        "moods":         moods,
    }
    _atomic_write_json(companion_dir / "config.json", config)

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
    _atomic_write_json(base_info_path, base_info)

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
