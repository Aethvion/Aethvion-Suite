"""
Aethvion Suite - OpenRouter Provider
OpenRouter multi-model gateway implementation (OpenAI-compatible API)
"""

import os
import requests
import json
from typing import Iterator, Optional
from .base_provider import BaseProvider, ProviderResponse, ProviderConfig
from core.utils.logger import get_logger

logger = get_logger(__name__)

APP_NAME = "Aethvion Suite"
APP_URL  = "https://github.com/Aethvion/Aethvion-Suite"


class OpenRouterProvider(BaseProvider):
    """
    OpenRouter provider implementation.
    Routes requests through OpenRouter's unified gateway to hundreds of models.
    Uses the OpenAI-compatible chat completions API.
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.api_key = os.getenv(config.api_key, config.api_key)
        if not self.api_key:
            logger.warning(f"OpenRouter API key not found in environment: {config.api_key}")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": APP_URL,
            "X-Title": APP_NAME,
        }
        logger.info(f"Initialized OpenRouter provider with model: {config.model}")

    def generate(
        self,
        prompt: str,
        trace_id: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs,
    ) -> ProviderResponse:
        """Generate response via OpenRouter."""
        active_model = model if model else self.config.model
        try:
            system_prompt = kwargs.pop("system_prompt", None)
            kwargs.pop("model", None)
            kwargs.pop("json_mode", None)

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": active_model,
                "messages": messages,
                "temperature": temperature,
                **kwargs,
            }
            if max_tokens:
                payload["max_tokens"] = max_tokens

            response = requests.post(
                f"{self.config.endpoint}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=self.config.timeout,
            )
            if not response.ok:
                logger.error(f"[{trace_id}] OpenRouter API error {response.status_code}: {response.text[:500]}")
            response.raise_for_status()
            data = response.json()
            self.record_success()
            return ProviderResponse(
                content=data["choices"][0]["message"]["content"],
                model=active_model,
                provider="openrouter",
                trace_id=trace_id,
                metadata={
                    "model": active_model,
                    "finish_reason": data["choices"][0].get("finish_reason"),
                    "usage": data.get("usage", {}),
                },
            )
        except requests.HTTPError as e:
            body = e.response.text[:500] if e.response is not None else ""
            logger.error(f"[{trace_id}] OpenRouter HTTP error: {e} | Body: {body}")
            self.record_failure()
            return ProviderResponse(content="", model=active_model, provider="openrouter", trace_id=trace_id, error=f"{e} | {body}")
        except Exception as e:
            logger.error(f"[{trace_id}] OpenRouter generation failed: {e}")
            self.record_failure()
            return ProviderResponse(content="", model=active_model, provider="openrouter", trace_id=trace_id, error=str(e))

    def stream(
        self,
        prompt: str,
        trace_id: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Iterator[str]:
        """Stream response via OpenRouter."""
        try:
            payload = {
                "model": self.config.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "stream": True,
            }
            if max_tokens:
                payload["max_tokens"] = max_tokens

            response = requests.post(
                f"{self.config.endpoint}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=self.config.timeout,
                stream=True,
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        data = line[6:]
                        if data != "[DONE]":
                            chunk = json.loads(data)
                            delta = chunk["choices"][0]["delta"].get("content")
                            if delta:
                                yield delta

            self.record_success()
        except Exception as e:
            logger.error(f"[{trace_id}] OpenRouter streaming failed: {e}")
            self.record_failure()
            yield f"Error: {e}"

    def generate_image(self, prompt, trace_id, **kwargs) -> ProviderResponse:
        return ProviderResponse(content="", model=self.config.model, provider="openrouter", trace_id=trace_id, error="Image generation not supported via OpenRouter")

    def generate_speech(self, text, trace_id, **kwargs) -> ProviderResponse:
        return ProviderResponse(content="", model=self.config.model, provider="openrouter", trace_id=trace_id, error="Speech synthesis not supported via OpenRouter")

    def transcribe(self, audio_bytes, trace_id, **kwargs) -> ProviderResponse:
        return ProviderResponse(content="", model=self.config.model, provider="openrouter", trace_id=trace_id, error="Audio transcription not supported via OpenRouter")

    def validate_credentials(self) -> bool:
        try:
            response = requests.get(
                f"{self.config.endpoint}/models",
                headers=self.headers,
                timeout=10,
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"OpenRouter credential validation failed: {e}")
            return False
