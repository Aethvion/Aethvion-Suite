"""
Aethvion Suite - History Manager
Manages chat session history and thread persistence
"""

import json
import datetime
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional

from core.utils.logger import get_logger
from core.utils.paths import HISTORY_CHAT

logger = get_logger(__name__)

# Constants
HISTORY_DIR = HISTORY_CHAT

_lock = threading.Lock()

class HistoryManager:
    """
    Manages Misaka Cipher's chat history with support for multiple platforms.
    """

    @staticmethod
    def _get_history_file(dt: datetime.datetime) -> Path:
        """Get the path to the daily history file."""
        month_str = dt.strftime("%Y-%m")
        day_str = dt.strftime("%Y-%m-%d")
        day_dir = HISTORY_DIR / month_str
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir / f"chat_{day_str}.json"

    @staticmethod
    def log_message(
        role: str,
        content: str,
        platform: str = "dashboard",
        timestamp: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Log a message to the unified history.
        
        Args:
            role: "user" or "assistant"
            content: Message content
            platform: "dashboard" or "discord"
            timestamp: ISO format string (optional)
            attachments: List of attachments
            metadata: Additional metadata (mood, expression, etc.)
            
        Returns:
            The logged message entry.
        """
        now = datetime.datetime.now()
        if not timestamp:
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

        entry = {
            "role": role,
            "content": content,
            "platform": platform,
            "timestamp": timestamp
        }

        if attachments:
            entry["attachments"] = attachments
        
        if metadata:
            # Flatten metadata into entry for assistant role (backwards compatibility)
            if role == "assistant":
                if "mood" in metadata:
                    entry["mood"] = metadata["mood"]
                if "expression" in metadata:
                    entry["expression"] = metadata["expression"]
            
            # Keep original metadata if complex
            entry["metadata"] = metadata

        # Write to file
        day_file = HistoryManager._get_history_file(now)
        
        with _lock:
            history = []
            if day_file.exists():
                try:
                    with open(day_file, "r", encoding="utf-8") as f:
                        history = json.load(f)
                except Exception as e:
                    logger.error(f"Failed to load history file {day_file}: {e}")
            
            history.append(entry)
            
            try:
                with open(day_file, "w", encoding="utf-8") as f:
                    json.dump(history, f, indent=4)
            except Exception as e:
                logger.error(f"Failed to save history to {day_file}: {e}")

        return entry

    @staticmethod
    def get_history(offset_days: int = 0, limit_days: int = 3) -> List[Dict[str, Any]]:
        """
        Load history for a range of days.
        
        Returns:
            List of daily history objects: [{"date": "...", "messages": [...]}, ...]
        """
        results = []
        now = datetime.datetime.now()
        
        for i in range(offset_days, offset_days + limit_days):
            dt = now - datetime.timedelta(days=i)
            day_file = HistoryManager._get_history_file(dt)
            
            if day_file.exists():
                try:
                    with open(day_file, "r", encoding="utf-8") as f:
                        messages = json.load(f)
                        results.append({
                            "date": dt.strftime("%Y-%m-%d"),
                            "messages": messages
                        })
                except Exception as e:
                    logger.error(f"Failed to read history {day_file}: {e}")
            else:
                # Still add the entry with empty messages so the frontend knows we checked
                results.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "messages": []
                })
                
        return results

    @staticmethod
    def get_total_message_count() -> int:
        """Get total message count for the current day (for synthesis triggering)."""
        day_file = HistoryManager._get_history_file(datetime.datetime.now())
        if not day_file.exists():
            return 0
        try:
            with open(day_file, "r", encoding="utf-8") as f:
                history = json.load(f)
                return len(history)
        except Exception:
            return 0

    @staticmethod
    def get_recent_history(limit: int = 15) -> List[Dict[str, Any]]:
        """
        Get the most recent messages across days up to the limit.
        Used for providing context to new interactions.
        """
        all_messages = []
        now = datetime.datetime.now()
        
        # Look back up to 7 days
        for i in range(7):
            dt = now - datetime.timedelta(days=i)
            day_file = HistoryManager._get_history_file(dt)
            if day_file.exists():
                try:
                    with open(day_file, "r", encoding="utf-8") as f:
                        day_messages = json.load(f)
                        # We want the MOST RECENT first for efficient limiting, 
                        # but usually history is chronological.
                        all_messages = day_messages + all_messages
                        if len(all_messages) > limit * 2: # Buffer for safety
                            break
                except Exception as e:
                    logger.error(f"Error reading history for {dt}: {e}")
        
        return all_messages[-limit:] if all_messages else []
