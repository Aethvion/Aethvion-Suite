"""
Misaka Cipher - Tool Specification
Defines tool requirements for The Forge
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from core.utils import utcnow_iso


@dataclass
class ParameterSpec:
    """
    Specification for a tool parameter.
    """
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'type': self.type,
            'description': self.description,
            'required': self.required,
            'default': self.default
        }


@dataclass
class ToolSpec:
    """
    Specification for generating a tool.
    
    Follows Aethvion Standard: [Domain]_[Action]_[Object]
    
    Example:
        ToolSpec(
            domain="Finance",
            action="Fetch",
            object="StockPrice",
            description="Fetches current stock price for a symbol",
            parameters=[
                ParameterSpec("symbol", "str", "Stock symbol (e.g., AAPL)")
            ],
            return_type="dict"
        )
        
        Generates: Finance_Fetch_StockPrice
    """
    
    domain: str
    action: str
    object: str
    description: str
    parameters: List[ParameterSpec] = field(default_factory=list)
    return_type: str = "Any"
    
    # Implementation details
    implementation_type: str = "function"  # function or class
    implementation_hints: Dict[str, Any] = field(default_factory=dict)
    imports: List[str] = field(default_factory=list)
    
    # Metadata
    created_at: str = field(default_factory=utcnow_iso)
    trace_id: Optional[str] = None
    reasoning: str = ""
    
    def __post_init__(self):
        """Validate and normalize tool specification."""
        # Ensure domain, action, object are capitalized
        self.domain = self.domain.capitalize()
        self.action = self.action.capitalize()
        # Object can be multi-word, capitalize each word
        self.object = ''.join(word.capitalize() for word in self.object.split('_'))
    
    @property
    def name(self) -> str:
        """Generate Aethvion-compliant tool name."""
        return f"{self.domain}_{self.action}_{self.object}"
    
    @property
    def file_name(self) -> str:
        """Generate file name (lowercase with underscores)."""
        return f"{self.domain.lower()}_{self.action.lower()}_{self.object.lower()}.py"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'domain': self.domain,
            'action': self.action,
            'object': self.object,
            'description': self.description,
            'parameters': [p.to_dict() for p in self.parameters],
            'return_type': self.return_type,
            'implementation_type': self.implementation_type,
            'implementation_hints': self.implementation_hints,
            'imports': self.imports,
            'created_at': self.created_at,
            'trace_id': self.trace_id,
            'reasoning': self.reasoning
        }
    
    def __str__(self) -> str:
        """String representation."""
        return f"ToolSpec({self.name})"
