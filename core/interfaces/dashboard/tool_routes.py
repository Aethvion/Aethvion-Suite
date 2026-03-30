"""
Aethvion Suite - Tool Registry API Routes
FastAPI routes for tool management operations
"""

from fastapi import APIRouter, HTTPException
from core.utils import get_logger
from core.forge import ToolForge, get_tool_registry

logger = get_logger("web.tool_routes")

# Create router
router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("/list")
async def list_tools():
    """List all registered tools."""
    try:
        registry = get_tool_registry()
        tools = registry.list_tools()
        
        # Helper to check if system tool
        def is_system_tool(path_str):
            if not path_str: return False
            return "tools\\standard" in path_str or "tools/standard" in path_str

        return {
            "count": len(tools),
            "tools": [
                {
                    "name": t.get('name', 'unknown'),
                    "domain": t.get('domain', 'unknown'),
                    "description": t.get('description', ''),
                    "parameters": t.get('parameters', {}),
                    "created_at": t.get('created_at'),
                    "file_path": t.get('file_path'),
                    "usage_count": t.get('usage_count', 0),
                    "is_system": is_system_tool(t.get('file_path'))
                }
                for t in tools
            ]
        }
    except Exception as e:
        logger.error(f"Error listing tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{tool_name}")
async def delete_tool(tool_name: str):
    """Delete a tool and its associated file."""
    try:
        registry = get_tool_registry()
        
        if not registry.tool_exists(tool_name):
            raise HTTPException(status_code=404, detail=f"Tool {tool_name} not found")
            
        tool_info = registry.get_tool(tool_name)
        file_path = tool_info.get('file_path', '')
        if "tools\\standard" in file_path or "tools/standard" in file_path:
            raise HTTPException(status_code=403, detail=f"Cannot delete system tool: {tool_name}")

        success = registry.unregister(tool_name, delete_file=True)
        
        if success:
            logger.info(f"Tool {tool_name} deleted via API")
            return {"success": True, "message": f"Tool {tool_name} deleted successfully"}
        else:
            return {"success": False, "message": f"Failed to delete tool {tool_name}"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting tool {tool_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
