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
from core.utils.paths import HISTORY_CHAT, COMPANIONS_PERSONAS

logger = get_logger(__name__)

def _get_history_dir(companion_id: Optional[str] = None) -> Path:
    """Get the history directory for a specific companion."""
    if companion_id and companion_id != "misakacipher":
        return COMPANIONS_PERSONAS / companion_id / "threads"
    return HISTORY_CHAT

_lock = threading.Lock()

class HistoryManager:
    """
    Manages chat history with support for multiple companions.
    """

    @staticmethod
    def _get_history_file(dt: datetime.datetime, companion_id: Optional[str] = None) -> Path:
        """Get the path to the daily history file."""
        month_str = dt.strftime("%Y-%m")
        day_str = dt.strftime("%Y-%m-%d")
        history_dir = _get_history_dir(companion_id)
        day_dir = history_dir / month_str
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir / f"chat_{day_str}.json"

    @staticmethod
    def log_message(
        role: str,
        content: str,
        platform: str = "dashboard",
        timestamp: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        companion_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Log a message to the unified history.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        if not timestamp:
            timestamp = utcnow_iso()

        entry = {
            "role": role,
            "content": content,
            "platform": platform,
            "timestamp": timestamp
        }

        if attachments:
            entry["attachments"] = attachments
        
        if metadata:
            if role == "assistant":
                if "mood" in metadata:
                    entry["mood"] = metadata["mood"]
                if "expression" in metadata:
                    entry["expression"] = metadata["expression"]
            entry["metadata"] = metadata

        # Write to file
        day_file = HistoryManager._get_history_file(now, companion_id)
        
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
    def get_history(offset_days: int = 0, limit_days: int = 3, companion_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Load history for a range of days.
        """
        results = []
        now = datetime.datetime.now(datetime.timezone.utc)
        
        for i in range(offset_days, offset_days + limit_days):
            dt = now - datetime.timedelta(days=i)
            day_file = HistoryManager._get_history_file(dt, companion_id)
            
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
                results.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "messages": []
                })
                
        return results

    @staticmethod
    def get_total_message_count(companion_id: Optional[str] = None) -> int:
        """Get total message count for the current day."""
        day_file = HistoryManager._get_history_file(datetime.datetime.now(datetime.timezone.utc), companion_id)
        if not day_file.exists():
            return 0
        try:
            with open(day_file, "r", encoding="utf-8") as f:
                history = json.load(f)
                return len(history)
        except Exception:
            return 0

    @staticmethod
    def get_recent_history(limit: int = 15, companion_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get the most recent messages across days up to the limit.
        """
        all_messages = []
        now = datetime.datetime.now(datetime.timezone.utc)
        
        for i in range(7):
            dt = now - datetime.timedelta(days=i)
            day_file = HistoryManager._get_history_file(dt, companion_id)
            if day_file.exists():
                try:
                    with open(day_file, "r", encoding="utf-8") as f:
                        day_messages = json.load(f)
                        all_messages = day_messages + all_messages
                        if len(all_messages) > limit * 2:
                            break
                except Exception as e:
                    logger.error(f"Error reading history for {dt} ({companion_id}): {e}")
        
        return all_messages[-limit:] if all_messages else []
