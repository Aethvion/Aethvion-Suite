import threading
import time
import cv2
import mss
import numpy as np
from typing import Optional, Dict, Any

class CaptureManager:
    """
    Singleton Manager for Optical Hardware Access (Webcam/Screen).
    Allows Synapse Trackers and the Dashboard Preview to share the same feed.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CaptureManager, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self.cap: Optional[cv2.VideoCapture] = None
        self.sct: Optional[mss.mss] = None
        self.monitor: Optional[Dict] = None
        self.source_type = "webcam:0"
        
        self.latest_raw_frame = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self, source: str = "webcam:0"):
        """Initialize hardware and start the capture thread."""
        with self._lock:
            if self._running and self.source_type == source:
                return
            
            if self._running:
                self.stop()

            self.source_type = source
            self._running = True
            self._thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._thread.start()
            print(f"[CaptureManager] Started capturing from {source}")

    def stop(self):
        """Stop the capture thread and release hardware."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        
        with self._lock:
            if self.cap:
                self.cap.release()
                self.cap = None
            if self.sct:
                self.sct = None
            self.latest_raw_frame = None
        print("[CaptureManager] Hardware released.")

    def get_frame(self) -> Optional[np.ndarray]:
        """Returns the latest captured frame as a BGR numpy array."""
        return self.latest_raw_frame

    def _capture_loop(self):
        """Internal loop that polls the hardware."""
        try:
            if self.source_type.startswith("webcam"):
                idx = int(self.source_type.split(":")[1])
                self.cap = cv2.VideoCapture(idx)
                if not self.cap.isOpened():
                    print(f"[CaptureManager] Error: Could not open webcam {idx}")
                    self._running = False
                    return
            elif self.source_type.startswith("monitor"):
                idx = int(self.source_type.split(":")[1])
                self.sct = mss.mss()
                monitors = self.sct.monitors
                self.monitor = monitors[idx] if idx < len(monitors) else monitors[0]
            
            while self._running:
                frame = None
                if self.cap:
                    success, frame = self.cap.read()
                    if success:
                        frame = cv2.flip(frame, 1) # Mirror webcam
                elif self.sct and self.monitor:
                    sct_img = self.sct.grab(self.monitor)
                    frame = np.array(sct_img)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                if frame is not None:
                    self.latest_raw_frame = frame
                
                time.sleep(1/30.0) # Cap capture at 30 FPS
        except Exception as e:
            print(f"[CaptureManager] Loop Error: {e}")
        finally:
            self._running = False

# Singleton instance
capture_manager = CaptureManager()
