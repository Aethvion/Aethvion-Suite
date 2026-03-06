import cv2
import datetime
from pathlib import Path
from core.utils.logger import get_logger

logger = get_logger(__name__)

# Base directory for media storage
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
WEBCAM_DIR = PROJECT_ROOT / "data" / "workspace" / "media" / "webcam"

def capture_image(args=None):
    """
    Capture a single frame from a connected webcam.
    Args:
        index: Camera index (default 0)
    """
    index = 0
    if args and "index" in args:
        try:
            index = int(args["index"])
        except (ValueError, TypeError):
            logger.warning(f"Invalid camera index provided: {args['index']}. Defaulting to 0.")

    try:
        # Create directory early
        WEBCAM_DIR.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Attempting to open webcam at index {index}...")
        # Use CAP_DSHOW on Windows for faster initialization
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            logger.error(f"Failed to open webcam at index {index}.")
            return f"Nexus Error: Could not open webcam at index {index}."

        # Set resolution
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        logger.info("Webcam opened. Warming up...")

        # Allow camera to warm up
        for i in range(3):
            cap.read()
            logger.info(f"Warmup frame {i+1}...")

        logger.info("Capturing final frame...")
        # Read several frames to clear the hardware buffer for a fresh capture
        for _ in range(5):
            cap.read()
            
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            logger.error("Failed to capture frame from webcam (ret=False or frame=None).")
            return "Nexus Error: Failed to capture frame from webcam."

        # Build output path
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"webcam_{timestamp}.jpg"
        filepath = WEBCAM_DIR / filename
        logger.info(f"Saving webcam image to {filepath}...")

        # Save the image
        success = cv2.imwrite(str(filepath), frame)
        if not success:
            logger.error(f"Failed to write image file: {filepath}")
            return f"Nexus Error: Failed to save captured image to {filepath}"

        return (
            f"Webcam image captured successfully.\n"
            f"Saved to: {filepath}\n"
            f"Resolution: {frame.shape[1]}x{frame.shape[0]}"
        )

    except Exception as e:
        logger.error(f"Webcam capture error: {e}", exc_info=True)
        return f"Nexus Error: {str(e)}"
