"""
Misaka Cipher - Standard File Operations
"""

import os
import json
from pathlib import Path
from typing import Optional, Union, Any, Dict
from datetime import datetime
from core.utils.paths import WS_OUTPUTS

# Define workspace root - use environment variable or default to WS_OUTPUTS
WORKSPACE_ROOT = Path(os.environ.get("MISAKA_WORKSPACE", str(WS_OUTPUTS)))

def data_save_file(content: Any, filename: str, domain: str = "General") -> Dict[str, Any]:
    """
    Save content to a file in the workspace.
    
    Args:
        content: Content to write (string, dict, list, or bytes)
        filename: Name of the file (e.g., report.txt)
        domain: Domain subdirectory (default: General)
        
    Returns:
        Dict with file metadata: {path, size, created_at, success}
    """
    try:
        # VALIDATION: Detect if content is a file path (common error)
        if isinstance(content, str):
            # Check if it looks like a file path
            is_path = (
                content.startswith('C:\\') or 
                content.startswith('/') or
                content.startswith('./') or
                'data/outputfiles' in content or
                (len(content) < 200 and ('\\' in content or '/' in content))
            )
            
            if is_path:
                raise ValueError(
                    f"❌ VALIDATION ERROR: Attempted to save a file path as content!\n"
                    f"Content: {content}\n\n"
                    f"This is likely a bug in the tool implementation. "
                    f"The tool should return actual data (analysis, report, etc.), "
                    f"not a file path string."
                )
        
        # Sanitize inputs
        clean_domain = "".join(c for c in domain if c.isalnum() or c in ('_', '-'))
        clean_filename = "".join(c for c in filename if c.isalnum() or c in ('_', '-', '.'))
        
        # Create directory
        file_dir = WORKSPACE_ROOT / clean_domain
        file_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = file_dir / clean_filename
        
        # Convert content to appropriate format
        if isinstance(content, (dict, list)):
            # JSON serialization for dicts/lists
            final_content = json.dumps(content, indent=2)
            mode = 'w'
            encoding = 'utf-8'
        elif isinstance(content, bytes):
            # Binary content
            final_content = content
            mode = 'wb'
            encoding = None
        else:
            # String content
            final_content = str(content)
            mode = 'w'
            encoding = 'utf-8'
        
        # Write file
        with open(file_path, mode, encoding=encoding) as f:
            f.write(final_content)
        
        # Get file stats
        file_stats = file_path.stat()
        
        return {
            "success": True,
            "path": str(file_path),
            "size": file_stats.st_size,
            "created_at": datetime.now().isoformat(),
            "domain": clean_domain,
            "filename": clean_filename
        }
        
    except ValueError as e:
        # Validation errors - re-raise to agent
        raise e
    except Exception as e:
        return {
            "success": False,
            "error": f"Error saving file: {str(e)}",
            "path": None
        }

def data_read_file(filename: str, domain: str = "General") -> str:
    """
    Read content from a file in the workspace.
    
    Args:
        filename: Name of the file
        domain: Domain subdirectory
        
    Returns:
        File content
    """
    try:
        # Sanitize inputs
        clean_domain = "".join(c for c in domain if c.isalnum() or c in ('_', '-'))
        clean_filename = "".join(c for c in filename if c.isalnum() or c in ('_', '-', '.'))
        
        file_path = WORKSPACE_ROOT / clean_domain / clean_filename
        
        if not file_path.exists():
            return f"Error: File not found at {file_path}"
            
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
            
    except Exception as e:
        return f"Error reading file: {str(e)}"


# ===== BACKWARD COMPATIBILITY ALIASES =====
# Old function names that agents may still reference

def file_save_string(content: str, filename: str, domain: str = "General") -> Dict[str, Any]:
    """Backward compatibility alias for data_save_file."""
    return data_save_file(content, filename, domain)

def file_read_string(filename: str, domain: str = "General") -> str:
    """Backward compatibility alias for data_read_file."""
    return data_read_file(filename, domain)

def save_file(content: Any, filename: str, domain: str = "General") -> Dict[str, Any]:
    """Backward compatibility alias for data_save_file."""
    return data_save_file(content, filename, domain)

def read_file(filename: str, domain: str = "General") -> str:
    """Backward compatibility alias for data_read_file."""
    return data_read_file(filename, domain)

def file_save(content: Any, filename: str, domain: str = "General") -> Dict[str, Any]:
    """Backward compatibility alias for data_save_file."""
    return data_save_file(content, filename, domain)
