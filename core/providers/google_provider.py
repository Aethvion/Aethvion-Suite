"""
Aethvion Suite - Google AI Provider
Google Generative AI (Gemini) implementation
"""

import os
from typing import Iterator, Optional, Dict, Any, List
# from google import genai
# from google.genai import types
from .base_provider import BaseProvider, ProviderResponse, ProviderConfig
from core.utils.logger import get_logger

logger = get_logger(__name__)


class GoogleAIProvider(BaseProvider):
    """
    Google AI (Gemini) provider implementation.
    
    Primary provider for Aethvion Suite.
    """
    
    def __init__(self, config: ProviderConfig):
        """Initialize Google AI provider."""
        super().__init__(config)
        
        # Configure API - read from environment variable
        api_key = os.getenv(config.api_key)
        if not api_key:
            # Fallback to direct key if provided in config (less common but possible)
            api_key = config.api_key if not config.api_key.isupper() else None
            
        if not api_key:
            logger.error(f"Google AI API key not found in environment: {config.api_key}")
        
        # New SDK uses a client-based approach
        from google import genai
        self.client = genai.Client(api_key=api_key)
        
        logger.info(f"Initialized Google AI provider with model: {config.model}")
    
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
        """Generate response using Google AI."""
        try:
            active_model = model if model else self.config.model
            logger.debug(f"[{trace_id}] Generating with Google AI model {active_model}")
            
            # Extract system prompt from kwargs for backwards compatibility if needed, 
            # but prefer the explicit parameter.
            final_system_prompt = system_prompt or kwargs.pop('system_prompt', None)
            
            # Configure generation
            config_params = {
                'temperature': temperature,
            }
            if max_tokens:
                config_params['max_output_tokens'] = max_tokens
            if final_system_prompt:
                config_params['system_instruction'] = final_system_prompt
            
            # Support JSON mode if requested
            if kwargs.get('json_mode'):
                config_params['response_mime_type'] = 'application/json'
            
            # Remove unsupported kwargs
            kwargs.pop('json_mode', None)
            kwargs.pop('model', None)

            # Extract tools if provided and convert to Google-specific types
            tools = kwargs.pop('tools', None)
            google_tools = []
            if tools:
                from google.genai import types
                decls = []
                for t in tools:
                    if t.get('type') == 'function':
                        f = t.get('function', {})
                        # Convert parameter schema to Google's uppercase types
                        params = f.get('parameters', {})
                        schema = self._convert_to_google_schema(params)
                        decls.append(types.FunctionDeclaration(
                            name=f.get('name'),
                            description=f.get('description'),
                            parameters=schema
                        ))
                if decls:
                    google_tools.append(types.Tool(function_declarations=decls))
                config_params['tools'] = google_tools

            # Generate response via client
            from google.genai import types
            
            # Build contents
            from google.genai import types
            contents = []
            
            if messages:
                for m in messages:
                    role = 'user' if m.get('role') == 'user' else 'model'
                    contents.append(types.Content(role=role, parts=[types.Part.from_text(text=m.get('content', ''))]))
                
                # Append current prompt if it's the new user turn
                if prompt and (not messages or messages[-1].get('content') != prompt):
                     contents.append(types.Content(role='user', parts=[types.Part.from_text(text=prompt)]))
            else:
                user_content = prompt or kwargs.get('user_message', '')
                if images:
                    parts = []
                    for img in images:
                        parts.append(types.Part.from_bytes(
                            data=img['data'], 
                            mime_type=img.get('mime_type', 'image/jpeg')
                        ))
                    parts.append(types.Part.from_text(text=user_content))
                    contents.append(types.Content(role='user', parts=parts))
                else:
                    contents.append(types.Content(role='user', parts=[types.Part.from_text(text=user_content)]))
            
            response = self.client.models.generate_content(
                model=active_model,
                contents=contents,
                config=types.GenerateContentConfig(**config_params)
            )
            
            # Extract tool calls
            tool_calls = []
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.function_call:
                        tool_calls.append({
                            "name": part.function_call.name,
                            "arguments": part.function_call.args
                        })

            # Record success
            self.record_success()
            
            logger.info(f"[{trace_id}] Successfully generated response with Google AI")
            
            # Extract usage
            usage_meta = {
                'prompt_token_count': response.usage_metadata.prompt_token_count if response.usage_metadata else None,
                'candidates_token_count': response.usage_metadata.candidates_token_count if response.usage_metadata else None,
                'total_tokens': response.usage_metadata.total_token_count if response.usage_metadata else None
            } if hasattr(response, 'usage_metadata') and response.usage_metadata else {}

            response_text = response.text if response.text else ""

            # safety filter or a finish_reason other than STOP.  Helps diagnose
            # "empty response" issues without breaking the call.
            if not response_text:
                finish_reason = response.candidates[0].finish_reason if response.candidates else "NO_CANDIDATES"
                logger.warning(
                    f"[{trace_id}] Google AI returned empty text. "
                    f"finish_reason={finish_reason!r}  model={active_model!r}. "
                    f"Candidates: {len(response.candidates) if response.candidates else 0}."
                )

            return ProviderResponse(
                content=response_text,
                model=active_model,
                provider="google_ai",
                trace_id=trace_id,
                metadata={
                    'model': active_model,
                    'finish_reason': response.candidates[0].finish_reason if response.candidates else None,
                    'tool_calls': tool_calls,
                    'usage': usage_meta
                }
            )
            
        except Exception as e:
            logger.error(f"[{trace_id}] Google AI generation failed: {str(e)}")
            self.record_failure()
            
            return ProviderResponse(
                content="",
                model=self.config.model,
                provider="google_ai",
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
        """Stream response using Google AI."""
        try:
            logger.debug(f"[{trace_id}] Streaming with Google AI model {self.config.model}")

            # Combine system_prompt
            final_system_prompt = system_prompt or kwargs.pop('system_prompt', None)

            # Configure generation
            config_params = {
                'temperature': temperature,
            }
            if max_tokens:
                config_params['max_output_tokens'] = max_tokens
            if final_system_prompt:
                config_params['system_instruction'] = final_system_prompt

            # Build contents — include image parts if provided
            from google.genai import types
            active_model = model if model else self.config.model
            
            contents = []
            if messages:
                for m in messages:
                    role = 'user' if m.get('role') == 'user' else 'model'
                    contents.append(types.Content(role=role, parts=[types.Part.from_text(text=m.get('content', ''))]))
                
                # Append current prompt if it's the new user turn
                if prompt and (not messages or messages[-1].get('content') != prompt):
                    contents.append(types.Content(role='user', parts=[types.Part.from_text(text=prompt)]))
            else:
                user_content = prompt or kwargs.get('user_message', '')
                if images:
                    parts = []
                    for img in images:
                        parts.append(types.Part.from_bytes(
                            data=img['data'],
                            mime_type=img.get('mime_type', 'image/jpeg')
                        ))
                    parts.append(types.Part.from_text(text=user_content))
                    contents.append(types.Content(role='user', parts=parts))
                else:
                    contents = user_content

            response = self.client.models.generate_content_stream(
                model=active_model,
                contents=contents,
                config=types.GenerateContentConfig(**config_params)
            )

            for chunk in response:
                if chunk.text:
                    yield chunk.text
            
            # Record success
            self.record_success()
            logger.info(f"[{trace_id}] Successfully streamed response with Google AI")
            
        except Exception as e:
            logger.error(f"[{trace_id}] Google AI streaming failed: {str(e)}")
            self.record_failure()
            yield f"Error: {str(e)}"
    
    def _convert_to_google_schema(self, schema: Dict[str, Any]) -> Any:
        """Recursively convert JSON schema types to Google-specific uppercase strings."""
        from google.genai import types
        
        type_map = {
            "string": "STRING",
            "number": "NUMBER",
            "integer": "INTEGER",
            "boolean": "BOOLEAN",
            "object": "OBJECT",
            "array": "ARRAY",
            "null": "NULL"
        }
        
        # Determine the type
        stype = schema.get("type", "object")
        google_type = type_map.get(stype, "OBJECT")
        
        # Build schema object
        schema_kwargs = {"type": google_type}
        
        if "description" in schema:
            schema_kwargs["description"] = schema["description"]
            
        if "properties" in schema:
            google_props = {}
            for k, v in schema["properties"].items():
                google_props[k] = self._convert_to_google_schema(v)
            schema_kwargs["properties"] = google_props
            
        if "required" in schema:
            schema_kwargs["required"] = schema["required"]
            
        if "items" in schema:
            schema_kwargs["items"] = self._convert_to_google_schema(schema["items"])
            
        if "enum" in schema:
            schema_kwargs["enum"] = schema["enum"]

        return types.Schema(**schema_kwargs)

    def validate_credentials(self) -> bool:
        """Validate Google AI API credentials."""
        try:
            # Try to list models as a validation check
            self.client.models.list(config={'page_size': 1})
            return True
        except Exception as e:
            logger.warning(f"Google AI credential validation failed: {str(e)}")
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
        """Generate or manipulate an image using Google AI."""
        try:
            if action != "generate":
                return ProviderResponse(
                    content="",
                    model=model or "google_ai",
                    provider="google_ai",
                    trace_id=trace_id,
                    error=f"Action '{action}' is currently not supported natively by the Misaka Google AI integration."
                )

            active_model = model if model else "imagen-3.0-generate-002"
            logger.debug(f"[{trace_id}] Generating image with Google AI model {active_model}")

            aspect_ratio = kwargs.get('aspect_ratio', '1:1')
            negative_prompt = kwargs.get('negative_prompt')
            seed = kwargs.get('seed')

            # Generate via new SDK
            from google.genai import types
            response = self.client.models.generate_images(
                model=active_model,
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=n,
                    aspect_ratio=aspect_ratio,
                    negative_prompt=negative_prompt,
                )
            )
            
            image_bytes_list = []
            if hasattr(response, 'generated_images') and response.generated_images:
                for img in response.generated_images:
                    if hasattr(img, 'image') and hasattr(img.image, 'image_bytes'):
                        image_bytes_list.append(img.image.image_bytes)
            
            if not image_bytes_list:
                raise ValueError("No images returned from Google API")

            self.record_success()
            logger.info(f"[{trace_id}] Successfully generated {len(image_bytes_list)} images with Google AI")

            return ProviderResponse(
                content=f"Generated {len(image_bytes_list)} images",
                model=active_model,
                provider="google_ai",
                trace_id=trace_id,
                metadata={
                    'images': image_bytes_list,
                    'format': 'png'
                }
            )

        except Exception as e:
            logger.error(f"[{trace_id}] Google AI image generation failed: {str(e)}")
            self.record_failure()
            return ProviderResponse(
                content="",
                model=active_model if 'active_model' in locals() else "google_ai",
                provider="google_ai",
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
        """Placeholder for Google AI TTS (not natively supported by Gemini AI Studio SDK)."""
        return ProviderResponse(
            content="",
            model=model or "google_ai",
            provider="google_ai",
            trace_id=trace_id,
            error="Native text-to-speech is currently not supported by the Google AI provider. Please use an OpenAI model for speech generation."
        )

    def transcribe(
        self,
        audio_bytes: bytes,
        trace_id: str,
        model: Optional[str] = None,
        **kwargs
    ) -> ProviderResponse:
        """Transcribe audio using Gemini's multimodal capabilities."""
        try:
            active_model = model if model else "gemini-1.5-flash"
            logger.debug(f"[{trace_id}] Transcribing with Google AI model {active_model}")

            # Prepare contents with audio bytes
            from google.genai import types
            
            # We use the generate_content method with a Part containing the audio bytes
            contents = [
                types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type="audio/wav"
                ),
                types.Part.from_text(text="Transcribe this audio exactly as heard.")
            ]

            response = self.client.models.generate_content(
                model=active_model,
                contents=contents
            )

            self.record_success()
            logger.info(f"[{trace_id}] Successfully transcribed audio with Google AI")

            return ProviderResponse(
                content=response.text if response.text else "",
                model=active_model,
                provider="google_ai",
                trace_id=trace_id,
                metadata={
                    'model': active_model
                }
            )
        except Exception as e:
            logger.error(f"[{trace_id}] Google AI transcription failed: {str(e)}")
            self.record_failure()
            return ProviderResponse(
                content="",
                model=model or "gemini-1.5-flash",
                provider="google_ai",
                trace_id=trace_id,
                error=str(e)
            )
