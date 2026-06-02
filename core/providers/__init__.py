"""
Aethvion Suite - Providers Package
Interface to various LLM providers
"""

from typing import Optional

from .base_provider import (
    BaseProvider,
    ProviderResponse,
    ProviderConfig,
    ProviderStatus
)

from .google_provider import GoogleAIProvider
from .openai_provider import OpenAIProvider
from .grok_provider import GrokProvider
from .groq_provider import GroqProvider
from .mistral_provider import MistralProvider
from .openrouter_provider import OpenRouterProvider
from .provider_manager import ProviderManager, get_provider_manager

# Singleton
# All call sites should use get_provider_manager() instead of ProviderManager().
# This ensures config is read from disk exactly once, all components share the
# same routing/priority state, and changes like privacy-mode toggles propagate
# everywhere automatically.


__all__ = [
    # Base Classes
    'BaseProvider',
    'ProviderResponse',
    'ProviderConfig',
    'ProviderStatus',

    # Provider Implementations
    'GoogleAIProvider',
    'OpenAIProvider',
    'GrokProvider',
    'GroqProvider',
    'MistralProvider',
    'OpenRouterProvider',

    # Manager + singleton accessor
    'ProviderManager',
    'get_provider_manager',
]
