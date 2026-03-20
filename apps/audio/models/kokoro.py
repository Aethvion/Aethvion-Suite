"""
Aethvion Suite — Kokoro TTS
Lightweight, fast, CPU-friendly. ~0.3 GB. 20+ built-in voices.
Install: pip install kokoro soundfile
"""
import io
from pathlib import Path
from typing import Optional, List

from core.utils.logger import get_logger
from .base import LocalAudioModel, VoiceInfo, TTSResult

logger = get_logger(__name__)

KOKORO_VOICES = [
    VoiceInfo("af_heart",    "Heart",    "en-us", "female"),
    VoiceInfo("af_bella",    "Bella",    "en-us", "female"),
    VoiceInfo("af_aoede",    "Aoede",    "en-us", "female"),
    VoiceInfo("af_kore",     "Kore",     "en-us", "female"),
    VoiceInfo("af_nicole",   "Nicole",   "en-us", "female"),
    VoiceInfo("af_nova",     "Nova",     "en-us", "female"),
    VoiceInfo("af_river",    "River",    "en-us", "female"),
    VoiceInfo("af_sarah",    "Sarah",    "en-us", "female"),
    VoiceInfo("af_sky",      "Sky",      "en-us", "female"),
    VoiceInfo("am_adam",     "Adam",     "en-us", "male"),
    VoiceInfo("am_echo",     "Echo",     "en-us", "male"),
    VoiceInfo("am_eric",     "Eric",     "en-us", "male"),
    VoiceInfo("am_fenrir",   "Fenrir",   "en-us", "male"),
    VoiceInfo("am_liam",     "Liam",     "en-us", "male"),
    VoiceInfo("am_michael",  "Michael",  "en-us", "male"),
    VoiceInfo("am_onyx",     "Onyx",     "en-us", "male"),
    VoiceInfo("bf_emma",     "Emma",     "en-gb", "female"),
    VoiceInfo("bf_isabella", "Isabella", "en-gb", "female"),
    VoiceInfo("bm_george",   "George",   "en-gb", "male"),
    VoiceInfo("bm_lewis",    "Lewis",    "en-gb", "male"),
]

_LANG_CODE = {
    "en-us": "a", "en": "a", "en-gb": "b",
    "ja": "j", "ko": "k", "zh": "z",
    "fr": "f", "es": "e", "hi": "h",
    "it": "i", "pt": "p",
}


class KokoroModel(LocalAudioModel):
    MODEL_ID = "kokoro"
    MODEL_NAME = "Kokoro TTS"
    CAPABILITIES = ["tts"]
    VRAM_ESTIMATE_GB = 0.3

    def __init__(self, models_dir: Path, voices_dir: Path):
        super().__init__(models_dir, voices_dir)
        self._pipeline = None

    @property
    def is_installed(self) -> bool:
        try:
            import kokoro  # noqa: F401
            return True
        except ImportError:
            return False

    def load(self, device: str = "cuda") -> None:
        from kokoro import KPipeline
        self._pipeline = KPipeline(lang_code="a")  # American English default
        self._device = device
        self._loaded = True
        logger.info("Kokoro TTS loaded")

    def unload(self) -> None:
        self._pipeline = None
        self._loaded = False

    def generate_tts(self, text: str, voice_id: Optional[str] = None,
                     speed: float = 1.0, language: str = "en", **kwargs) -> TTSResult:
        if not self._loaded:
            raise RuntimeError("Kokoro not loaded — call load() first")

        import numpy as np
        import soundfile as sf

        lang_code = _LANG_CODE.get(language, "a")
        # Reinitialise pipeline if language changed
        if self._pipeline.lang_code != lang_code:
            from kokoro import KPipeline
            self._pipeline = KPipeline(lang_code=lang_code)

        voice = voice_id or "af_heart"
        chunks = [audio for _, _, audio in self._pipeline(text, voice=voice, speed=speed)
                  if audio is not None]
        if not chunks:
            raise RuntimeError("Kokoro produced no audio output")

        audio_np = np.concatenate(chunks)
        buf = io.BytesIO()
        sf.write(buf, audio_np, 24000, format="WAV")
        return TTSResult(audio_bytes=buf.getvalue(), sample_rate=24000, format="wav")

    def list_voices(self) -> List[VoiceInfo]:
        return list(KOKORO_VOICES)
