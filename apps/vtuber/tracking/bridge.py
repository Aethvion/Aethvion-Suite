"""
apps/vtuber/tracking/bridge.py
──────────────────────────────
Async WebSocket client bridge to the Aethvion Tracking Engine.

Used by the VTuber server (or any other Python consumer) to subscribe to live
face-tracking parameters from the standalone Tracking Engine running at
ws://localhost:{SYNAPSE_PORT}/ws/tracking.

Quick usage
-----------
    import asyncio
    from apps.vtuber.tracking.bridge import TrackingBridge

    async def main():
        bridge = TrackingBridge()
        bridge.on_params(lambda p: print(p))
        await bridge.run()   # blocks until stopped

    asyncio.run(main())

Non-blocking usage (embed in an existing asyncio app)
------------------------------------------------------
    bridge = TrackingBridge()
    bridge.on_params(handle_params)
    task = asyncio.create_task(bridge.run())
    ...
    bridge.stop()
    await task
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Callable, Optional

log = logging.getLogger(__name__)

# Parameter schema reference

#: Standard parameter names emitted by the Tracking Engine.
TRACKING_PARAMS = {
    "ParamAngleX":     (-30.0,  30.0),   # head yaw  (left / right)
    "ParamAngleY":     (-30.0,  30.0),   # head pitch (up / down)
    "ParamAngleZ":     (-30.0,  30.0),   # head roll  (tilt)
    "ParamEyeOpenL":   (  0.0,   1.0),   # left eye  open (0 = closed)
    "ParamEyeOpenR":   (  0.0,   1.0),   # right eye open
    "ParamMouthOpenY": (  0.0,   1.0),   # jaw open
    "ParamMouthForm":  ( -1.0,   1.0),   # smile / frown
    "ParamBrowLY":     ( -1.0,   1.0),   # left brow height
    "ParamBrowRY":     ( -1.0,   1.0),   # right brow height
    "is_detected":     (  0.0,   1.0),   # 1 = face detected
}

# Default param → raw-tracking-key mapping (used by legacy _emit helper)
DEFAULT_MAPPING: dict[str, str] = {
    "head_yaw":      "ParamAngleX",
    "head_pitch":    "ParamAngleY",
    "head_roll":     "ParamAngleZ",
    "eye_open_left": "ParamEyeOpenL",
    "eye_open_right":"ParamEyeOpenR",
    "mouth_open":    "ParamMouthOpenY",
    "mouth_smile":   "ParamMouthForm",
    "brow_left_y":   "ParamBrowLY",
    "brow_right_y":  "ParamBrowRY",
}


# TrackingBridge

class TrackingBridge:
    """
    Async WebSocket client that connects to the Tracking Engine and forwards
    ``{type: "params", params: {...}}`` messages to registered callbacks.

    The bridge auto-reconnects on disconnect (with exponential backoff up to
    ``max_retry_delay`` seconds) and can be stopped gracefully via ``stop()``.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: Optional[int] = None,
        path: str = "/ws/tracking",
        reconnect: bool = True,
        max_retry_delay: float = 30.0,
    ) -> None:
        self._port    = port or int(os.getenv("SYNAPSE_PORT", "8082"))
        self._host    = host
        self._path    = path
        self._reconnect       = reconnect
        self._max_retry_delay = max_retry_delay

        self._callback: Optional[Callable[[dict], None]] = None
        self._running  = False
        self._stop_evt = asyncio.Event()
        self._ws       = None

    # Public API

    @property
    def ws_url(self) -> str:
        return f"ws://{self._host}:{self._port}{self._path}"

    @property
    def is_running(self) -> bool:
        return self._running

    def on_params(self, callback: Callable[[dict], None]) -> None:
        """Register a callback that receives standardised parameter dicts."""
        self._callback = callback

    def stop(self) -> None:
        """Signal the bridge to stop (graceful, async-safe)."""
        self._running = False
        self._stop_evt.set()
        if self._ws:
            asyncio.ensure_future(self._ws.close())

    async def run(self) -> None:
        """
        Connect and listen.  Reconnects automatically unless *reconnect* is
        False or ``stop()`` has been called.
        """
        self._running  = True
        self._stop_evt.clear()
        delay = 1.0

        while self._running:
            try:
                await self._connect_and_listen()
                delay = 1.0   # reset backoff on clean close
            except Exception as exc:
                if not self._running:
                    break
                log.warning("[TrackingBridge] %s — retry in %.0fs", exc, delay)
                try:
                    await asyncio.wait_for(self._stop_evt.wait(), timeout=delay)
                    break  # stop() was called during sleep
                except asyncio.TimeoutError:
                    pass
                if not self._reconnect:
                    break
                delay = min(delay * 2, self._max_retry_delay)

        self._running = False
        log.info("[TrackingBridge] Stopped.")

    # Internal

    async def _connect_and_listen(self) -> None:
        """Open one WebSocket connection and process messages until it closes."""
        try:
            import websockets  # optional dependency
        except ImportError:
            raise RuntimeError(
                "The 'websockets' package is required for TrackingBridge. "
                "Install it with:  pip install websockets"
            )

        log.info("[TrackingBridge] Connecting to %s", self.ws_url)
        async with websockets.connect(self.ws_url) as ws:
            self._ws = ws
            log.info("[TrackingBridge] Connected.")
            async for raw in ws:
                if not self._running:
                    break
                try:
                    msg = json.loads(raw)
                    if msg.get("type") == "params" and self._callback:
                        self._callback(msg["params"])
                except Exception:
                    pass
            self._ws = None

    # Legacy helper (synchronous emit for non-async callers)

    def _emit(self, raw_tracking: dict) -> None:
        """
        Convert a raw-key tracking dict to standard param names and call the
        callback synchronously.  Kept for backward compatibility.
        """
        if not self._callback:
            return
        params = {}
        for raw_key, param_id in DEFAULT_MAPPING.items():
            if raw_key in raw_tracking:
                params[param_id] = raw_tracking[raw_key]
        self._callback(params)


# Convenience: synchronous one-shot snapshot fetch

def get_last_params(
    host: str = "127.0.0.1",
    port: Optional[int] = None,
    timeout: float = 1.0,
) -> Optional[dict]:
    """
    Synchronously fetch the most-recently-broadcast parameter frame from the
    Tracking Engine REST API.  Returns ``None`` if the server is unreachable.

        params = get_last_params()
        if params:
            print(params["ParamAngleX"])
    """
    import urllib.request, json as _json
    _port = port or int(os.getenv("SYNAPSE_PORT", "8082"))
    url   = f"http://{host}:{_port}/api/trackers"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = _json.loads(resp.read())
            return data  # returns tracker status; extend if server exposes /last-frame
    except Exception:
        return None
