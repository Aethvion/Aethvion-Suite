"""
Misaka Cipher - Social Registry
Maps platform-specific IDs to human-readable names and memory profiles.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from core.utils import get_logger

logger = get_logger(__name__)

class SocialRegistry:
    """
    Social Registry - Maps platform IDs (Discord, etc.) to internal profiles.
    
    Ensures Misaka knows who she's talking to across different services
    and can link conversations to the same episodic memory context.
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize Social Registry.
        
        Args:
            storage_path: Path to registry storage (JSON)
        """
        if storage_path is None:
            # core/memory/social_registry.py -> parent.parent.parent = project root
            project_root = Path(__file__).parent.parent.parent
            self.storage_path = project_root / "data" / "memory" / "storage" / "social_registry.json"
        else:
            self.storage_path = storage_path
            
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry: Dict[str, Dict[str, Any]] = {}
        self._load()
        
    def _load(self):
        """Load registry from disk."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    self.registry = json.load(f)
                logger.info(f"Loaded {len(self.registry)} social profiles from registry")
            except Exception as e:
                logger.error(f"Failed to load social registry: {e}")
                self.registry = {}
        else:
            logger.info("No social registry found, starting fresh")
            self.registry = {}
            
    def _save(self):
        """Save registry to disk."""
        try:
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(self.registry, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save social registry: {e}")
            
    def get_profile(self, platform: str, platform_id: str) -> Optional[Dict[str, Any]]:
        """
        Get profile mapped to a platform ID.
        
        Args:
            platform: Platform name (e.g., "discord")
            platform_id: Platform-specific unique ID
            
        Returns:
            Profile dictionary or None
        """
        key = f"{platform}:{platform_id}"
        return self.registry.get(key)
        
    def map_user(self, platform: str, platform_id: str, name: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Map a platform ID to a user profile.
        
        Args:
            platform: Platform name
            platform_id: Platform-specific ID
            name: Human-readable name
            metadata: Optional additional metadata (roles, avatar, etc.)
            
        Returns:
            The created or updated profile
        """
        key = f"{platform}:{platform_id}"
        
        profile = {
            "platform": platform,
            "platform_id": platform_id,
            "display_name": name,
            "internal_id": f"USER_{platform}_{platform_id}", # Consistent ID for memory
            "metadata": metadata or {},
            "last_seen": Path(__file__).stat().st_mtime # Placeholder for timestamp
        }
        
        # In a real system, we'd use datetime.now().isoformat()
        import datetime
        profile["last_seen"] = datetime.datetime.now().isoformat()
        
        self.registry[key] = profile
        self._save()
        
        logger.info(f"Mapped {platform} user '{name}' ({platform_id}) to registry")
        return profile

    def resolve_display_name(self, platform: str, platform_id: str, default: str = "Unknown User") -> str:
        """Helper to get a name for logging/generation."""
        profile = self.get_profile(platform, platform_id)
        return profile["display_name"] if profile else default

# Singleton
_social_registry = None

def get_social_registry() -> SocialRegistry:
    """Get global social registry instance."""
    global _social_registry
    if _social_registry is None:
        _social_registry = SocialRegistry()
    return _social_registry
