"""
Aethvion Audio Editor - Multi-Track Core
Provides Track and MultiTrackSession replacing the old single-file AudioSession.
Effects are stored as non-destructive modifier chains applied at render time.
"""

import io
import uuid
from pathlib import Path
from typing import Optional, Dict, List

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

# Register bundled ffmpeg/ffprobe binaries (installed via static-ffmpeg).
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

# Colours assigned to tracks in order

TRACK_COLORS = [
    "#00d9ff", "#ff6b6b", "#ffd93d", "#6bcb77",
    "#4d96ff", "#ff922b", "#cc5de8", "#20c997",
]

# Pure effect helpers

def _uid() -> str:
    return str(uuid.uuid4())[:8]


def _apply_one(audio: "AudioSegment", op: str, params: dict) -> "AudioSegment":
    """Apply a single named operation to an AudioSegment. Pure — never mutates."""
    try:
        if op == "fade_in":
            dur = max(1, min(int(params.get("duration_ms", 1000)), len(audio)))
            return audio.fade_in(dur)
        if op == "fade_out":
            dur = max(1, min(int(params.get("duration_ms", 1000)), len(audio)))
            return audio.fade_out(dur)
        if op == "normalize":
            return normalize(audio)
        if op == "volume":
            return audio + float(params.get("db", 0))
        if op == "speed":
            rate = max(0.25, min(4.0, float(params.get("rate", 1.0))))
            new_rate = int(audio.frame_rate * rate)
            return audio._spawn(
                audio.raw_data, overrides={"frame_rate": new_rate}
            ).set_frame_rate(audio.frame_rate)
        if op == "reverse":
            return audio.reverse()
        if op == "crop_silence":
            from pydub.silence import detect_nonsilent
            thresh = float(params.get("threshold_db", -50))
            ranges = detect_nonsilent(audio, min_silence_len=100, silence_thresh=thresh)
            if ranges:
                return audio[ranges[0][0]: ranges[-1][1]]
        if op == "trim":
            s = int(params.get("start_ms", 0))
            e = int(params.get("end_ms", len(audio)))
            return audio[s:e]
    except Exception:
        pass
    return audio


def _apply_chain(audio: "AudioSegment", effects: list) -> "AudioSegment":
    """Walk the effect list, skipping disabled entries."""
    result = audio
    for fx in effects:
        if fx.get("enabled", True):
            result = _apply_one(result, fx["op"], fx.get("params", {}))
    return result


def _get_waveform(audio: "AudioSegment", num_points: int = 2000) -> dict:
    """Return peak + RMS amplitude arrays for professional dual-layer waveform display.

    Returns a dict ``{"peaks": [...], "rms": [...]}`` where each list has
    *num_points* floats in [0, 1].  Peak shows transients (outer envelope),
    RMS shows perceived loudness (inner body) — exactly what Ableton, Reaper,
    etc. render.  Falls back to empty lists when numpy is unavailable.
    """
    if not NUMPY_AVAILABLE or not audio:
        return {"peaks": [], "rms": []}

    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
    if audio.channels == 2:
        samples = samples.reshape(-1, 2).mean(axis=1)
    max_val = float(2 ** (audio.sample_width * 8 - 1)) or 1.0
    samples = samples / max_val

    total = len(samples)
    chunk = max(1, total // num_points)
    peaks: list = []
    rms_vals: list = []

    for i in range(num_points):
        seg = samples[i * chunk: (i + 1) * chunk]
        if len(seg):
            peaks.append(float(np.max(np.abs(seg))))
            rms_vals.append(float(np.sqrt(np.mean(seg ** 2))))
        else:
            peaks.append(0.0)
            rms_vals.append(0.0)

    return {"peaks": peaks, "rms": rms_vals}


def _load_audio(data: bytes, filename: str) -> "AudioSegment":
    """Decode raw bytes into an AudioSegment using format-specific loaders."""
    ext = Path(filename).suffix.lower().lstrip(".")
    buf = io.BytesIO(data)
    try:
        if ext == "wav":
            return AudioSegment.from_wav(buf)
        if ext == "ogg":
            return AudioSegment.from_ogg(buf)
        if ext == "mp3":
            return AudioSegment.from_mp3(buf)
        if ext == "flac":
            return AudioSegment.from_file(buf, format="flac")
        fmt = {"aac": "aac", "m4a": "mp4", "wma": "asf", "opus": "ogg"}.get(ext, ext)
        return AudioSegment.from_file(buf, format=fmt)
    except FileNotFoundError:
        raise RuntimeError(
            f"FFmpeg is required to open .{ext} files. "
            "Run: pip install static-ffmpeg, or use a WAV file."
        )


# Track

class Track:
    """One audio clip in the multi-track workspace."""

    def __init__(self, audio: "AudioSegment", filename: str, color: str):
        self.track_id: str = _uid()
        self.name: str = Path(filename).stem
        self.filename: str = filename
        self.original: "AudioSegment" = audio
        self.start_ms: float = 0.0       # Position in the workspace timeline
        self.muted: bool = False
        self.color: str = color
        self.effects: List[dict] = []    # [{effect_id, op, params, enabled}, ...]
        self._waveform: Optional[list] = None

    # --- Effects ---

    def add_effect(self, op: str, params: dict) -> dict:
        fx = {"effect_id": _uid(), "op": op, "params": dict(params or {}), "enabled": True}
        self.effects.append(fx)
        return fx

    def remove_effect(self, effect_id: str) -> bool:
        before = len(self.effects)
        self.effects = [f for f in self.effects if f["effect_id"] != effect_id]
        return len(self.effects) < before

    def get_effect(self, effect_id: str) -> Optional[dict]:
        return next((f for f in self.effects if f["effect_id"] == effect_id), None)

    def reorder_effects(self, ordered_ids: list):
        by_id = {f["effect_id"]: f for f in self.effects}
        ordered = [by_id[i] for i in ordered_ids if i in by_id]
        remainder = [f for f in self.effects if f["effect_id"] not in set(ordered_ids)]
        self.effects = ordered + remainder

    # --- Audio ---

    def get_rendered(self) -> "AudioSegment":
        """Return audio with all enabled effects applied (non-destructive)."""
        return _apply_chain(self.original, self.effects)

    def get_waveform(self, num_points: int = 2000) -> dict:
        if self._waveform is None:
            self._waveform = _get_waveform(self.original, num_points)
        return self._waveform

    # --- Serialise ---

    def to_dict(self, include_waveform: bool = True) -> dict:
        d = {
            "track_id": self.track_id,
            "name": self.name,
            "filename": self.filename,
            "duration_ms": len(self.original),
            "start_ms": self.start_ms,
            "end_ms": self.start_ms + len(self.original),
            "muted": self.muted,
            "color": self.color,
            "sample_rate": self.original.frame_rate,
            "channels": self.original.channels,
            "bit_depth": self.original.sample_width * 8,
            "effects": self.effects,
        }
        if include_waveform:
            d["waveform"] = self.get_waveform(2000)
        return d


# MultiTrackSession

class MultiTrackSession:
    """Holds all tracks, manages workspace length, and renders the mix."""

    def __init__(self):
        self._tracks: Dict[str, Track] = {}
        self._order: List[str] = []     # Display order (top → bottom)
        self.workspace_ms: float = 0.0  # Explicit workspace length

    # --- Track management ---

    def add_track(
        self, data: bytes, filename: str, start_ms: Optional[float] = None
    ) -> Track:
        if not PYDUB_AVAILABLE:
            raise RuntimeError("pydub is not installed. Run: pip install pydub")
        audio = _load_audio(data, filename)
        color = TRACK_COLORS[len(self._tracks) % len(TRACK_COLORS)]
        track = Track(audio, filename, color)

        if start_ms is not None:
            track.start_ms = max(0.0, start_ms)
        elif self._tracks:
            # Default: place right after the last track ends, no overlap
            track.start_ms = max(
                t.start_ms + len(t.original) for t in self._tracks.values()
            )

        self._tracks[track.track_id] = track
        self._order.append(track.track_id)
        self._auto_expand()
        return track

    def remove_track(self, track_id: str) -> bool:
        if track_id not in self._tracks:
            return False
        del self._tracks[track_id]
        self._order = [i for i in self._order if i != track_id]
        self._auto_expand()
        return True

    def get_track(self, track_id: str) -> Optional[Track]:
        return self._tracks.get(track_id)

    def get_tracks_ordered(self) -> List[Track]:
        return [self._tracks[i] for i in self._order if i in self._tracks]

    def reorder_tracks(self, new_order: list):
        valid = [i for i in new_order if i in self._tracks]
        rest = [i for i in self._order if i not in set(valid)]
        self._order = valid + rest

    # --- Workspace ---

    def _auto_expand(self):
        """Expand workspace to cover all track content + 5 s padding. Never shrinks."""
        if not self._tracks:
            return
        max_end = max(
            t.start_ms + len(t.original) for t in self._tracks.values()
        )
        self.workspace_ms = max(self.workspace_ms, max_end + 5000)

    def set_workspace(self, ms: float):
        self.workspace_ms = max(1000.0, ms)
        self._auto_expand()  # Prevent shrinking below content

    # --- Mix ---

    def mix(self) -> "AudioSegment":
        """Combine all non-muted tracks at their timeline positions."""
        if not self._tracks:
            return AudioSegment.silent(duration=1000)

        total_ms = max(1000, int(self.workspace_ms))
        tracks = self.get_tracks_ordered()
        rate = max(t.original.frame_rate for t in tracks)
        channels = max(t.original.channels for t in tracks)

        base = AudioSegment.silent(duration=total_ms, frame_rate=rate).set_channels(channels)

        for track in tracks:
            if track.muted:
                continue
            rendered = track.get_rendered()
            if rendered.frame_rate != rate:
                rendered = rendered.set_frame_rate(rate)
            if rendered.channels != channels:
                rendered = rendered.set_channels(channels)
            base = base.overlay(rendered, position=max(0, int(track.start_ms)))

        return base

    def get_mix_bytes(self, fmt: str = "wav") -> bytes:
        mixed = self.mix()
        buf = io.BytesIO()
        try:
            if fmt == "mp3":
                mixed.export(buf, format="mp3", bitrate="192k")
            elif fmt == "ogg":
                mixed.export(buf, format="ogg")
            else:
                mixed.export(buf, format="wav")
        except FileNotFoundError:
            if fmt in ("mp3", "ogg"):
                raise RuntimeError(f"FFmpeg required for {fmt.upper()} export.")
            raise
        return buf.getvalue()

    # --- Serialise ---

    def to_dict(self) -> dict:
        return {
            "workspace_ms": self.workspace_ms,
            "track_count": len(self._tracks),
            "tracks": [t.to_dict() for t in self.get_tracks_ordered()],
        }


# Global session instance
session = MultiTrackSession()
