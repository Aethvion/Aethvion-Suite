"""
core/interfaces/dashboard/ws_manager.py
═══════════════════════════════════════
WebSocket connection management and log streaming.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Dict, List, Any, Optional
from core.utils import utcnow_iso
from core.utils import get_logger

logger = get_logger(__name__)

class ConnectionManager:
    """Manages WebSocket connections."""
    
    def __init__(self):
        self.active_connections: Dict[str, List[Any]] = {
            'chat': [],
            'logs': [],
            'agents': []
        }
    
    async def connect(self, websocket: Any, channel: str):
        """Connect a new WebSocket client."""
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = []
        self.active_connections[channel].append(websocket)
    
    def disconnect(self, websocket: Any, channel: str):
        """Disconnect a WebSocket client."""
        if channel in self.active_connections and websocket in self.active_connections[channel]:
            self.active_connections[channel].remove(websocket)
    
    async def broadcast(self, message: dict, channel: str):
        """Broadcast message to all clients on a channel."""
        if channel not in self.active_connections:
            return
        
        disconnected = []
        for connection in self.active_connections[channel]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to {channel}: {type(e).__name__}: {e}")
                disconnected.append(connection)
        
        for conn in disconnected:
            self.disconnect(conn, channel)

manager = ConnectionManager()

class WebSocketLogHandler(logging.Handler):
    """Custom handler to pipe logs to WebSocket."""
    
    def __init__(self):
        super().__init__()
        self.main_loop: Optional[asyncio.AbstractEventLoop] = None
    
    def emit(self, record):
        try:
            msg = self.format(record)
            if "GET /api/system/status" in msg or "GET /api/workspace/files" in msg:
                return
                
            log_entry = {
                "type": "log",
                "level": record.levelname,
                "message": msg,
                "source": record.name,
                "timestamp": utcnow_iso()
            }

            if self.main_loop and self.main_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast(log_entry, "logs"),
                    self.main_loop
                )
        except Exception:
            self.handleError(record)