"""
Misaka Cipher - Provider Manager
Orchestrates multi-provider failover and routing
"""

import yaml
import json
from pathlib import Path
from typing import Dict, List, Optional, Iterator
from .base_provider import BaseProvider, ProviderResponse, ProviderConfig, ProviderStatus
from .google_provider import GoogleAIProvider
from .openai_provider import OpenAIProvider
from .grok_provider import GrokProvider
from .anthropic_provider import AnthropicProvider
from core.utils.logger import get_logger

logger = get_logger(__name__)


class ProviderManager:
    """
    Manages multiple LLM providers with profile-based routing.
    """
    
    PROVIDER_CLASSES = {
        'google_ai': GoogleAIProvider,
        'openai': OpenAIProvider,
        'grok': GrokProvider,
        'anthropic': AnthropicProvider
    }
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize provider manager.
        
        Args:
            config_path: Path to providers.yaml
        """
        self.providers: Dict[str, BaseProvider] = {}
        self.priority_order: List[str] = []
        self.config = {}
        self.model_to_provider_map: Dict[str, str] = {}
        self.model_descriptor_map: Dict[str, Dict] = {}
        self.auto_routing_config: Dict = {}
        self.registry: Dict = {}
        
        # Load configuration
        if config_path is None:
            # __file__ = core/providers/provider_manager.py → parent.parent.parent = project root
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "core" / "config" / "providers.yaml"
        
        self._load_config(config_path)
        self._initialize_providers()
        
        logger.info("Provider Manager initialized with providers: " + 
                   ", ".join(self.priority_order))
    
    def _load_config(self, config_path: Path):
        """Load provider configuration from YAML."""
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
            self.config = data.get('providers', {})
            self.failover_config = data.get('failover', {})
            
        # Load Overrides from model_registry.json
        self._load_registry_overrides()

    def _load_registry_overrides(self):
        """Load overrides from model_registry.json if present."""
        # Find registry file: data/config/model_registry.json
        # __file__ = core/providers/provider_manager.py → parent.parent.parent = project root
        project_root = Path(__file__).parent.parent.parent
        registry_path = project_root / "data" / "config" / "model_registry.json"
        
        if not registry_path.exists():
            return
            
        try:
            with open(registry_path, 'r') as f:
                registry = json.load(f)
            
            self.registry = registry
            registry_providers = registry.get('providers', {})
            
            self.model_to_provider_map = {}
            
            for name, reg_config in registry_providers.items():
                if name in self.config:
                    # Build Model Map (model_id -> provider_name)
                    models = reg_config.get('models', {})
                    for model_id, model_data in models.items():
                        if model_id:
                            self.model_to_provider_map[model_id] = name
                            # Also store full descriptor for Auto routing
                            self.model_descriptor_map[model_id] = {
                                'provider': name,
                                'description': model_data.get('description', '') if isinstance(model_data, dict) else '',
                                'capabilities': model_data.get('capabilities', []) if isinstance(model_data, dict) else [],
                            }

                    logger.info(f"Loaded registry models for {name}")
            
            # Load Profiles
            profiles = registry.get('profiles', {})
            chat_profiles = profiles.get('chat_profiles', {})
            agent_profiles = profiles.get('agent_profiles', {})
            
            # Default profiles
            self.chat_priority_order = chat_profiles.get('default', [])
            self.agent_priority_order = agent_profiles.get('default', [])

            # Fallback if profiles are empty
            if not self.chat_priority_order:
                self.chat_priority_order = [
                    mid for mid, info in self.model_descriptor_map.items()
                    if 'CHAT' in [c.upper() for c in info.get('capabilities', [])]
                ]
            if not self.agent_priority_order:
                self.agent_priority_order = [
                    mid for mid, info in self.model_descriptor_map.items()
                    if 'CHAT' in [c.upper() for c in info.get('capabilities', [])]
                ]

            # Load Auto Routing config
            self.auto_routing_config = registry.get('auto_routing', {})
            if not self.auto_routing_config:
                logger.warning("[AUTO ROUTING] No configuration found in registry")

            logger.info(f"Chat Priority: {self.chat_priority_order}")
            logger.info(f"Agent Priority: {self.agent_priority_order}")
                    
        except Exception as e:
            logger.error(f"Failed to load model registry overrides: {str(e)}")
            # Fallback to default behavior if failed
            self.chat_priority_order = []
            self.agent_priority_order = []
            self.model_descriptor_map = {}
            self.auto_routing_config = {}
            self.registry = {}

    def reload_config(self):
        """Reload configuration from disk and update active providers."""
        logger.info("Reloading provider configuration...")
        
        # 1. Reload registry overrides (Priorities, Model Maps)
        self._load_registry_overrides()
        
        # 2. Update active provider instances with new config
        project_root = Path(__file__).parent.parent.parent
        registry_path = project_root / "data" / "config" / "model_registry.json"
        
        if not registry_path.exists():
            return
            
        try:
            with open(registry_path, 'r') as f:
                registry = json.load(f)
            
            for name, reg_config in registry.get('providers', {}).items():
                if name in self.providers:
                    provider = self.providers[name]
                    
                    # Update Max Retries
                    if 'retries_per_step' in reg_config:
                        provider.config.max_retries = int(reg_config['retries_per_step'])
                        logger.debug(f"Updated {name} max_retries to {provider.config.max_retries}")
                        
                    # We could also update specific model configs here if we tracked them per-provider
                    
            logger.info("Provider configuration reload complete")
            
        except Exception as e:
            logger.error(f"Failed to reload provider config: {e}")

    def _initialize_providers(self):
        """Initialize only providers that are defined in the model registry."""
        # Get providers mentioned in registry
        project_root = Path(__file__).parent.parent.parent
        registry_path = project_root / "data" / "config" / "model_registry.json"
        
        registered_provider_names = []
        if registry_path.exists():
            try:
                with open(registry_path, 'r') as f:
                    registry = json.load(f)
                registered_provider_names = list(registry.get('providers', {}).keys())
            except Exception as e:
                logger.error(f"Failed to read registry for initialization: {e}")

        for name, config in self.config.items():
            try:
                # ONLY initialize if present in registry
                if name not in registered_provider_names:
                    logger.debug(f"Skipping initialization for unconfigured provider: {name}")
                    continue
                
                provider_class = self.PROVIDER_CLASSES.get(name)
                if not provider_class:
                    logger.warning(f"Unknown provider: {name}")
                    continue
                
                # Get the first model from registry for this provider if default is missing
                default_model = config.get('model')
                if not default_model and registry_path.exists():
                    # Re-read or use cached models
                    registry_models = registry.get('providers', {}).get(name, {}).get('models', {})
                    if registry_models:
                        default_model = list(registry_models.keys())[0]

                provider_config = ProviderConfig(
                    name=config.get('name', name),
                    model=default_model,
                    api_key=config.get('api_key_env', ''),
                    endpoint=config.get('endpoint', ''),
                    timeout=config.get('timeout', 30),
                    fallback_models=config.get('fallback_models', [])
                )
                
                self.providers[name] = provider_class(provider_config)
                logger.info(f"Initialized provider: {name} (default model: {default_model})")
                
            except Exception as e:
                logger.error(f"Failed to initialize provider {name}: {str(e)}")
    
    def get_provider(self, name: str) -> Optional[BaseProvider]:
        """
        Get a specific provider by name.
        
        Args:
            name: Provider name (google_ai, openai, grok)
            
        Returns:
            Provider instance or None if not found
        """
        return self.providers.get(name)
    
    def call_with_failover(
        self,
        prompt: str,
        trace_id: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        preferred_provider: Optional[str] = None,
        model: Optional[str] = None,
        request_type: str = "generation",
        source: str = "chat",
        **kwargs
    ) -> ProviderResponse:
        """
        Call providers with automatic failover and profile-based routing.
        """
        model_order = []
        is_agent = request_type == "agent_call" or "agent" in request_type

        # Extract auto-routing metadata placeholder (set later if AUTO mode runs)
        auto_routing_meta: dict = {}

        # 1. Profile Routing & Specific Models
        if model:
            if model == "auto":
                # Description-aware Auto Complexity Routing using configured profile
                logger.info(f"[{trace_id}] AUTO mode: description-aware routing")

                profile_type = 'agent' if is_agent else 'chat'
                auto_profile = self.auto_routing_config.get(profile_type, {})

                # Build candidate pool from enabled models in auto_routing config
                pool_config = auto_profile.get('models', {})
                if pool_config:
                    candidate_pool = [
                        mid for mid, cfg in pool_config.items()
                        if cfg.get('enabled', True) and mid in self.model_to_provider_map
                    ]
                else:
                    # Fallback: use default profile order
                    candidate_pool = (
                        self.agent_priority_order.copy() if is_agent
                        else self.chat_priority_order.copy()
                    )

                if not candidate_pool:
                    logger.warning(f"[{trace_id}] AUTO: no enabled models in pool, using full descriptor map")
                    candidate_pool = [
                        mid for mid, info in self.model_descriptor_map.items()
                        if 'chat' in info.get('capabilities', [])
                    ]

                # Bypassing Routing if <= 1 model
                if len(candidate_pool) <= 1:
                    if candidate_pool:
                        model_order = [candidate_pool[0]]
                        logger.info(f"[{trace_id}] AUTO mode: skipping complexity routing for single-model pool ('{candidate_pool[0]}')")
                    # If empty, model_order remains empty and falls through to default priorities
                else:
                    # FULL ROUTING LOGIC
                    # Configured route picker (falls back to first candidate)
                    configured_picker = auto_profile.get('route_picker', '')
                    route_picker = configured_picker if configured_picker in self.model_to_provider_map else candidate_pool[0]

                    # Build descriptor lines
                    descriptor_lines = []
                    for mid in candidate_pool:
                        info = self.model_descriptor_map.get(mid, {})
                        provider_name = info.get('provider', '').lower()
                        desc = info.get('description', '').strip()
                        descriptor_lines.append(f"- {mid} (Provider: {provider_name}): {desc}" if desc else f"- {mid} (Provider: {provider_name})")

                    chosen = None
                    routing_reason = ''
                    direct_answer = None

                    if route_picker:
                        routing_prompt = (
                            f"You are a model router. The user wants to send a message to the best-fit AI model.\n"
                            f"Select the single best model from the list below for the user's message.\n\n"
                            f"CRITICAL RULES:\n"
                            f"1. If the user explicitly requests a specific PROVIDER (e.g., 'openai', 'grok', 'google', 'anthropic', 'claude', 'xai') or a specific MODEL, you MUST select that model or a model from that provider.\n"
                            f"2. If the user's request is simple (facts, simple greeting, short math, etc.) and YOU can answer it yourself, provide the answer in the 'answer' field and select yourself ('{route_picker}') as the model.\n"
                            f"3. Otherwise, select the most capable model for complex reasoning or the fastest model for simple tasks if not specified.\n\n"
                            f"Return ONLY valid JSON with exactly three fields, no markdown, no code fences:\n"
                            f"{{\"model\": \"<exact_model_id_from_list>\", \"reason\": \"<one sentence why>\", \"answer\": \"<optional direct answer if step 2 applies, else null>\"}}\n\n"
                            f"Available models:\n" + "\n".join(descriptor_lines) + "\n\n"
                            f"User message (first 800 chars): {prompt[:800]}"
                        )
                        try:
                            routing_response = self.call_with_failover(
                                prompt=routing_prompt,
                                trace_id=f"{trace_id}-router",
                                temperature=0.0,
                                model=route_picker,
                                request_type="generation",
                                source="auto_router",
                                images=kwargs.get('images')
                            )
                            if routing_response.success:
                                raw_content = routing_response.content.strip()
                                try:
                                    # Ensure we don't have markdown fences
                                    if "```json" in raw_content:
                                        raw_content = raw_content.split("```json")[1].split("```")[0].strip()
                                    elif "```" in raw_content:
                                        raw_content = raw_content.split("```")[1].split("```")[0].strip()
                                    
                                    parsed = json.loads(raw_content)
                                    raw_model = str(parsed.get('model', '')).strip().strip('"').split()[0]
                                    routing_reason = str(parsed.get('reason', '')).strip()
                                    direct_answer = parsed.get('answer')
                                except Exception:
                                    # Fallback: treat as plain model ID string
                                    raw_model = raw_content.strip('\"').strip("'").split()[0]
                                    routing_reason = 'Fallback parsing'
                                
                                if raw_model in candidate_pool:
                                    chosen = raw_model
                                    logger.info(f"[{trace_id}] AUTO router ({route_picker}) chose: '{chosen}' reason: '{routing_reason}' DirectAnswer: {bool(direct_answer)}")
                                else:
                                    logger.warning(f"[{trace_id}] Router returned unknown model '{raw_model}', using pool order")
                            else:
                                logger.warning(f"[{trace_id}] Router call failed, using pool order")
                        except Exception as router_err:
                            logger.error(f"[{trace_id}] Router exception: {router_err}")

                    # 2.2 Handle Direct Answer Efficiency
                    if direct_answer and isinstance(direct_answer, str) and direct_answer.strip():
                        logger.info(f"[{trace_id}] ROUTER DIRECT ANSWER: Bypassing second model call.")
                        return ProviderResponse(
                            content=direct_answer,
                            model=route_picker or "auto_router",
                            provider=self.model_to_provider_map.get(route_picker, "unknown"),
                            trace_id=trace_id,
                            metadata={
                                'auto_routed': True,
                                'route_picker': route_picker,
                                'routing_reason': routing_reason,
                                'direct_answer': True
                            }
                        )

                    if chosen:
                        model_order = [chosen] + [m for m in candidate_pool if m != chosen]
                    else:
                        model_order = candidate_pool

                    # Capture routing metadata
                    auto_routing_meta = {
                        'route_picker': route_picker or '',
                        'routed_to': chosen or (candidate_pool[0] if candidate_pool else ''),
                        'routing_reason': routing_reason,
                        'auto_routed': True
                    }

            
            elif model.startswith("profile:"):
                # Profile selected from UI dropdown (e.g., profile:chat:default)
                parts = model.split(":")
                if len(parts) >= 3:
                    p_type, p_name = parts[1], parts[2]
                    profiles = {}
                    if hasattr(self, 'registry') and isinstance(self.registry, dict):
                        profiles = self.registry.get('profiles', {})
                    
                    target_dict = profiles.get(f"{p_type}_profiles", {})
                    if p_name in target_dict:
                        model_order = target_dict[p_name].copy()
                        logger.info(f"[{trace_id}] Using Profile '{p_name}' ({p_type}): {model_order}")
                    else:
                        logger.warning(f"[{trace_id}] Requested profile '{p_name}' not found. Falling back to default.")
            else:
                # Specific Model Override
                model_order = [model]
                logger.info(f"[{trace_id}] Specific Model requested: {model}")
        
        # 2. Select Default Priority List if nothing else matched
        if not model_order:
            if is_agent:
                model_order = self.agent_priority_order.copy()
                logger.info(f"[{trace_id}] Using DEFAULT AGENT priority: {model_order}")
            else:
                model_order = self.chat_priority_order.copy()
                logger.info(f"[{trace_id}] Using DEFAULT CHAT priority: {model_order}")
        
        # Ensure we have something
        if not model_order:
             logger.error(f"[{trace_id}] CRITICAL: No model routing order could be established.")
             return ProviderResponse(
                 content="", model="none", provider="none", trace_id=trace_id, 
                 error="No model routing configured."
             )

        last_error = None
        
        # Check if ALL mapped providers in the order are OFFLINE - if so, reset them
        # This prevents permanent lockout from temporary failures
        mapped_providers = [
            self.model_to_provider_map.get(m) for m in model_order 
            if hasattr(self, 'model_to_provider_map')
        ]
        
        all_offline = all(
            self.providers.get(name) and self.providers[name].status == ProviderStatus.OFFLINE
            for name in mapped_providers
            if name
        )
        if all_offline and mapped_providers:
            logger.warning(f"[{trace_id}] All requested providers are OFFLINE, resetting status to retry")
            for name in mapped_providers:
                if not name: continue
                provider = self.providers.get(name)
                if provider:
                    provider._consecutive_failures = 0
                    provider._status = ProviderStatus.HEALTHY
        
        # Try each model in order
        for model_id in model_order:
            target_provider_name = None
            if hasattr(self, 'model_to_provider_map'):
                target_provider_name = self.model_to_provider_map.get(model_id)
            
            if not target_provider_name:
                logger.warning(f"[{trace_id}] Skipping model '{model_id}', no mapped provider found.")
                continue
                
            provider = self.providers.get(target_provider_name)
            if not provider:
                continue
            
            # Skip if provider is offline
            if provider.status == ProviderStatus.OFFLINE:
                logger.warning(f"[{trace_id}] Skipping offline provider: {target_provider_name}")
                continue
            
            logger.info(f"[{trace_id}] Attempting request with model: {model_id} via {target_provider_name}")
            
            try:
                response = provider.generate(
                    prompt=prompt,
                    trace_id=trace_id,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    model=model_id, # Pass specific model
                    **kwargs
                )
                
                # Check if successful
                if response.success:
                    logger.info(f"[{trace_id}] Request successful with provider: {target_provider_name}")

                    # Merge auto-routing metadata into response for downstream tools/UI
                    if not response.metadata:
                        response.metadata = {}
                    if auto_routing_meta:
                        response.metadata.update(auto_routing_meta)
                        response.metadata['routed_model'] = model_id

                    # Log usage
                    try:
                        from core.workspace.usage_tracker import get_usage_tracker
                        tracker = get_usage_tracker()
                        tracker.log_api_call(
                            provider=response.provider,
                            model=response.model,
                            prompt=prompt,
                            response_content=response.content,
                            trace_id=trace_id,
                            success=True,
                            metadata=response.metadata,
                            source=source
                        )
                    except Exception as usage_err:
                        logger.debug(f"[{trace_id}] Usage tracking failed (non-critical): {usage_err}")

                    return response
                
                last_error = response.error
                logger.warning(f"[{trace_id}] Provider {target_provider_name} returned error: {last_error}")
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"[{trace_id}] Provider {target_provider_name} raised exception: {last_error}")
        
        # All providers failed
        logger.error(f"[{trace_id}] All providers failed. Last error: {last_error}")
        
        return ProviderResponse(
            content="",
            model="none",
            provider="none",
            trace_id=trace_id,
            error=f"All providers failed. Last error: {last_error}"
        )

    def call_with_failover_stream(
        self,
        prompt: str,
        trace_id: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> Iterator[str]:
        """
        Stream from providers with automatic failover.
        """
        model_order = [model] if model and model != "auto" else self.chat_priority_order.copy()
        
        last_error = None
        for model_id in model_order:
            target_provider_name = self.model_to_provider_map.get(model_id)
            if not target_provider_name:
                continue
                
            provider = self.providers.get(target_provider_name)
            if not provider or provider.status == ProviderStatus.OFFLINE:
                continue
            
            logger.info(f"[{trace_id}] Attempting stream with model: {model_id} via {target_provider_name}")
            
            try:
                # We need to know if the provider succeeded to skip others
                success = False
                for chunk in provider.stream(
                    prompt=prompt,
                    trace_id=trace_id,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    model=model_id,
                    **kwargs
                ):
                    success = True
                    yield chunk
                
                if success:
                    return
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[{trace_id}] Stream failed for {target_provider_name}: {last_error}")
        
        if last_error:
            yield f" [STREAM ERROR: {last_error}] "
    
    def health_check_all(self) -> Dict[str, ProviderStatus]:
        """
        Run health checks on all providers.
        
        Returns:
            Dictionary of provider name to status
        """
        results = {}
        for name, provider in self.providers.items():
            status = provider.health_check()
            results[name] = status
            logger.info(f"Provider {name} status: {status.value}")
        
        return results
    
    def get_status_summary(self) -> Dict:
        """Get summary of all provider statuses."""
        return {
            'providers': {
                name: {
                    'status': provider.status.value,
                    'model': provider.config.model,
                    'is_healthy': provider.is_healthy
                }
                for name, provider in self.providers.items()
            },
            'chat_priority': getattr(self, 'chat_priority_order', []),
            'agent_priority': getattr(self, 'agent_priority_order', [])
        }

    def get_provider_for_capability(self, capability: str) -> Optional[BaseProvider]:
        """Find the first healthy provider that supports the given capability."""
        # capability should be CHAT, IMAGE, AUDIO (case-insensitive)
        cap = capability.upper()
        
        # Check model descriptor map for models with this capability
        for model_id, info in self.model_descriptor_map.items():
            if cap in [c.upper() for c in info.get('capabilities', [])]:
                provider_name = info.get('provider')
                if provider_name:
                    p = self.providers.get(provider_name)
                    if p and p.is_healthy:
                        return p
        
        # Fallback to priority order if no descriptor match
        for name in self.priority_order:
            p = self.providers.get(name)
            if p and p.is_healthy:
                return p
        
        return None

    def generate_speech(
        self,
        text: str,
        trace_id: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        voice: str = "alloy",
        format: str = "mp3",
        **kwargs
    ) -> ProviderResponse:
        """Generate speech using a specific provider or model."""
        p = self.get_provider(provider) if provider else self.get_provider_for_capability("VOICEOUTPUT")
        if not p:
            p = self.get_provider_for_capability("AUDIO")
        if not p:
            return ProviderResponse(content="", model=model or "unknown", provider="unknown", trace_id=trace_id, error="No provider found for speech synthesis capability")
        
        return p.generate_speech(text, trace_id, model=model, voice=voice, format=format, **kwargs)

    def transcribe(
        self,
        audio_bytes: bytes,
        trace_id: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> ProviderResponse:
        """Transcribe audio using a specific provider or model."""
        p = self.get_provider(provider) if provider else self.get_provider_for_capability("VOICEINPUT")
        if not p:
            p = self.get_provider_for_capability("AUDIO")
        if not p:
            return ProviderResponse(content="", model=model or "unknown", provider="unknown", trace_id=trace_id, error="No provider found for audio transcription capability")
        
        return p.transcribe(audio_bytes, trace_id, model=model, **kwargs)

