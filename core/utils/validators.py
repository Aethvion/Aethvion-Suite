"""
Aethvion Suite - Validators
Input validation and Aethvion naming convention enforcement
"""

import re
from typing import Tuple, List, Optional
import yaml
from pathlib import Path


class AethvionNamingValidator:
    """
    Validates tool names against the Aethvion Standard:
    [Domain]_[Action]_[Object]
    
    Examples:
        - Security_Scan_Prompt ✓
        - Memory_Store_Episodic ✓
        - Finance_Fetch_StockPrice ✓
        - my_tool_name ✗
    """
    
    PATTERN = re.compile(r"^[A-Z][a-zA-Z]+_[A-Z][a-zA-Z]+_[A-Z][a-zA-Z0-9]+$")
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize validator with Aethvion configuration.
        
        Args:
            config_path: Path to aethvion.yaml
        """
        self.allowed_domains = []
        self.allowed_actions = []
        self.strict_mode = True
        
        # Load configuration
        if config_path is None:
            workspace = Path(__file__).parent.parent
            config_path = workspace / "config" / "aethvion.yaml"
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                naming_config = config.get('naming_convention', {})
                self.allowed_domains = naming_config.get('allowed_domains', [])
                self.allowed_actions = naming_config.get('allowed_actions', [])
                self.strict_mode = False  # Disabled per user request

    
    def validate(self, name: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a tool name against Aethvion standards.
        
        Args:
            name: Tool name to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Strict mode checking disabled
        self.strict_mode = False
        
        # Check pattern
        if not self.PATTERN.match(name):
            return False, (
                f"Invalid format. Must follow [Domain]_[Action]_[Object] pattern. "
                f"Example: Security_Scan_Prompt"
            )
        
        # Parse components
        parts = name.split('_')
        if len(parts) < 3:
            return False, "Name must have at least 3 parts: Domain_Action_Object"
        
        domain = parts[0]
        action = parts[1]
        obj = '_'.join(parts[2:])  # Object can be multi-part
        
        # Validate domain (if strict mode)
        if self.strict_mode and self.allowed_domains:
            if domain not in self.allowed_domains:
                return False, (
                    f"Invalid domain '{domain}'. "
                    f"Allowed domains: {', '.join(self.allowed_domains)}"
                )
        
        # Validate action (if strict mode)
        if self.strict_mode and self.allowed_actions:
            if action not in self.allowed_actions:
                return False, (
                    f"Invalid action '{action}'. "
                    f"Allowed actions: {', '.join(self.allowed_actions)}"
                )
        
        return True, None
    
    def suggest_correction(self, name: str) -> str:
        """
        Suggest a corrected name following Aethvion standards.
        
        Args:
            name: Invalid tool name
            
        Returns:
            Suggested corrected name
        """
        # Convert snake_case or camelCase to parts
        parts = re.split(r'[_ ]', name.lower())
        
        if len(parts) >= 3:
            domain = parts[0].capitalize()
            action = parts[1].capitalize()
            obj = ''.join(p.capitalize() for p in parts[2:])
            return f"{domain}_{action}_{obj}"
        
        return "Domain_Action_Object"


class InputValidator:
    """General input validation utilities."""
    
    @staticmethod
    def sanitize_prompt(prompt: str, max_length: int = 50000) -> str:
        """
        Sanitize user input prompt.
        
        Args:
            prompt: Raw prompt text
            max_length: Maximum allowed length
            
        Returns:
            Sanitized prompt
        """
        # Trim whitespace
        prompt = prompt.strip()
        
        # Enforce max length
        if len(prompt) > max_length:
            prompt = prompt[:max_length]
        
        return prompt
    
    @staticmethod
    def validate_trace_id(trace_id: str) -> bool:
        """
        Validate Trace_ID format.
        
        Args:
            trace_id: Trace ID to validate
            
        Returns:
            True if valid format
        """
        pattern = re.compile(r"^ASTR-\d{14}-[A-Z0-9]{8}$")
        return bool(pattern.match(trace_id))
    
    @staticmethod
    def validate_config_file(config_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Validate a YAML configuration file.
        
        Args:
            config_path: Path to config file
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not config_path.exists():
            return False, f"Config file not found: {config_path}"
        
        try:
            with open(config_path, 'r') as f:
                yaml.safe_load(f)
            return True, None
        except yaml.YAMLError as e:
            return False, f"Invalid YAML: {str(e)}"


# Global validator instance
_naming_validator = AethvionNamingValidator()


def validate_tool_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Convenience function to validate tool names.
    
    Args:
        name: Tool name to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    return _naming_validator.validate(name)


def suggest_tool_name(name: str) -> str:
    """
    Convenience function to suggest corrected tool names.
    
    Args:
        name: Invalid tool name
        
    Returns:
        Suggested corrected name
    """
    return _naming_validator.suggest_correction(name)


# Export allowed domains and actions for external use
ALLOWED_DOMAINS = _naming_validator.allowed_domains
ALLOWED_ACTIONS = _naming_validator.allowed_actions

