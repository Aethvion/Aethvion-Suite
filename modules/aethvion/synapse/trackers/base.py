from typing import Callable, Optional, Dict, Any

class BaseTracker:
    """
    Base class for all Synapse tracking backends.
    Any custom tracker (e.g., MediaPipe, OpenSeeFace, generic webcam) must inherit from this.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._callback: Optional[Callable[[Dict[str, float]], None]] = None
        self._running = False

    def on_tracking_data(self, callback: Callable[[Dict[str, float]], None]) -> None:
        """
        Register a callback that receives standardized tracking parameters.
        The parameters should map to generic VTube output format (e.g. ParamAngleX).
        """
        self._callback = callback

    def start(self) -> None:
        """Start the tracking backend (should be non-blocking or managed via thread)."""
        raise NotImplementedError("Trackers must implement the 'start' method.")

    def stop(self) -> None:
        """Stop the tracking backend and release resources."""
        raise NotImplementedError("Trackers must implement the 'stop' method.")

    def emit(self, tracking_data: Dict[str, float]) -> None:
        """Emit data to the registered listeners."""
        if self._callback:
            self._callback(tracking_data)

    @property
    def is_running(self) -> bool:
        return self._running
