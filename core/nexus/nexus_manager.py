import os
import json
import importlib
import logging
from pathlib import Path

# Setup logging
logger = logging.getLogger(__name__)

# Paths - Use project root relative path
PROJECT_ROOT = Path(__file__).parent.parent.parent
REGISTRY_FILE = Path(__file__).parent / "registry.json"

def get_registry() -> dict:
    """Loads the Nexus registry."""
    if not REGISTRY_FILE.exists():
        return {"modules": []}
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load Nexus registry: {e}")
        return {"modules": []}

def save_registry(registry: dict):
    """Saves the Nexus registry."""
    try:
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save Nexus registry: {e}")

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
    Dynamically loads a Nexus module and calls a command.
    Includes an execution sandbox to catch errors.
    """
    if args is None:
        args = {}

    registry = get_registry()
    module_info = next((m for m in registry.get("modules", []) if m["id"] == module_id), None)

    if not module_info:
        return f"Nexus Error: Module '{module_id}' not found in registry."

    module_path = module_info.get("module_path")
    if not module_path:
        return f"Nexus Error: Module '{module_id}' has no module_path defined."

    try:
        # Import the module dynamically
        module = importlib.import_module(module_path)
        
        # Get the command function
        func = getattr(module, command, None)
        if not func:
            return f"Nexus Error: Command '{command}' not found in module '{module_id}'."

        # Execute in sandbox
        result = func(args)
        return str(result)

    except Exception as e:
        logger.error(f"Nexus Sandbox Error ({module_id}.{command}): {e}", exc_info=True)
        return f"Nexus Error: {module_id} failed. {str(e)}"
