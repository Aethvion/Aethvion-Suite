import logging
import psutil
import json
from pathlib import Path

logger = logging.getLogger(__name__)

# To calculate disk usage, we need a path. We'll use the root folder or C drive.
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

def get_hardware_telemetry(args: dict) -> str:
    """Get system CPU, RAM, and Disk usage stats."""
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage(str(PROJECT_ROOT))
        
        # We directly return the formatted string.
        return (
            f"CPU: {cpu}% | RAM: {vm.percent}% used "
            f"({vm.used // (1024**2)}MB / {vm.total // (1024**2)}MB) | "
            f"Disk: {disk.percent}% used ({disk.free // (1024**3)}GB free)"
        )
    except Exception as e:
        logger.error(f"System Link Error: {e}")
        return f"Nexus Error: Could not read hardware telemetry. {str(e)}"
