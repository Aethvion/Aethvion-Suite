"""
Aethvion Suite - Anthropic Provider
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
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> ProviderResponse:
        """Generate response using Anthropic Claude."""
        try:
            active_model = model if model else self.config.model
            logger.debug(f"[{trace_id}] Generating with Anthropic model {active_model}")

            final_system_prompt = system_prompt or kwargs.pop('system_prompt', None)
            kwargs.pop('model', None)
            kwargs.pop('json_mode', None)

            # Build messages
            if messages:
                active_messages = list(messages)
                if prompt and (not messages or messages[-1].get('content') != prompt):
                    active_messages.append({"role": "user", "content": prompt})
            else:
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
                active_messages = [{"role": "user", "content": content}]

            create_kwargs: Dict[str, Any] = {
                "model": active_model,
                "messages": active_messages,
                "temperature": temperature,
                "max_tokens": max_tokens or 8192,
            }
            if final_system_prompt:
                create_kwargs["system"] = final_system_prompt

            # Thinking / Extended Reasoning Configuration (Claude 3.7 Sonnet / hybrid models)
            thinking_budget = kwargs.pop('thinking_budget', None)
            thinking_param = kwargs.pop('thinking', None)
            if thinking_param is not None:
                create_kwargs["thinking"] = thinking_param
                create_kwargs["temperature"] = 1.0
            elif thinking_budget is not None and int(thinking_budget) > 0:
                budget = max(1024, int(thinking_budget))
                create_kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
                create_kwargs["temperature"] = 1.0
                if create_kwargs.get("max_tokens", 8192) <= budget:
                    create_kwargs["max_tokens"] = budget + 4096

            # Forward remaining kwargs
            for k, v in kwargs.items():
                if k not in create_kwargs:
                    create_kwargs[k] = v

            response = self.client.messages.create(**create_kwargs)
            self.record_success()

            text_content = ""
            thinking_content = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    text_content += block.text
                elif getattr(block, 'type', None) == 'thinking' or hasattr(block, 'thinking'):
                    thinking_content += getattr(block, 'thinking', '')

            logger.info(f"[{trace_id}] Successfully generated response with Anthropic")

            metadata = {
                'model': active_model,
                'stop_reason': response.stop_reason,
                'usage': {
                    'prompt_tokens': response.usage.input_tokens,
                    'completion_tokens': response.usage.output_tokens,
                    'total_tokens': response.usage.input_tokens + response.usage.output_tokens
                }
            }
            if thinking_content:
                metadata['reasoning_content'] = thinking_content

            return ProviderResponse(
                content=text_content,
                model=active_model,
                provider="anthropic",
                trace_id=trace_id,
                metadata=metadata
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
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Iterator[str]:
        """Stream response using Anthropic Claude."""
        try:
            active_model = model if model else self.config.model
            logger.debug(f"[{trace_id}] Streaming with Anthropic model {active_model}")

            final_system_prompt = system_prompt or kwargs.pop('system_prompt', None)

            # Build messages
            if messages:
                active_messages = list(messages)
                if prompt and (not messages or messages[-1].get('content') != prompt):
                    active_messages.append({"role": "user", "content": prompt})
            else:
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
                                "data": b64_data,
                            }
                        })
                else:
                    content = prompt
                active_messages = [{"role": "user", "content": content}]

            create_kwargs: Dict[str, Any] = {
                "model": active_model,
                "messages": active_messages,
                "temperature": temperature,
                "max_tokens": max_tokens or 8192,
            }
            if final_system_prompt:
                create_kwargs["system"] = final_system_prompt

            # Thinking / Extended Reasoning Configuration
            thinking_budget = kwargs.pop('thinking_budget', None)
            thinking_param = kwargs.pop('thinking', None)
            include_thinking = kwargs.pop('include_thinking', False)

            if thinking_param is not None:
                create_kwargs["thinking"] = thinking_param
                create_kwargs["temperature"] = 1.0
            elif thinking_budget is not None and int(thinking_budget) > 0:
                budget = max(1024, int(thinking_budget))
                create_kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
                create_kwargs["temperature"] = 1.0
                if create_kwargs.get("max_tokens", 8192) <= budget:
                    create_kwargs["max_tokens"] = budget + 4096

            # Forward remaining kwargs
            for k, v in kwargs.items():
                if k not in create_kwargs:
                    create_kwargs[k] = v

            with self.client.messages.stream(**create_kwargs) as stream:
                for event in stream:
                    event_type = getattr(event, 'type', None)
                    if event_type == "content_block_delta":
                        delta = getattr(event, 'delta', None)
                        delta_type = getattr(delta, 'type', None)
                        if delta_type == "text_delta":
                            yield delta.text
                        elif delta_type == "thinking_delta" and include_thinking:
                            yield delta.thinking
                    elif hasattr(stream, 'text_stream') and not event_type:
                        for text in stream.text_stream:
                            yield text
                        break

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
