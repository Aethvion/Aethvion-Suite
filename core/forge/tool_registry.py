"""
Misaka Cipher - Tool Registry
JSON-based catalog of generated tools
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from threading import Lock
from datetime import datetime

from core.utils import get_logger
from core.utils.paths import WS_TOOLS

logger = get_logger(__name__)


class ToolRegistry:
    """
    Central registry for generated tools.
    
    Maintains a JSON catalog of all tools created by The Forge.
    Thread-safe for concurrent tool generation.
    """
    
    def __init__(self, registry_path: Optional[Path] = None):
        """
        Initialize Tool Registry.
        
        Args:
            registry_path: Path to registry.json file
        """
        if registry_path is None:
            registry_path = WS_TOOLS / "registry.json"
        
        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._tools: Dict[str, Dict] = {}
        self._lock = Lock()
        
        # Load existing registry
        self._load_registry()
        
        logger.info(f"Tool Registry initialized: {self.registry_path}")
    
    def _load_registry(self):
        """Load registry from JSON file."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, 'r') as f:
                    self._tools = json.load(f)
                logger.info(f"Loaded {len(self._tools)} tools from registry")
            except Exception as e:
                logger.error(f"Failed to load registry: {str(e)}")
                self._tools = {}
        else:
            logger.info("No existing registry found, starting fresh")
            self._tools = {}
    
    def _save_registry(self):
        """Save registry to JSON file."""
        try:
            with open(self.registry_path, 'w') as f:
                json.dump(self._tools, f, indent=2)
            logger.debug(f"Registry saved: {len(self._tools)} tools")
        except Exception as e:
            logger.error(f"Failed to save registry: {str(e)}")
    
    def register(self, tool_info: Dict):
        """
        Register a new tool.
        
        Args:
            tool_info: Tool information dict with:
                - name: Tool name (Aethvion format)
                - domain, action, object
                - description
                - file_path
                - trace_id
                - created_at
        """
        with self._lock:
            tool_name = tool_info['name']
            
            # Add registration metadata
            tool_info['registered_at'] = datetime.now().isoformat()
            tool_info['version'] = tool_info.get('version', '1.0.0')
            if 'usage_count' not in tool_info:
                tool_info['usage_count'] = 0
            
            self._tools[tool_name] = tool_info
            self._save_registry()
            
            logger.info(f"Registered tool: {tool_name}")
    
    def get_tool(self, name: str) -> Optional[Dict]:
        """
        Get tool information by name.
        
        Args:
            name: Tool name
            
        Returns:
            Tool info dict or None
        """
        with self._lock:
            return self._tools.get(name)
    
    def list_tools(self, domain: Optional[str] = None) -> List[Dict]:
        """
        List all tools, optionally filtered by domain.
        
        Args:
            domain: Optional domain filter
            
        Returns:
            List of tool info dicts
        """
        with self._lock:
            if domain:
                return [
                    tool for tool in self._tools.values()
                    if tool['domain'] == domain
                ]
            return list(self._tools.values())
    
    def search_tools(self, query: str) -> List[Dict]:
        """
        Search tools by name or description.
        
        Args:
            query: Search query
            
        Returns:
            List of matching tool info dicts
        """
        with self._lock:
            query_lower = query.lower()
            return [
                tool for tool in self._tools.values()
                if query_lower in tool['name'].lower()
                or query_lower in tool.get('description', '').lower()
            ]
    
    def get_tool_count(self) -> int:
        """
        Get total number of registered tools.
        
        Returns:
            Tool count
        """
        with self._lock:
            return len(self._tools)
    
    def tool_exists(self, name: str) -> bool:
        """
        Check if tool is registered.
        
        Args:
            name: Tool name
            
        Returns:
            True if tool exists
        """
        with self._lock:
            return name in self._tools
    
    def unregister(self, name: str, delete_file: bool = False) -> bool:
        """
        Unregister a tool.
        
        Args:
            name: Tool name
            delete_file: If True, also delete the tool's python file
            
        Returns:
            True if tool was unregistered
        """
        with self._lock:
            if name in self._tools:
                if delete_file:
                    file_path = self._tools[name].get('file_path')
                    if file_path:
                        try:
                            Path(file_path).unlink()
                            logger.info(f"Deleted tool file: {file_path}")
                        except FileNotFoundError:
                            logger.warning(f"Tool file not found for deletion: {file_path}")
                        except Exception as e:
                            logger.error(f"Failed to delete tool file {file_path}: {e}")

                del self._tools[name]
                self._save_registry()
                logger.info(f"Unregistered tool: {name}")
                return True
            return False

    def increment_usage(self, name: str) -> int:
        """
        Increment usage count for a tool.
        
        Args:
            name: Tool name
            
        Returns:
            New usage count
        """
        with self._lock:
            if name in self._tools:
                tool = self._tools[name]
                count = tool.get('usage_count', 0) + 1
                tool['usage_count'] = count
                tool['last_used_at'] = datetime.now().isoformat()
                self._save_registry()
                return count
            return 0


# Global registry instance
_registry = None


def get_tool_registry(registry_path: Optional[Path] = None) -> ToolRegistry:
    """Get the global tool registry."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry(registry_path)
    return _registry
