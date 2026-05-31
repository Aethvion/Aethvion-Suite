"""
core/orchestrator/cancellation.py
Lightweight cancellation signalling for agent tasks.

Kept in its own module so agent_runner (execution layer) and task_queue
(orchestration layer) can both import it without creating a circular dependency.
"""
from __future__ import annotations

_cancelled: set[str] = set()


def cancel_agent_task(task_id: str) -> None:
    """Signal the AgentRunner for this task to stop after its current iteration."""
    _cancelled.add(task_id)


def is_agent_task_cancelled(task_id: str) -> bool:
    """Return True if a stop has been requested for this task."""
    return task_id in _cancelled
