"""
core/companions
═══════════════
Dynamic, data-driven Companion system for Aethvion Suite.
"""

from .registry import CompanionConfig, CompanionRegistry, get_companion

__all__ = ["CompanionConfig", "CompanionRegistry", "get_companion"]