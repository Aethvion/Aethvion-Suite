import importlib
import logging
from pathlib import Path

from core.utils import load_json, atomic_json_write

logger = logging.getLogger(__name__)

PROJECT_ROOT  = Path(__file__).parent.parent.parent
REGISTRY_FILE = Path(__file__).parent / "registry.json"

def get_registry() -> dict:
    """Load the Bridge registry."""
    return load_json(REGISTRY_FILE, default={"modules": []})

def save_registry(registry: dict) -> None:
    """Persist the Bridge registry atomically."""
    atomic_json_write(REGISTRY_FILE, registry)

def update_auth_state(module_id: str, is_authorized: bool):
    """Updates the authorization state of a module."""
    registry = get_registry()
    for mod in registry.get("modules", []):
        if mod["id"] == module_id:
            mod["is_authorized"] = is_authorized
            break
    save_registry(registry)

def call_module(module_id: str, command: str, args: dict = None) -> str:
    """
    Dynamically loads a Bridge module and calls a command.
    Includes an execution sandbox to catch errors.
    """
    if args is None:
        args = {}

    registry = get_registry()
    module_info = next((m for m in registry.get("modules", []) if m["id"] == module_id), None)

    if not module_info:
        return f"Bridge Error: Module '{module_id}' not found in registry."

    if not module_info.get("enabled", True):
        return f"Bridge Error: Module '{module_id}' is currently disabled."

    module_path = module_info.get("module_path")
    if not module_path:
        return f"Bridge Error: Module '{module_id}' has no module_path defined."

    # Security: only allow modules inside the core.bridges package.
    # This prevents a tampered registry.json from loading arbitrary system modules.
    _ALLOWED_PREFIX = "core.bridges."
    if not module_path.startswith(_ALLOWED_PREFIX):
        logger.error(
            f"Bridge Security: Refusing to import '{module_path}' — "
            f"only '{_ALLOWED_PREFIX}*' modules are permitted."
        )
        return (
            f"Bridge Error: Module '{module_id}' has an invalid module_path "
            f"(must be within core.bridges)."
        )

    # Security: block dunder / private attribute access to prevent abuse via getattr.
    if not command or command.startswith("_"):
        logger.error(
            f"Bridge Security: Refusing command '{command}' — "
            "commands must not start with an underscore."
        )
        return f"Bridge Error: Invalid command '{command}'."

    try:
        # Import the module dynamically
        module = importlib.import_module(module_path)

        # Get the command function
        func = getattr(module, command, None)
        if not func:
            return f"Bridge Error: Command '{command}' not found in module '{module_id}'."

        # Execute in sandbox
        result = func(args)
        return str(result)

    except Exception as e:
        logger.error(f"Bridge Sandbox Error ({module_id}.{command}): {e}", exc_info=True)
        return f"Bridge Error: {module_id} failed. {str(e)}"
