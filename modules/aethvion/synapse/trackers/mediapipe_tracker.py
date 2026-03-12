import threading
import time
import math
import cv2
import numpy as np
import os
from pathlib import Path
from typing import Dict, Optional, Any
from .base import BaseTracker
from .capture_manager import capture_manager

# Global state for tracking availability
IMPORT_ERROR = None
MP_AVAILABLE = False

try:
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    MP_AVAILABLE = True
except Exception as e:
    IMPORT_ERROR = str(e)
    MP_AVAILABLE = False

# Global constants pointing to the downloaded model
MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "face_landmarker.task")

class MediaPipeTracker(BaseTracker):
    """
    MediaPipe Face Tracking Backend.
    Uses the modern Tasks API (FaceLandmarker) to generate facial landmarks
    and transform them into VTube-compatible parameters.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._thread: Optional[threading.Thread] = None
        self.latest_frame = None  
        self.source_type = self.config.get("source", "webcam:0")
        
        self.landmarker: Optional[vision.FaceLandmarker] = None
        self._initialize_landmarker()

    def _initialize_landmarker(self):
        """Initialize the Tasks-based landmarker using the float16 model."""
        if not MP_AVAILABLE:
            return

        try:
            if not os.path.exists(MODEL_PATH):
                print(f"[MediaPipeTracker] ERROR: Model missing at {MODEL_PATH}")
                return

            base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
            options = vision.FaceLandmarkerOptions(
                base_options=base_options,
                output_face_blendshapes=True,
                num_faces=1
            )
            self.landmarker = vision.FaceLandmarker.create_from_options(options)
            print("[MediaPipeTracker] Tasks Landmarker initialized successfully.")
        except Exception as e:
            print(f"[MediaPipeTracker] Failed to initialize Tasks Landmarker: {e}")

    def start(self) -> None:
        if self._running:
            return
            
        if not self.landmarker:
            # Try to re-init if it failed before
            self._initialize_landmarker()
            if not self.landmarker:
                print(f"[MediaPipeTracker] ERROR: Tracker not initialized. Details: {IMPORT_ERROR}")
                return

        self._running = True
        capture_manager.start(self.source_type)
        
        self._thread = threading.Thread(target=self._tracking_loop, daemon=True)
        self._thread.start()
        print(f"[MediaPipeTracker] Started tracking on source: {self.source_type}")

    def stop(self) -> None:
        if not self._running:
            return
            
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self.latest_frame = None

    def _get_distance(self, p1, p2):
        """Calculate Euclidean distance between two landmarks."""
        return math.hypot(p1.x - p2.x, p1.y - p2.y)

    def _tracking_loop(self):
        """Main optical loop that runs detection and emits parameters."""
        try:
            while self._running:
                start_time = time.time()
                frame = capture_manager.get_frame()

                if frame is None:
                    time.sleep(0.01)
                    continue

                processed_frame = frame.copy()
                
                # Tasks API requires mp.Image
                rgb_frame = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                
                # Perform detection synchronously in this thread
                detection_result = self.landmarker.detect(mp_image)

                # Default static parameters
                tracking_data = {
                    "ParamAngleX": 0.0, "ParamAngleY": 0.0, "ParamAngleZ": 0.0,
                    "ParamEyeOpenL": 1.0, "ParamEyeOpenR": 1.0, 
                    "ParamMouthOpenY": 0.0, "is_detected": False
                }

                if detection_result.face_landmarks:
                    tracking_data["is_detected"] = True
                    # In Tasks, landmarks are normalized by default
                    landmarks = detection_result.face_landmarks[0]
                    
                    # --- Geometric Approximations (Legacy fallback) ---
                    nose = landmarks[1]; left_bound = landmarks[234]; right_bound = landmarks[454]
                    top_bound = landmarks[10]; bottom_bound = landmarks[152]

                    face_width = right_bound.x - left_bound.x
                    nose_offset_x = (nose.x - left_bound.x) / face_width if face_width > 0 else 0.5
                    tracking_data["ParamAngleX"] = (nose_offset_x - 0.5) * 60.0

                    face_height = bottom_bound.y - top_bound.y
                    nose_offset_y = (nose.y - top_bound.y) / face_height if face_height > 0 else 0.5
                    tracking_data["ParamAngleY"] = (0.5 - nose_offset_y) * 60.0

                    # --- Blendshape Mapping (Modern precision) ---
                    if detection_result.face_blendshapes:
                        for bs in detection_result.face_blendshapes[0]:
                            if bs.category_name == 'jawOpen':
                                tracking_data["ParamMouthOpenY"] = bs.score
                            elif bs.category_name == 'eyeBlinkLeft':
                                tracking_data["ParamEyeOpenL"] = 1.0 - bs.score
                            elif bs.category_name == 'eyeBlinkRight':
                                tracking_data["ParamEyeOpenR"] = 1.0 - bs.score
                            elif bs.category_name == 'faceYaw':
                                # Override geometric yaw if blendshape is stable
                                tracking_data["ParamAngleX"] = bs.score * 30.0
                            elif bs.category_name == 'facePitch':
                                tracking_data["ParamAngleY"] = bs.score * 30.0

                    # Visual feedback indicator
                    cv2.putText(processed_frame, "AI Tracking Active", (20, 40), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 127), 2)
                    
                    # Scale factor for drawing landmarks
                    h, w, _ = processed_frame.shape
                    # Draw only key landmarks to save CPU
                    for idx in [1, 33, 263, 13, 14]: # Nose, Eyes, Mouth
                        lm = landmarks[idx]
                        cv2.circle(processed_frame, (int(lm.x * w), int(lm.y * h)), 2, (0, 0, 255), -1)

                self.emit(tracking_data)

                # MJPEG encode for dashboard preview
                ret, buffer = cv2.imencode('.jpg', processed_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
                if ret:
                    self.latest_frame = buffer.tobytes()

                # Maintain ~30 FPS
                elapsed = time.time() - start_time
                time.sleep(max(0, (1.0 / 30.0) - elapsed))

        except Exception as e:
            print(f"[MediaPipeTracker] Loop Error: {e}")
        finally:
            if self.landmarker:
                self.landmarker.close()
                self.landmarker = None
            print("[MediaPipeTracker] Processing loop terminated.")
