"""
Aethvion Suite - Corp Worker Runner
AgentRunner subclass for Agent Corp workers.

Adds corp-specific tools (post_to_log, create_task, update_memory,
read_log, read_task_board) on top of the standard agent toolkit.
Any capability added to AgentRunner automatically flows through here.

TOKEN OPTIMISATIONS vs base AgentRunner
• CORP_SYSTEM_PROMPT   ~1,400 chars  (vs 6,025 for full SYSTEM_PROMPT)
• _task_short          ~200  chars   (vs ~7,000 for full worker context)
  Full context only in iteration 0; subsequent iterations use short reminder.
• _conv_window = 6     (vs 8) — focused corp tasks need less lookback.

Combined these cut per-iteration overhead by ~55 % for long-running corps.
"""
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.orchestrator.agent_runner import AgentRunner
from core.utils.logger import get_logger

logger = get_logger(__name__)


# Focused system prompt for corp workers
# ~1,400 chars vs the 6,025-char base SYSTEM_PROMPT.
# Removes verbose web-search/fetch sections workers rarely use; keeps all
# file-editing, corp tools, and the surgical-edit rules that matter most.

# Focused system prompt for corp workers
# ~1,400 chars vs the full SYSTEM_PROMPT. Edit core/config/code/corp_system_prompt.txt.
from core.utils.paths import CODE_CORP_PROMPT
CORP_SYSTEM_PROMPT: str = CODE_CORP_PROMPT.read_text(encoding='utf-8')


class CorpWorkerRunner(AgentRunner):
    """AgentRunner subclass that knows about corp-specific tools."""

    def __init__(
        self,
        task: str,
        workspace_path: str,
        step_callback: Callable[[Dict[str, Any]], None],
        model_id: Optional[str] = None,
        state_path: Optional[Path] = None,
        images: Optional[List[Dict]] = None,
        # Corp-specific
        corp_manager=None,
        corp_id: str = "",
        worker_id: str = "",
        worker_name: str = "",
        task_title: str = "",
        corp_name: str = "",
    ):
        super().__init__(
            task=task,
            workspace_path=workspace_path,
            step_callback=step_callback,
            model_id=model_id,
            state_path=state_path,
            images=images,
        )
        self._corp_manager = corp_manager
        self._corp_id = corp_id
        self._worker_id = worker_id
        self._worker_name = worker_name

        # Refreshed lazily: when the corp log grows (new lines appended) the cached
        # line count changes and we re-filter; otherwise we reuse the cached result.
        self._op_cached_lines: list = []   # last extracted [Operator→ …] lines
        self._op_log_line_count: int = 0   # log line count at last refresh

        # Route blueprint cache to the corp data dir so it never appears
        # inside the user's project workspace.
        if corp_manager and corp_id:
            try:
                self._blueprint_cache_path = corp_manager._corp_dir(corp_id) / "_blueprint.txt"
            except Exception:
                pass

        # Token optimisations
        # Narrow conversation window: focused corp tasks need less lookback.
        self._conv_window = 6

        # Compact task reminder for iterations 1+.
        # in conversation history.  Repeating ~7 k chars every call is wasteful.
        title = task_title or task.split("\n")[0][:80]
        self._task_short = (
            f"[{worker_name} continuing task: {title}]\n"
            f"Navigate: get_project_blueprint (tree) · search_codebase(query,path) (find text).\n"
            f"Corp: post_to_log · create_task · update_memory · read_shared_memory · "
            f"update_shared_memory(key,content) · read_log · read_task_board · done(summary).\n"
            f"Edit: patch_file (existing files) · append_file (new code) · Knowledge block has line numbers."
        )

    # Corp-specific system prompt & prompt building

    def _build_prompt(self) -> str:
        """Like parent, but injects recent operator steering messages on iterations 1+."""
        if not self.conversation or not self._task_short:
            return super()._build_prompt()

        task_block = self._task_short
        if self._corp_manager:
            try:
                # Refresh operator-message cache only when the log has grown.
                # read_log is a file read; doing it every LLM call is wasteful.
                full_log = self._corp_manager.read_log(self._corp_id, last_n=200)
                all_lines = full_log.splitlines()
                current_count = len(all_lines)
                if current_count != self._op_log_line_count:
                    self._op_cached_lines = [
                        ln for ln in all_lines if "[Operator →" in ln
                    ]
                    self._op_log_line_count = current_count
                if self._op_cached_lines:
                    recent_op = "\n".join(self._op_cached_lines[-3:])
                    task_block = (
                        f"OPERATOR STEERING (read and respond/act if relevant):\n"
                        f"{recent_op}\n\n{self._task_short}"
                    )
            except Exception:
                pass

        system = self._get_system_prompt()
        parts = [system]
        ctx = self.state.build_context()
        if ctx:
            parts.append(f"Context:\n{ctx}")
        parts.append(f"User: {task_block}")
        recent = self.conversation[-self._conv_window:]
        parts.extend(recent)
        return "\n\n".join(parts)

    def _get_system_prompt(self) -> str:
        from datetime import datetime
        return CORP_SYSTEM_PROMPT.format(
            workspace=str(self.workspace),
            current_date=datetime.utcnow().strftime("%B %d, %Y"),
        )

    # Corp tool execution

    def _execute(self, action: Dict[str, Any], iteration: int = 0) -> str:
        """Handle corp-specific action types; fall through to parent for the rest."""
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
            if priority == "urgent":
                priority = "high"
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

        if t == "update_shared_memory":
            key     = action.get("key", "").strip()
            content = action.get("content", "").strip()
            if not key or not content:
                return "[update_shared_memory] 'key' and 'content' are required."
            if self._corp_manager:
                return self._corp_manager.update_shared_memory(
                    self._corp_id, self._worker_name, key, content
                )
            return "[update_shared_memory] Corp manager not available."

        if t == "read_shared_memory":
            if not self._corp_manager:
                return "(shared memory not available)"
            key = action.get("key", "")
            return self._corp_manager.read_shared_memory(self._corp_id, key)

        # Everything else handled by parent (write_file, patch_file, search_web, etc.)
        return super()._execute(action, iteration)
