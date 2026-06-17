"""
Aethvion Suite - Aether Core
Central routing, logging, and orchestration layer

This is the SINGLE POINT OF ENTRY for all system interactions.
All agent-to-agent calls, tool executions, and external API requests
MUST route through Aether Core.
"""

from typing import Optional, Dict, Any, List, Iterator
from dataclasses import dataclass

from core.providers import get_provider_manager
from core.security import IntelligenceFirewall, RoutingDecision
from core.utils import (
    get_trace_manager,
    get_logger,
    utcnow_iso,
    InputValidator
)
from core.utils.registry_utils import ensure_registry_initialized

logger = get_logger(__name__)


@dataclass
class Request:
    """Request object for Aether Core."""
    prompt: str
    system_prompt: Optional[str] = None
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
    """Response object from Aether Core."""
    content: str
    trace_id: str
    provider: str
    success: bool
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    firewall_status: Optional[str] = None
    routing_decision: Optional[str] = None


class AetherCore:
    """
    Aether Core - Central routing and orchestration system.

    Responsibilities:
    - Single point of entry for all requests
    - Trace ID generation and management
    - Intelligence Firewall pre-flight scanning
    - Provider routing and failover
    - Full transaction logging
    """

    def __init__(self):
        """Initialize Aether Core."""
        self.trace_manager = get_trace_manager()
        self.provider_manager = None
        self.firewall = None
        self._initialized = False

        logger.info("=" * 60)
        logger.info("Aethvion Suite - AETHER CORE")
        logger.info("=" * 60)

    def initialize(self):
        """Initialize all Aether Core components."""
        if self._initialized:
            logger.warning("Aether Core already initialized")
            return

        logger.info("Initializing Aether Core components...")

        try:
            # Ensure Model Registry is initialized
            logger.info("Checking Model Registry...")
            ensure_registry_initialized()

            # Initialize Provider Manager (singleton — shared across all subsystems)
            logger.info("Loading Provider Manager...")
            self.provider_manager = get_provider_manager()

            # Initialize Intelligence Firewall
            logger.info("Loading Intelligence Firewall...")
            self.firewall = IntelligenceFirewall()

            self._initialized = True
            logger.info("Aether Core initialization: COMPLETE")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Aether Core initialization FAILED: {str(e)}")
            raise

    def route_request(self, request: Request) -> Response:
        """
        Route a request through the Aether Core pipeline.

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
            raise RuntimeError("Aether Core not initialized. Call initialize() first.")

        # Use caller's trace_id if provided (for usage log correlation with task queue)
        if request.trace_id:
            trace_id = request.trace_id
            # Register manually — start_trace() always generates a new ID
            self.trace_manager._active_traces[trace_id] = {
                'trace_id': trace_id,
                'started_at': utcnow_iso(),
                'metadata': {'request_type': request.request_type},
                'status': 'active'
            }
        else:
            trace_id = self.trace_manager.start_trace(metadata={
                'request_type': request.request_type,
                'source': request.metadata.get('source', 'unknown') if request.metadata else 'unknown',
                'timestamp': utcnow_iso()
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

            # Route to provider (either LOCAL or EXTERNAL)
            if routing_decision in (RoutingDecision.EXTERNAL, RoutingDecision.LOCAL):
                logger.info(f"[{trace_id}] Routing request (decision: {routing_decision.value})")

                # Extract source from metadata if present
                source = "unknown"
                if request.metadata and 'source' in request.metadata:
                    source = request.metadata['source']

                local_only = (routing_decision == RoutingDecision.LOCAL)

                provider_response = self.provider_manager.call_with_failover(
                    prompt=request.prompt,
                    system_prompt=request.system_prompt,
                    trace_id=trace_id,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    preferred_provider=request.preferred_provider,
                    model=request.model,
                    request_type=request.request_type,
                    source=source,
                    images=request.images,
                    local_only=local_only
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
            logger.error(f"[{trace_id}] Aether Core routing failed: {str(e)}")
            self.trace_manager.end_trace(trace_id, status='error')

            return Response(
                content="",
                trace_id=trace_id,
                provider="none",
                success=False,
                error=f"Aether Core error: {str(e)}"
            )

    def route_stream(self, request: Request) -> Iterator[str]:
        """
        Stream a request through the Aether Core pipeline.
        
        Args:
            request: Request object
            
        Yields:
            Chunks of response content
        """
        if not self._initialized:
            raise RuntimeError("Aether Core not initialized.")

        trace_id = request.trace_id or self.trace_manager.start_trace(metadata={
            'request_type': 'streaming',
            'source': request.metadata.get('source', 'unknown') if request.metadata else 'unknown'
        })

        logger.info(f"[{trace_id}] === NEW STREAMING REQUEST ===")
        
        try:
            # Pre-flight firewall scan
            routing_decision, scan_result = self.firewall.scan_and_route(
                prompt=request.prompt,
                trace_id=trace_id,
                request_type=request.request_type
            )

            if routing_decision == RoutingDecision.BLOCKED:
                logger.error(f"[{trace_id}] Request BLOCKED by Intelligence Firewall")
                self.trace_manager.end_trace(trace_id, status='blocked')
                yield "Request blocked by Intelligence Firewall"
                return

            # Extract source from metadata if present
            source = "unknown"
            if request.metadata and 'source' in request.metadata:
                source = request.metadata['source']

            local_only = (routing_decision == RoutingDecision.LOCAL)

            generator = self.provider_manager.call_with_failover_stream(
                prompt=request.prompt,
                system_prompt=request.system_prompt,
                trace_id=trace_id,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                model=request.model,
                messages=request.metadata.get('messages') if request.metadata else None,
                source=source,
                local_only=local_only
            )
            
            for chunk in generator:
                yield chunk
                
            self.trace_manager.end_trace(trace_id, status='completed')
            
        except Exception as e:
            logger.error(f"[{trace_id}] Aether Core streaming failed: {str(e)}")
            self.trace_manager.end_trace(trace_id, status='error')
            yield f"\n[Aether Core Error: {str(e)}]"

    def get_status(self) -> Dict:
        """Get Aether Core status."""
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
        logger.info("Aether Core reloading configuration...")
        if self.provider_manager:
            self.provider_manager.reload_config()
        # IntelligenceFirewall reads config at init time; re-instantiate to pick up changes.
        if self.firewall is not None:
            from core.security.firewall import IntelligenceFirewall
            self.firewall = IntelligenceFirewall()
