"""
Aethvion Suite - Chat Token Store
Thread-safe asyncio.Queue-based per-task token store for live chat streaming.

Usage flow:
  Worker:      create_token_queue(task_id)  →  push tokens via loop.call_soon_threadsafe
  SSE handler: get_token_queue(task_id)     →  await queue.get() in a loop
"""
import threading
import asyncio
from typing import Dict, Optional

_queues: Dict[str, asyncio.Queue] = {}
_lock = threading.Lock()


def create_token_queue(task_id: str) -> asyncio.Queue:
    """Create a new asyncio.Queue for the given task and return it."""
    q: asyncio.Queue = asyncio.Queue()
    with _lock:
        _queues[task_id] = q
    return q


def get_token_queue(task_id: str) -> Optional[asyncio.Queue]:
    """Return the Queue for the task, or None if it doesn't exist yet."""
    with _lock:
        return _queues.get(task_id)


def cleanup_token_queue(task_id: str) -> None:
    """Remove the queue from the store (call after the SSE handler is done)."""
    with _lock:
        _queues.pop(task_id, None)
