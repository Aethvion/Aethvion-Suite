"""
Data profiles — Standard vs Private.

The active profile tags data (threads, memories) at creation time so private
material can later be excluded from prompts routed to API providers. Reads and
writes the persisted setting so every component stays in sync, mirroring how
privacy mode works.
"""

from core.utils import get_logger

logger = get_logger(__name__)

PROFILES = ("standard", "private")


def get_active_profile() -> str:
    """Return the currently active data profile ('standard' | 'private')."""
    try:
        from core.config.settings_manager import get_settings_manager
        profile = get_settings_manager().settings.get("active_profile", "standard")
        return profile if profile in PROFILES else "standard"
    except Exception:
        return "standard"


def set_active_profile(profile: str) -> str:
    """Persist the active profile. Returns the applied value."""
    if profile not in PROFILES:
        profile = "standard"
    try:
        from core.config.settings_manager import get_settings_manager
        get_settings_manager().set("active_profile", profile)
        logger.info(f"Active data profile set to: {profile}")
    except Exception as exc:
        logger.error(f"Failed to persist active profile: {exc}")
    return profile


def provider_class_for(provider_name: str) -> str:
    """Classify a provider as 'local' or 'api' (mirrors ProviderManager.LOCAL_PROVIDER_NAMES)."""
    return "local" if provider_name in ("local", "ollama") else "api"
