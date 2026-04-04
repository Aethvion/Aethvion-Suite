"""
Misaka Cipher - Agent Result
Result object returned by agent execution
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from core.utils import utcnow_iso


@dataclass
class AgentResult:
    """
    Result of agent execution.
    
    Contains the output, status, and metadata from agent task.
    """
    
    content: str
    agent_name: str
    trace_id: str
    success: bool
    
    # Execution metadata
    started_at: str
    completed_at: str = field(default_factory=utcnow_iso)
    duration_seconds: Optional[float] = None
    
    # Additional data
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    iterations: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'content': self.content,
            'agent_name': self.agent_name,
            'trace_id': self.trace_id,
            'success': self.success,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'duration_seconds': self.duration_seconds,
            'error': self.error,
            'metadata': self.metadata,
            'iterations': self.iterations
        }
    
    def __str__(self) -> str:
        """String representation."""
        status = "SUCCESS" if self.success else "FAILED"
        return f"AgentResult({self.agent_name}, {status})"
