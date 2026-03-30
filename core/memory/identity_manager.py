"""
Aethvion Suite - Identity Manager
Handles persistent identity (base_info.json) and dynamic memory (memory.json).
"""

import json
import logging
import datetime
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from core.utils.paths import PERSONA_MISAKA

logger = logging.getLogger(__name__)

# Constants
MEMORY_DIR = PERSONA_MISAKA
BASE_INFO_PATH = MEMORY_DIR / "base_info.json"
MEMORY_PATH = MEMORY_DIR / "memory.json"

class IdentityManager:
    """
    Manages Misaka Cipher's identity and dynamic memory files.
    Ensures shared context between different platforms.
    """

    @staticmethod
    def get_base_info() -> Dict[str, Any]:
        """Load personality and identity info."""
        if not BASE_INFO_PATH.exists():
            return {}
        try:
            with open(BASE_INFO_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load base_info.json: {e}")
            return {}

    @staticmethod
    def get_dynamic_memory() -> Dict[str, Any]:
        """Load factual memory and observations."""
        if not MEMORY_PATH.exists():
            return {"user_info": {}, "recent_observations": []}
        try:
            with open(MEMORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load memory.json: {e}")
            return {"user_info": {}, "recent_observations": []}

    @staticmethod
    def update_identity(update_json: Dict[str, Any]) -> bool:
        """
        Process a memory update JSON object.
        Supports updating both base_info and dynamic memory.
        """
        try:
            MEMORY_DIR.mkdir(parents=True, exist_ok=True)
            updated = False

            # 1. Update Base Info (Personality)
            if "base_info" in update_json:
                base_info = IdentityManager.get_base_info()
                base_info.update(update_json["base_info"])
                with open(BASE_INFO_PATH, "w", encoding="utf-8") as f:
                    json.dump(base_info, f, indent=4)
                logger.info("IdentityManager: Updated base_info.json")
                updated = True

            # 2. Update Dynamic Memory (Observations)
            if "user_info" in update_json or "recent_observations" in update_json:
                memory = IdentityManager.get_dynamic_memory()
                
                if "user_info" in update_json:
                    memory.setdefault("user_info", {}).update(update_json["user_info"])
                
                if "recent_observations" in update_json:
                    obs = update_json["recent_observations"]
                    if isinstance(obs, list):
                        curr_obs = memory.setdefault("recent_observations", [])
                        curr_obs.extend(obs)
                        memory["recent_observations"] = curr_obs[-20:] # Keep last 20
                
                memory["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(MEMORY_PATH, "w", encoding="utf-8") as f:
                    json.dump(memory, f, indent=4)
                logger.info("IdentityManager: Updated memory.json")
                updated = True

            return updated
        except Exception as e:
            logger.error(f"IdentityManager failed to update memory: {e}")
            return False

    @staticmethod
    def extract_and_update(text: str) -> str:
        """
        Extract <memory_update> tags from text, update files, and return cleaned text.
        """
        match = re.search(r"<memory_update>(.*?)</memory_update>", text, re.DOTALL)
        if match:
            try:
                update_json = json.loads(match.group(1).strip())
                IdentityManager.update_identity(update_json)
                # Remove tags from text
                return re.sub(r"<memory_update>.*?</memory_update>", "", text, flags=re.DOTALL).strip()
            except Exception as e:
                logger.error(f"Failed to parse memory_update tags: {e}")
        
        return text
