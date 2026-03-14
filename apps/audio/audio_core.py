"""
Aethvion Audio Editor - Core Processing Module
Uses pydub for audio manipulation, numpy for waveform data.
"""

import io
from pathlib import Path
from typing import Optional

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from pydub import AudioSegment
    from pydub.effects import normalize
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False


class AudioSession:
    """Holds the current audio editing session state with undo history."""

    MAX_HISTORY = 30

    def __init__(self):
        self.original: Optional["AudioSegment"] = None
        self.current: Optional["AudioSegment"] = None
        self.filename: str = ""
        self.history: list = []

    # ------------------------------------------------------------------
    # Load / Export
    # ------------------------------------------------------------------

    def load(self, data: bytes, filename: str) -> dict:
        """Load audio bytes into the session."""
        if not PYDUB_AVAILABLE:
            raise RuntimeError("pydub is not installed. Run: pip install pydub")

        ext = Path(filename).suffix.lower().lstrip(".")
        fmt_map = {
            "mp3": "mp3", "wav": "wav", "ogg": "ogg",
            "flac": "flac", "aac": "aac", "m4a": "mp4",
            "wma": "asf", "opus": "ogg",
        }
        fmt = fmt_map.get(ext, "wav")

        audio_io = io.BytesIO(data)
        self.original = AudioSegment.from_file(audio_io, format=fmt)
        self.current = self.original
        self.filename = filename
        self.history = []
        return self._get_info()

    def get_audio_bytes(self, fmt: str = "wav") -> bytes:
        """Export current audio to bytes."""
        if not self.current:
            return b""
        buf = io.BytesIO()
        if fmt == "mp3":
            self.current.export(buf, format="mp3", bitrate="192k")
        elif fmt == "ogg":
            self.current.export(buf, format="ogg")
        else:
            self.current.export(buf, format="wav")
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Info & Waveform
    # ------------------------------------------------------------------

    def _get_info(self) -> dict:
        if not self.current:
            return {}
        duration_ms = len(self.current)
        minutes = int(duration_ms / 60000)
        seconds = (duration_ms % 60000) / 1000.0
        return {
            "filename": self.filename,
            "duration_ms": duration_ms,
            "duration_display": f"{minutes}:{seconds:05.2f}",
            "sample_rate": self.current.frame_rate,
            "channels": self.current.channels,
            "bit_depth": self.current.sample_width * 8,
            "can_undo": len(self.history) > 0,
        }

    def get_waveform(self, num_points: int = 2000) -> list:
        """Compute downsampled peak amplitude array for waveform display."""
        if not self.current or not NUMPY_AVAILABLE:
            return []

        samples = np.array(self.current.get_array_of_samples(), dtype=np.float32)

        if self.current.channels == 2:
            samples = samples.reshape(-1, 2).mean(axis=1)

        max_val = float(2 ** (self.current.sample_width * 8 - 1))
        samples = samples / max_val

        total = len(samples)
        chunk_size = max(1, total // num_points)
        waveform = []
        for i in range(0, total, chunk_size):
            chunk = samples[i : i + chunk_size]
            if len(chunk) > 0:
                waveform.append(float(np.max(np.abs(chunk))))
            if len(waveform) >= num_points:
                break

        return waveform

    # ------------------------------------------------------------------
    # Undo / Reset
    # ------------------------------------------------------------------

    def _push_history(self):
        self.history.append(self.current)
        if len(self.history) > self.MAX_HISTORY:
            self.history.pop(0)

    def undo(self) -> Optional[dict]:
        if not self.history:
            return None
        self.current = self.history.pop()
        return self._get_info()

    def reset(self) -> dict:
        self.current = self.original
        self.history = []
        return self._get_info()

    # ------------------------------------------------------------------
    # Effects
    # ------------------------------------------------------------------

    def trim(self, start_ms: float, end_ms: float) -> dict:
        """Trim audio to the given range."""
        self._push_history()
        self.current = self.current[int(start_ms) : int(end_ms)]
        return self._get_info()

    def fade_in(self, duration_ms: float) -> dict:
        self._push_history()
        dur = max(1, min(int(duration_ms), len(self.current)))
        self.current = self.current.fade_in(dur)
        return self._get_info()

    def fade_out(self, duration_ms: float) -> dict:
        self._push_history()
        dur = max(1, min(int(duration_ms), len(self.current)))
        self.current = self.current.fade_out(dur)
        return self._get_info()

    def do_normalize(self) -> dict:
        self._push_history()
        self.current = normalize(self.current)
        return self._get_info()

    def reverse(self) -> dict:
        self._push_history()
        self.current = self.current.reverse()
        return self._get_info()

    def change_volume(self, db: float) -> dict:
        """Boost or cut volume by db decibels."""
        self._push_history()
        self.current = self.current + db
        return self._get_info()

    def change_speed(self, rate: float) -> dict:
        """
        Change playback speed without pitch shift.
        rate > 1 = faster, rate < 1 = slower.
        """
        self._push_history()
        rate = max(0.25, min(4.0, rate))
        new_rate = int(self.current.frame_rate * rate)
        manipulated = self.current._spawn(
            self.current.raw_data,
            overrides={"frame_rate": new_rate},
        )
        self.current = manipulated.set_frame_rate(self.current.frame_rate)
        return self._get_info()

    def silence_region(self, start_ms: float, end_ms: float) -> dict:
        """Replace a region with silence."""
        self._push_history()
        silence = AudioSegment.silent(
            duration=int(end_ms - start_ms),
            frame_rate=self.current.frame_rate,
        )
        before = self.current[: int(start_ms)]
        after = self.current[int(end_ms) :]
        self.current = before + silence + after
        return self._get_info()

    def crop_silence(self, threshold_db: float = -50.0) -> dict:
        """Strip leading and trailing silence."""
        self._push_history()
        from pydub.silence import detect_nonsilent
        ranges = detect_nonsilent(self.current, min_silence_len=100, silence_thresh=threshold_db)
        if ranges:
            self.current = self.current[ranges[0][0] : ranges[-1][1]]
        return self._get_info()

    def stereo_to_mono(self) -> dict:
        self._push_history()
        self.current = self.current.set_channels(1)
        return self._get_info()

    def mono_to_stereo(self) -> dict:
        self._push_history()
        self.current = self.current.set_channels(2)
        return self._get_info()

    def resample(self, sample_rate: int) -> dict:
        self._push_history()
        self.current = self.current.set_frame_rate(sample_rate)
        return self._get_info()


# Global session
audio_session = AudioSession()
