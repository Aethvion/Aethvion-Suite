from typing import Optional, Dict, Any
from .bridge import TrackingBridge
from .trackers.base import BaseTracker

class TrackingCore:
    """
    Main manager for the Tracking Module.
    Handles the instantiation and switching of trackers, and ensures
    their output is streamed securely through the TrackingBridge.
    """

    def __init__(self):
        self.bridge = TrackingBridge()
        self.active_tracker: Optional[BaseTracker] = None
        self.tracker_registry: Dict[str, callable] = self._build_registry()

    def _build_registry(self) -> Dict[str, callable]:
        """Discover and register all available tracking backends."""
        trackers = {}

        try:
            from .trackers.mediapipe_tracker import MediaPipeTracker, MP_AVAILABLE
            if MP_AVAILABLE:
                trackers["mediapipe"] = MediaPipeTracker
                print("[Tracking] Backend registered: mediapipe")
            else:
                print("[Tracking] MediaPipe unavailable — skipping mediapipe backend")
        except Exception as e:
            print(f"[Tracking] Failed to load mediapipe backend: {e}")

        try:
            from .trackers.openseeface_tracker import OpenSeeFaceTracker
            trackers["openseeface"] = OpenSeeFaceTracker
            print("[Tracking] Backend registered: openseeface")
        except Exception as e:
            print(f"[Tracking] Failed to load openseeface backend: {e}")

        if not trackers:
            print("[Tracking] WARNING: No tracking backends available.")

        return trackers

    def start_tracker(self, tracker_name: str, config: Optional[Dict[str, Any]] = None) -> bool:
        """Initialize and start a specific tracking backend."""
        tracker_name = tracker_name.lower()
        if tracker_name not in self.tracker_registry:
            print(f"[Tracking] Error: Tracker '{tracker_name}' not found.")
            return False

        if self.active_tracker and self.active_tracker.is_running:
            self.stop_tracker()

        # Instantiate tracking class
        tracker_class = self.tracker_registry[tracker_name]
        self.active_tracker = tracker_class(config=config)

        # Connect the tracker's emit output directly to the bridge's broadcast
        self.active_tracker.on_tracking_data(self.bridge.broadcast)
        
        # Start the video/processing loop
        self.active_tracker.start()
        print(f"[Tracking] Started tracker backend: {tracker_name}")
        return True

    def stop_tracker(self) -> None:
        """Stop the currently running tracker."""
        if self.active_tracker:
            self.active_tracker.stop()
            self.active_tracker = None
            print("[Tracking] Active tracker stopped.")

    def get_supported_trackers(self) -> list:
        """Returns list of string names for available tracking backends."""
        return list(self.tracker_registry.keys())

# Create a singleton instance for simplified module-level imports
tracking_core = TrackingCore()
