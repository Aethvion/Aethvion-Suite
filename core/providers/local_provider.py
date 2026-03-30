"""
Aethvion Suite - Local Provider
Local LLM implementation (llama-cpp-python)
"""

import os
import re
import sys
import multiprocessing
from pathlib import Path
from typing import Dict, Optional, Iterator, Any, List
from .base_provider import BaseProvider, ProviderResponse, ProviderConfig, ProviderStatus
from core.utils.logger import get_logger

logger = get_logger(__name__)

def _safe_test_llama_load(model_path: str):
    """
    Run in an isolated process to catch hard C-level crashes (like missing AVX instructions).
    """
    try:
        from llama_cpp import Llama
        # Mute stdout/stderr so we don't spam the console during the test
        with open(os.devnull, 'w') as devnull:
            old_out = sys.stdout
            old_err = sys.stderr
            sys.stdout = devnull
            sys.stderr = devnull
            try:
                # Load with vocab_only to skip full weight allocation but still trigger
                # GGML backend initialization (which catches CPU instruction faults)
                llm = Llama(model_path=model_path, vocab_only=True, n_ctx=8, verbose=False)
            finally:
                sys.stdout = old_out
                sys.stderr = old_err
    except Exception:
        # Standard exceptions are fine, they don't hard-crash the process anyway.
        # We only care if the process exits with a non-zero crash code (e.g. 0xC000001D).
        pass
    sys.exit(0)

# Lazy import for llama-cpp-python
Llama = None

class LocalProvider(BaseProvider):
    """
    Local provider for Aethvion Suite (private offline fallback).
    """
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.llm = None
        self.current_model_path = None
        
        # Determine base directory for GGUF models
        from core.utils.paths import LOCAL_MODELS_GGUF
        self.base_dir = LOCAL_MODELS_GGUF
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
                raise ImportError(
                    f"llama-cpp-python not installed or failed to load. "
                    f"To use local models, run: pip install -e \".[local-llm]\" "
                    f"(Original error: {e})"
                )

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
            logger.info(f"Safely testing local model stability for {model_path}...")
            
            # Spawn a subprocess to test if model loading triggers a fatal hardware crash
            ctx = multiprocessing.get_context("spawn")
            p = ctx.Process(target=_safe_test_llama_load, args=(str(model_path),))
            p.start()
            p.join()
            
            if p.exitcode != 0:
                logger.error(f"FATAL: Local model initialisation crashed. Exit code: {p.exitcode}")
                raise RuntimeError(
                    f"Fatal Hardware Crash Detected (Exit code: {p.exitcode}).\n"
                    f"Your PC's CPU may not support the modern instructions (like AVX/AVX2) required "
                    f"by the currently installed llama-cpp-python package.\n"
                    f"Fix: Uninstall and reinstall with basic CPU flags, or use Aethvion's minimal installer."
                )

            logger.info(f"Loading local model from {model_path} in main process...")
            # Unload old model if exists
            self.llm = None
            
            # Load new model
            self.llm = Llama(
                model_path=str(model_path),
                n_ctx=kwargs.get('n_ctx', 4096),
                n_threads=kwargs.get('n_threads', os.cpu_count()),
                verbose=False
            )
            self.current_model_path = str(model_path)
            logger.info(f"Local model loaded successfully")

    # ── Model family detection ──────────────────────────────────────────────────

    _FAMILY_PATTERNS: Dict[str, List[str]] = {
        # Checked in order — first match wins.
        "nemotron": ["nemotron"],
        "phi3":     ["phi-3", "phi3", "phi_3", "phi-4", "phi4", "phi_4"],
        "qwen":     ["qwen2", "qwen-2", "qwen_2", "qwen3", "qwen-3", "qwen_3", "qwen"],
        "gemma":    ["gemma-2", "gemma2", "gemma_2", "gemma-3", "gemma3", "gemma_3", "gemma"],
        "mistral":  ["mistral", "mixtral"],
        "deepseek": ["deepseek"],
        "llama2":   ["llama-2", "llama2", "llama_2"],
        # Default: llama3 (covers Llama 3.x, Meta-Llama-3, etc.)
    }

    def _detect_family(self, model_id: str) -> str:
        """Return the chat-template family for the given model filename."""
        name = model_id.lower()
        for family, patterns in self._FAMILY_PATTERNS.items():
            if any(p in name for p in patterns):
                return family
        return "llama3"

    def _get_stop_tokens(self, family: str) -> List[str]:
        """Return the appropriate EOS / stop tokens for the model family."""
        stops: Dict[str, List[str]] = {
            "llama3":   ["<|eot_id|>", "<|end_of_text|>", "User:", "Misaka:"],
            "nemotron": ["<extra_id_1>", "User:", "Misaka:"],
            "phi3":     ["<|end|>", "<|endoftext|>", "<|user|>", "User:", "Misaka:"],
            "qwen":     ["<|im_end|>", "User:", "Misaka:"],
            "gemma":    ["<end_of_turn>", "User:", "Misaka:"],
            "mistral":  ["</s>", "[INST]", "User:", "Misaka:"],
            "deepseek": ["<|end▁of▁sentence|>", "<|User|>", "User:", "Misaka:"],
            "llama2":   ["</s>", "[INST]", "User:", "Misaka:"],
        }
        return stops.get(family, stops["llama3"])

    # ── Prompt parsing (model-agnostic) ─────────────────────────────────────────

    def _parse_prompt(self, prompt: str, system_prompt: str = None):
        """
        Parse the Aethvion prompt format into (system, history_turns, user_message).
        history_turns is a list of ("user"|"assistant", content) tuples.
        """
        system_part = system_prompt or ""
        history_turns: List[tuple] = []
        user_part = ""

        if "--- RECENT CONVERSATION history ---" in prompt:
            parts = prompt.split("--- RECENT CONVERSATION history ---", 1)
            if not system_part:
                system_part = parts[0].strip()
            rest = parts[1].strip()

            if "\nUser: " in rest:
                history_raw, user_content = rest.rsplit("\nUser: ", 1)
                history_raw = history_raw.strip()
            else:
                history_raw = ""
                user_content = rest

            user_part = user_content.replace("User: ", "").split("\nMisaka:")[0].strip()

            if history_raw:
                turns = re.split(r'\n(User|Misaka): ', "\n" + history_raw)
                for i in range(1, len(turns) - 1, 2):
                    role = "user" if turns[i] == "User" else "assistant"
                    content = turns[i + 1].strip()
                    if content:
                        history_turns.append((role, content))
        else:
            # Plain format used by agent runner / Code IDE
            user_part = prompt.replace("User: ", "").split("\nMisaka:")[0].strip()

        if not system_part:
            system_part = "You are Misaka Cipher, a sentient AI assistant."

        return system_part, history_turns, user_part

    # ── Per-family template renderers ────────────────────────────────────────────

    def _fmt_llama3(self, system: str, history: List[tuple], user: str) -> str:
        out = f"<|start_header_id|>system<|end_header_id|>\n\n{system}<|eot_id|>"
        for role, content in history:
            out += f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}<|eot_id|>"
        out += f"<|start_header_id|>user<|end_header_id|>\n\n{user}<|eot_id|>"
        out += "<|start_header_id|>assistant<|end_header_id|>\n\n"
        return out

    def _fmt_nemotron(self, system: str, history: List[tuple], user: str) -> str:
        out = f"<extra_id_0>System\n{system}\n"
        for role, content in history:
            tag = "User" if role == "user" else "Assistant"
            out += f"<extra_id_1>{tag}\n{content}\n"
        out += f"<extra_id_1>User\n{user}\n<extra_id_1>Assistant\n"
        return out

    def _fmt_phi3(self, system: str, history: List[tuple], user: str) -> str:
        out = f"<|system|>\n{system}<|end|>\n"
        for role, content in history:
            tag = "<|user|>" if role == "user" else "<|assistant|>"
            out += f"{tag}\n{content}<|end|>\n"
        out += f"<|user|>\n{user}<|end|>\n<|assistant|>\n"
        return out

    def _fmt_qwen(self, system: str, history: List[tuple], user: str) -> str:
        out = f"<|im_start|>system\n{system}<|im_end|>\n"
        for role, content in history:
            out += f"<|im_start|>{role}\n{content}<|im_end|>\n"
        out += f"<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n"
        return out

    def _fmt_gemma(self, system: str, history: List[tuple], user: str) -> str:
        # Gemma injects system into the first user turn
        first_user = f"{system}\n\n{user}" if not history else user
        out = ""
        for role, content in history:
            tag = "user" if role == "user" else "model"
            turn_content = f"{system}\n\n{content}" if tag == "user" and not out else content
            out += f"<start_of_turn>{tag}\n{turn_content}<end_of_turn>\n"
        out += f"<start_of_turn>user\n{first_user if not history else user}<end_of_turn>\n"
        out += "<start_of_turn>model\n"
        return out

    def _fmt_mistral(self, system: str, history: List[tuple], user: str) -> str:
        # Mistral v1/v2: system injected into first [INST] block
        out = ""
        first = True
        for role, content in history:
            if role == "user":
                if first:
                    out += f"[INST] {system}\n\n{content} [/INST]"
                    first = False
                else:
                    out += f"[INST] {content} [/INST]"
            else:
                out += f" {content}</s>"
        if first:
            out += f"[INST] {system}\n\n{user} [/INST]"
        else:
            out += f"[INST] {user} [/INST]"
        return out

    def _fmt_deepseek(self, system: str, history: List[tuple], user: str) -> str:
        out = f"<|begin▁of▁sentence|>{system}\n"
        for role, content in history:
            tag = "<|User|>" if role == "user" else "<|Assistant|>"
            out += f"{tag}{content}"
            if role == "assistant":
                out += "<|end▁of▁sentence|>"
        out += f"<|User|>{user}<|Assistant|>"
        return out

    def _fmt_llama2(self, system: str, history: List[tuple], user: str) -> str:
        out = ""
        first = True
        for role, content in history:
            if role == "user":
                if first:
                    out += f"[INST] <<SYS>>\n{system}\n<</SYS>>\n\n{content} [/INST]"
                    first = False
                else:
                    out += f"[INST] {content} [/INST]"
            else:
                out += f" {content} </s><s>"
        if first:
            out += f"[INST] <<SYS>>\n{system}\n<</SYS>>\n\n{user} [/INST]"
        else:
            out += f"[INST] {user} [/INST]"
        return out

    _FORMATTERS = {
        "llama3":   _fmt_llama3,
        "nemotron": _fmt_nemotron,
        "phi3":     _fmt_phi3,
        "qwen":     _fmt_qwen,
        "gemma":    _fmt_gemma,
        "mistral":  _fmt_mistral,
        "deepseek": _fmt_deepseek,
        "llama2":   _fmt_llama2,
    }

    def _apply_chat_template(self, prompt: str, model_id: str = "", system_prompt: str = None) -> str:
        """
        Detect the model family, parse the prompt, and apply the correct chat template.
        Already-formatted prompts (containing known template tokens) are passed through.
        """
        # Pass-through if already formatted
        known_tokens = [
            "<|begin_of_text|>", "<|start_header_id|>",  # llama3
            "<extra_id_0>",                                # nemotron
            "<|im_start|>",                                # qwen
            "<|system|>",                                  # phi3
            "<start_of_turn>",                             # gemma
        ]
        if any(t in prompt for t in known_tokens):
            return prompt

        family = self._detect_family(model_id)
        system, history, user = self._parse_prompt(prompt, system_prompt)
        formatter = self._FORMATTERS.get(family, self._FORMATTERS["llama3"])
        result = formatter(self, system, history, user)
        logger.debug(f"[LocalProvider] family={family} model={model_id} prompt_len={len(result)}")
        return result

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

            family = self._detect_family(model_id)
            formatted_prompt = self._apply_chat_template(
                prompt, model_id=model_id, system_prompt=kwargs.get('system_prompt')
            )

            response = self.llm(
                formatted_prompt,
                max_tokens=max_tokens or 512,
                temperature=temperature,
                stop=self._get_stop_tokens(family),
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

            family = self._detect_family(model_id)
            formatted_prompt = self._apply_chat_template(
                prompt, model_id=model_id, system_prompt=kwargs.get('system_prompt')
            )

            stream = self.llm(
                formatted_prompt,
                max_tokens=max_tokens or 512,
                temperature=temperature,
                stop=self._get_stop_tokens(family),
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
