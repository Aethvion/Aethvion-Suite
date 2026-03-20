"""
Aethvion Suite — Local Audio Model Base
Abstract base for all local TTS/STT model wrappers.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any


@dataclass
class VoiceInfo:
    id: str
    name: str
    language: str = "en"
    gender: str = "neutral"
    description: str = ""
    preview_path: Optional[str] = None
    is_cloned: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "language": self.language,
            "gender": self.gender, "description": self.description,
            "preview_path": self.preview_path, "is_cloned": self.is_cloned,
        }


@dataclass
class TTSResult:
    audio_bytes: bytes
    sample_rate: int
    format: str = "wav"
    duration_ms: Optional[int] = None


@dataclass
class STTResult:
    text: str
    language: Optional[str] = None
    confidence: Optional[float] = None
    segments: List[dict] = field(default_factory=list)


class LocalAudioModel(ABC):
    MODEL_ID: str = ""
    MODEL_NAME: str = ""
    CAPABILITIES: List[str] = []   # "tts", "stt", "voice_cloning"
    VRAM_ESTIMATE_GB: float = 0.0

    def __init__(self, models_dir: Path, voices_dir: Path):
        self.models_dir = models_dir
        self.voices_dir = voices_dir
        self._loaded = False
        self._device = "cpu"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def is_installed(self) -> bool:
        return False

    @abstractmethod
    def load(self, device: str = "cuda") -> None: ...

    @abstractmethod
    def unload(self) -> None: ...

    def generate_tts(self, text: str, voice_id: Optional[str] = None,
                     speed: float = 1.0, language: str = "en", **kwargs) -> TTSResult:
        raise NotImplementedError(f"{self.MODEL_NAME} does not support TTS")

    def transcribe(self, audio_bytes: bytes, language: Optional[str] = None,
                   **kwargs) -> STTResult:
        raise NotImplementedError(f"{self.MODEL_NAME} does not support STT")

    def list_voices(self) -> List[VoiceInfo]:
        return []

    def clone_voice(self, reference_audio: bytes, name: str,
                    language: str = "en") -> VoiceInfo:
        raise NotImplementedError(f"{self.MODEL_NAME} does not support voice cloning")

    def to_status_dict(self) -> dict:
        return {
            "id": self.MODEL_ID,
            "name": self.MODEL_NAME,
            "capabilities": self.CAPABILITIES,
            "vram_estimate_gb": self.VRAM_ESTIMATE_GB,
            "loaded": self._loaded,
            "installed": self.is_installed,
            "device": self._device if self._loaded else None,
        }
