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

from fastapi import APIRouter, HTTPException
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
    from core.utils.paths import APP_AUDIO
    vdir = APP_AUDIO / "voices" / req.model_id
    wav = vdir / f"{req.voice_id}.wav"
    meta = vdir / f"{req.voice_id}.json"
    if not wav.exists():
        raise HTTPException(404, f"Voice '{req.voice_id}' not found")
    wav.unlink(missing_ok=True)
    meta.unlink(missing_ok=True)
    return {"success": True}


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
