"""Thread-safe per-task event store for agent step streaming."""
import threading
from typing import Dict, List, Optional, Any

_store: Dict[str, Dict] = {}
_lock = threading.Lock()


def create_task_store(task_id: str) -> None:
    with _lock:
        _store[task_id] = {"events": [], "done": False}


def push_event(task_id: str, event: Dict[str, Any]) -> None:
    with _lock:
        if task_id in _store:
            _store[task_id]["events"].append(event)


def mark_task_done(task_id: str) -> None:
    with _lock:
        if task_id in _store:
            _store[task_id]["done"] = True


def get_snapshot(task_id: str) -> Optional[Dict]:
    """Returns a copy of {events: [...], done: bool} or None if not found."""
    with _lock:
        s = _store.get(task_id)
        if s is None:
            return None
        return {"events": list(s["events"]), "done": s["done"]}


def cleanup_task(task_id: str) -> None:
    with _lock:
        _store.pop(task_id, None)
