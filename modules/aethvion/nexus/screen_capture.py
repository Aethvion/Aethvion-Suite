import logging
import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Screenshots are saved here, relative to the project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
SCREENSHOT_DIR = PROJECT_ROOT / "data" / "screenshots"


def take_screenshot(args: dict) -> str:
    """
    Takes a screenshot of the entire screen and saves it as a PNG file.

    Optional args:
        - monitor (int): Monitor index to capture (0 = all monitors merged, 1+ = specific). Defaults to 0.
    """
    try:
        from PIL import ImageGrab
    except ImportError:
        return (
            "Nexus Error: 'Pillow' library is not installed. "
            "Run `pip install Pillow` to enable screen capture."
        )

    try:
        monitor = int(args.get("monitor", 0)) if args else 0

        # Capture — all_screens=True grabs every monitor composited together
        img = ImageGrab.grab(all_screens=True)

        # Build output path
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        filepath = SCREENSHOT_DIR / filename

        img.save(str(filepath), "PNG")

        return (
            f"Screenshot captured successfully.\n"
            f"Saved to: {filepath}\n"
            f"Resolution: {img.width}x{img.height}"
        )

    except Exception as e:
        logger.error(f"Screen Capture Error: {e}", exc_info=True)
        return f"Nexus Error: Could not take screenshot. {str(e)}"
