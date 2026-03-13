"""
Synapse — OpenSeeFace Tracker Backend

Receives face tracking data from a running OpenSeeFace instance via UDP
and maps it to the standard Synapse VTube parameter schema.

OpenSeeFace must be started separately and pointed at this port:
  facetracker.exe -c 0 -P 11573 -i 127.0.0.1

Project: https://github.com/emilianavt/OpenSeeFace
"""

import socket
import struct
import threading
import time
import logging
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from .base import BaseTracker


# ── Per-face field sizes (little-endian) ───────────────────────────────────────
#
# OpenSeeFace sends 68-point landmark data plus head pose per face.
# Two known layout variants:
#
#   Variant A — pose FIRST (header_size=12 or 4, face_size=1712):
#     face_id(4) + time(4) + confidence(4) + pnp_error(4)
#     + quaternion(16) + euler(12) + translation(12)
#     + lm_conf(272) + lm_2d(544) + lm_3d(816)
#     + gaze(16) + eye_open(8)  → 1712 bytes
#
#   Variant B — landmarks FIRST (header_size=12 or 4, face_size=1716):
#     face_id(4) + time(4)
#     + lm_conf(272) + lm_2d(544) + lm_3d(816)
#     + right_gaze(8) + left_gaze(8) + right_open(4) + left_open(4)
#     + success(4) + pnp_error(4)
#     + quaternion(16) + euler(12) + translation(12) + confidence(4)  → 1716 bytes
#
# The parser tries all reasonable (header_size, face_size) combinations
# and auto-detects the one that produces valid data.

_SZ_FACE_A = 1712
_SZ_FACE_B = 1716

# Candidate (header_bytes, face_bytes) pairs in order of likelihood
_FORMAT_CANDIDATES: Tuple[Tuple[int, int], ...] = (
    (12, _SZ_FACE_A),   # 12-byte header, pose-first
    ( 4, _SZ_FACE_A),   #  4-byte header, pose-first
    ( 0, _SZ_FACE_A),   # no header,      pose-first
    (12, _SZ_FACE_B),   # 12-byte header, landmarks-first
    ( 4, _SZ_FACE_B),   #  4-byte header, landmarks-first
    ( 0, _SZ_FACE_B),   # no header,      landmarks-first
)

# Seconds without a packet before we mark is_detected=False
_STALE_TIMEOUT = 2.0

_CANVAS_W = 640
_CANVAS_H = 480
_BG_COLOR = (10, 10, 18)

# EMA smoothing factor for fallback bounding-box (lower = smoother, more lag)
_BBOX_ALPHA = 0.08

# 68-point landmark connectivity for wireframe drawing
_SEGMENTS = [
    list(range(0, 17)),              # jaw line
    list(range(17, 22)),             # left eyebrow
    list(range(22, 27)),             # right eyebrow
    list(range(27, 31)),             # nose bridge
    list(range(31, 36)),             # nose bottom
    list(range(36, 42)) + [36],      # left eye  (closed loop)
    list(range(42, 48)) + [42],      # right eye (closed loop)
    list(range(48, 60)) + [48],      # outer mouth (closed loop)
    list(range(60, 68)) + [60],      # inner mouth (closed loop)
]
_SEG_COLORS = {
    5: (100, 220, 100), 6: (100, 220, 100),   # eyes — green
    7: (200, 80,  200), 8: (200, 80,  200),   # mouth — magenta
}


class OpenSeeFaceTracker(BaseTracker):
    """
    Synapse tracking backend that receives data from OpenSeeFace via UDP.
    Auto-detects the packet format variant in use.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        cfg = config or {}
        # Bind to 0.0.0.0 to accept packets regardless of which interface OSF uses
        self._listen_host: str = "0.0.0.0"
        self._port: int = int(cfg.get("osf_port", 11573))
        self._camera_index: int = int(cfg.get("camera_index", 0))
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._last_packet_time: float = 0.0
        self._detected_fmt: Optional[Tuple[int, int]] = None   # (hdr_size, face_size)
        self.latest_frame: Optional[bytes] = None

        # Camera capture (shared with OSF — may fail if cam is exclusive)
        self._cap = None
        self._cam_w: int = _CANVAS_W
        self._cam_h: int = _CANVAS_H
        self._cam_ok: bool = False

        # EMA-smoothed bounding box for fallback dark-canvas rendering
        # Tuple[min_x, min_y, max_x, max_y] in OSF pixel space
        self._bbox_ema: Optional[Tuple[float, float, float, float]] = None

        # Exposed debug stats (read via /api/trackers/debug)
        self.stats: Dict[str, Any] = {
            "packets_received": 0,
            "packets_parsed":   0,
            "last_size":        0,
            "format":           "auto-detecting",
            "last_error":       "",
        }

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.settimeout(1.0)

        try:
            self._sock.bind((self._listen_host, self._port))
        except OSError as e:
            msg = f"Cannot bind UDP 0.0.0.0:{self._port} — {e}"
            logger.error(f"[OSF] {msg}")
            self.stats["last_error"] = msg
            self._sock.close()
            self._sock = None
            return

        # Try to open camera for background feed.
        # On Windows a camera may be locked by facetracker.exe — fail silently.
        if CV2_AVAILABLE:
            try:
                cap = cv2.VideoCapture(self._camera_index, cv2.CAP_DSHOW)
                if cap.isOpened():
                    self._cam_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    self._cam_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    self._cap = cap
                    self._cam_ok = True
                    logger.info(f"[OSF] Camera {self._camera_index} opened "
                                f"({self._cam_w}×{self._cam_h})")
                else:
                    cap.release()
                    logger.info(f"[OSF] Camera {self._camera_index} unavailable "
                                "(likely locked by facetracker.exe); using dark canvas")
            except Exception as exc:
                logger.info(f"[OSF] Camera open failed: {exc}; using dark canvas")

        self._running = True
        self._thread = threading.Thread(target=self._receive_loop, daemon=True, name="OSF-Recv")
        self._thread.start()
        logger.info(f"[OSF] Listening on UDP 0.0.0.0:{self._port}")
        self._render_waiting_frame()

    def stop(self) -> None:
        self._running = False
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
            self._cam_ok = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._bbox_ema = None
        self.latest_frame = None
        logger.info("[OSF] Tracker stopped.")

    # ── UDP receive loop ───────────────────────────────────────────────────────

    def _receive_loop(self) -> None:
        while self._running:
            try:
                data, addr = self._sock.recvfrom(65536)
                self._last_packet_time = time.time()
                self.stats["packets_received"] += 1
                self.stats["last_size"] = len(data)

                params = self._parse_packet(data)
                if params is not None:
                    self.stats["packets_parsed"] += 1
                    self.emit(params)
                else:
                    # Packet arrived but couldn't be parsed — reset stale timer
                    # so the stale path doesn't interfere, but log the issue once
                    if self.stats["packets_received"] == 1:
                        logger.warning(
                            f"[OSF] First packet ({len(data)} bytes) could not be parsed. "
                            f"Expected sizes: {[h+f for h,f in _FORMAT_CANDIDATES]}. "
                            f"Check that OpenSeeFace is sending to port {self._port}."
                        )
                        self.stats["last_error"] = (
                            f"Unrecognised packet ({len(data)} B). "
                            f"Expected one of: {sorted(set(h+f for h,f in _FORMAT_CANDIDATES))}"
                        )

            except socket.timeout:
                if self._last_packet_time > 0 and (time.time() - self._last_packet_time) > _STALE_TIMEOUT:
                    self._broadcast_stale()
            except OSError:
                break
            except Exception as e:
                logger.debug(f"[OSF] Receive error: {e}")

    # ── Packet auto-detection + parsing ───────────────────────────────────────

    def _parse_packet(self, data: bytes) -> Optional[Dict[str, float]]:
        size = len(data)

        # If we've already locked onto a format, try it first
        if self._detected_fmt:
            hdr, fsz = self._detected_fmt
            if size >= hdr + fsz:
                result = self._try_format(data, hdr, fsz)
                if result is not None:
                    return result
            # Format no longer matches (packet size changed?) — re-detect
            self._detected_fmt = None
            self.stats["format"] = "re-detecting"

        # Try all candidate formats
        for hdr_size, face_size in _FORMAT_CANDIDATES:
            if size < hdr_size + face_size:
                continue
            result = self._try_format(data, hdr_size, face_size)
            if result is not None:
                self._detected_fmt = (hdr_size, face_size)
                label = f"hdr={hdr_size}B face={'A' if face_size == _SZ_FACE_A else 'B'}({face_size}B)"
                self.stats["format"] = label
                logger.info(f"[OSF] Auto-detected packet format: {label} (packet size {size}B)")
                return result

        return None

    def _try_format(self, data: bytes, hdr_size: int, face_size: int) -> Optional[Dict[str, float]]:
        """Try to parse using a specific (header_size, face_size) combination."""
        offset = hdr_size
        try:
            if face_size == _SZ_FACE_A:
                return self._parse_face_a(data, offset)
            else:
                return self._parse_face_b(data, offset)
        except (struct.error, IndexError, ZeroDivisionError):
            return None

    # ── Format A: pose first ───────────────────────────────────────────────────
    # face_id(4) + time(4) + confidence(4) + pnp_error(4)
    # + quat(16) + euler(12) + trans(12)
    # + lm_conf(272) + lm_2d(544) + lm_3d(816)
    # + gaze(16) + eye_open(8) = 1712

    def _parse_face_a(self, data: bytes, o: int) -> Optional[Dict[str, float]]:
        face_id, face_time, confidence, pnp_error = struct.unpack_from("<iiff", data, o); o += 16
        qx, qy, qz, qw = struct.unpack_from("<4f", data, o); o += 16
        pitch, yaw, roll = struct.unpack_from("<3f", data, o); o += 12
        o += 12  # translation (skip)
        o += 272  # lm_confidence (skip)
        lm_2d_raw = struct.unpack_from("<136f", data, o); o += 544
        o += 816  # lm_3d (skip)
        # gaze: right_x, right_y, left_x, left_y
        o += 16
        right_eye_open, left_eye_open = struct.unpack_from("<2f", data, o)

        lm_2d = [(lm_2d_raw[i * 2], lm_2d_raw[i * 2 + 1]) for i in range(68)]
        return self._build_params(pitch, yaw, roll, left_eye_open, right_eye_open, lm_2d, confidence)

    # ── Format B: landmarks first ──────────────────────────────────────────────
    # face_id(4) + time(4)
    # + lm_conf(272) + lm_2d(544) + lm_3d(816)
    # + right_gaze(8) + left_gaze(8)
    # + right_open(4) + left_open(4)
    # + success(4) + pnp_error(4)
    # + quat(16) + euler(12) + trans(12) + confidence(4) = 1716

    def _parse_face_b(self, data: bytes, o: int) -> Optional[Dict[str, float]]:
        o += 8   # face_id + time
        o += 272  # lm_confidence (skip)
        lm_2d_raw = struct.unpack_from("<136f", data, o); o += 544
        o += 816  # lm_3d (skip)
        o += 8   # right_gaze (skip)
        o += 8   # left_gaze (skip)
        right_eye_open, left_eye_open = struct.unpack_from("<2f", data, o); o += 8
        o += 4   # success (skip)
        o += 4   # pnp_error (skip)
        o += 16  # quaternion (skip)
        pitch, yaw, roll = struct.unpack_from("<3f", data, o); o += 12
        o += 12  # translation (skip)
        confidence = struct.unpack_from("<f", data, o)[0]

        lm_2d = [(lm_2d_raw[i * 2], lm_2d_raw[i * 2 + 1]) for i in range(68)]
        return self._build_params(pitch, yaw, roll, left_eye_open, right_eye_open, lm_2d, confidence)

    # ── Shared param builder ───────────────────────────────────────────────────

    def _build_params(self, pitch, yaw, roll, eye_l, eye_r, lm_2d, confidence) -> Dict[str, float]:
        # OSF euler angles in degrees.
        # pitch positive = looking down → invert for VTube AngleY
        # yaw  positive = turning right → AngleX directly
        # roll positive = tilting right → invert for VTube AngleZ
        angle_x = float(max(-30.0, min(30.0,  yaw)))
        angle_y = float(max(-30.0, min(30.0, -pitch)))
        angle_z = float(max(-30.0, min(30.0, -roll)))
        eye_l   = float(max(0.0, min(1.0, eye_l)))
        eye_r   = float(max(0.0, min(1.0, eye_r)))
        mouth   = self._compute_mouth_open(lm_2d)

        params = {
            "ParamAngleX":     angle_x,
            "ParamAngleY":     angle_y,
            "ParamAngleZ":     angle_z,
            "ParamEyeOpenL":   eye_l,
            "ParamEyeOpenR":   eye_r,
            "ParamMouthOpenY": mouth,
            "is_detected":     1.0 if confidence > 0.3 else 0.0,
        }
        self._render_wireframe(lm_2d, params)
        return params

    def _compute_mouth_open(self, lm_2d) -> float:
        """Inner-lip vertical distance normalised by face height."""
        try:
            upper_y = lm_2d[62][1]
            lower_y = lm_2d[66][1]
            face_h  = abs(lm_2d[8][1] - lm_2d[27][1]) or 1.0
            return float(max(0.0, min(1.0, (lower_y - upper_y) / (face_h * 0.25))))
        except (IndexError, ZeroDivisionError):
            return 0.0

    def _broadcast_stale(self) -> None:
        self.emit({
            "ParamAngleX": 0.0, "ParamAngleY": 0.0, "ParamAngleZ": 0.0,
            "ParamEyeOpenL": 1.0, "ParamEyeOpenR": 1.0,
            "ParamMouthOpenY": 0.0, "is_detected": 0.0,
        })
        self._render_waiting_frame()
        self._last_packet_time = 0.0

    # ── Wireframe rendering ────────────────────────────────────────────────────

    def _render_wireframe(self, lm_2d, params: dict) -> None:
        if not CV2_AVAILABLE:
            return

        # ── Try to grab a live camera frame ──────────────────────────────────
        cam_frame = None
        if self._cam_ok and self._cap is not None:
            try:
                ret, f = self._cap.read()
                if ret and f is not None:
                    cam_frame = f
                else:
                    # Camera lost — stop trying
                    self._cam_ok = False
                    logger.info("[OSF] Camera read failed; switching to dark canvas")
            except Exception:
                self._cam_ok = False

        if cam_frame is not None:
            self._render_on_camera(cam_frame, lm_2d, params)
        else:
            self._render_on_canvas(lm_2d, params)

    def _render_on_camera(self, cam_frame, lm_2d, params: dict) -> None:
        """Draw wireframe directly on the live camera image."""
        h, w = cam_frame.shape[:2]

        # OSF landmark coords are in the camera's pixel space.
        # Scale them to match our output frame dimensions.
        sx = w / self._cam_w
        sy = h / self._cam_h

        def to_px(x, y):
            return (
                int(max(0, min(w - 1, x * sx))),
                int(max(0, min(h - 1, y * sy))),
            )

        pts = [to_px(x, y) for x, y in lm_2d]

        for si, seg in enumerate(_SEGMENTS):
            color = _SEG_COLORS.get(si, (0, 210, 230))
            for i in range(len(seg) - 1):
                cv2.line(cam_frame, pts[seg[i]], pts[seg[i + 1]], color, 2, cv2.LINE_AA)
        for pt in pts:
            cv2.circle(cam_frame, pt, 2, (200, 200, 200), -1, cv2.LINE_AA)

        detected   = params.get("is_detected", 0) > 0
        status_col = (0, 200, 100) if detected else (80, 80, 200)
        cv2.putText(cam_frame, f"OpenSeeFace  |  {'DETECTED' if detected else 'NO FACE'}", (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, status_col, 1, cv2.LINE_AA)

        ax = params.get("ParamAngleX", 0.0)
        ay = params.get("ParamAngleY", 0.0)
        az = params.get("ParamAngleZ", 0.0)
        cv2.putText(cam_frame, f"Yaw {ax:+.1f}  Pitch {ay:+.1f}  Roll {az:+.1f}", (10, 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 180, 180), 1, cv2.LINE_AA)

        self._encode_frame(cam_frame)

    def _render_on_canvas(self, lm_2d, params: dict) -> None:
        """
        Draw wireframe on a dark canvas using an EMA-smoothed bounding box.
        EMA prevents the per-frame rescaling flicker of the old approach.
        """
        frame = np.full((_CANVAS_H, _CANVAS_W, 3), _BG_COLOR, dtype=np.uint8)

        # Filter valid (non-zero) landmark coords
        valid = [(x, y) for x, y in lm_2d if x > 0.5 or y > 0.5]
        if not valid:
            self._encode_frame(frame)
            return

        xs = [p[0] for p in valid]
        ys = [p[1] for p in valid]
        cur = (min(xs), min(ys), max(xs), max(ys))

        # Update EMA bounding box
        if self._bbox_ema is None:
            self._bbox_ema = cur
        else:
            a = _BBOX_ALPHA
            self._bbox_ema = tuple(
                a * c + (1.0 - a) * e for c, e in zip(cur, self._bbox_ema)
            )

        min_x, min_y, max_x, max_y = self._bbox_ema
        bw = max_x - min_x or 1.0
        bh = max_y - min_y or 1.0
        pad = 0.12

        def to_canvas(x, y):
            cx = int((x - min_x) / bw * _CANVAS_W * (1 - 2 * pad) + _CANVAS_W * pad)
            cy = int((y - min_y) / bh * _CANVAS_H * (1 - 2 * pad) + _CANVAS_H * pad)
            return (
                max(0, min(_CANVAS_W - 1, cx)),
                max(0, min(_CANVAS_H - 1, cy)),
            )

        pts = [to_canvas(x, y) for x, y in lm_2d]

        for si, seg in enumerate(_SEGMENTS):
            color = _SEG_COLORS.get(si, (0, 200, 220))
            for i in range(len(seg) - 1):
                cv2.line(frame, pts[seg[i]], pts[seg[i + 1]], color, 1, cv2.LINE_AA)
        for pt in pts:
            cv2.circle(frame, pt, 2, (160, 160, 160), -1, cv2.LINE_AA)

        detected   = params.get("is_detected", 0) > 0
        status_col = (0, 200, 100) if detected else (200, 60, 60)
        cv2.putText(frame, f"OpenSeeFace  |  {'DETECTED' if detected else 'NO FACE'}", (12, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, status_col, 1, cv2.LINE_AA)

        ax = params.get("ParamAngleX", 0.0)
        ay = params.get("ParamAngleY", 0.0)
        az = params.get("ParamAngleZ", 0.0)
        cv2.putText(frame, f"Yaw {ax:+.1f}  Pitch {ay:+.1f}  Roll {az:+.1f}", (12, 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (140, 140, 140), 1, cv2.LINE_AA)

        fmt = self.stats.get("format", "")
        if fmt:
            cv2.putText(frame, fmt, (12, _CANVAS_H - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, (60, 60, 80), 1, cv2.LINE_AA)

        self._encode_frame(frame)

    def _render_waiting_frame(self) -> None:
        if not CV2_AVAILABLE:
            return
        frame = np.full((_CANVAS_H, _CANVAS_W, 3), _BG_COLOR, dtype=np.uint8)
        cv2.putText(frame, "Waiting for OpenSeeFace...", (75, _CANVAS_H // 2 - 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 170, 200), 1, cv2.LINE_AA)
        cv2.putText(frame, f"UDP  0.0.0.0:{self._port}", (170, _CANVAS_H // 2 + 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 100, 100), 1, cv2.LINE_AA)
        rx = self.stats["packets_received"]
        if rx > 0:
            msg = f"Received {rx} packet(s) — {self.stats.get('last_error', 'parsing...')}"
            cv2.putText(frame, msg[:72], (12, _CANVAS_H // 2 + 44),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, (200, 120, 60), 1, cv2.LINE_AA)
        self._encode_frame(frame)

    def _encode_frame(self, frame) -> None:
        try:
            ret, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
            if ret:
                self.latest_frame = buf.tobytes()
        except Exception:
            pass
