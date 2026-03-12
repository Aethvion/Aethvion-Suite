import threading
from typing import Callable, Dict, List, Optional
import time

class SynapseBridge:
    """
    Bridge layer for the Synapse Module.
    It receives standardized parameters from the active tracker and broadcasts them
    to registered listeners (e.g., Specter's VTuber engine).
    """

    def __init__(self):
        self._listeners: List[Callable[[Dict[str, float]], None]] = []
        self._last_data: Dict[str, float] = {}
        self._lock = threading.Lock()

    def subscribe(self, callback: Callable[[Dict[str, float]], None]) -> None:
        """Register a callback to receive tracking updates."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[Dict[str, float]], None]) -> None:
        """Remove a previously registered callback."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def broadcast(self, tracking_data: Dict[str, float]) -> None:
        """Broadcat tracking parameters from the tracker engine to all listeners."""
        with self._lock:
            self._last_data = tracking_data.copy()
            for listener in self._listeners:
                try:
                    listener(self._last_data)
                except Exception as e:
                    print(f"[Synapse Bridge] Listener callback error: {e}")

    def get_last_frame(self) -> Dict[str, float]:
        """Fetch the most recent tracking frame explicitly."""
        with self._lock:
            return self._last_data.copy()
