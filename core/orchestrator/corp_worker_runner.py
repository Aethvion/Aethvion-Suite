"""
CorpWorkerRunner — AgentRunner subclass for Agent Corp workers.

Adds corp-specific tools (post_to_log, create_task, update_memory,
read_log, read_task_board) on top of the standard agent toolkit.
Any capability added to AgentRunner automatically flows through here.
"""
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.orchestrator.agent_runner import AgentRunner
from core.utils.logger import get_logger

logger = get_logger(__name__)


class CorpWorkerRunner(AgentRunner):
    """AgentRunner subclass that knows about corp-specific tools."""

    def __init__(
        self,
        task: str,
        workspace_path: str,
        nexus,
        step_callback: Callable[[Dict[str, Any]], None],
        model_id: Optional[str] = None,
        state_path: Optional[Path] = None,
        images: Optional[List[Dict]] = None,
        # Corp-specific
        corp_manager=None,
        corp_id: str = "",
        worker_id: str = "",
        worker_name: str = "",
    ):
        super().__init__(
            task=task,
            workspace_path=workspace_path,
            nexus=nexus,
            step_callback=step_callback,
            model_id=model_id,
            state_path=state_path,
            images=images,
        )
        self._corp_manager = corp_manager
        self._corp_id = corp_id
        self._worker_id = worker_id
        self._worker_name = worker_name

    # ── extend action parsing to handle corp tools ────────────────────────────

    def _execute(self, action: Dict[str, Any], iteration: int = 0) -> str:
        """
        Handle corp-specific action types; fall through to parent for the rest.
        """
        t = action.get("type", "")

        if t == "post_to_log":
            message = action.get("message", "").strip()
            to      = action.get("to", "All")
            if not message:
                return "[post_to_log] No message provided."
            if self._corp_manager:
                self._corp_manager.post_to_log(
                    self._corp_id, self._worker_id, self._worker_name, message, to
                )
            return f"Message posted to team log (to: {to})."

        if t == "create_task":
            title       = action.get("title", "Untitled Task")
            description = action.get("description", "")
            assigned_to = action.get("assigned_to", "any")
            priority    = action.get("priority", "medium")
            if not self._corp_manager:
                return "[create_task] Corp manager not available."
            task = self._corp_manager.add_task(
                self._corp_id, title, description,
                assigned_to, priority, created_by=self._worker_id
            )
            return f"Task created: {task['task_id']} — '{title}' assigned to {assigned_to}."

        if t == "update_memory":
            content = action.get("content", "").strip()
            if not content:
                return "[update_memory] No content provided."
            if self._corp_manager:
                self._corp_manager.update_worker_memory(
                    self._corp_id, self._worker_id, content
                )
            return "Memory updated successfully."

        if t == "read_log":
            if not self._corp_manager:
                return "(no log)"
            return self._corp_manager.read_log(self._corp_id, last_n=30)

        if t == "read_task_board":
            if not self._corp_manager:
                return "(no task board)"
            tasks = self._corp_manager.get_tasks(self._corp_id)
            lines = [
                f"[{task['status'].upper()}] {task['task_id']}: {task['title']} "
                f"→ {task['assigned_to']}"
                for task in tasks
            ]
            return "\n".join(lines) or "Empty task board."

        # Everything else handled by parent (write_file, search_web, etc.)
        return super()._execute(action, iteration)
