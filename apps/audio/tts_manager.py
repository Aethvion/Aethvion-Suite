"""
Aethvion Suite — TTS/STT Manager
Unified interface for all local audio models. Thread-safe singleton.
"""
from __future__ import annotations
import threading
from pathlib import Path
from typing import Optional, Dict, List

from core.utils.logger import get_logger
from core.utils.paths import APP_AUDIO
from .models.base import LocalAudioModel, TTSResult, STTResult, VoiceInfo
from .models.registry import get_all_model_classes, get_model_class

logger = get_logger(__name__)

MODELS_DIR = APP_AUDIO / "models"
VOICES_DIR = APP_AUDIO / "voices"


class TTSManager:
    def __init__(self):
        self._instances: Dict[str, LocalAudioModel] = {}
        self._lock = threading.Lock()
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        VOICES_DIR.mkdir(parents=True, exist_ok=True)

    def _get_or_create(self, model_id: str) -> LocalAudioModel:
        if model_id not in self._instances:
            cls = get_model_class(model_id)
            if cls is None:
                raise ValueError(f"Unknown audio model: '{model_id}'")
            self._instances[model_id] = cls(MODELS_DIR, VOICES_DIR)
        return self._instances[model_id]

    def get_all_statuses(self) -> List[dict]:
        statuses = []
        for mid, cls in get_all_model_classes().items():
            inst = self._instances.get(mid)
            if inst:
                statuses.append(inst.to_status_dict())
            else:
                # Not instantiated — report static info, check install
                try:
                    tmp = cls(MODELS_DIR, VOICES_DIR)
                    installed = tmp.is_installed
                except Exception:
                    installed = False
                statuses.append({
                    "id": cls.MODEL_ID,
                    "name": cls.MODEL_NAME,
                    "capabilities": cls.CAPABILITIES,
                    "vram_estimate_gb": cls.VRAM_ESTIMATE_GB,
                    "loaded": False,
                    "installed": installed,
                    "device": None,
                })
        return statuses

    def load_model(self, model_id: str, device: str = "cuda",
                   model_size: str = "medium") -> None:
        with self._lock:
            # For whisper: allow re-creating with different size
            if model_id == "whisper" and model_id in self._instances:
                existing = self._instances[model_id]
                if hasattr(existing, "model_size") and existing.model_size != model_size:
                    existing.unload()
                    del self._instances[model_id]

            model = self._get_or_create(model_id)
            # Inject model_size for Whisper before loading
            if model_id == "whisper" and hasattr(model, "model_size"):
                model.model_size = model_size
            if not model.is_loaded:
                model.load(device)

    def unload_model(self, model_id: str) -> None:
        with self._lock:
            if model_id in self._instances:
                self._instances[model_id].unload()

    def generate_tts(self, text: str, model_id: str,
                     voice_id: Optional[str] = None, speed: float = 1.0,
                     language: str = "en", device: str = "cuda",
                     **kwargs) -> TTSResult:
        with self._lock:
            model = self._get_or_create(model_id)
            if not model.is_loaded:
                model.load(device)
        return model.generate_tts(text, voice_id=voice_id, speed=speed,
                                   language=language, **kwargs)

    def transcribe(self, audio_bytes: bytes, model_id: str = "whisper",
                   language: Optional[str] = None, device: str = "cuda",
                   **kwargs) -> STTResult:
        with self._lock:
            model = self._get_or_create(model_id)
            if not model.is_loaded:
                model.load(device)
        return model.transcribe(audio_bytes, language=language, **kwargs)

    def list_voices(self, model_id: str) -> List[dict]:
        model = self._get_or_create(model_id)
        return [v.to_dict() for v in model.list_voices()]

    def clone_voice(self, model_id: str, reference_audio: bytes, name: str,
                    language: str = "en", device: str = "cuda") -> dict:
        with self._lock:
            model = self._get_or_create(model_id)
            if not model.is_loaded:
                model.load(device)
        return model.clone_voice(reference_audio, name, language).to_dict()


# Singleton
tts_manager = TTSManager()
