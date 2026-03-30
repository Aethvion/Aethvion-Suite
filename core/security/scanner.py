"""
Aethvion Suite - Content Scanner
Analyzes content for restricted patterns and security threats
"""

import re
import hashlib
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
from enum import Enum
from core.utils.logger import get_logger

logger = get_logger(__name__)


# Intent-Based Patterns (for conceptual threat detection)
INTENT_PATTERNS = {
    'filesystem_access': [
        r'\b(read|write|open|delete|remove|modify)\s+(file|directory|folder)',
        r'\bfile\s+(operations?|access|I/?O)\b',
        r'\b(access|manipulate)\s+(filesystem|disk)',
        r'\b(save|load|store)\s+(to|from)\s+(file|disk)',
    ],
    'network_access': [
        r'\b(http|api|web)\s+request',
        r'\bfetch\s+(from|data\s+from)\s+(url|web|internet|api)',
        r'\b(download|upload|send|receive)\s+(data|file)',
        r'\bmake\s+(network|http)\s+call',
    ],
    'code_execution': [
        r'\bexecute\s+(code|script|command)',
        r'\brun\s+(shell|command|script|python|code)',
        r'\beval\b.*\bcode\b',
        r'\b(inject|compile|interpret)\s+code',
    ],
    'system_operations': [
        r'\b(system|os|subprocess)\s+(call|command|operation)',
        r'\b(spawn|create)\s+process',
        r'\baccess\s+(environment|system)\s+variables',
    ]
}


class ScanSeverity(Enum):
    """Severity levels for scan results."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ScanAction(Enum):
    """Actions to take based on scan results."""
    ROUTE_LOCAL = "route_local"
    BLOCK = "block"
    ALLOW = "allow"


@dataclass
class ScanResult:
    """Result of a content scan."""
    is_clean: bool
    action: ScanAction
    matches: List[Dict]
    severity: Optional[ScanSeverity] = None
    prompt_hash: Optional[str] = None
    intent_flags: Optional[List[str]] = None  # NEW: Intent categories detected
    
    def __str__(self):
        if self.is_clean:
            return "CLEAN"
        intent_info = f", intents: {', '.join(self.intent_flags)}" if self.intent_flags else ""
        return f"FLAGGED: {self.action.value} (severity: {self.severity.value if self.severity else 'unknown'}){intent_info}"


class ContentScanner:
    """
    Scans content for restricted patterns and security threats.
    
    Part of the Intelligence Firewall system.
    """
    
    def __init__(self, patterns: List[Dict]):
        """
        Initialize scanner with restriction patterns.
        
        Args:
            patterns: List of pattern dictionaries from security.yaml
        """
        self.patterns = []
        
        # Compile content patterns
        for pattern_config in patterns:
            try:
                flags = 0 if pattern_config.get('case_sensitive', True) else re.IGNORECASE
                compiled_pattern = re.compile(pattern_config['pattern'], flags)
                
                self.patterns.append({
                    'pattern': compiled_pattern,
                    'category': pattern_config.get('category', 'unknown'),
                    'action': ScanAction(pattern_config.get('action', 'allow')),
                    'severity': ScanSeverity(pattern_config.get('severity', 'medium')),
                    'original': pattern_config['pattern']
                })
            except Exception as e:
                logger.error(f"Failed to compile pattern {pattern_config.get('pattern')}: {str(e)}")
        
        # Compile intent patterns
        self.intent_patterns = {}
        for category, pattern_list in INTENT_PATTERNS.items():
            self.intent_patterns[category] = [
                re.compile(pattern, re.IGNORECASE) for pattern in pattern_list
            ]
        
        logger.info(f"Content scanner initialized with {len(self.patterns)} patterns")
    
    def scan(self, content: str, trace_id: str, request_type: Optional[str] = None) -> ScanResult:
        """
        Scan content for restricted patterns and intents.
        
        Args:
            content: Content to scan
            trace_id: Trace ID for this scan
            request_type: Type of request (e.g., "forge_analysis")
            
        Returns:
            ScanResult with findings
        """
        matches = []
        intent_flags = []
        highest_severity = None
        recommended_action = ScanAction.ALLOW
        
        # Generate content hash for privacy
        prompt_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        logger.debug(f"[{trace_id}] Scanning content (hash: {prompt_hash}, type: {request_type})")
        
        # INTENT-BASED SCAN (for forge_analysis)
        if request_type == "forge_analysis":
            intent_flags = self._scan_intent(content, trace_id)
            
            if intent_flags:
                # Flag high-risk intents
                matches.append({
                    'category': 'intent_detection',
                    'action': ScanAction.ALLOW,  # Allow but log warning
                    'severity': ScanSeverity.MEDIUM,
                    'intent_categories': intent_flags
                })
                highest_severity = ScanSeverity.MEDIUM
                
                logger.warning(
                    f"[{trace_id}] Intent detection: High-risk intents detected: {', '.join(intent_flags)}. "
                    f"Tool will be generated with strict validation."
                )
        
        # CONTENT-BASED SCAN (existing patterns)
        for pattern_info in self.patterns:
            pattern = pattern_info['pattern']
            found_matches = pattern.findall(content)
            
            if found_matches:
                match_info = {
                    'category': pattern_info['category'],
                    'action': pattern_info['action'],
                    'severity': pattern_info['severity'],
                    'match_count': len(found_matches)
                }
                matches.append(match_info)
                
                logger.warning(
                    f"[{trace_id}] Pattern match: category={pattern_info['category']}, "
                    f"severity={pattern_info['severity'].value}, matches={len(found_matches)}"
                )
                
                # Track highest severity
                if highest_severity is None or self._compare_severity(pattern_info['severity'], highest_severity) > 0:
                    highest_severity = pattern_info['severity']
                    recommended_action = pattern_info['action']
        
        # Determine final result
        is_clean = len(matches) == 0
        
        if is_clean:
            logger.info(f"[{trace_id}] Content scan: CLEAN")
        else:
            logger.warning(
                f"[{trace_id}] Content scan: FLAGGED with {len(matches)} pattern matches, "
                f"action={recommended_action.value}"
            )
        
        return ScanResult(
            is_clean=is_clean,
            action=recommended_action if not is_clean else ScanAction.ALLOW,
            matches=matches,
            severity=highest_severity,
            prompt_hash=prompt_hash,
            intent_flags=intent_flags if intent_flags else None
        )
    
    def _scan_intent(self, content: str, trace_id: str) -> List[str]:
        """
        Scan for high-risk intents in tool descriptions.
        
        Args:
            content: Content to scan
            trace_id: Trace ID for logging
            
        Returns:
            List of detected intent categories
        """
        detected_intents = []
        
        for category, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if pattern.search(content):
                    if category not in detected_intents:
                        detected_intents.append(category)
                        logger.info(f"[{trace_id}] Intent detected: {category}")
                    break  # One match per category is enough
        
        return detected_intents
    
    def _compare_severity(self, sev1: ScanSeverity, sev2: ScanSeverity) -> int:
        """
        Compare two severity levels.
        
        Returns:
            1 if sev1 > sev2, -1 if sev1 < sev2, 0 if equal
        """
        severity_order = {
            ScanSeverity.LOW: 1,
            ScanSeverity.MEDIUM: 2,
            ScanSeverity.HIGH: 3,
            ScanSeverity.CRITICAL: 4
        }
        
        rank1 = severity_order.get(sev1, 0)
        rank2 = severity_order.get(sev2, 0)
        
        if rank1 > rank2:
            return 1
        elif rank1 < rank2:
            return -1
        return 0
