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
from core.utils import utcnow_iso
from core.utils.paths import COMPANIONS_PERSONAS, PERSONA_MISAKA

logger = logging.getLogger(__name__)

def _get_companion_dir(companion_id: str) -> Path:
    """Get the persistent directory for a companion."""
    if companion_id == "misakacipher":
        return PERSONA_MISAKA
    return COMPANIONS_PERSONAS / companion_id

class IdentityManager:
    """
    Manages identity and dynamic memory files for companions.
    Identities are stored in data/modes/companions/personas/{id}/base_info.json.
    Memories are stored in data/modes/companions/personas/{id}/memory.json.
    """

    @staticmethod
    def get_base_info(companion_id: str = "misakacipher") -> Dict[str, Any]:
        """Load personality and identity info."""
        path = _get_companion_dir(companion_id) / "base_info.json"
        if not path.exists():
            # If default doesn't exist, try to load defaults from companion config?
            # For now, just return empty to avoid crashes.
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load base_info.json for {companion_id}: {e}")
            return {}

    @staticmethod
    def get_dynamic_memory(companion_id: str = "misakacipher") -> Dict[str, Any]:
        """Load factual memory and observations."""
        path = _get_companion_dir(companion_id) / "memory.json"
        if not path.exists():
            return {"user_info": {}, "recent_observations": []}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load memory.json for {companion_id}: {e}")
            return {"user_info": {}, "recent_observations": []}

    @staticmethod
    def update_identity(update_json: Dict[str, Any], companion_id: str = "misakacipher") -> bool:
        """
        Process a memory update JSON object.
        Supports updating both base_info and dynamic memory.
        """
        try:
            memory_dir = _get_companion_dir(companion_id)
            memory_dir.mkdir(parents=True, exist_ok=True)
            
            base_info_path = memory_dir / "base_info.json"
            memory_path = memory_dir / "memory.json"
            
            updated = False

            # 1. Update Base Info (Personality)
            if "base_info" in update_json:
                base_info = IdentityManager.get_base_info(companion_id)
                base_info.update(update_json["base_info"])
                with open(base_info_path, "w", encoding="utf-8") as f:
                    json.dump(base_info, f, indent=4)
                logger.info(f"IdentityManager: Updated base_info.json for {companion_id}")
                updated = True

            # 2. Update Dynamic Memory (Observations)
            if "user_info" in update_json or "recent_observations" in update_json:
                memory = IdentityManager.get_dynamic_memory(companion_id)
                
                if "user_info" in update_json:
                    memory.setdefault("user_info", {}).update(update_json["user_info"])
                
                if "recent_observations" in update_json:
                    obs = update_json["recent_observations"]
                    if isinstance(obs, list):
                        curr_obs = memory.setdefault("recent_observations", [])
                        curr_obs.extend(obs)
                        memory["recent_observations"] = curr_obs[-20:] # Keep last 20
                
                memory["last_updated"] = utcnow_iso()
                with open(memory_path, "w", encoding="utf-8") as f:
                    json.dump(memory, f, indent=4)
                logger.info(f"IdentityManager: Updated memory.json for {companion_id}")
                updated = True

            return updated
        except Exception as e:
            logger.error(f"IdentityManager failed to update memory for {companion_id}: {e}")
            return False

    @staticmethod
    def extract_and_update(text: str, companion_id: str = "misakacipher") -> str:
        """
        Extract <memory_update> tags from text, update files, and return cleaned text.
        """
        match = re.search(r"<memory_update>(.*?)</memory_update>", text, re.DOTALL)
        if match:
            try:
                update_json = json.loads(match.group(1).strip())
                IdentityManager.update_identity(update_json, companion_id)
                # Remove tags from text
                return re.sub(r"<memory_update>.*?</memory_update>", "", text, flags=re.DOTALL).strip()
            except Exception as e:
                logger.error(f"Failed to parse memory_update tags for {companion_id}: {e}")
        
        return text
