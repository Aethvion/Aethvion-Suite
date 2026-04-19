"""
Aethvion Suite — Ollama Provider
Routes requests to a locally-running Ollama instance (http://localhost:11434).
Ollama handles GPU offload automatically and supports 100+ GGUF models.
"""

import json
from typing import Optional, Iterator, List, Dict, Any

from .base_provider import BaseProvider, ProviderResponse, ProviderConfig
from core.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_ENDPOINT = "http://localhost:11434"


class OllamaProvider(BaseProvider):
    """
    Provider backed by a local Ollama instance.
    No API key needed — just Ollama running on the host.
    """

    def _base(self) -> str:
        return (self.config.endpoint or _DEFAULT_ENDPOINT).rstrip("/")

    def _build_messages(self, prompt: str, kwargs: dict) -> list:
        """Convert raw prompt string into Ollama message list."""
        system = kwargs.get("system_prompt") or "You are a helpful assistant."
        return [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ]

    def generate(
        self,
        prompt: str,
        trace_id: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> ProviderResponse:
        import requests as _req

        model_id = model or self.config.model
        try:
            r = _req.post(
                f"{self._base()}/api/chat",
                json={
                    "model":    model_id,
                    "messages": self._build_messages(prompt, kwargs),
                    "stream":   False,
                    "options":  {
                        "temperature": temperature,
                        "num_predict": max_tokens or 1024,
                    },
                },
                timeout=self.config.timeout or 300,
            )
            r.raise_for_status()
            data    = r.json()
            content = data.get("message", {}).get("content", "")
            return ProviderResponse(
                content=content,
                model=model_id,
                provider="ollama",
                trace_id=trace_id,
                metadata={"eval_count": data.get("eval_count")},
            )
        except Exception as exc:
            logger.error(f"Ollama generate error: {exc}")
            return ProviderResponse(
                content="", model=model_id, provider="ollama",
                trace_id=trace_id, error=str(exc),
            )

    def stream(
        self,
        prompt: str,
        trace_id: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> Iterator[str]:
        import requests as _req

        model_id = kwargs.get("model") or self.config.model
        try:
            with _req.post(
                f"{self._base()}/api/chat",
                json={
                    "model":    model_id,
                    "messages": self._build_messages(prompt, kwargs),
                    "stream":   True,
                    "options":  {
                        "temperature": temperature,
                        "num_predict": max_tokens or 1024,
                    },
                },
                stream=True,
                timeout=self.config.timeout or 300,
            ) as r:
                r.raise_for_status()
                for raw in r.iter_lines():
                    if raw:
                        try:
                            data  = json.loads(raw)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                yield token
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
        except Exception as exc:
            logger.error(f"Ollama stream error: {exc}")
            yield f" [OLLAMA ERROR: {exc}] "

    def validate_credentials(self) -> bool:
        import requests as _req
        try:
            r = _req.get(f"{self._base()}/api/tags", timeout=3)
            return r.ok
        except Exception:
            return False

    # ── Unsupported capabilities ──────────────────────────────────────────────

    def generate_image(self, *args, **kwargs) -> ProviderResponse:
        return ProviderResponse(
            content="", model="", provider="ollama", trace_id="",
            error="Ollama does not support image generation",
        )

    def generate_speech(self, *args, **kwargs) -> ProviderResponse:
        return ProviderResponse(
            content="", model="", provider="ollama", trace_id="",
            error="Ollama does not support TTS",
        )

    def transcribe(self, *args, **kwargs) -> ProviderResponse:
        return ProviderResponse(
            content="", model="", provider="ollama", trace_id="",
            error="Ollama does not support STT",
        )
