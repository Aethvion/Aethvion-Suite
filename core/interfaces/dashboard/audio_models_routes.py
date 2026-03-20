"""
Aethvion Suite — Local Audio Models Routes
Install, load, generate TTS, transcribe STT, and manage voice profiles.
"""
import asyncio
import base64
import subprocess
import sys
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.utils.logger import get_logger
from core.utils.paths import DATA

logger = get_logger(__name__)
router = APIRouter(prefix="/api/audio/local", tags=["audio-models"])

SUGGESTED_PATH = DATA / "config" / "suggested_audio_models.json"


def _mgr():
    try:
        from apps.audio.tts_manager import tts_manager
        return tts_manager
    except Exception as e:
        logger.warning(f"TTS manager unavailable: {e}")
        return None


# ── Request models ────────────────────────────────────────────────────────────

class LoadRequest(BaseModel):
    model_id: str
    device: str = "cuda"
    model_size: str = "medium"   # whisper only

class GenerateRequest(BaseModel):
    text: str
    model_id: str
    voice_id: Optional[str] = None
    speed: float = 1.0
    language: str = "en"
    device: str = "cuda"

class TranscribeRequest(BaseModel):
    audio_b64: str
    model_id: str = "whisper"
    language: Optional[str] = None
    device: str = "cuda"

class CloneVoiceRequest(BaseModel):
    model_id: str
    reference_audio_b64: str
    name: str
    language: str = "en"
    device: str = "cuda"

class InstallRequest(BaseModel):
    packages: str   # space-separated pip packages

class DeleteVoiceRequest(BaseModel):
    model_id: str
    voice_id: str

class SetDefaultRequest(BaseModel):
    model_id: str
    voice_id: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/models")
async def get_models():
    mgr = _mgr()
    if mgr is None:
        return {"models": []}
    return {"models": mgr.get_all_statuses()}


@router.get("/suggested")
async def get_suggested():
    if not SUGGESTED_PATH.exists():
        return {"audio_models": []}
    try:
        return json.loads(SUGGESTED_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/load")
async def load_model(req: LoadRequest):
    mgr = _mgr()
    if not mgr:
        raise HTTPException(503, "TTS manager unavailable")
    try:
        await asyncio.to_thread(mgr.load_model, req.model_id, req.device, req.model_size)
        return {"success": True, "model_id": req.model_id, "device": req.device}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/models/unload")
async def unload_model(req: LoadRequest):
    mgr = _mgr()
    if not mgr:
        raise HTTPException(503, "TTS manager unavailable")
    try:
        await asyncio.to_thread(mgr.unload_model, req.model_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/generate")
async def generate_tts(req: GenerateRequest):
    mgr = _mgr()
    if not mgr:
        raise HTTPException(503, "TTS manager unavailable")
    try:
        result = await asyncio.to_thread(
            mgr.generate_tts,
            req.text, req.model_id, req.voice_id, req.speed, req.language, req.device,
        )
        b64 = base64.b64encode(result.audio_bytes).decode()
        return {
            "success": True,
            "audio": f"data:audio/wav;base64,{b64}",
            "sample_rate": result.sample_rate,
        }
    except Exception as e:
        logger.error(f"TTS generate error: {e}")
        raise HTTPException(500, str(e))


@router.post("/transcribe")
async def transcribe(req: TranscribeRequest):
    mgr = _mgr()
    if not mgr:
        raise HTTPException(503, "TTS manager unavailable")
    try:
        audio_bytes = base64.b64decode(req.audio_b64)
        result = await asyncio.to_thread(
            mgr.transcribe, audio_bytes, req.model_id, req.language, req.device,
        )
        return {
            "success": True,
            "text": result.text,
            "language": result.language,
            "confidence": result.confidence,
            "segments": result.segments,
        }
    except Exception as e:
        logger.error(f"STT transcribe error: {e}")
        raise HTTPException(500, str(e))


@router.get("/voices/{model_id}")
async def get_voices(model_id: str):
    mgr = _mgr()
    if not mgr:
        return {"voices": []}
    try:
        return {"voices": mgr.list_voices(model_id)}
    except Exception as e:
        return {"voices": [], "error": str(e)}


@router.post("/voices/clone")
async def clone_voice(req: CloneVoiceRequest):
    mgr = _mgr()
    if not mgr:
        raise HTTPException(503, "TTS manager unavailable")
    try:
        audio_bytes = base64.b64decode(req.reference_audio_b64)
        voice = await asyncio.to_thread(
            mgr.clone_voice, req.model_id, audio_bytes, req.name, req.language, req.device,
        )
        return {"success": True, "voice": voice}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.delete("/voices")
async def delete_voice(req: DeleteVoiceRequest):
    """Delete a cloned voice by removing its files."""
    from core.utils.paths import LOCAL_MODELS_AUDIO_VOICES
    vdir = LOCAL_MODELS_AUDIO_VOICES / req.model_id
    wav = vdir / f"{req.voice_id}.wav"
    meta = vdir / f"{req.voice_id}.json"
    if not wav.exists():
        raise HTTPException(404, f"Voice '{req.voice_id}' not found")
    wav.unlink(missing_ok=True)
    meta.unlink(missing_ok=True)
    return {"success": True}


@router.post("/models/set-default")
async def set_default_model(req: SetDefaultRequest):
    """Save the preferred TTS model and voice to preferences."""
    try:
        from core.workspace.preferences_manager import get_preferences_manager
        pm = get_preferences_manager()
        pm.set("audio.default_tts_model", req.model_id)
        if req.voice_id is not None:
            pm.set("audio.default_tts_voice", req.voice_id)
        return {"success": True, "model_id": req.model_id}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/models/defaults")
async def get_defaults():
    """Return saved default TTS model and voice."""
    try:
        from core.workspace.preferences_manager import get_preferences_manager
        pm = get_preferences_manager()
        return {
            "model_id": pm.get("audio.default_tts_model"),
            "voice_id": pm.get("audio.default_tts_voice"),
        }
    except Exception:
        return {"model_id": None, "voice_id": None}


@router.post("/models/register-to-registry")
async def register_to_registry(req: SetDefaultRequest, request: Request):
    """Register an audio model in the main model_registry.json with TTS/STT capability tags."""
    try:
        from core.interfaces.dashboard.registry_routes import _load_registry, _save_registry

        # Look up capabilities from suggested config
        caps: list[str] = []
        if SUGGESTED_PATH.exists():
            try:
                data = json.loads(SUGGESTED_PATH.read_text(encoding="utf-8"))
                for m in data.get("audio_models", []):
                    if m["id"] == req.model_id:
                        caps = [c.upper() for c in (m.get("capabilities") or [])]
                        break
            except Exception:
                pass
        if not caps:
            caps = ["TTS"]  # safe fallback

        registry = _load_registry()
        providers = registry.setdefault("providers", {})
        if "audio_models" not in providers:
            providers["audio_models"] = {
                "name": "Local Audio Models",
                "active": True,
                "models": {},
            }

        providers["audio_models"]["models"][req.model_id] = {
            "input_cost_per_1m_tokens": 0,
            "output_cost_per_1m_tokens": 0,
            "capabilities": caps,
            "description": f"Local audio model: {req.model_id}",
        }

        _save_registry(registry)
        if hasattr(request.app.state, "nexus"):
            request.app.state.nexus.reload_config()

        return {"success": True, "model_id": req.model_id, "capabilities": caps}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/models/registry-status")
async def get_registry_status():
    """Return which audio models are already registered in the main registry."""
    try:
        from core.interfaces.dashboard.registry_routes import _load_registry
        registry = _load_registry()
        registered = set(registry.get("providers", {}).get("audio_models", {}).get("models", {}).keys())
        return {"registered": list(registered)}
    except Exception:
        return {"registered": []}


@router.get("/models/tts-for-dropdown")
async def get_tts_for_dropdown():
    """Return all TTS-capable models from the registry, grouped by provider,
    enriched with current load status. Used to populate voice-output dropdowns."""
    try:
        from core.interfaces.dashboard.registry_routes import _load_registry
        registry = _load_registry()

        # Current load status from tts_manager
        mgr = _mgr()
        loaded_ids: set[str] = set()
        if mgr:
            for s in mgr.get_all_statuses():
                if s.get("loaded"):
                    loaded_ids.add(s["id"])

        providers_out = []
        for provider_key, provider_cfg in registry.get("providers", {}).items():
            models_out = []
            for model_id, model_info in provider_cfg.get("models", {}).items():
                caps = [c.upper() for c in (model_info.get("capabilities") or [])]
                if "TTS" not in caps:
                    continue
                models_out.append({
                    "id": model_id,
                    "name": model_info.get("description", model_id).replace("Local audio model: ", ""),
                    "description": model_info.get("description", ""),
                    "loaded": model_id in loaded_ids,
                    "capabilities": caps,
                })
            if models_out:
                providers_out.append({
                    "key": provider_key,
                    "name": provider_cfg.get("name", provider_key),
                    "models": models_out,
                })

        return {"providers": providers_out}
    except Exception as e:
        logger.warning(f"tts-for-dropdown error: {e}")
        return {"providers": []}


@router.post("/install")
async def install_packages(req: InstallRequest):
    """pip-install the packages required by an audio model."""
    packages = req.packages.strip().split()
    if not packages:
        raise HTTPException(400, "No packages specified")
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "pip", "install"] + packages,
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            return {"success": False, "error": proc.stderr[-2000:]}
        return {"success": True, "output": proc.stdout[-500:]}
    except Exception as e:
        raise HTTPException(500, str(e))
