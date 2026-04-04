"""
Misaka Cipher - Agent Specification
Defines agent tasks using Aethvion Standard: [Domain]_[Action]_[Object]
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from core.utils import utcnow_iso


@dataclass
class AgentSpec:
    """
    Specification for creating an agent.
    
    Follows Aethvion Standard: [Domain]_[Action]_[Object]
    
    Example:
        AgentSpec(
            domain="Analytics",
            action="Generate", 
            object="Report",
            context={"data_source": "sales.csv"}
        )
        
        Generates agent name: Analytics_Generate_Report
    """
    
    domain: str
    action: str
    object: str
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Execution parameters
    max_iterations: int = 1
    timeout: int = 300  # seconds
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    
    description: Optional[str] = None
    created_at: str = field(default_factory=utcnow_iso)
    images: Optional[List[Dict[str, Any]]] = None
    
    def __post_init__(self):
        """Validate agent specification."""
        # Ensure domain, action, object are capitalized
        self.domain = self.domain.capitalize()
        self.action = self.action.capitalize()
        # Object can be multi-word, capitalize each word
        self.object = ''.join(word.capitalize() for word in self.object.split('_'))
    
    @property
    def name(self) -> str:
        """Generate Aethvion-compliant agent name."""
        return f"{self.domain}_{self.action}_{self.object}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'domain': self.domain,
            'action': self.action,
            'object': self.object,
            'context': self.context,
            'max_iterations': self.max_iterations,
            'timeout': self.timeout,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'description': self.description,
            'created_at': self.created_at
        }
    
    def __str__(self) -> str:
        """String representation."""
        return f"AgentSpec({self.name})"
