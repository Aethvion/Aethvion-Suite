"""
Misaka Cipher - Usage Routes
API endpoints for the Usage Dashboard
"""

from fastapi import APIRouter, HTTPException
from typing import Optional

from core.utils import get_logger

from datetime import datetime
from core.utils import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/usage", tags=["usage"])


def parse_dates(start: Optional[str], end: Optional[str]):
    """Parse ISO date strings into datetime objects."""
    start_dt = None
    end_dt = None
    try:
        if start:
            # Handle YYYY-MM-DD or ISO
            if len(start) == 10:
                start_dt = datetime.fromisoformat(start)
            else:
                start_dt = datetime.fromisoformat(start.replace("Z", ""))
        if end:
            if len(end) == 10:
                end_dt = datetime.fromisoformat(end).replace(hour=23, minute=59, second=59)
            else:
                end_dt = datetime.fromisoformat(end.replace("Z", ""))
    except Exception as e:
        logger.warning(f"Failed to parse dates: {e}")
    
    return start_dt, end_dt


@router.get("/summary")
async def get_usage_summary(
    start: Optional[str] = None, 
    end: Optional[str] = None,
    local: bool = True,
    api: bool = True
):
    """Get aggregated usage statistics."""
    try:
        from core.workspace.usage_tracker import get_usage_tracker
        tracker = get_usage_tracker()
        s, e = parse_dates(start, end)
        return tracker.get_summary(start_date=s, end_date=e, show_local=local, show_api=api)
    except Exception as e:
        logger.error(f"Failed to get usage summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_usage_history(
    limit: int = 100, 
    start: Optional[str] = None, 
    end: Optional[str] = None,
    local: bool = True,
    api: bool = True
):
    """Get recent usage entries."""
    try:
        from core.workspace.usage_tracker import get_usage_tracker
        tracker = get_usage_tracker()
        s, e = parse_dates(start, end)
        return {"entries": tracker.get_history(limit=limit, start_date=s, end_date=e, show_local=local, show_api=api)}
    except Exception as e:
        logger.error(f"Failed to get usage history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hourly")
async def get_hourly_breakdown(
    hours: int = 24, 
    start: Optional[str] = None, 
    end: Optional[str] = None,
    local: bool = True,
    api: bool = True
):
    """Get hourly token/call breakdown for charts."""
    try:
        from core.workspace.usage_tracker import get_usage_tracker
        tracker = get_usage_tracker()
        s, e = parse_dates(start, end)
        return {"hours": tracker.get_hourly_breakdown(hours=hours, start_date=s, end_date=e, show_local=local, show_api=api)}
    except Exception as e:
        logger.error(f"Failed to get hourly breakdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cost-by-model")
async def get_cost_by_model(
    start: Optional[str] = None, 
    end: Optional[str] = None,
    local: bool = True,
    api: bool = True
):
    """Get cost breakdown by model for chart data."""
    try:
        from core.workspace.usage_tracker import get_usage_tracker
        tracker = get_usage_tracker()
        s, e = parse_dates(start, end)
        return tracker.get_cost_by_model(start_date=s, end_date=e, show_local=local, show_api=api)
    except Exception as e:
        logger.error(f"Failed to get cost by model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tokens-by-model")
async def get_tokens_by_model(
    start: Optional[str] = None, 
    end: Optional[str] = None,
    local: bool = True,
    api: bool = True
):
    """Get token breakdown by model for chart data."""
    try:
        from core.workspace.usage_tracker import get_usage_tracker
        tracker = get_usage_tracker()
        s, e = parse_dates(start, end)
        return tracker.get_tokens_by_model(start_date=s, end_date=e, show_local=local, show_api=api)
    except Exception as e:
        logger.error(f"Failed to get tokens by model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools")
async def get_tool_usage():
    """Get tool usage statistics from the tool registry."""
    try:
        from core.forge.tool_registry import get_tool_registry
        registry = get_tool_registry()
        tools = registry.list_tools()

        # Sort by usage count (if tracked)
        tool_list = []
        for tool in tools:
            tool_list.append({
                "name": tool.get("name", "unknown"),
                "domain": tool.get("domain", ""),
                "usage_count": tool.get("usage_count", 0),
                "last_used": tool.get("last_used"),
                "created": tool.get("created"),
                "file_path": tool.get("file_path", "")
            })

        # Most used first
        tool_list.sort(key=lambda x: x["usage_count"], reverse=True)

        return {"tools": tool_list}
    except Exception as e:
        logger.error(f"Failed to get tool usage: {e}")
        raise HTTPException(status_code=500, detail=str(e))
