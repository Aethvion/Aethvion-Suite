"""
core/companions/engine/history.py
══════════════════════════════════
CompanionHistory — per-day JSON chat history for any companion.

history_dir/
    YYYY-MM/
        chat_YYYY-MM-DD.json   — list of message dicts
"""
from __future__ import annotations
import datetime
import json
import shutil
from pathlib import Path
from typing import Callable
from core.utils import get_logger, atomic_json_write

logger = get_logger(__name__)




def _default_time_formatter(total_seconds: int) -> str:
    if total_seconds < 120:
        return "Just moments ago"
    if total_seconds < 3600:
        m = total_seconds // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if total_seconds < 86400:
        h = total_seconds // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    if total_seconds < 172800:
        return "Yesterday"
    d = total_seconds // 86400
    return f"{d} days ago"


class CompanionHistory:
    """
    Manages daily chat history JSON files for a single companion.
    Thread-safe for reads; writes are append-only per session.
    """

    def __init__(
        self,
        history_dir: Path,
        companion_name: str = "Companion",
        time_formatter: Callable[[int], str] | None = None,
    ):
        self._dir = history_dir
        self._name = companion_name
        self._time_formatter: Callable[[int], str] = time_formatter or _default_time_formatter
        self._dir.mkdir(parents=True, exist_ok=True)

    # Internal helpers

    def _today_file(self) -> Path:
        now = datetime.datetime.now()
        month_dir = self._dir / now.strftime("%Y-%m")
        month_dir.mkdir(parents=True, exist_ok=True)
        return month_dir / f"chat_{now.strftime('%Y-%m-%d')}.json"

    def _all_files(self) -> list[Path]:
        files: list[Path] = []
        for month_dir in sorted(self._dir.glob("*-*"), reverse=True):
            if month_dir.is_dir():
                files.extend(sorted(month_dir.glob("chat_*.json"), reverse=True))
        return files

    # Write

    def save_message(
        self,
        role: str,
        content: str,
        timestamp: str,
        mood: str = "",
        expression: str = "",
        attachments: list | None = None,
        **extra,
    ) -> None:
        try:
            day_file = self._today_file()
            history: list = []
            if day_file.exists():
                try:
                    history = json.loads(day_file.read_text(encoding="utf-8"))
                except Exception:
                    history = []
            entry: dict = {"role": role, "content": content, "timestamp": timestamp}
            if mood:
                entry["mood"] = mood
            if expression:
                entry["expression"] = expression
            if attachments:
                entry["attachments"] = attachments
            entry.update(extra)
            history.append(entry)
            atomic_json_write(day_file, history, indent=4)
        except Exception as e:
            logger.error(f"{self._name}: Failed to save history message: {e}")

    # Read

    def load_days(self, offset: int = 0, limit: int = 3) -> dict:
        all_files = self._all_files()
        target = all_files[offset: offset + limit]
        data: list[dict] = []
        for f in target:
            try:
                date_str = f.stem.replace("chat_", "")
                messages = json.loads(f.read_text(encoding="utf-8"))
                data.append({"date": date_str, "messages": messages})
            except Exception as e:
                logger.error(f"{self._name}: Error reading {f.name}: {e}")
        return {"history": data, "has_more": len(all_files) > (offset + limit)}

    def get_total_message_count(self) -> int:
        """Count of messages in today's file (used to trigger synthesis)."""
        try:
            day_file = self._today_file()
            if day_file.exists():
                return len(json.loads(day_file.read_text(encoding="utf-8")))
        except Exception:
            pass
        return 0

    # Time since last

    def time_since_last(self) -> str:
        try:
            all_files = self._all_files()
            if not all_files:
                return "First conversation"
            messages = json.loads(all_files[0].read_text(encoding="utf-8"))
            if not messages:
                return "First conversation"
            last_ts_str: str | None = next(
                (m["timestamp"] for m in reversed(messages) if m.get("timestamp")), None
            )
            if not last_ts_str:
                return "Recently"
            last_ts = datetime.datetime.strptime(last_ts_str, "%Y-%m-%d %H:%M:%S")
            delta = int((datetime.datetime.now() - last_ts).total_seconds())
            return self._time_formatter(delta)
        except Exception as e:
            logger.warning(f"{self._name}: time_since_last error: {e}")
            return "Some time ago"

    # Clear / Reset

    def clear(self) -> None:
        if self._dir.exists():
            shutil.rmtree(self._dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"{self._name}: History cleared.")
