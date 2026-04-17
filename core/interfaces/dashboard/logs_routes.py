from fastapi import APIRouter, HTTPException
from pathlib import Path
import os
import json
from datetime import datetime
from core.utils import get_logger

logger = get_logger(__name__)
from core.utils.paths import LOGS
router = APIRouter(prefix="/api/logs", tags=["Logs"])

# Use centralized LOGS directory
LOGS_DIR = LOGS

@router.get("/list")
async def list_logs():
    """List all available system logs (.txt, .log)."""
    if not LOGS_DIR.exists():
        logger.warning(f"Logs directory not found: {LOGS_DIR}")
        return {"logs": []}
    
    files = []
    try:
        for f in LOGS_DIR.iterdir():
            if f.is_file() and f.suffix.lower() in [".log", ".txt"]:
                stats = f.stat()
                files.append({
                    "name": f.name,
                    "size": stats.st_size,
                    "modified": stats.st_mtime,
                    "modified_pretty": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
        
        # Sort by modified time (newest first)
        files.sort(key=lambda x: x["modified"], reverse=True)
    except Exception as e:
        logger.error(f"Failed to list logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
    return {"logs": files}

@router.get("/read/{filename}")
async def read_log(filename: str):
    """Read contents of a specific log file with safety limits."""
    # Security: prevent directory traversal
    safe_name = os.path.basename(filename)
    log_path = LOGS_DIR / safe_name
    
    if not log_path.exists() or not log_path.is_file():
        logger.error(f"Log file not found: {log_path}")
        raise HTTPException(status_code=404, detail="Log file not found")
        
    try:
        file_size = log_path.stat().st_size
        
        # Limit reading to last 1MB if file is huge (5MB+)
        if file_size > 5 * 1024 * 1024:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(file_size - 1024 * 1024)
                content = f.read()
                return {
                    "content": "... (File truncated - showing last 1MB) ...\n" + content, 
                    "truncated": True,
                    "size": file_size,
                    "name": safe_name
                }
        
        content = log_path.read_text(encoding="utf-8", errors="replace")
        return {
            "content": content, 
            "truncated": False,
            "size": file_size,
            "name": safe_name
        }
    except Exception as e:
        logger.error(f"Error reading log {safe_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
