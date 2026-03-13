"""
Misaka Cipher - Local Provider
Implementation for local LLMs using llama-cpp-python
"""

import os
import re
from pathlib import Path
from typing import Dict, Optional, Iterator, Any, List
from .base_provider import BaseProvider, ProviderResponse, ProviderConfig, ProviderStatus
from core.utils.logger import get_logger

logger = get_logger(__name__)

# Lazy import for llama-cpp-python
Llama = None

class LocalProvider(BaseProvider):
    """
    Provider implementation for local models using llama-cpp-python.
    """
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.llm = None
        self.current_model_path = None
        
        # Determine base directory for models
        # project_root / LocalModels
        self.base_dir = Path(__file__).parent.parent.parent / "LocalModels"
        if not self.base_dir.exists():
            self.base_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_llama(self, model_id: str, **kwargs):
        """Ensure the llama-cpp-python model is loaded."""
        global Llama
        if Llama is None:
            try:
                from llama_cpp import Llama as LlamaClass
                Llama = LlamaClass
                logger.info("Successfully imported llama-cpp-python")
            except Exception as e:
                logger.error(f"Failed to import llama-cpp-python: {e}", exc_info=True)
                raise ImportError(f"llama-cpp-python not installed or failed to load: {e}")

        # Resolve model path
        model_path = self.base_dir / model_id
        if not model_path.exists():
            # Support .gguf extension if not provided
            if not model_id.endswith(".gguf"):
                model_path = self.base_dir / f"{model_id}.gguf"
        
        if not model_path.exists():
            logger.error(f"Local model not found at {model_path}")
            raise FileNotFoundError(f"Local model not found: {model_path}")

        # Check if we need to (re)load the model
        if self.llm is None or self.current_model_path != str(model_path):
            logger.info(f"Loading local model from {model_path}...")
            # Unload old model if exists
            self.llm = None
            
            # Load new model
            self.llm = Llama(
                model_path=str(model_path),
                n_ctx=kwargs.get('n_ctx', 2048),
                n_threads=kwargs.get('n_threads', os.cpu_count()),
                verbose=False
            )
            self.current_model_path = str(model_path)
            logger.info(f"Local model loaded successfully")

    def _apply_chat_template(self, prompt: str) -> str:
        """
        Wraps a raw text prompt into the Llama 3 Chat Template format.
        Expects Misaka's default prompt format: [System] \n--- HISTORY ---\n User: ... \n Misaka:
        """
        # If the prompt already has Llama 3 tags, don't double-wrap
        if "<|begin_of_text|>" in prompt or "<|start_header_id|>" in prompt:
            return prompt

        # Attempt to split system prompt from history/current message
        system_part = ""
        history_part = ""
        user_part = prompt

        if "--- RECENT CONVERSATION history ---" in prompt:
            parts = prompt.split("--- RECENT CONVERSATION history ---")
            system_part = parts[0].strip()
            rest = parts[1].strip()
            
            # Ensure rest starts with a newline for consistent rsplit or handle it
            # We look for the last occurrence of "User: " that isn't the first character if possible,
            # or just handle the first character case.
            if "\nUser: " in rest:
                history_and_user_parts = rest.rsplit("\nUser: ", 1)
                history_part = history_and_user_parts[0].strip()
                user_content = history_and_user_parts[1]
            else:
                user_content = rest
            
            # Clean up role labels from user_content
            user_part = user_content.replace("User: ", "").split("\nMisaka:")[0].strip()
        else:
            # Fallback for simple prompts
            user_part = prompt.replace("User: ", "").split("\nMisaka:")[0].strip()

        # Build the template
        formatted = "<|start_header_id|>system<|end_header_id|>\n\n"
        formatted += system_part if system_part else "You are Misaka Cipher, a helpful digital companion."
        formatted += "<|eot_id|>"

        if history_part:
            # Simple parsing of history turns
            turns = re.split(r'\n(User|Misaka): ', "\n" + history_part)
            # turns[0] will be empty. Even indices (2, 4, ...) are content, odd indices (1, 3, ...) are roles
            for i in range(1, len(turns), 2):
                role = "user" if turns[i] == "User" else "assistant"
                content = turns[i+1].strip()
                if content:
                    formatted += f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}<|eot_id|>"

        formatted += f"<|start_header_id|>user<|end_header_id|>\n\n{user_part}<|eot_id|>"
        formatted += "<|start_header_id|>assistant<|end_header_id|>\n\n"
        
        return formatted

    def generate(
        self,
        prompt: str,
        trace_id: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> ProviderResponse:
        try:
            model_id = model or self.config.model
            self._ensure_llama(model_id, **kwargs)
            
            # Apply chat template
            import re
            formatted_prompt = self._apply_chat_template(prompt)
            
            response = self.llm(
                formatted_prompt,
                max_tokens=max_tokens or 512,
                temperature=temperature,
                stop=["<|eot_id|>", "<|end_of_text|>", "User:", "Misaka:"],
                echo=False,
                repeat_penalty=kwargs.get('repeat_penalty', 1.1),
                top_p=kwargs.get('top_p', 0.9)
            )
            
            content = response['choices'][0]['text'].strip()
            
            return ProviderResponse(
                content=content,
                model=model_id,
                provider="local",
                trace_id=trace_id,
                metadata={'usage': response.get('usage', {})}
            )
            
        except Exception as e:
            logger.error(f"Local model generation failed: {str(e)}")
            return ProviderResponse(
                content="",
                model=model or self.config.model,
                provider="local",
                trace_id=trace_id,
                error=str(e)
            )

    def generate_image(self, *args, **kwargs) -> ProviderResponse:
        return ProviderResponse(content="", model="", provider="local", trace_id="", error="Local image generation not supported yet")

    def generate_speech(self, *args, **kwargs) -> ProviderResponse:
        return ProviderResponse(content="", model="", provider="local", trace_id="", error="Local speech generation not supported yet")

    def transcribe(self, *args, **kwargs) -> ProviderResponse:
        return ProviderResponse(content="", model="", provider="local", trace_id="", error="Local transcription not supported yet")

    def stream(
        self,
        prompt: str,
        trace_id: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Iterator[str]:
        try:
            model_id = kwargs.get('model') or self.config.model
            self._ensure_llama(model_id, **kwargs)
            
            formatted_prompt = self._apply_chat_template(prompt)
            
            stream = self.llm(
                formatted_prompt,
                max_tokens=max_tokens or 512,
                temperature=temperature,
                stop=["<|eot_id|>", "<|end_of_text|>", "User:", "Misaka:"],
                stream=True,
                repeat_penalty=kwargs.get('repeat_penalty', 1.1),
                top_p=kwargs.get('top_p', 0.9)
            )
            
            for chunk in stream:
                text = chunk['choices'][0]['text']
                if text:
                    yield text
                    
        except Exception as e:
            logger.error(f"Local model streaming failed: {str(e)}")
            yield f" [LOCAL ERROR: {str(e)}] "

    def validate_credentials(self) -> bool:
        # Local provider doesn't need credentials, just check if base_dir exists
        return self.base_dir.exists()
