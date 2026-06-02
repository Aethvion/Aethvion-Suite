"""
core/orchestrator/agent_state.py
═════════════════════════════════
AgentState — persistent session state for the Code agent runner.
Handles file cache, plan tracking, context building, and JSON-backed persistence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.utils import get_logger, utcnow_iso, atomic_json_write

logger = get_logger(__name__)

class AgentState:
    """Persistent state for an AgentRunner session.

    State is stored as JSON at state_path (if provided) and loaded on
    construction so sessions can resume after a crash or restart.
    """

    _MAX_NOTES = 10
    _MAX_LOG = 30

    def __init__(self, state_path: Optional[Path] = None):
        self.state_path = state_path

        # Mutable state fields
        self.plan: List[Dict[str, Any]] = []        # [{"text": str, "done": bool}]
        self.notes: List[str] = []
        self.file_cache: Dict[str, Dict[str, Any]] = {}  # path -> {size, cached_at}
        self.workspace_map: List[str] = []
        self.action_log: List[Dict[str, Any]] = []  # [{i, type, detail, at}]
        self.prior_tasks: List[Dict[str, str]] = []  # [{task, summary}] across the thread
        # Semantic memory: compact structural digest for every file ever read/modified.
        # without having to re-read raw content that long-since scrolled out of history.
        self.file_digests: Dict[str, str] = {}      # path -> digest string

        self._load()

    # persistence

    def _load(self) -> None:
        if not self.state_path:
            return
        try:
            p = Path(self.state_path)
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                self.plan = data.get("plan", [])
                self.notes = data.get("notes", [])
                self.file_cache = data.get("file_cache", {})
                self.workspace_map = data.get("workspace_map", [])
                self.action_log = data.get("action_log", [])
                self.prior_tasks = data.get("prior_tasks", [])
                self.file_digests = data.get("file_digests", {})
                logger.info(f"[AgentState] Loaded state from {self.state_path}")
        except Exception as e:
            logger.warning(f"[AgentState] Could not load state from {self.state_path}: {e}")

    def save(self) -> None:
        if not self.state_path:
            return
        try:
            p = Path(self.state_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "plan": self.plan,
                "notes": self.notes,
                "file_cache": self.file_cache,
                "workspace_map": self.workspace_map,
                "action_log": self.action_log,
                "prior_tasks": self.prior_tasks,
                "file_digests": self.file_digests,
            }
            atomic_json_write(p, data)
        except Exception as e:
            logger.warning(f"[AgentState] Could not save state to {self.state_path}: {e}")

    # file cache

    def is_cached(self, path: str) -> bool:
        return path in self.file_cache

    def cache_file(self, path: str, size: int, turn: int = 0, modified: bool = False) -> None:
        existing = self.file_cache.get(path, {})
        self.file_cache[path] = {
            "size": size,
            "cached_at": utcnow_iso(),
            "turn": turn,
            # Once a file is marked modified, never downgrade it back to read-only.
            "modified": modified or existing.get("modified", False),
        }
        if path not in self.workspace_map:
            self.workspace_map.append(path)

    def evict_file(self, path: str) -> bool:
        """Manually evict a single file from file_cache.

        The agent calls this immediately after finishing with a reference or
        template file — one pass to learn the pattern is enough.  The file
        stays in workspace_map and file_digests so the agent still knows it
        exists and has its structure.
        """
        if path in self.file_cache:
            del self.file_cache[path]
            return True
        return False

    def evict_read_only_files(self) -> List[str]:
        """Evict all files that were only read, never written/patched/appended.

        Called automatically on phase transitions (when set_plan is called after
        an exploration phase) to clear out reference files the agent learned from
        but is no longer actively modifying.
        """
        evicted = []
        for path in list(self.file_cache.keys()):
            if not self.file_cache[path].get("modified", False):
                del self.file_cache[path]
                evicted.append(path)
        return evicted

    def evict_stale_cache(self, current_turn: int, max_idle_turns: int = 2) -> List[str]:
        """Remove files from file_cache that haven't been accessed in max_idle_turns.

        The file remains in workspace_map (agent still knows it exists) and
        file_digests (structural knowledge is preserved). Only the '(cached)'
        marker in the Files: context line is removed, signalling the agent it
        should re-read if it needs the current content again.

        Returns the list of evicted paths for logging.
        """
        evicted = []
        for path in list(self.file_cache.keys()):
            idle = current_turn - self.file_cache[path].get("turn", 0)
            if idle > max_idle_turns:
                del self.file_cache[path]
                evicted.append(path)
        return evicted

    def update_workspace_map(self, entries: List[str]) -> None:
        """Replace workspace_map with entries from list_dir, evicting stale cache."""
        self.workspace_map = list(entries)
        stale = [p for p in list(self.file_cache.keys()) if p not in entries]
        for p in stale:
            del self.file_cache[p]

    # plan

    def set_plan(self, steps: List[str]) -> None:
        self.plan = [{"text": s, "done": False} for s in steps]

    def mark_done(self, step_text: str) -> None:
        """Mark a plan step done using exact match first, then fuzzy substring."""
        step_lower = step_text.lower().strip()
        # Exact match
        for item in self.plan:
            if item["text"].lower().strip() == step_lower:
                item["done"] = True
                return
        # Fuzzy: first plan item whose text contains the query as substring
        for item in self.plan:
            if step_lower in item["text"].lower():
                item["done"] = True
                return

    # prior task history

    def record_task(self, task: str, summary: str) -> None:
        """Append a completed task to the thread history (capped at 20)."""
        self.prior_tasks.append({
            "task": task[:300],
            "summary": summary[:500],
        })
        if len(self.prior_tasks) > 20:
            self.prior_tasks = self.prior_tasks[-20:]

    # notes

    def update_file_digest(self, path: str, digest: str) -> None:
        """Store or update the semantic digest for a file.

        Re-inserting the key moves it to the end of the dict so that
        build_context() (which iterates in reverse) shows the most-recently-
        accessed files first — most relevant to the current task.
        """
        self.file_digests.pop(path, None)   # remove old entry to reset position
        self.file_digests[path] = digest

    def add_note(self, note: str) -> None:
        self.notes.append(note)
        if len(self.notes) > self._MAX_NOTES:
            self.notes = self.notes[-self._MAX_NOTES:]

    # action log

    def log_action(self, iteration: int, action_type: str, detail: str) -> None:
        self.action_log.append({
            "i": iteration,
            "type": action_type,
            "detail": detail,
            "at": utcnow_iso(),
        })
        if len(self.action_log) > self._MAX_LOG:
            self.action_log = self.action_log[-self._MAX_LOG:]

    # context builder

    def build_context(self, current_turn: int = 0) -> str:
        """Return a compact context string injected into every prompt."""
        parts: List[str] = []

        # Capped at 3 to keep prompt overhead low in long sessions.
        if self.prior_tasks:
            history_lines = ["Thread history (previous tasks in this thread):"]
            for pt in self.prior_tasks[-3:]:
                history_lines.append(f"  • Task: {pt['task']}")
                history_lines.append(f"    Result: {pt['summary']}")
            parts.append("\n".join(history_lines))

        # Files line
        if self.workspace_map:
            file_tokens: List[str] = []
            for fname in self.workspace_map:
                if fname in self.file_cache:
                    info = self.file_cache[fname]
                    file_tokens.append(f"{fname} ({info['size']}b, cached)")
                else:
                    file_tokens.append(fname)
            parts.append("Files: " + ", ".join(file_tokens))

        # Plan
        if self.plan:
            plan_lines = ["Plan:"]
            for item in self.plan:
                marker = "[x]" if item["done"] else "[ ]"
                plan_lines.append(f"  {marker} {item['text']}")
            parts.append("\n".join(plan_lines))

        # Notes
        if self.notes:
            parts.append("Notes: " + "; ".join(self.notes))

        # Semantic file digests — compact structural knowledge about every file
        # ever read or modified; persists across all iterations in this thread.
        # Show most-recently-updated first (dict preserves insertion order; re-inserting
        # on update moves a key to the end, so reversing gives MRU-first).
        if self.file_digests:
            digest_lines = ["Knowledge (file structure — use this before re-reading):"]
            used = 0
            hidden = 0
            _DIGEST_CAP = 1500
            for path, digest in reversed(list(self.file_digests.items())):
                entry = f"  {digest}"
                if used + len(entry) > _DIGEST_CAP:
                    hidden += 1
                else:
                    digest_lines.append(entry)
                    used += len(entry)
            if hidden:
                digest_lines.append(
                    f"  … {hidden} more file(s) — call get_project_blueprint to see all"
                )
            parts.append("\n".join(digest_lines))

        # Recent actions — always show every write/patch/append (so the model knows
        # exactly what was changed), plus the last few non-write actions for context.
        if self.action_log:
            _WRITE_TYPES = {"write_file", "patch_file", "append_file", "create_file"}
            writes   = [e for e in self.action_log if e["type"] in _WRITE_TYPES]
            non_writes = [e for e in self.action_log if e["type"] not in _WRITE_TYPES]
            shown = writes[-10:] + non_writes[-4:]
            shown.sort(key=lambda e: e.get("i", 0))
            tokens = [f"{e['type']}({e['detail']})" for e in shown]
            parts.append("Recent: " + ", ".join(tokens))

        # Eviction nudge — gently remind the agent when read-only files have been
        # during the first exploration pass (where the agent is still reading).
        _NUDGE_AFTER = 3
        if current_turn >= _NUDGE_AFTER:
            stale_reads = [
                path for path, info in self.file_cache.items()
                if not info.get("modified", False)
                and (current_turn - info.get("turn", 0)) >= _NUDGE_AFTER
            ]
            if stale_reads:
                names  = ", ".join(stale_reads[:4])
                extra  = f" (+{len(stale_reads) - 4} more)" if len(stale_reads) > 4 else ""
                parts.append(
                    f"⚠ Eviction nudge: {len(stale_reads)} read-only file(s) idle ≥{_NUDGE_AFTER} turns — "
                    f"call distill_file_context (or evict_file) if you no longer need the raw content: "
                    f"{names}{extra}"
                )

        return "\n".join(parts)
