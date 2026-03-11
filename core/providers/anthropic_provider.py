"""
Misaka Cipher - Anthropic Provider
Anthropic Claude implementation
"""

import os
from typing import Iterator, Optional, List, Dict, Any
from .base_provider import BaseProvider, ProviderResponse, ProviderConfig
from core.utils.logger import get_logger

logger = get_logger(__name__)


class AnthropicProvider(BaseProvider):
    """
    Anthropic (Claude) provider implementation.
    """

    def __init__(self, config: ProviderConfig):
        """Initialize Anthropic provider."""
        super().__init__(config)

        api_key = os.getenv(config.api_key, config.api_key)
        if not api_key:
            logger.warning(f"Anthropic API key not found in environment: {config.api_key}")

        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        logger.info(f"Initialized Anthropic provider with model: {config.model}")

    def generate(
        self,
        prompt: str,
        trace_id: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> ProviderResponse:
        """Generate response using Anthropic Claude."""
        try:
            active_model = model if model else self.config.model
            logger.debug(f"[{trace_id}] Generating with Anthropic model {active_model}")

            system_prompt = kwargs.pop('system_prompt', None)
            kwargs.pop('model', None)
            kwargs.pop('json_mode', None)

            # Build content
            if images:
                import base64
                content: Any = [{"type": "text", "text": prompt}]
                for img in images:
                    b64_data = base64.b64encode(img['data']).decode('utf-8')
                    mime = img.get('mime_type', 'image/jpeg')
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime,
                            "data": b64_data
                        }
                    })
            else:
                content = prompt

            messages = [{"role": "user", "content": content}]

            create_kwargs: Dict[str, Any] = {
                "model": active_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens or 8192,
            }
            if system_prompt:
                create_kwargs["system"] = system_prompt

            response = self.client.messages.create(**create_kwargs)
            self.record_success()

            text_content = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text_content += block.text

            logger.info(f"[{trace_id}] Successfully generated response with Anthropic")

            return ProviderResponse(
                content=text_content,
                model=active_model,
                provider="anthropic",
                trace_id=trace_id,
                metadata={
                    'model': active_model,
                    'stop_reason': response.stop_reason,
                    'usage': {
                        'prompt_tokens': response.usage.input_tokens,
                        'completion_tokens': response.usage.output_tokens,
                        'total_tokens': response.usage.input_tokens + response.usage.output_tokens
                    }
                }
            )

        except Exception as e:
            logger.error(f"[{trace_id}] Anthropic generation failed: {str(e)}")
            self.record_failure()
            return ProviderResponse(
                content="",
                model=model or self.config.model,
                provider="anthropic",
                trace_id=trace_id,
                error=str(e)
            )

    def stream(
        self,
        prompt: str,
        trace_id: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> Iterator[str]:
        """Stream response using Anthropic Claude."""
        try:
            active_model = model if model else self.config.model
            logger.debug(f"[{trace_id}] Streaming with Anthropic model {active_model}")

            system_prompt = kwargs.pop('system_prompt', None)

            create_kwargs: Dict[str, Any] = {
                "model": active_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens or 8192,
            }
            if system_prompt:
                create_kwargs["system"] = system_prompt

            with self.client.messages.stream(**create_kwargs) as stream:
                for text in stream.text_stream:
                    yield text

            self.record_success()
            logger.info(f"[{trace_id}] Successfully streamed response with Anthropic")

        except Exception as e:
            logger.error(f"[{trace_id}] Anthropic streaming failed: {str(e)}")
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
        """Anthropic does not support image generation."""
        logger.warning(f"[{trace_id}] Anthropic does not support image generation")
        return ProviderResponse(
            content="",
            model=model or self.config.model,
            provider="anthropic",
            trace_id=trace_id,
            error="Anthropic does not support image generation"
        )

    def generate_speech(
        self,
        text: str,
        trace_id: str,
        model: Optional[str] = None,
        voice: str = "alloy",
        format: str = "mp3",
        **kwargs
    ) -> ProviderResponse:
        """Anthropic does not support speech synthesis."""
        logger.warning(f"[{trace_id}] Anthropic does not support speech synthesis")
        return ProviderResponse(
            content="",
            model=model or self.config.model,
            provider="anthropic",
            trace_id=trace_id,
            error="Anthropic does not support speech synthesis"
        )

    def transcribe(
        self,
        audio_bytes: bytes,
        trace_id: str,
        model: Optional[str] = None,
        **kwargs
    ) -> ProviderResponse:
        """Anthropic does not support audio transcription."""
        logger.warning(f"[{trace_id}] Anthropic does not support audio transcription")
        return ProviderResponse(
            content="",
            model=model or self.config.model,
            provider="anthropic",
            trace_id=trace_id,
            error="Anthropic does not support audio transcription"
        )

    def validate_credentials(self) -> bool:
        """Validate Anthropic API credentials."""
        try:
            self.client.models.list()
            return True
        except Exception as e:
            logger.warning(f"Anthropic credential validation failed: {str(e)}")
            return False
