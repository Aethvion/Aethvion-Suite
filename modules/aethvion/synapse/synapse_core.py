from typing import Optional, Dict, Any
from .bridge import SynapseBridge
from .trackers.base import BaseTracker

class SynapseCore:
    """
    Main manager for the Synapse Module.
    Handles the instantiation and switching of trackers, and ensures
    their output is streamed securely through the SynapseBridge.
    """

    def __init__(self):
        self.bridge = SynapseBridge()
        self.active_tracker: Optional[BaseTracker] = None
        self.tracker_registry: Dict[str, callable] = self._build_registry()

    def _build_registry(self) -> Dict[str, callable]:
        """Discover and build a registry of available tracking plugins."""
        # Hardcoding the default stub for now, but this could use importlib 
        # to dynamically load plugins from the `trackers` directory.
        from .trackers.mediapipe_tracker import MediaPipeTracker
        return {
            "mediapipe": MediaPipeTracker
        }

    def start_tracker(self, tracker_name: str, config: Optional[Dict[str, Any]] = None) -> bool:
        """Initialize and start a specific tracking backend."""
        tracker_name = tracker_name.lower()
        if tracker_name not in self.tracker_registry:
            print(f"[Synapse] Error: Tracker '{tracker_name}' not found.")
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
        print(f"[Synapse] Started tracker backend: {tracker_name}")
        return True

    def stop_tracker(self) -> None:
        """Stop the currently running tracker."""
        if self.active_tracker:
            self.active_tracker.stop()
            self.active_tracker = None
            print("[Synapse] Active tracker stopped.")

    def get_supported_trackers(self) -> list:
        """Returns list of string names for available tracking backends."""
        return list(self.tracker_registry.keys())

# Create a singleton instance for simplified module-level imports
synapse_core = SynapseCore()
