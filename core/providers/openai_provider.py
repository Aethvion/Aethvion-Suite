"""
Aethvion Suite - OpenAI Provider
OpenAI GPT-4 implementation
"""

import os
from typing import Iterator, Optional, List, Dict, Any
# from openai import OpenAI
from .base_provider import BaseProvider, ProviderResponse, ProviderConfig
from core.utils.logger import get_logger

logger = get_logger(__name__)


class OpenAIProvider(BaseProvider):
    """
    OpenAI (GPT) provider implementation.
    
    Secondary provider for Aethvion Suite.
    """
    
    def __init__(self, config: ProviderConfig):
        """Initialize OpenAI provider."""
        super().__init__(config)
        
        # Get API key - read from environment variable
        api_key = os.getenv(config.api_key, config.api_key)
        if not api_key:
            logger.warning(f"OpenAI API key not found in environment: {config.api_key}")
        
        # Initialize client
        from openai import OpenAI
        self.client = OpenAI(
            api_key=api_key,
            timeout=config.timeout
        )
        
        logger.info(f"Initialized OpenAI provider with model: {config.model}")
    
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
        """Generate response using OpenAI."""
        try:
            # Use explicit model override or fall back to config
            active_model = model if model else self.config.model
            logger.debug(f"[{trace_id}] Generating with OpenAI model {active_model}")
            # Extract system prompt if present
            system_prompt = kwargs.pop('system_prompt', None)
            
            # Build messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
                
            if images:
                import base64
                content_list = [{"type": "text", "text": prompt}]
                for img in images:
                    b64_data = base64.b64encode(img['data']).decode('utf-8')
                    mime = img.get('mime_type', 'image/jpeg')
                    content_list.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64_data}"}
                    })
                messages.append({"role": "user", "content": content_list})
            else:
                messages.append({"role": "user", "content": prompt})
            
            # Remove unsupported kwargs
            kwargs.pop('model', None)
            kwargs.pop('json_mode', None)
            
            # Generate response
            response = self.client.chat.completions.create(
                model=active_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            # Record success
            self.record_success()
            
            logger.info(f"[{trace_id}] Successfully generated response with OpenAI")
            
            # Extract tool calls
            tool_calls = []
            if response.choices[0].message.tool_calls:
                for tc in response.choices[0].message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    })

            return ProviderResponse(
                content=response.choices[0].message.content or "",
                model=active_model,
                provider="openai",
                trace_id=trace_id,
                metadata={
                    'model': active_model,
                    'finish_reason': response.choices[0].finish_reason,
                    'tool_calls': tool_calls,
                    'usage': {
                        'prompt_tokens': response.usage.prompt_tokens,
                        'completion_tokens': response.usage.completion_tokens,
                        'total_tokens': response.usage.total_tokens
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"[{trace_id}] OpenAI generation failed: {str(e)}")
            self.record_failure()
            
            return ProviderResponse(
                content="",
                model=active_model,
                provider="openai",
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
        """Stream response using OpenAI."""
        try:
            logger.debug(f"[{trace_id}] Streaming with OpenAI model {self.config.model}")
            
            # Build messages
            messages = [{"role": "user", "content": prompt}]
            
            # Stream response
            active_model = model if model else self.config.model
            stream = self.client.chat.completions.create(
                model=active_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs
            )
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            
            # Record success
            self.record_success()
            logger.info(f"[{trace_id}] Successfully streamed response with OpenAI")
            
        except Exception as e:
            logger.error(f"[{trace_id}] OpenAI streaming failed: {str(e)}")
            self.record_failure()
            yield f"Error: {str(e)}"
    
    def validate_credentials(self) -> bool:
        """Validate OpenAI API credentials."""
        try:
            # Try to list models as a validation check
            self.client.models.list()
            return True
        except Exception as e:
            logger.warning(f"OpenAI credential validation failed: {str(e)}")
            return False
            return False

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
        """Generate or manipulate an image using OpenAI."""
        try:
            active_model = model if model else "dall-e-3"
            logger.debug(f"[{trace_id}] {action.capitalize()} image with OpenAI model {active_model}")

            if action == "edit":
                if not input_image_bytes:
                    raise ValueError("input_image_bytes is required for 'edit' action")
                edit_kwargs = {
                    "model": active_model if "dall-e-2" in active_model else "dall-e-2", # OpenAI Edit requires DALL-E 2
                    "image": input_image_bytes,
                    "prompt": prompt,
                    "n": n,
                    "size": size,
                    "response_format": "b64_json",
                    "user": trace_id
                }
                if mask_image_bytes:
                    edit_kwargs["mask"] = mask_image_bytes
                
                response = self.client.images.edit(**edit_kwargs)
            elif action == "generate":
                response = self.client.images.generate(
                    model=active_model,
                    prompt=prompt,
                    n=n,
                    size=size,
                    quality=quality,
                    response_format="b64_json",
                    user=trace_id
                )
            else:
                return ProviderResponse(
                    content="",
                    model=active_model,
                    provider="openai",
                    trace_id=trace_id,
                    error=f"Action '{action}' is currently not supported natively by the Misaka OpenAI integration."
                )
            
            import base64
            image_bytes_list = []
            for img_data in response.data:
                if img_data.b64_json:
                    image_bytes_list.append(base64.b64decode(img_data.b64_json))
            
            self.record_success()
            logger.info(f"[{trace_id}] Successfully generated {len(image_bytes_list)} images with OpenAI")

            return ProviderResponse(
                content=f"Generated {len(image_bytes_list)} images",
                model=active_model,
                provider="openai",
                trace_id=trace_id,
                metadata={
                    'images': image_bytes_list,
                    'format': 'png' # OpenAI returns PNG by default for b64_json
                }
            )

        except Exception as e:
            logger.error(f"[{trace_id}] OpenAI image generation failed: {str(e)}")
            self.record_failure()
            return ProviderResponse(
                content="",
                model=active_model if 'active_model' in locals() else "openai",
                provider="openai",
                trace_id=trace_id,
                error=str(e)
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
        """Generate speech using OpenAI TTS."""
        try:
            active_model = model if model else "tts-1"
            logger.debug(f"[{trace_id}] Generating speech with OpenAI model {active_model}")

            response = self.client.audio.speech.create(
                model=active_model,
                voice=voice,
                input=text,
                response_format=format
            )

            # Extract bytes from response (iter_bytes is available in the SDK response)
            audio_bytes = response.content

            self.record_success()
            logger.info(f"[{trace_id}] Successfully generated speech with OpenAI")

            return ProviderResponse(
                content=f"Generated {len(audio_bytes)} bytes of speech",
                model=active_model,
                provider="openai",
                trace_id=trace_id,
                metadata={
                    'audio': audio_bytes,
                    'format': format,
                    'voice': voice
                }
            )
        except Exception as e:
            logger.error(f"[{trace_id}] OpenAI speech generation failed: {str(e)}")
            self.record_failure()
            return ProviderResponse(
                content="",
                model=model or "tts-1",
                provider="openai",
                trace_id=trace_id,
                error=str(e)
            )

    def transcribe(
        self,
        audio_bytes: bytes,
        trace_id: str,
        model: Optional[str] = None,
        **kwargs
    ) -> ProviderResponse:
        """Transcribe audio using OpenAI Whisper."""
        try:
            active_model = model if model else "whisper-1"
            logger.debug(f"[{trace_id}] Transcribing with OpenAI model {active_model}")

            # OpenAI expects a file-like object for audio
            import io
            audio_file = io.BytesIO(audio_bytes)
            # We need to give it a name so the SDK can infer the format/mimetype
            audio_file.name = "audio.wav" 

            response = self.client.audio.transcriptions.create(
                model=active_model,
                file=audio_file,
                **kwargs
            )

            self.record_success()
            logger.info(f"[{trace_id}] Successfully transcribed audio with OpenAI")

            return ProviderResponse(
                content=response.text,
                model=active_model,
                provider="openai",
                trace_id=trace_id,
                metadata={
                    'model': active_model
                }
            )
        except Exception as e:
            logger.error(f"[{trace_id}] OpenAI transcription failed: {str(e)}")
            self.record_failure()
            return ProviderResponse(
                content="",
                model=model or "whisper-1",
                provider="openai",
                trace_id=trace_id,
                error=str(e)
            )
