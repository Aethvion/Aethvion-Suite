"""
Misaka Cipher - Nexus Core
Central routing, logging, and orchestration layer

This is the SINGLE POINT OF ENTRY for all system interactions.
All agent-to-agent calls, tool executions, and external API requests
MUST route through Nexus Core.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

from core.providers import ProviderManager, ProviderResponse
from core.security import IntelligenceFirewall, RoutingDecision
from core.utils import (
    get_trace_manager,
    get_logger,
    InputValidator
)

logger = get_logger(__name__)


@dataclass
class Request:
    """Request object for Nexus Core."""
    prompt: str
    request_type: str = "generation"  # generation, tool_execution, agent_call
    metadata: Optional[Dict[str, Any]] = None
    preferred_provider: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    trace_id: Optional[str] = None  # Caller-provided trace ID for usage log correlation
    images: Optional[List[Dict[str, Any]]] = None

    def __post_init__(self):
        # Sanitize prompt
        self.prompt = InputValidator.sanitize_prompt(self.prompt)


@dataclass
class Response:
    """Response object from Nexus Core."""
    content: str
    trace_id: str
    provider: str
    success: bool
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    firewall_status: Optional[str] = None
    routing_decision: Optional[str] = None


class NexusCore:
    """
    Nexus Core - Central routing and orchestration system.

    Responsibilities:
    - Single point of entry for all requests
    - Trace ID generation and management
    - Intelligence Firewall pre-flight scanning
    - Provider routing and failover
    - Full transaction logging
    """

    def __init__(self):
        """Initialize Nexus Core."""
        self.trace_manager = get_trace_manager()
        self.provider_manager = None
        self.firewall = None
        self._initialized = False

        logger.info("=" * 60)
        logger.info("MISAKA CIPHER - NEXUS CORE")
        logger.info("M.I.S.A.K.A.: Multitask Intelligence & Strategic Analysis")
        logger.info("          Kernel Architecture")
        logger.info("=" * 60)

    def initialize(self):
        """Initialize all Nexus Core components."""
        if self._initialized:
            logger.warning("Nexus Core already initialized")
            return

        logger.info("Initializing Nexus Core components...")

        try:
            # Initialize Provider Manager
            logger.info("Loading Provider Manager...")
            self.provider_manager = ProviderManager()

            # Initialize Intelligence Firewall
            logger.info("Loading Intelligence Firewall...")
            self.firewall = IntelligenceFirewall()

            # Health check all providers
            logger.info("Running provider health checks...")
            health_status = self.provider_manager.health_check_all()

            for provider_name, status in health_status.items():
                logger.info(f"  {provider_name}: {status.value}")

            self._initialized = True
            logger.info("Nexus Core initialization: COMPLETE")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Nexus Core initialization FAILED: {str(e)}")
            raise

    def route_request(self, request: Request) -> Response:
        """
        Route a request through the Nexus Core pipeline.

        Pipeline:
        1. Generate Trace_ID
        2. Pre-flight firewall scan
        3. Route based on firewall decision
        4. Provider failover if needed
        5. Log transaction

        Args:
            request: Request object

        Returns:
            Response object
        """
        if not self._initialized:
            raise RuntimeError("Nexus Core not initialized. Call initialize() first.")

        # Use caller's trace_id if provided (for usage log correlation with task queue)
        if request.trace_id:
            trace_id = request.trace_id
            # Register manually — start_trace() always generates a new ID
            self.trace_manager._active_traces[trace_id] = {
                'trace_id': trace_id,
                'started_at': datetime.now().isoformat(),
                'metadata': {'request_type': request.request_type},
                'status': 'active'
            }
        else:
            trace_id = self.trace_manager.start_trace(metadata={
                'request_type': request.request_type,
                'timestamp': datetime.now().isoformat()
            })

        logger.info(f"[{trace_id}] === NEW REQUEST ===")
        logger.info(f"[{trace_id}] Type: {request.request_type}")
        logger.info(f"[{trace_id}] Prompt length: {len(request.prompt)} chars")
        if request.model:
            logger.info(f"[{trace_id}] Requested Model: {request.model}")

        try:
            # Pre-flight firewall scan (with intent detection)
            routing_decision, scan_result = self.firewall.scan_and_route(
                prompt=request.prompt,
                trace_id=trace_id,
                request_type=request.request_type
            )

            # Handle routing decision
            if routing_decision == RoutingDecision.BLOCKED:
                logger.error(f"[{trace_id}] Request BLOCKED by Intelligence Firewall")
                self.trace_manager.end_trace(trace_id, status='blocked')

                return Response(
                    content="",
                    trace_id=trace_id,
                    provider="none",
                    success=False,
                    error="Request blocked by Intelligence Firewall",
                    firewall_status="blocked",
                    routing_decision=routing_decision.value
                )

            elif routing_decision == RoutingDecision.LOCAL:
                # TODO: Implement local inference routing when Ollama/vLLM is ready
                logger.warning(
                    f"[{trace_id}] LOCAL routing not yet implemented, "
                    f"falling back to external"
                )
                routing_decision = RoutingDecision.EXTERNAL

            # Route to external provider
            if routing_decision == RoutingDecision.EXTERNAL:
                logger.info(f"[{trace_id}] Routing to external provider")

                provider_response = self.provider_manager.call_with_failover(
                    prompt=request.prompt,
                    trace_id=trace_id,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    preferred_provider=request.preferred_provider,
                    model=request.model,
                    request_type=request.request_type,
                    images=request.images
                )

                # Build response
                if provider_response.success:
                    logger.info(f"[{trace_id}] Request completed successfully")
                    self.trace_manager.end_trace(trace_id, status='completed')

                    # Ensure model is in metadata so Orchestrator can see it
                    metadata = provider_response.metadata or {}
                    if 'model' not in metadata and provider_response.model:
                        metadata['model'] = provider_response.model

                    return Response(
                        content=provider_response.content,
                        trace_id=trace_id,
                        provider=provider_response.provider,
                        success=True,
                        metadata=metadata,
                        firewall_status="clean" if scan_result and scan_result.is_clean else "flagged",
                        routing_decision=routing_decision.value
                    )
                else:
                    logger.error(f"[{trace_id}] Request failed: {provider_response.error}")
                    self.trace_manager.end_trace(trace_id, status='failed')

                    return Response(
                        content="",
                        trace_id=trace_id,
                        provider=provider_response.provider,
                        success=False,
                        error=provider_response.error,
                        firewall_status="clean" if scan_result and scan_result.is_clean else "flagged",
                        routing_decision=routing_decision.value
                    )

        except Exception as e:
            logger.error(f"[{trace_id}] Nexus Core routing failed: {str(e)}")
            self.trace_manager.end_trace(trace_id, status='error')

            return Response(
                content="",
                trace_id=trace_id,
                provider="none",
                success=False,
                error=f"Nexus Core error: {str(e)}"
            )

    def get_status(self) -> Dict:
        """Get Nexus Core status."""
        if not self._initialized:
            return {'initialized': False}

        return {
            'initialized': True,
            'providers': self.provider_manager.get_status_summary(),
            'firewall': self.firewall.get_status(),
            'active_traces': len(self.trace_manager.get_active_traces())
        }

    def reload_config(self):
        """Reload configuration for all components."""
        logger.info("Nexus Core reloading configuration...")
        if self.provider_manager:
            self.provider_manager.reload_config()
        # TODO: Reload firewall if needed
