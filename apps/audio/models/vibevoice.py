"""
Aethvion Suite — Microsoft VibeVoice
Open-source frontier voice AI from Microsoft.

  VibeVoice Realtime-0.5B : streaming TTS, ~300 ms first-token latency
  VibeVoice ASR (9B)       : long-form STT with speaker diarisation, 50+ languages

Install: pip install vibevoice torch soundfile

Models are downloaded automatically from HuggingFace on first load.
Voice presets for the Realtime model are fetched once and cached locally.

Note: models are MIT licensed; intended for research / development use.
"""

from __future__ import annotations

import copy
import io
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional, List

from core.utils.logger import get_logger
from .base import LocalAudioModel, VoiceInfo, TTSResult, STTResult

logger = get_logger(__name__)

# ── HuggingFace model IDs ────────────────────────────────────────────────────
HF_REALTIME = "microsoft/VibeVoice-Realtime-0.5B"
HF_ASR      = "microsoft/VibeVoice-ASR"

# ── Voice preset metadata ────────────────────────────────────────────────────
# Presets are pre-computed speaker embeddings (.pt files).
# They are fetched from the community mirror on first use and cached locally.
_VOICE_PRESET_BASE = (
    "https://huggingface.co/spaces/anycoderapps/"
    "VibeVoice-Realtime-0.5B/resolve/main/demo/voices/streaming_model"
)

_VOICE_DEFS: List[tuple] = [
    # (preset_filename,  display_name,  lang,   gender,  description)
    ("en-Carter_man.pt",  "Carter",  "en", "male",   "Deep, authoritative voice"),
    ("en-Davis_man.pt",   "Davis",   "en", "male",   "Warm, conversational voice"),
    ("en-Emma_woman.pt",  "Emma",    "en", "female", "Clear, professional voice"),
    ("en-Frank_man.pt",   "Frank",   "en", "male",   "Casual, friendly voice"),
    ("en-Grace_woman.pt", "Grace",   "en", "female", "Smooth, expressive voice"),
    ("en-Mike_man.pt",    "Mike",    "en", "male",   "Energetic, dynamic voice"),
    ("in-Samuel_man.pt",  "Samuel",  "en", "male",   "Distinctive Indian-accented voice"),
]

REALTIME_VOICES: List[VoiceInfo] = [
    VoiceInfo(
        id=fname,          # use filename as stable ID
        name=name,
        language=lang,
        gender=gender,
        description=desc,
    )
    for (fname, name, lang, gender, desc) in _VOICE_DEFS
]


# ── Helper ───────────────────────────────────────────────────────────────────

def _download_file(url: str, dest: Path, desc: str = "") -> bool:
    """Download *url* to *dest*, returning True on success."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    try:
        logger.info(f"Downloading {desc or url} …")
        urllib.request.urlretrieve(url, str(tmp))
        tmp.replace(dest)
        return True
    except Exception as exc:
        logger.warning(f"Failed to download {url}: {exc}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return False


# ── VibeVoice Realtime (0.5B) — TTS ─────────────────────────────────────────

class VibeVoiceRealtimeModel(LocalAudioModel):
    """
    VibeVoice-Realtime-0.5B — fast streaming text-to-speech.

    * ~300 ms to first audible speech on GPU
    * English only (non-English input may produce unexpected output)
    * Single speaker per generation
    * VRAM: ~2 GB (float16)

    Voices are pre-computed speaker embeddings fetched automatically from
    HuggingFace on first use.  Add your own by placing <name>.pt files in
    the voices/vibevoice directory.
    """

    MODEL_ID         = "vibevoice-realtime"
    MODEL_NAME       = "VibeVoice Realtime (0.5B)"
    CAPABILITIES     = ["tts"]
    VRAM_ESTIMATE_GB = 2.0

    def __init__(self, models_dir: Path, voices_dir: Path):
        super().__init__(models_dir, voices_dir)
        self._model     = None
        self._processor = None

    # ── Package detection ────────────────────────────────────────────────────

    @property
    def is_installed(self) -> bool:
        try:
            import vibevoice  # noqa: F401
            return True
        except ImportError:
            return False

    # ── Load / Unload ─────────────────────────────────────────────────────────

    def load(self, device: str = "cuda") -> None:
        import torch
        from vibevoice.modular.modeling_vibevoice_streaming_inference import (
            VibeVoiceStreamingForConditionalGenerationInference,
        )
        from vibevoice.processor.vibevoice_streaming_processor import (
            VibeVoiceStreamingProcessor,
        )

        cache_dir = str(self.models_dir / "vibevoice-realtime")
        dtype     = torch.float16 if device == "cuda" else torch.float32

        logger.info("Loading VibeVoice Realtime processor …")
        self._processor = VibeVoiceStreamingProcessor.from_pretrained(
            HF_REALTIME,
            cache_dir=cache_dir,
        )

        logger.info("Loading VibeVoice Realtime model (2 GB) …")
        self._model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
            HF_REALTIME,
            torch_dtype=dtype,
            device_map=device if device == "cuda" else "cpu",
            attn_implementation="sdpa",
            cache_dir=cache_dir,
        )
        self._model.eval()
        self._model.set_ddpm_inference_steps(num_steps=5)

        # Pre-fetch voice presets in background so first TTS call is instant
        self._ensure_voices(silent=True)

        self._device = device
        self._loaded = True
        logger.info(f"VibeVoice Realtime loaded on {device}")

    def unload(self) -> None:
        self._model     = None
        self._processor = None
        self._loaded    = False

    # ── Voices ────────────────────────────────────────────────────────────────

    def list_voices(self) -> List[VoiceInfo]:
        # Mark voices that are already downloaded as available
        voices = []
        for v in REALTIME_VOICES:
            v2 = VoiceInfo(
                id=v.id, name=v.name, language=v.language,
                gender=v.gender,
                description=v.description
                + (" ✓" if self._preset_path(v.id).exists() else " (not downloaded)"),
            )
            voices.append(v2)
        return voices

    def _preset_dir(self) -> Path:
        d = self.voices_dir / "vibevoice"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _preset_path(self, voice_id: str) -> Path:
        return self._preset_dir() / voice_id

    def _ensure_voices(self, silent: bool = False) -> None:
        """Download any missing voice presets from the HuggingFace mirror."""
        for v in REALTIME_VOICES:
            dest = self._preset_path(v.id)
            if not dest.exists():
                url = f"{_VOICE_PRESET_BASE}/{v.id}"
                ok  = _download_file(url, dest, desc=f"voice preset '{v.name}'")
                if not ok and not silent:
                    logger.warning(f"Could not fetch preset for '{v.name}'.")

    # ── TTS ───────────────────────────────────────────────────────────────────

    def generate_tts(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        language: str = "en",
        **kwargs,
    ) -> TTSResult:
        if not self._loaded:
            raise RuntimeError("VibeVoice Realtime not loaded — call load() first")

        import soundfile as sf

        # Resolve voice preset
        chosen_id = voice_id or REALTIME_VOICES[0].id
        preset_path = self._preset_path(chosen_id)

        if not preset_path.exists():
            logger.info(f"Preset '{chosen_id}' not cached — downloading …")
            url = f"{_VOICE_PRESET_BASE}/{chosen_id}"
            _download_file(url, preset_path, desc=f"voice preset '{chosen_id}'")

        if not preset_path.exists():
            raise RuntimeError(
                f"Voice preset '{chosen_id}' could not be downloaded.  "
                "Check your internet connection or add a .pt preset file manually "
                f"to: {self._preset_dir()}"
            )

        audio_np = self._generate_with_preset(text, preset_path)

        buf = io.BytesIO()
        sf.write(buf, audio_np, 24000, format="WAV")
        buf.seek(0)
        return TTSResult(audio_bytes=buf.getvalue(), sample_rate=24000, format="wav")

    def _generate_with_preset(self, text: str, preset_path: Path):
        import torch
        dev    = "cuda" if self._device == "cuda" else "cpu"
        cached = torch.load(str(preset_path), map_location=dev, weights_only=False)

        inputs = self._processor.process_input_with_cached_prompt(
            text=text,
            cached_prompt=cached,
            padding=True,
            return_tensors="pt",
            return_attention_mask=True,
        )
        inputs = {
            k: v.to(dev) if isinstance(v, torch.Tensor) else v
            for k, v in inputs.items()
        }

        with torch.inference_mode():
            autocast = (
                torch.cuda.amp.autocast()
                if self._device == "cuda"
                else contextlib_nullcontext()
            )
            with autocast:
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=None,
                    cfg_scale=1.5,
                    tokenizer=self._processor.tokenizer,
                    generation_config={"do_sample": False},
                    verbose=False,
                    all_prefilled_outputs=copy.deepcopy(cached),
                )

        return outputs.speech_outputs[0].cpu().numpy()


# ── VibeVoice ASR (9B) — STT ─────────────────────────────────────────────────

class VibeVoiceASRModel(LocalAudioModel):
    """
    VibeVoice-ASR (9B) — long-form speech recognition with diarisation.

    * Up to 60 minutes of audio in a single pass
    * Speaker diarisation (who spoke when)
    * Word-level timestamps
    * Customisable hotwords / context via ``context_info``
    * 50+ languages with code-switching
    * VRAM: ~18 GB (bfloat16).  CPU mode available but very slow.
    """

    MODEL_ID         = "vibevoice-asr"
    MODEL_NAME       = "VibeVoice ASR (9B)"
    CAPABILITIES     = ["stt"]
    VRAM_ESTIMATE_GB = 18.0

    def __init__(self, models_dir: Path, voices_dir: Path):
        super().__init__(models_dir, voices_dir)
        self._model     = None
        self._processor = None

    # ── Package detection ────────────────────────────────────────────────────

    @property
    def is_installed(self) -> bool:
        try:
            import vibevoice  # noqa: F401
            return True
        except ImportError:
            return False

    # ── Load / Unload ─────────────────────────────────────────────────────────

    def load(self, device: str = "cuda") -> None:
        import torch
        from vibevoice.modular.modeling_vibevoice_asr import (
            VibeVoiceASRForConditionalGeneration,
        )
        from vibevoice.processor.vibevoice_asr_processor import (
            VibeVoiceASRProcessor,
        )

        cache_dir = str(self.models_dir / "vibevoice-asr")

        # Choose best available attention implementation
        attn_impl = "sdpa"
        try:
            import flash_attn  # noqa: F401
            attn_impl = "flash_attention_2"
            logger.info("Flash Attention 2 detected — using for VibeVoice ASR")
        except ImportError:
            pass

        dtype = torch.bfloat16 if device == "cuda" else torch.float32

        logger.info("Loading VibeVoice ASR processor …")
        self._processor = VibeVoiceASRProcessor.from_pretrained(
            HF_ASR,
            cache_dir=cache_dir,
        )

        logger.info("Loading VibeVoice ASR model (~18 GB — this will take a while) …")
        self._model = VibeVoiceASRForConditionalGeneration.from_pretrained(
            HF_ASR,
            dtype=dtype,
            device_map=device if device == "cuda" else "cpu",
            attn_implementation=attn_impl,
            trust_remote_code=True,
            cache_dir=cache_dir,
        )
        self._model.eval()
        self._device = device
        self._loaded = True
        logger.info(f"VibeVoice ASR loaded on {device}")

    def unload(self) -> None:
        self._model     = None
        self._processor = None
        self._loaded    = False

    # ── STT ───────────────────────────────────────────────────────────────────

    def transcribe(
        self,
        audio_bytes: bytes,
        language: Optional[str] = None,
        **kwargs,
    ) -> STTResult:
        if not self._loaded:
            raise RuntimeError("VibeVoice ASR not loaded — call load() first")

        suffix = kwargs.get("audio_format", ".wav")
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            tf.write(audio_bytes)
            tmp = Path(tf.name)
        try:
            return self._run_transcription(str(tmp), language=language, **kwargs)
        finally:
            tmp.unlink(missing_ok=True)

    def _run_transcription(
        self,
        audio_path: str,
        language: Optional[str] = None,
        **kwargs,
    ) -> STTResult:
        import torch
        dev          = "cuda" if self._device == "cuda" else "cpu"
        context_info = kwargs.get("context_info")   # optional hotwords / speaker names

        inputs = self._processor(
            audio=audio_path,
            return_tensors="pt",
            add_generation_prompt=True,
            context_info=context_info,
        )
        inputs = {
            k: v.to(dev) if isinstance(v, torch.Tensor) else v
            for k, v in inputs.items()
        }

        # Resolve pad / eos token ids safely
        pad_id = getattr(self._processor, "pad_id",
                         self._processor.tokenizer.pad_token_id)
        eos_id = self._processor.tokenizer.eos_token_id

        with torch.no_grad():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=kwargs.get("max_new_tokens", 4096),
                temperature=None,
                do_sample=False,
                num_beams=1,
                pad_token_id=pad_id,
                eos_token_id=eos_id,
            )

        prompt_len = inputs["input_ids"].shape[1]
        generated  = output_ids[0, prompt_len:]
        raw_text   = self._processor.decode(generated, skip_special_tokens=True)

        # post_process_transcription returns list of dicts with
        # {text, speaker, start, end} when diarisation is available
        try:
            segments = self._processor.post_process_transcription(raw_text)
        except Exception:
            segments = [{"text": raw_text}]

        full_text = " ".join(s.get("text", "") for s in segments).strip() or raw_text

        return STTResult(
            text=full_text,
            language=language or "auto",
            segments=segments,
        )

    def list_voices(self) -> List[VoiceInfo]:
        return []

    def to_status_dict(self) -> dict:
        d = super().to_status_dict()
        d["note"] = "Supports speaker diarisation and timestamps in output segments."
        return d


# ── contextlib shim for Python < 3.7 ─────────────────────────────────────────

try:
    from contextlib import nullcontext as contextlib_nullcontext
except ImportError:
    from contextlib import contextmanager

    @contextmanager
    def contextlib_nullcontext():
        yield
