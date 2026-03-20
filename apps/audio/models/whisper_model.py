"""
Aethvion Suite — Whisper STT (faster-whisper)
GPU-accelerated transcription. 99 languages. Multiple model sizes.
Install: pip install faster-whisper
"""
import tempfile
from pathlib import Path
from typing import Optional, List

from core.utils.logger import get_logger
from .base import LocalAudioModel, VoiceInfo, STTResult

logger = get_logger(__name__)

SIZES = ["tiny", "base", "small", "medium", "large-v3"]
VRAM_MAP = {"tiny": 0.15, "base": 0.3, "small": 0.5, "medium": 1.5, "large-v3": 3.0}


class WhisperModel(LocalAudioModel):
    MODEL_ID = "whisper"
    MODEL_NAME = "Whisper (faster-whisper)"
    CAPABILITIES = ["stt"]
    VRAM_ESTIMATE_GB = 1.5  # medium default

    def __init__(self, models_dir: Path, voices_dir: Path, model_size: str = "medium"):
        super().__init__(models_dir, voices_dir)
        self._model = None
        self.model_size = model_size if model_size in SIZES else "medium"
        self.VRAM_ESTIMATE_GB = VRAM_MAP.get(self.model_size, 1.5)

    @property
    def is_installed(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def load(self, device: str = "cuda") -> None:
        from faster_whisper import WhisperModel as FW
        compute_type = "float16" if device == "cuda" else "int8"
        cache = str(self.models_dir / "whisper")
        self._model = FW(self.model_size, device=device,
                         compute_type=compute_type, download_root=cache)
        self._device = device
        self._loaded = True
        logger.info(f"Whisper {self.model_size} loaded on {device}")

    def unload(self) -> None:
        self._model = None
        self._loaded = False

    def transcribe(self, audio_bytes: bytes, language: Optional[str] = None,
                   **kwargs) -> STTResult:
        if not self._loaded:
            raise RuntimeError("Whisper not loaded — call load() first")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tf.write(audio_bytes)
            tmp = Path(tf.name)
        try:
            segments, info = self._model.transcribe(
                str(tmp), language=language, beam_size=5, vad_filter=True,
            )
            parts, segs = [], []
            for s in segments:
                parts.append(s.text)
                segs.append({"start": s.start, "end": s.end,
                              "text": s.text, "confidence": s.avg_logprob})
        finally:
            tmp.unlink(missing_ok=True)

        return STTResult(
            text=" ".join(parts).strip(),
            language=info.language,
            confidence=info.language_probability,
            segments=segs,
        )

    def list_voices(self) -> List[VoiceInfo]:
        return []

    def to_status_dict(self) -> dict:
        d = super().to_status_dict()
        d["model_size"] = self.model_size
        d["available_sizes"] = SIZES
        return d
