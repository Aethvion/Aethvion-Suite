"""
core/utils/registry_utils.py
---------------------------
Utilities for managing and initializing the model registry using the new defaults system.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List

from core.utils.logger import get_logger
from core.utils.paths import MODEL_REGISTRY
from core.providers.model_defaults import build_initial_registry, build_full_registry

logger = get_logger(__name__)

def ensure_registry_initialized() -> bool:
    """
    Ensure the model registry exists. If not, build it from defaults.
    
    Returns:
        True if the registry was created/initialized, False if it already existed.
    """
    registry_path = MODEL_REGISTRY
    
    if registry_path.exists():
        # Check if it's empty or invalid
        try:
            with open(registry_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data and "providers" in data:
                    return False
        except Exception:
            logger.warning(f"Existing registry at {registry_path} is invalid. Re-initializing.")
            
    try:
        logger.info("Initializing new model registry from defaults...")
        registry = build_initial_registry()
        
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(registry_path, 'w', encoding='utf-8') as f:
            json.dump(registry, f, indent=4)
            
        logger.info(f"Model registry initialized successfully at {registry_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize model registry: {e}")
        return False

# Keep legacy name for compatibility with current turn's changes if needed
def seed_registry_with_defaults(force: bool = False) -> bool:
    """Legacy wrapper for backward compatibility."""
    return ensure_registry_initialized()
