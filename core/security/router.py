"""
Aethvion Suite - Router
Routes flagged requests based on firewall rules
"""

from typing import Optional
from enum import Enum
from core.utils.logger import get_logger

logger = get_logger(__name__)


class RoutingDecision(Enum):
    """Routing decisions for requests."""
    EXTERNAL = "external"  # Route to external provider
    LOCAL = "local"  # Route to local inference node
    BLOCKED = "blocked"  # Block request


class RequestRouter:
    """
    Routes requests based on firewall scan results.
    
    Part of the Intelligence Firewall system.
    """
    
    def __init__(self, local_inference_enabled: bool = False):
        """
        Initialize router.
        
        Args:
            local_inference_enabled: Whether local inference node is available
        """
        self.local_inference_enabled = local_inference_enabled
        logger.info(
            f"Request router initialized. Local inference: "
            f"{'ENABLED' if local_inference_enabled else 'DISABLED (placeholder)'}"
        )
    
    def route(
        self,
        scan_action: str,
        trace_id: str,
        fallback_to_external: bool = True
    ) -> RoutingDecision:
        """
        Determine routing decision based on scan action.
        
        Args:
            scan_action: Action from content scanner ('route_local', 'block', 'allow')
            trace_id: Trace ID for this request
            fallback_to_external: Whether to fallback to external if local unavailable
            
        Returns:
            RoutingDecision
        """
        if scan_action == "allow":
            logger.info(f"[{trace_id}] Routing decision: EXTERNAL (clean content)")
            return RoutingDecision.EXTERNAL
        
        if scan_action == "block":
            logger.warning(f"[{trace_id}] Routing decision: BLOCKED (critical violation)")
            return RoutingDecision.BLOCKED
        
        if scan_action == "route_local":
            if self.local_inference_enabled:
                logger.info(f"[{trace_id}] Routing decision: LOCAL (flagged content)")
                return RoutingDecision.LOCAL
            else:
                if fallback_to_external:
                    logger.warning(
                        f"[{trace_id}] Local inference unavailable, "
                        f"falling back to EXTERNAL (degraded security)"
                    )
                    return RoutingDecision.EXTERNAL
                else:
                    logger.warning(
                        f"[{trace_id}] Local inference unavailable, "
                        f"no fallback allowed, BLOCKING request"
                    )
                    return RoutingDecision.BLOCKED
        
        # Default to external
        logger.warning(f"[{trace_id}] Unknown action '{scan_action}', defaulting to EXTERNAL")
        return RoutingDecision.EXTERNAL
