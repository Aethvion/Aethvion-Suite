"""
Misaka Cipher - Base Provider
Abstract base class for all LLM providers
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Iterator, Any
from dataclasses import dataclass
from enum import Enum


class ProviderStatus(Enum):
    """Provider health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class ProviderResponse:
    """Standardized response from providers."""
    content: str
    model: str
    provider: str
    trace_id: str
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    @property
    def success(self) -> bool:
        """Check if request was successful."""
        return self.error is None


@dataclass
class ProviderConfig:
    """Configuration for a provider."""
    name: str
    model: str
    api_key: str
    endpoint: str
    timeout: int = 30
    max_retries: int = 3
    fallback_models: Optional[list] = None


class BaseProvider(ABC):
    """
    Abstract base class for all LLM providers.
    
    All providers (Google AI, OpenAI, Grok) must implement this interface
    to ensure consistent behavior across the Nexus Core.
    """
    
    def __init__(self, config: ProviderConfig):
        """
        Initialize provider with configuration.
        
        Args:
            config: Provider configuration
        """
        self.config = config
        # Start as HEALTHY so providers are always attempted on first use.
        # Status will change to OFFLINE after max_retries consecutive failures.
        self._status = ProviderStatus.HEALTHY
        self._consecutive_failures = 0
    
    @abstractmethod
    def generate(
        self,
        prompt: str,
        trace_id: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> ProviderResponse:
        """
        Generate a response from the provider.
        
        Args:
            prompt: Input prompt
            trace_id: Trace ID for this request
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            model: Optional model override (overrides config model)
            **kwargs: Additional provider-specific parameters
            
        Returns:
            ProviderResponse object
        """
        pass

    @abstractmethod
    def generate_image(
        self,
        prompt: str,
        trace_id: str,
        model: Optional[str] = None,
        n: int = 1,
        size: str = "1024x1024",
        quality: str = "standard",
        action: str = "generate",
        input_image_bytes: Optional[bytes] = None,
        mask_image_bytes: Optional[bytes] = None,
        **kwargs
    ) -> ProviderResponse:
        """
        Generate or manipulate an image from the provider.
        """
        pass

    @abstractmethod
    def generate_speech(
        self,
        text: str,
        trace_id: str,
        model: Optional[str] = None,
        voice: str = "alloy",
        format: str = "mp3",
        **kwargs
    ) -> ProviderResponse:
        """
        Generate speech from text (TTS).
        
        Args:
            text: Input text
            trace_id: Trace ID
            model: Optional model override
            voice: Voice ID
            format: Output format (mp3, wav, etc.)
            
        Returns:
            ProviderResponse (content=metadata summary, metadata['audio']=bytes)
        """
        pass

    @abstractmethod
    def transcribe(
        self,
        audio_bytes: bytes,
        trace_id: str,
        model: Optional[str] = None,
        **kwargs
    ) -> ProviderResponse:
        """
        Transcribe audio to text (STT).
        
        Args:
            audio_bytes: Input audio data
            trace_id: Trace ID
            model: Optional model override
            
        Returns:
            ProviderResponse (content=transcribed text)
        """
        pass
    
    @abstractmethod
    def stream(
        self,
        prompt: str,
        trace_id: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Iterator[str]:
        """
        Stream a response from the provider.
        
        Args:
            prompt: Input prompt
            trace_id: Trace ID for this request
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters
            
        Yields:
            Response chunks
        """
        pass
    
    @abstractmethod
    def validate_credentials(self) -> bool:
        """
        Validate API credentials.
        
        Returns:
            True if credentials are valid
        """
        pass
    
    def health_check(self) -> ProviderStatus:
        """
        Check provider health status.
        
        Returns:
            Current provider status
        """
        try:
            if self.validate_credentials():
                self._status = ProviderStatus.HEALTHY
                self._consecutive_failures = 0
            else:
                self._status = ProviderStatus.OFFLINE
        except Exception:
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                self._status = ProviderStatus.OFFLINE
            else:
                self._status = ProviderStatus.DEGRADED
        
        return self._status
    
    @property
    def status(self) -> ProviderStatus:
        """Get current provider status."""
        return self._status
    
    @property
    def is_healthy(self) -> bool:
        """Check if provider is healthy."""
        return self._status == ProviderStatus.HEALTHY
    
    def record_failure(self):
        """Record a failed request."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.config.max_retries:
            self._status = ProviderStatus.OFFLINE
    
    def record_success(self):
        """Record a successful request."""
        self._consecutive_failures = 0
        self._status = ProviderStatus.HEALTHY
