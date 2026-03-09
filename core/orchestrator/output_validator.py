"""
Misaka Cipher - Output Validator
Validates agent outputs to ensure they match user intent
"""

import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from core.utils import get_logger

logger = get_logger(__name__)

# Use environment variable or default to relative path
WORK_FOLDER = Path(os.environ.get("MISAKA_WORKSPACE", Path(__file__).parent.parent.parent / "data/outputfiles"))


@dataclass
class ValidationResult:
    """Result of output validation."""
    success: bool
    errors: List[str]
    warnings: List[str]
    metadata: Dict[str, Any]


class OutputValidator:
    """
    Validates agent outputs to ensure quality and correctness.
    
    Checks:
    - Files exist and are in correct locations
    - Files contain actual content (not paths or placeholders)
    - File sizes are reasonable
    - Domain-specific validation rules
    """
    
    def __init__(self):
        """Initialize output validator."""
        self.min_file_size = 10  # bytes
        logger.info("Output Validator initialized")
    
    def validate_file_output(
        self, 
        file_path: Optional[Path], 
        expected_domain: str,
        min_content_length: int = 50
    ) -> ValidationResult:
        """
        Validate that a file was created correctly.
        
        Args:
            file_path: Path to the file (can be None)
            expected_domain: Expected domain folder (e.g., "Finance")
            min_content_length: Minimum expected content length
            
        Returns:
            ValidationResult with success status and any errors/warnings
        """
        errors = []
        warnings = []
        metadata = {}
        
        # Check 1: File path provided
        if file_path is None:
            errors.append("No file path provided")
            return ValidationResult(False, errors, warnings, metadata)
        
        file_path = Path(file_path)
        metadata['file_path'] = str(file_path)
        
        # Check 2: File exists
        if not file_path.exists():
            errors.append(f"File was not created: {file_path}")
            return ValidationResult(False, errors, warnings, metadata)
        
        # Check 3: File is in correct domain folder
        expected_folder = WORK_FOLDER / expected_domain
        if not str(file_path).startswith(str(expected_folder)):
            warnings.append(
                f"File in unexpected location. "
                f"Expected: {expected_folder}/, Got: {file_path}"
            )
        
        # Check 4: File has content
        file_size = file_path.stat().st_size
        metadata['file_size'] = file_size
        
        if file_size == 0:
            errors.append("File is empty (0 bytes)")
            return ValidationResult(False, errors, warnings, metadata)
        
        if file_size < self.min_file_size:
            warnings.append(
                f"File is very small ({file_size} bytes). "
                f"May be incomplete or contain only a path."
            )
        
        # Check 5: Content is not just a path
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            metadata['content_length'] = len(content)
            
            # Check if content looks like a file path
            content_stripped = content.strip()
            is_path = (
                content_stripped.startswith('C:\\') or
                content_stripped.startswith('/') or
                'data/outputfiles' in content_stripped or
                (len(content_stripped) < 200 and ('\\' in content_stripped or '/' in content_stripped))
            )
            
            if is_path:
                errors.append(
                    f"File contains a file path instead of actual content: {content_stripped[:100]}"
                )
                return ValidationResult(False, errors, warnings, metadata)
            
            # Check 6: Content length
            if len(content) < min_content_length:
                warnings.append(
                    f"Content is shorter than expected "
                    f"({len(content)} chars < {min_content_length} chars minimum)"
                )
            
        except Exception as e:
            warnings.append(f"Could not read file content: {e}")
        
        # All checks passed
        success = len(errors) == 0
        return ValidationResult(success, errors, warnings, metadata)
    
    def validate_execution_result(
        self,
        result: Dict[str, Any],
        expected_outputs: Optional[List[str]] = None
    ) -> ValidationResult:
        """
        Validate agent execution result.
        
        Args:
            result: Agent execution result dict
            expected_outputs: List of expected output types (e.g., ["file", "data"])
            
        Returns:
            ValidationResult
        """
        errors = []
        warnings = []
        metadata = {}
        
        # Check if execution succeeded
        if not result.get('success', True):
            errors.append(f"Execution failed: {result.get('error', 'Unknown error')}")
        
        # Check for output
        output = result.get('output', '')
        metadata['output_length'] = len(str(output))
        
        if not output:
            warnings.append("No output returned from execution")
        
        # Check for code blocks in output (usually indicates agent returned code instead of result)
        if isinstance(output, str):
            if '```' in output or 'def ' in output or 'import ' in output:
                warnings.append(
                    "Output contains code blocks. "
                    "Agent may have returned code instead of executing it."
                )
        
        success = len(errors) == 0
        return ValidationResult(success, errors, warnings, metadata)
    
    def extract_file_path_from_output(self, output: str) -> Optional[Path]:
        """
        Extract file path from agent output.
        
        Args:
            output: Agent output string
            
        Returns:
            Path object if found, None otherwise
        """
        if not isinstance(output, str):
            return None
        
        # Look for common patterns
        patterns = [
            "saved to: ",
            "saved at: ",
            "created: ",
            "file: ",
            "path: "
        ]
        
        for pattern in patterns:
            if pattern in output.lower():
                # Extract path after pattern
                idx = output.lower().index(pattern) + len(pattern)
                path_str = output[idx:].strip().split()[0]
                
                # Clean up path
                path_str = path_str.strip('"\' ')
                
                if Path(path_str).exists():
                    return Path(path_str)
        
        # Look for outputfiles paths
        if 'data/outputfiles' in output:
            # Extract path containing outputfiles
            lines = output.split('\n')
            for line in lines:
                if 'data/outputfiles' in line:
                    # Try to extract path
                    parts = line.split()
                    for part in parts:
                        if 'data/outputfiles' in part:
                            path_str = part.strip('"\',.:;')
                            if Path(path_str).exists():
                                return Path(path_str)
        
        return None


# Singleton instance
_validator = None

def get_output_validator() -> OutputValidator:
    """Get the singleton OutputValidator instance."""
    global _validator
    if _validator is None:
        _validator = OutputValidator()
    return _validator
