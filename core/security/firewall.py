"""
Aethvion Suite - Intelligence Firewall
Pre-flight scanning and routing for sensitive content
"""

import yaml
from pathlib import Path
from typing import Optional, Tuple
from .scanner import ContentScanner, ScanResult, ScanAction
from .router import RequestRouter, RoutingDecision
from core.utils.logger import get_logger

logger = get_logger(__name__)


class IntelligenceFirewall:
    """
    Intelligence Firewall - Pre-flight content scanning and routing.
    
    Protects external API standing by routing sensitive/restricted content
    to local inference nodes (Ollama/vLLM).
    
    Current Status: Local inference is PLACEHOLDER (to be integrated later).
    Flagged content currently routes to external with warning.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize Intelligence Firewall.
        
        Args:
            config_path: Path to security.yaml
        """
        self.enabled = True
        self.scanner = None
        self.router = None
        self.config = {}
        
        # Load configuration
        if config_path is None:
            workspace = Path(__file__).parent.parent
            config_path = workspace / "config" / "security.yaml"
        else:
            config_path = Path(config_path)
            
        if not config_path.exists():
            logger.warning(f"Security config not found at {config_path}. Firewall will operate in default (enabled) mode with no patterns.")
            self.enabled = True
            self.restricted_patterns = []
            self.audit_config = {"log_all_scans": True}
        else:
            self._load_config(config_path)
        
        # Initialize components
        self._initialize_scanner()
        self._initialize_router()
        
        logger.info(f"Intelligence Firewall initialized (enabled: {self.enabled})")
    
    def _load_config(self, config_path: Path):
        """Load firewall configuration."""
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
            self.config = data.get('firewall', {})
            self.enabled = self.config.get('enabled', True)
            self.restricted_patterns = data.get('restricted_patterns', [])
            self.audit_config = data.get('audit', {})
    
    def _initialize_scanner(self):
        """Initialize content scanner."""
        if self.enabled and self.config.get('scan_all_requests', True):
            self.scanner = ContentScanner(self.restricted_patterns)
            logger.info("Content scanner initialized")
    
    def _initialize_router(self):
        """Initialize request router."""
        local_config = self.config.get('local_inference', {})
        local_enabled = local_config.get('enabled', False)
        
        self.router = RequestRouter(local_inference_enabled=local_enabled)
        
        if not local_enabled:
            logger.warning(
                "Local inference node is DISABLED (placeholder). "
                "Flagged requests will fall back to external providers."
            )
    
    def scan_and_route(
        self,
        prompt: str,
        trace_id: str,
        request_type: Optional[str] = None
    ) -> Tuple[RoutingDecision, Optional[ScanResult]]:
        """
        Scan content and determine routing.
        
        Args:
            prompt: Content to scan
            trace_id: Trace ID for this request
            request_type: Type of request (e.g., "forge_analysis")
            
        Returns:
            Tuple of (RoutingDecision, ScanResult)
        """
        # If firewall disabled, allow everything
        if not self.enabled:
            logger.debug(f"[{trace_id}] Firewall disabled, routing to EXTERNAL")
            return RoutingDecision.EXTERNAL, None
        
        # Scan content (with intent detection for forge_analysis)
        scan_result = self.scanner.scan(prompt, trace_id, request_type=request_type)
        
        # Log scan result
        if self.audit_config.get('log_all_scans', True):
            self._log_scan(trace_id, scan_result)
        
        # Route based on scan result
        routing_decision = self.router.route(
            scan_action=scan_result.action.value,
            trace_id=trace_id,
            fallback_to_external=self.config.get('local_inference', {}).get('fallback_to_external', True)
        )
        
        return routing_decision, scan_result
    
    def _log_scan(self, trace_id: str, result: ScanResult):
        """Log scan result to audit trail."""
        if result.is_clean:
            logger.info(
                f"[{trace_id}] Firewall scan: CLEAN (hash: {result.prompt_hash})"
            )
        else:
            logger.warning(
                f"[{trace_id}] Firewall scan: FLAGGED | "
                f"Action: {result.action.value} | "
                f"Severity: {result.severity.value if result.severity else 'unknown'} | "
                f"Matches: {len(result.matches)} | "
                f"Hash: {result.prompt_hash}"
            )
            
            # Log match details
            for match in result.matches:
                logger.warning(
                    f"[{trace_id}]   - Category: {match['category']}, "
                    f"Severity: {match['severity'].value}, "
                    f"Count: {match['match_count']}"
                )
    
    def is_enabled(self) -> bool:
        """Check if firewall is enabled."""
        return self.enabled
    
    def get_status(self) -> dict:
        """Get firewall status."""
        return {
            'enabled': self.enabled,
            'scanner_active': self.scanner is not None,
            'router_active': self.router is not None,
            'local_inference_enabled': self.router.local_inference_enabled if self.router else False,
            'pattern_count': len(self.restricted_patterns) if self.scanner else 0
        }
