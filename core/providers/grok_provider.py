"""
Misaka Cipher - Grok Provider
xAI Grok implementation (tertiary fallback provider)
"""

import os
import requests
from typing import Iterator, Optional
from .base_provider import BaseProvider, ProviderResponse, ProviderConfig
from core.utils.logger import get_logger

logger = get_logger(__name__)


class GrokProvider(BaseProvider):
    """
    xAI Grok provider implementation.
    
    Tertiary fallback provider for Misaka Cipher system.
    """
    
    def __init__(self, config: ProviderConfig):
        """Initialize Grok provider."""
        super().__init__(config)
        
        # Get API key - read from environment variable
        self.api_key = os.getenv(config.api_key, config.api_key)
        if not self.api_key:
            logger.warning(f"Grok API key not found in environment: {config.api_key}")
        
        # Set up headers
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"Initialized Grok provider with model: {config.model}")
    
    def generate(
        self,
        prompt: str,
        trace_id: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> ProviderResponse:
        """Generate response using Grok."""
        try:
            # Use explicit model override or fall back to config
            active_model = model if model else self.config.model
            logger.debug(f"[{trace_id}] Generating with Grok model {active_model}")
            
            # Build request payload
            # Extract system prompt if present
            system_prompt = kwargs.pop('system_prompt', None)
            
            # Build messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            # Remove unsupported kwargs
            kwargs.pop('model', None)
            kwargs.pop('json_mode', None)
            
            payload = {
                "model": active_model,
                "messages": messages,
                "temperature": temperature,
                **kwargs
            }
            
            if max_tokens:
                payload["max_tokens"] = max_tokens
            
            # Make API request
            response = requests.post(
                f"{self.config.endpoint}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=self.config.timeout
            )
            
            # Log response details on error
            if not response.ok:
                logger.error(
                    f"[{trace_id}] Grok API error {response.status_code}: "
                    f"{response.text[:500]}"
                )
            
            response.raise_for_status()
            data = response.json()
            
            # Record success
            self.record_success()
            
            logger.info(f"[{trace_id}] Successfully generated response with Grok")
            
            return ProviderResponse(
                content=data['choices'][0]['message']['content'],
                model=active_model,
                provider="grok",
                trace_id=trace_id,
                metadata={
                    'model': active_model,
                    'finish_reason': data['choices'][0].get('finish_reason'),
                    'usage': data.get('usage', {})
                }
            )
            
        except requests.HTTPError as e:
            error_body = ""
            if e.response is not None:
                error_body = e.response.text[:500]
            logger.error(f"[{trace_id}] Grok HTTP error: {e} | Body: {error_body}")
            self.record_failure()
            
            return ProviderResponse(
                content="",
                model=active_model,
                provider="grok",
                trace_id=trace_id,
                error=f"{str(e)} | {error_body}"
            )
            
        except Exception as e:
            logger.error(f"[{trace_id}] Grok generation failed: {str(e)}")
            self.record_failure()
            
            return ProviderResponse(
                content="",
                model=active_model,
                provider="grok",
                trace_id=trace_id,
                error=str(e)
            )
    
    def stream(
        self,
        prompt: str,
        trace_id: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Iterator[str]:
        """Stream response using Grok."""
        try:
            logger.debug(f"[{trace_id}] Streaming with Grok model {self.config.model}")
            
            # Build request payload
            payload = {
                "model": self.config.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "stream": True
            }
            
            if max_tokens:
                payload["max_tokens"] = max_tokens
            
            # Make streaming request
            response = requests.post(
                f"{self.config.endpoint}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=self.config.timeout,
                stream=True
            )
            
            response.raise_for_status()
            
            # Parse SSE stream
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = line[6:]
                        if data != '[DONE]':
                            import json
                            chunk = json.loads(data)
                            if chunk['choices'][0]['delta'].get('content'):
                                yield chunk['choices'][0]['delta']['content']
            
            # Record success
            self.record_success()
            logger.info(f"[{trace_id}] Successfully streamed response with Grok")
            
        except Exception as e:
            logger.error(f"[{trace_id}] Grok streaming failed: {str(e)}")
            self.record_failure()
            yield f"Error: {str(e)}"
    
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
        """Grok does not currently support image generation."""
        logger.warning(f"[{trace_id}] Grok does not support image generation")
        return ProviderResponse(
            content="",
            model=model or self.config.model,
            provider="grok",
            trace_id=trace_id,
            error="Grok does not support image generation"
        )
    
    def generate_speech(
        self,
        text: str,
        trace_id: str,
        model: Optional[str] = None,
        voice: str = "alloy",
        format: str = "mp3",
        **kwargs
    ) -> 'ProviderResponse':
        """Grok does not currently support speech synthesis."""
        from .base_provider import ProviderResponse
        logger.warning(f"[{trace_id}] Grok does not support speech synthesis")
        return ProviderResponse(
            content="",
            model=model or self.config.model,
            provider="grok",
            trace_id=trace_id,
            error="Grok does not support speech synthesis"
        )

    def transcribe(
        self,
        audio_bytes: bytes,
        trace_id: str,
        model: Optional[str] = None,
        **kwargs
    ) -> 'ProviderResponse':
        """Grok does not currently support audio transcription."""
        from .base_provider import ProviderResponse
        logger.warning(f"[{trace_id}] Grok does not support audio transcription")
        return ProviderResponse(
            content="",
            model=model or self.config.model,
            provider="grok",
            trace_id=trace_id,
            error="Grok does not support audio transcription"
        )

    def validate_credentials(self) -> bool:
        """Validate Grok API credentials."""
        try:
            # Try to make a minimal request
            response = requests.get(
                f"{self.config.endpoint}/models",
                headers=self.headers,
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Grok credential validation failed: {str(e)}")
            return False
