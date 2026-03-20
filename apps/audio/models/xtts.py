"""
Aethvion Suite — XTTS-v2 (Coqui TTS)
17-language TTS with voice cloning from a 6-second clip. ~2 GB VRAM.
Install: pip install TTS
"""
import io
import json
import tempfile
from pathlib import Path
from typing import Optional, List

from core.utils.logger import get_logger
from .base import LocalAudioModel, VoiceInfo, TTSResult

logger = get_logger(__name__)


class XTTSv2Model(LocalAudioModel):
    MODEL_ID = "xtts-v2"
    MODEL_NAME = "XTTS-v2 (Coqui)"
    CAPABILITIES = ["tts", "voice_cloning"]
    VRAM_ESTIMATE_GB = 2.0
    LANGUAGES = [
        "en", "es", "fr", "de", "it", "pt", "ru",
        "zh-cn", "ja", "ko", "ar", "nl", "cs", "pl", "tr", "hu", "hi",
    ]

    def __init__(self, models_dir: Path, voices_dir: Path):
        super().__init__(models_dir, voices_dir)
        self._tts = None

    @property
    def is_installed(self) -> bool:
        try:
            import TTS  # noqa: F401
            return True
        except ImportError:
            return False

    def load(self, device: str = "cuda") -> None:
        from TTS.api import TTS
        self._tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
        self._device = device
        self._loaded = True
        logger.info(f"XTTS-v2 loaded on {device}")

    def unload(self) -> None:
        self._tts = None
        self._loaded = False
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def generate_tts(self, text: str, voice_id: Optional[str] = None,
                     speed: float = 1.0, language: str = "en", **kwargs) -> TTSResult:
        if not self._loaded:
            raise RuntimeError("XTTS-v2 not loaded — call load() first")

        speaker_wav = self._resolve_speaker_wav(voice_id)
        if not speaker_wav:
            raise ValueError(
                "XTTS-v2 requires a reference speaker WAV. "
                "Clone a voice first in the Voices tab."
            )

        lang = language[:5].lower()  # e.g. "en", "zh-cn"
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tmp_path = Path(tf.name)
        try:
            self._tts.tts_to_file(
                text=text,
                speaker_wav=speaker_wav,
                language=lang,
                file_path=str(tmp_path),
                speed=speed,
            )
            audio_bytes = tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)

        return TTSResult(audio_bytes=audio_bytes, sample_rate=24000, format="wav")

    def list_voices(self) -> List[VoiceInfo]:
        voices = []
        vdir = self.voices_dir / "xtts"
        if not vdir.exists():
            return voices
        for wav in sorted(vdir.glob("*.wav")):
            meta = {}
            meta_f = wav.with_suffix(".json")
            if meta_f.exists():
                try:
                    meta = json.loads(meta_f.read_text(encoding="utf-8"))
                except Exception:
                    pass
            voices.append(VoiceInfo(
                id=wav.stem,
                name=meta.get("name", wav.stem),
                language=meta.get("language", "en"),
                gender=meta.get("gender", "neutral"),
                preview_path=str(wav),
                is_cloned=True,
            ))
        return voices

    def clone_voice(self, reference_audio: bytes, name: str,
                    language: str = "en") -> VoiceInfo:
        vdir = self.voices_dir / "xtts"
        vdir.mkdir(parents=True, exist_ok=True)
        vid = "".join(c if c.isalnum() or c in "-_" else "_" for c in name).lower()
        (vdir / f"{vid}.wav").write_bytes(reference_audio)
        (vdir / f"{vid}.json").write_text(
            json.dumps({"name": name, "language": language, "gender": "neutral"}, indent=2),
            encoding="utf-8",
        )
        return VoiceInfo(id=vid, name=name, language=language,
                         preview_path=str(vdir / f"{vid}.wav"), is_cloned=True)

    def _resolve_speaker_wav(self, voice_id: Optional[str]) -> Optional[str]:
        vdir = self.voices_dir / "xtts"
        if voice_id:
            p = vdir / f"{voice_id}.wav"
            if p.exists():
                return str(p)
        # Fallback to first available
        if vdir.exists():
            wavs = list(vdir.glob("*.wav"))
            if wavs:
                return str(wavs[0])
        return None
