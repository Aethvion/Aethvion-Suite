import logging
import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Screenshots are saved here, relative to the project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
SCREENSHOT_DIR = PROJECT_ROOT / "data" / "workspace" / "media" / "screenshots"


def take_screenshot(args: dict) -> str:
    """
    Takes a screenshot of a specific screen or all screens merged.

    Optional args:
        - monitor (int): Monitor index (0 = all, 1 = first monitor, etc.). Defaults to 0.
    """
    try:
        import mss
        import mss.tools
    except ImportError:
        return (
            "Nexus Error: 'mss' library is not installed. "
            "Run `pip install mss` to enable multi-monitor screen capture."
        )

    try:
        monitor_idx = 0
        if args and "monitor" in args:
            try:
                monitor_idx = int(args["monitor"])
            except (ValueError, TypeError):
                logger.warning(f"Invalid monitor index provided: {args['monitor']}. Defaulting to 0.")

        with mss.mss() as sct:
            monitors = sct.monitors
            logger.info(f"Detected {len(monitors)-1} physical monitors. Total monitors in list: {len(monitors)}")
            
            if monitor_idx < 0 or monitor_idx >= len(monitors):
                msg = f"Monitor index {monitor_idx} out of range. Available: 0 (all), 1 to {len(monitors)-1}."
                logger.error(msg)
                return f"Nexus Error: {msg}"

            # Capture the specified monitor
            target_monitor = monitors[monitor_idx]
            logger.info(f"Capturing monitor {monitor_idx}: {target_monitor}")
            sct_img = sct.grab(target_monitor)

            # Build output path within project
            month_str = datetime.datetime.now().strftime("%Y-%m")
            target_dir = SCREENSHOT_DIR / month_str
            target_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            filepath = target_dir / filename

            # Convert to PNG using mss.tools
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(filepath))

            monitor_desc = "All Monitors" if monitor_idx == 0 else f"Monitor {monitor_idx}"
            return (
                f"Screenshot captured successfully ({monitor_desc}).\n"
                f"Saved to: {filepath}\n"
                f"Resolution: {sct_img.width}x{sct_img.height}"
            )

    except Exception as e:
        logger.error(f"Screen Capture Error: {e}", exc_info=True)
        return f"Nexus Error: Could not take screenshot. {str(e)}"
