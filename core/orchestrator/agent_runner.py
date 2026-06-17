"""
Aethvion Suite - Agent Runner
Multi-step ReAct-style execution loop with persistent state.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, List, Dict, Any

from core.utils.logger import get_logger
from core.orchestrator.cancellation import is_agent_task_cancelled
from core.ai.call_contexts import CallSource
from core.utils.paths import CODE_AGENT_PROMPT
from core.orchestrator.workspace_tools import (
    build_workspace_blueprint,
    generate_file_digest, search_codebase, parse_dir_entries,
)
from core.orchestrator.agent_state import AgentState
from core.orchestrator.web_tools import fetch_url, search_web
from core.orchestrator.file_ops_mixin import FileOpsMixin

logger = get_logger(__name__)


from core.utils.paths import CODE_AGENT_PROMPT
from core.orchestrator.workspace_tools import (
    build_workspace_blueprint,
)
from core.orchestrator.agent_state import AgentState

# Safety backstop — effectively unlimited; the Stop button is the user's control.
MAX_ITERATIONS = 200

# System prompt
# Loaded from core/config/code/agent_system_prompt.txt at import time.
# Edit the .txt file directly — no Python changes needed.
SYSTEM_PROMPT: str = CODE_AGENT_PROMPT.read_text(encoding='utf-8')


class AgentRunner(FileOpsMixin):
    def __init__(
        self,
        task: str,
        workspace_path: str,
        step_callback: Callable[[Dict[str, Any]], None],
        model_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        state_path: Optional[Path] = None,
        images: Optional[List[Dict]] = None,
        nexus=None,        # Deprecated argument to prevent callers from crashing
        token_budget: Optional[int] = None,   # Max total tokens before stopping
        resume: bool = False,                  # Resume from saved checkpoint state
        workspace_id: Optional[str] = None,    # For project memory lookup
        memory_root: Optional[Path] = None,    # Root dir for project_memory.json
    ):
        self.task = task
        self.workspace = Path(workspace_path) if workspace_path else Path.cwd()
        from core.providers import get_provider_manager
        self.pm = get_provider_manager()
        self.step_callback = step_callback
        self.model_id = model_id
        self.trace_id = trace_id
        self.conversation: List[str] = []
        self.state = AgentState(state_path)
        # Subclasses override these to control per-prompt cost without touching run():
        #   _conv_window  — recent conversation entries to keep in each prompt
        self._conv_window: int = 16
        self._task_short: Optional[str] = None
        # there instead of into the user's project workspace.
        self._blueprint_cache_path: Optional[Path] = None
        # Token budget (None = unlimited). Checked before each LLM call.
        self._token_budget: Optional[int] = token_budget
        self._budget_warned: bool = False  # True after 80% warning fired once
        # Stall detection: track last iteration where mark_done was called.
        # If STALL_THRESHOLD iterations pass with a plan but no progress, warn.
        self._last_mark_done_iter: int = 0
        self._stall_warned: bool = False
        # Resume mode: keep the existing plan/notes/log instead of clearing them.
        self._resume: bool = resume
        if resume:
            # Preserve existing checkpoint state — don't wipe the plan.
            # file_cache and workspace_map are always kept across tasks.
            logger.info(f"[AgentRunner] Resume mode — reloading checkpoint: "
                        f"{len(self.state.plan)} plan steps, "
                        f"{sum(1 for s in self.state.plan if s.get('done'))} done")
        else:
            # Reset only per-task planning state between tasks.
            # file_cache and workspace_map are intentionally KEPT so the agent knows
            # which files it has already seen in this thread.
            self.state.plan = []
            self.state.action_log = []
            self.state.notes = []
        self._start_time = datetime.utcnow()
        self.run_input_tokens = 0
        self.run_output_tokens = 0
        # Images attached to this task — consumed on first LLM call only
        self._images: Optional[List[Dict]] = images or None
        self._images_sent: bool = False
        # Hard fetch limits enforced in code — the model cannot exceed these
        # regardless of what the prompt rules say, because conversation history
        # is bounded to 4 entries and the model forgets previous fetches/searches.
        self._search_count: int = 0
        self._search_cache: Dict[str, str] = {}   # query → result (dedup same query)
        self._fetch_cache: Dict[str, str] = {}    # url   → result (dedup same URL)
        self._read_cache: Dict[str, int] = {}     # "path:offset" → read count (dedup loops)
        # Repetition guard: track consecutive failed/no-progress actions per path.
        # Key = "type:path", value = consecutive count.  Reset on success.
        self._action_repeats: Dict[str, int] = {}
        # Dynamic replanning: count consecutive iterations that produced failures.
        # When this hits ≥ 2, inject a replanning suggestion.
        self._consecutive_failures: int = 0
        # Hard enforcement: paths whose last patch/write/append FAILED and have
        # not yet been resolved by a subsequent successful edit.
        # The `done` action is BLOCKED until this set is empty.
        self._unresolved_failures: set = set()
        # Project memory — workspace-level persistent rules/context/design/notes.
        # None when no workspace_id is provided (standalone / test runs).
        self._project_memory = None
        if workspace_id and memory_root:
            try:
                from core.orchestrator.project_memory import ProjectMemory
                self._project_memory = ProjectMemory(workspace_id, memory_root)
            except Exception as _pm_err:
                logger.warning("[AgentRunner] Could not load project memory: %s", _pm_err)

    # cache helpers

    def _invalidate_read_cache(self, path: str) -> None:
        """Remove all read-dedup entries for `path` so the agent can re-read
        it after a write/patch without being blocked by the duplicate guard."""
        keys = [k for k in list(self._read_cache) if k.startswith(path + ":") or k == path]
        for k in keys:
            del self._read_cache[k]

    # emit

    def _emit(self, event: Dict[str, Any]) -> None:
        self.step_callback(event)

    # LLM call

    def _render_conv_entry(self, entry: Any, current_turn: int) -> str:
        """Render one conversation entry, evicting stale large read_file payloads.

        Entries added by run() are dicts:
          {"role": "assistant", "text": "...", "turn": N}
          {"role": "user",      "results": ["action(p): ...", ...], "turn": N}

        Plain strings (pushback messages, legacy) are returned as-is.

        Eviction rule: read_file results older than _EVICT_AFTER turns AND larger
        than _EVICT_MIN_SIZE chars are replaced with a one-line stub.  The
        Knowledge block already has the file's structure; the model can re-read
        with an offset if it needs the raw content again.
        """
        _EVICT_AFTER    = 2    # rounds before evicting a stale read result
        _EVICT_MIN_SIZE = 400  # only evict results larger than this (chars)

        if isinstance(entry, str):
            return entry  # plain-string pushback / legacy format

        role = entry.get("role", "")
        if role == "assistant":
            return f"Assistant: {entry['text']}"

        # "user" results entry
        age = current_turn - entry.get("turn", 0)
        rendered: List[str] = []
        for r in entry.get("results", []):
            sep = r.find(": ")
            if sep == -1:
                rendered.append(r)
                continue
            action  = r[:sep]
            content = r[sep + 2:]
            if (
                action.startswith("read_file(")
                and age >= _EVICT_AFTER
                and len(content) > _EVICT_MIN_SIZE
            ):
                rendered.append(
                    f"{action}: [evicted — {len(content):,} chars; "
                    f"Knowledge block has structure, re-read with offset if content needed]"
                )
            else:
                rendered.append(r)

        header = entry.get("header", "User: Results:")
        suffix = entry.get("suffix", "\nKeep going until the task is fully complete.")
        return header + "\n" + "\n".join(rendered) + suffix

    def _build_prompt(self, current_turn: int = 0) -> str:
        """Mirror the exact format used by the working Code IDE (_messages_to_prompt):
        system + double-newline-separated 'User:' / 'Assistant:' blocks."""
        system = self._get_system_prompt()
        parts = [system]

        ctx = self.state.build_context(current_turn=current_turn)
        if ctx:
            parts.append(f"Context:\n{ctx}")

        # For iterations 1+ use a compact task reminder when _task_short is set.
        # Repeating 5k+ chars of memory/board/log on every call wastes tokens.
        if self._task_short and self.conversation:
            parts.append(f"User: {self._task_short}")
        else:
            parts.append(f"User: {self.task}")

        # Configurable conversation window — subclasses (e.g. CorpWorkerRunner)
        # can reduce this to cut token cost for focused single-file tasks.
        recent = self.conversation[-self._conv_window:]
        # Eviction-aware rendering: old read_file results are replaced with stubs
        parts.extend(self._render_conv_entry(e, current_turn) for e in recent)

        return "\n\n".join(parts)

    def _get_system_prompt(self) -> str:
        """Return the formatted system prompt. Subclasses override for a shorter version."""
        base = SYSTEM_PROMPT.format(
            workspace=str(self.workspace),
            current_date=datetime.utcnow().strftime("%B %d, %Y"),
        )
        # Prepend project memory block so workspace rules appear before all other
        # instructions — this ensures they are never overridden by later rules.
        if self._project_memory:
            mem_block = self._project_memory.get_injection_block()
            if mem_block:
                base = mem_block + "\n\n" + base
        return base

    def _call_llm(self, iteration: int = 0) -> str:
        """Use streaming — same path as the working Code IDE — for reliability."""
        prompt = self._build_prompt(current_turn=iteration)
        logger.info(f"[AgentRunner iter={iteration}] prompt_chars={len(prompt)}")

        # for the initial plan; subsequent iterations are text-only to save tokens
        call_images = None
        if self._images and not self._images_sent:
            call_images = self._images
            self._images_sent = True

        try:
            chunks: list[str] = []
            _llm_start = datetime.utcnow()
            for chunk in self.pm.call_with_failover_stream(
                prompt=prompt,
                trace_id=f"{self.trace_id}-i{iteration}",
                temperature=0.2,
                model=self.model_id,
                request_type="generation",
                source=CallSource.AGENT,
                max_tokens=32768,
                images=call_images,
            ):
                chunks.append(chunk)
                # Token-level streaming to UI
                # Emit each chunk immediately so the frontend Thoughts panel
                # shows the model "thinking" in real-time rather than waiting
                # for the entire LLM call to complete.
                if chunk:
                    self._emit({"type": "llm_token", "token": chunk})
            llm_elapsed = (datetime.utcnow() - _llm_start).total_seconds()
            full = "".join(chunks).strip()
            if not full:
                return "(LLM error: Provider returned empty response)"

            # Estimate token usage (~4 chars/token) and emit for the UI.
            # llm_elapsed_s is the actual streaming duration — used for accurate t/s
            # (excludes tool execution time that sits between LLM calls).
            est_in  = len(prompt) // 4
            est_out = len(full)   // 4
            self.run_input_tokens  += est_in
            self.run_output_tokens += est_out
            total       = self.run_input_tokens + self.run_output_tokens
            self._emit({
                "type":          "usage",
                "input_tokens":  est_in,
                "output_tokens": est_out,
                "run_input":     self.run_input_tokens,
                "run_output":    self.run_output_tokens,
                "run_total":     total,
                "llm_elapsed_s": round(llm_elapsed, 2),
                "tok_per_sec":   round(est_out / llm_elapsed, 1) if llm_elapsed > 0 else 0,
            })

            return full
        except Exception as e:
            logger.error(f"AgentRunner LLM call failed: {e}")
            return f"(Error calling LLM: {e})"

    # parsing

    def _parse_actions(self, text: str) -> List[Dict[str, Any]]:
        """Find every ACTION: {...} using raw_decode so nested braces are handled."""
        actions = []
        decoder = json.JSONDecoder()
        search_from = 0
        while True:
            idx = text.find("ACTION:", search_from)
            if idx == -1:
                break
            json_start = text.find("{", idx)
            if json_start == -1:
                break
            try:
                obj, json_end = decoder.raw_decode(text, json_start)
                if isinstance(obj, dict):
                    actions.append(obj)
                search_from = json_end  # raw_decode returns absolute index, not relative
            except json.JSONDecodeError:
                search_from = json_start + 1
        return actions

    def _thinking_text(self, text: str) -> str:
        idx = text.find("ACTION:")
        raw = text[:idx].strip() if idx != -1 else text.strip()
        return raw.strip()

    # tool execution


    # Action handlers

    def _handle_set_plan(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        steps = action.get("steps", [])
        # Phase transition: if a plan already exists this is a re-plan (e.g.
        # exploration → execution).  Evict all read-only files immediately so
        # template/reference files don't snowball into the execution phase.
        if self.state.plan:
            phase_evicted = self.state.evict_read_only_files()
            if phase_evicted:
                logger.info(
                    f"[AgentRunner iter={iteration}] Phase transition (new plan) → "
                    f"evicted {len(phase_evicted)} read-only file(s): {phase_evicted}"
                )
        self.state.set_plan(steps)
        return None  # state-only, not sent to LLM


    def _handle_mark_done(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        step = action.get("step", "")
        # Warn (but don't hard-block) if there are unresolved failures — the
        # step being marked done might be unrelated to the failed file, so we
        # let it proceed but append a reminder that `done` is still blocked.
        if self._unresolved_failures:
            failed_paths = ", ".join(sorted(self._unresolved_failures))
            self.state.mark_done(step)
            self._last_mark_done_iter = iteration
            self._stall_warned = False
            return (
                f"Step marked done. WARNING: done is still blocked because "
                f"{failed_paths} has an unresolved patch failure. Fix that file before calling done."
            )
        self.state.mark_done(step)
        self._last_mark_done_iter = iteration   # reset stall clock
        self._stall_warned = False               # allow re-warning after recovery
        return None  # state-only


    def _handle_evict_file(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        path = action.get("path", "")
        if not path:
            return "[evict_file] 'path' is required."
        success = self.state.evict_file(path)
        self.state.log_action(iteration, "evict_file", path)
        self._emit({"type": "thinking", "title": f"Evicted {path}", "detail": "Dropped from active context."})
        return (
            f"Evicted {path} from active context."
            if success
            else f"{path} was not in active context (already absent or never read)."
        )


    def _handle_distill_file_context(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        path    = action.get("path", "")
        summary = action.get("summary", "").strip()
        if not path:
            return "[distill_file_context] 'path' is required."
        if not summary:
            return "[distill_file_context] 'summary' is required — write compact notes about what you extracted."
        # Store the agent-authored summary in file_digests so it shows up in
        # the Knowledge block on every subsequent turn.  This replaces any
        # auto-generated digest for that file (agent notes are more precise).
        digest_entry = f"{path} [distilled]: {summary}"
        self.state.update_file_digest(path, digest_entry)
        was_cached = self.state.evict_file(path)
        self.state.log_action(iteration, "distill_file_context", path)
        self._emit({
            "type": "thinking",
            "title": f"Distilled {path}",
            "detail": summary[:120] + ("…" if len(summary) > 120 else ""),
        })
        evict_note = " Raw content evicted." if was_cached else " (was not in active context)"
        return f"Distilled {path} → stored in Knowledge block.{evict_note}"


    def _handle_add_note(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        note = action.get("note", "")
        self.state.add_note(note)
        return None  # state-only


    def _handle_respond(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        # Send a visible message to the user in the main chat panel.
        # Use this for suggestions, ideas, answers, status updates — anything
        # the user should see. Thinking text before ACTION: lines only goes to
        # the Thoughts side panel.
        message = action.get("message", "").strip()
        if not message:
            return "[respond] 'message' is required."
        self._emit({
            "type":    "agent_response",
            "content": message,
        })
        self.state.log_action(iteration, "respond", message[:60])
        return "Message sent to user."


    def _handle_observe(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        # Observation action — purely informational, emitted to the UI.
        content = action.get("content", "")
        self.state.log_action(iteration, "observe", content[:60])
        return content  # returned to LLM as confirmation


    def _handle_patch_file(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        path = action.get("path", "")
        old  = action.get("old", "")
        new  = action.get("new", "")
        repeat_key = f"patch_file:{path}:{old[:60]}"
        self._action_repeats[repeat_key] = self._action_repeats.get(repeat_key, 0) + 1
        attempt = self._action_repeats[repeat_key]

        had_backup = self._backup_file(path)
        result = self._patch_file(path, old, new)
        self.state.log_action(iteration, "patch_file", path)

        if result.startswith("patch_file FAILED"):
            # Track as an unresolved failure — blocks `done` until fixed.
            self._unresolved_failures.add(path)
            # Emit a dedicated patch_failed event so the main chat activity
            # area shows a visible red card (the thinking event only goes to
            # the Thoughts side panel and is invisible to most users).
            self._emit({
                "type":   "patch_failed",
                "path":   path,
                "title":  f"⚠ Patch failed — {path}",
                "detail": "Content mismatch — the agent will re-read and retry.",
            })
            # Also emit to Thoughts panel for detailed context
            self._emit({
                "type":   "thinking",
                "title":  f"⚠ Patch failed — {path}",
                "detail": (
                    f"All whitespace strategies failed. "
                    f"The agent will re-read the file and retry."
                ),
            })
            # Hard enforcement note appended to the result so the LLM sees it.
            result += (
                f"\n[ENFORCEMENT: {path} has an unresolved patch failure. "
                f"You CANNOT call done or mark_done until this is fixed. "
                f"Re-read {path} and retry the patch with the exact current text.]"
            )
            # Soft nudge on repeated failed patches
            if attempt >= 2:
                result += (
                    f"\n[NOTE: Attempt {attempt} with the same 'old' string. "
                    f"Use read_file to get the exact current content of {path}. "
                    f"Or use write_file / append_file as an alternative.]"
                )
        else:
            # Patch succeeded — remove from unresolved failures if it was there.
            self._unresolved_failures.discard(path)
            import difflib as _dl
            _diff_lines = list(_dl.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"a/{path}", tofile=f"b/{path}", n=2,
            ))
            _diff_str = "".join(_diff_lines)[:2500]
            self._emit({
                "type":       "write_file",
                "path":       path,
                "detail":     f"patch: {len(old):,}→{len(new):,} chars",
                "diff":       _diff_str,
                "has_backup": had_backup,
            })
            # Successful patch — reset the repeat counter and clear read dedup
            self._action_repeats.pop(repeat_key, None)
            self._invalidate_read_cache(path)
            # Mark as modified so phase-eviction doesn't drop it
            existing_size = self.state.file_cache.get(path, {}).get("size", 0)
            self.state.cache_file(path, existing_size, turn=iteration, modified=True)
            # Update digest to reflect the change
            try:
                fp = self.workspace / path
                full = fp.read_text(encoding="utf-8", errors="replace")
                summary = f"patched ({len(old)}→{len(new)} chars)"
                digest = generate_file_digest(path, full, last_action=summary)
                self.state.update_file_digest(path, digest)
            except Exception:
                pass
        return result


    def _handle_append_file(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        path    = action.get("path", "")
        content = action.get("content", "")
        result  = self._append_file(path, content)
        self.state.log_action(iteration, "append_file", path)
        self._emit({"type": "write_file", "path": path, "detail": f"append: {len(content)} chars"})
        self._invalidate_read_cache(path)
        if not result.startswith("Error:"):
            # Successful append resolves any prior patch failure on this file.
            self._unresolved_failures.discard(path)
            # Mark as modified so phase-eviction doesn't drop it
            existing_size = self.state.file_cache.get(path, {}).get("size", 0)
            self.state.cache_file(path, existing_size, turn=iteration, modified=True)
            try:
                fp = self.workspace / path
                full = fp.read_text(encoding="utf-8", errors="replace")
                digest = generate_file_digest(path, full, last_action=f"appended {len(content)} chars")
                self.state.update_file_digest(path, digest)
            except Exception:
                pass
        return result


    def _handle_write_file(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        path = action.get("path", "")
        content = action.get("content", "")
        self._backup_file(path)
        result = self._write_file(path, content)
        self.state.cache_file(path, len(content.encode()), turn=iteration, modified=True)
        self.state.log_action(iteration, "write_file", path)
        # File was written — clear its read-dedup entries.
        self._invalidate_read_cache(path)
        # Generate digest for the newly written content
        if not result.startswith("Error:"):
            # Successful write resolves any prior patch failure on this file.
            self._unresolved_failures.discard(path)
            try:
                digest = generate_file_digest(path, content, last_action="written")
                self.state.update_file_digest(path, digest)
            except Exception:
                pass
        return result


    def _handle_delete_file(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        path = action.get("path", "")
        self._backup_file(path)
        result = self._delete_file(path)
        # Remove from state caches on success
        if not result.startswith("Error:") and not result.startswith("Not found:"):
            self.state.file_cache.pop(path, None)
            if path in self.state.workspace_map:
                self.state.workspace_map.remove(path)
        self.state.log_action(iteration, "delete_file", path)
        return result


    def _handle_read_file(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        path   = action.get("path", "")
        offset = int(action.get("offset", 0))   # line offset (0 = start)
        limit  = action.get("limit")            # max lines to return (None = all)
        limit  = int(limit) if limit is not None else None

        # Track reads per section for the nudge system — no hard blocks.
        # Bucket offsets into 100-line windows so offset=0 and offset=10 are treated
        # identically.
        bucket    = (offset // 100) * 100
        cache_key = f"{path}:{bucket}"
        self._read_cache[cache_key] = self._read_cache.get(cache_key, 0) + 1
        read_count = self._read_cache[cache_key]

        result = self._read_file(path, offset=offset, limit=limit)
        # Cache with actual byte size of result if successful
        if not result.startswith("Error:") and not result.startswith("Not found:"):
            self.state.cache_file(path, len(result.encode()), turn=iteration)
            # Generate / refresh semantic digest on a full read (offset=0).
            # This populates the Knowledge block so subsequent iterations don't
            if offset == 0:
                try:
                    fp = self.workspace / path
                    full = fp.read_text(encoding="utf-8", errors="replace")
                    digest = generate_file_digest(path, full)
                    self.state.update_file_digest(path, digest)
                except Exception:
                    pass
            # Soft nudge after repeated reads of the same section — never block,
            # just remind the agent that the Knowledge block has the structure.
            if read_count >= 3:
                nudge = (
                    f"\n\n[NOTE: You have read this section of {path} {read_count} times. "
                    f"The Knowledge block in Context already lists all functions with line "
                    f"numbers — check it before reading again. If you have the content you "
                    f"need, write your patch now.]"
                )
                result = result + nudge
        suffix = f"@{offset}" if offset else ""
        self.state.log_action(iteration, "read_file", f"{path}{suffix}")
        return result


    def _handle_list_dir(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        path = action.get("path", "")
        result = self._list_dir(path)
        # Parse flat filenames from result to update workspace map
        if result and result != "(empty)" and not result.startswith("Error:"):
            entries = parse_dir_entries(result)
            if entries:
                self.state.update_workspace_map(entries)
        self.state.log_action(iteration, "list_dir", path or ".")
        return result


    def _handle_restore_file(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        path = action.get("path", "")
        if not path:
            return "[restore_file] 'path' is required."
        result = self._restore_file(path)
        self.state.log_action(iteration, "restore_file", path)
        if not result.startswith("Error:") and not result.startswith("No backup"):
            self._invalidate_read_cache(path)
        return result


    def _handle_run_command(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        cmd     = action.get("command", "")
        timeout = int(action.get("timeout", 120))
        result  = self._run_command(cmd, timeout=timeout)
        short_cmd = cmd[:40] if len(cmd) > 40 else cmd
        self.state.log_action(iteration, "run_command", short_cmd)
        return result


    def _handle_glob(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        pattern  = action.get("pattern", "**/*")
        sub_path = action.get("path", "")
        result = self._glob(pattern, sub_path)
        self.state.log_action(iteration, "glob", pattern)
        return result


    def _handle_move_file(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        src = action.get("src", "")
        dst = action.get("dst", "")
        result = self._move_file(src, dst)
        self.state.log_action(iteration, "move_file", f"{src}→{dst}")
        return result


    def _handle_create_directory(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        path = action.get("path", "")
        result = self._create_directory(path)
        self.state.log_action(iteration, "create_directory", path)
        return result


    def _handle_search_web(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        query = action.get("query", "")
        max_results = int(action.get("max_results", 6))
        # Hard limit: max 3 searches per task, enforced in code
        if self._search_count >= 3:
            return (
                "[SEARCH BLOCKED: you have already used all 3 search calls for this task. "
                "You MUST now use fetch_url with a specific URL, or write the output "
                "using the best information you already have. Do NOT search again.]"
            )
        # Dedup: never run the exact same query twice
        if query in self._search_cache:
            cached = self._search_cache[query]
            return f"[DUPLICATE SEARCH — returning cached result]\n{cached}"
        self._search_count += 1
        result = search_web(query, max_results)
        self._search_cache[query] = result
        self.state.log_action(iteration, "search_web", query[:40])
        return result


    def _handle_fetch_url(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        url = action.get("url", "")
        # Dedup: never fetch the same URL twice — return cached result instantly.
        # This breaks the most common runaway loop: the model forgets it already
        # fetched a URL (conversation window is only 4 entries) and retries it.
        if url in self._fetch_cache:
            cached = self._fetch_cache[url]
            return (
                f"[DUPLICATE FETCH — you already fetched this URL. "
                f"Use the data from the cached result below and write your files now.]\n{cached}"
            )
        result = fetch_url(url)
        # Only cache successful responses — never cache 429/5xx errors so
        # the agent can retry after a rate-limit window passes.
        if not result.startswith("HTTP 429") and not result.startswith("HTTP 5"):
            self._fetch_cache[url] = result
        self.state.log_action(iteration, "fetch_url", url[:40])
        return result


    def _handle_get_project_blueprint(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        sub_path = action.get("path", "")
        result = build_workspace_blueprint(
            self.workspace, sub_path, cache_path=self._blueprint_cache_path
        )
        self.state.log_action(iteration, "get_project_blueprint", sub_path or "workspace")
        return result


    def _handle_search_codebase(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        query = action.get("query", "")
        path  = action.get("path", "")
        ctx   = int(action.get("context", 1))
        max_r = int(action.get("max_results", 30))
        if not query:
            return "[search_codebase] 'query' is required."
        result = search_codebase(self.workspace, query, path, ctx, max_r)
        self.state.log_action(iteration, "search_codebase", query[:40])
        self._emit({"type": "read_file", "path": path or "workspace", "detail": f"search: {query[:40]}"})
        return result


    def _handle_save_to_project_memory(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        if not self._project_memory:
            return "[save_to_project_memory] No project memory available for this workspace."
        from core.orchestrator.project_memory import CATEGORY_META
        category = action.get("category", "note")
        text     = action.get("text")
        title    = action.get("title")
        raw_items = action.get("items", [])
        # Convert plain string list to checklist item dicts
        if raw_items and isinstance(raw_items[0], str):
            raw_items = [{"id": __import__("uuid").uuid4().hex[:8], "text": t, "done": False}
                         for t in raw_items]
        item = self._project_memory.add_item(
            category=category, text=text, title=title,
            items=raw_items if raw_items else None, source="agent",
        )
        meta = CATEGORY_META.get(category, {"icon": "📝", "label": category.title()})
        display = text or title or f"{len(raw_items)} items"
        self._emit({
            "type":     "project_memory_item",
            "action":   "added",
            "category": category,
            "icon":     meta["icon"],
            "label":    meta["label"],
            "text":     display,
            "item":     item,
            "title":    f"{meta['icon']} Saved to Project Memory",
            "detail":   f"[{meta['label']}] {display}",
        })
        self.state.log_action(iteration, "save_to_project_memory", f"{category}: {display[:40]}")
        return f"Saved to project memory — [{category}] {display}"


    def _handle_check_checklist_item(
        self, action: Dict[str, Any], iteration: int
    ) -> Optional[str]:
        if not self._project_memory:
            return "[check_checklist_item] No project memory available."
        checklist_id = action.get("checklist_id", "")
        item_id      = action.get("item_id", "")
        done         = bool(action.get("done", True))
        ok = self._project_memory.update_checklist_item(checklist_id, item_id, done)
        if ok:
            state_str = "done" if done else "undone"
            self._emit({
                "type":          "project_memory_item",
                "action":        "checklist_updated",
                "checklist_id":  checklist_id,
                "item_id":       item_id,
                "done":          done,
                "title":         "📋 Checklist updated",
                "detail":        f"Item marked {state_str}",
            })
            return f"Checklist item marked {state_str}."
        return f"[check_checklist_item] Item not found (checklist_id={checklist_id!r}, item_id={item_id!r})."


    _HANDLER_MAP = {
        "set_plan": "_handle_set_plan",
        "mark_done": "_handle_mark_done",
        "evict_file": "_handle_evict_file",
        "distill_file_context": "_handle_distill_file_context",
        "add_note": "_handle_add_note",
        "respond": "_handle_respond",
        "observe": "_handle_observe",
        "patch_file": "_handle_patch_file",
        "append_file": "_handle_append_file",
        "write_file": "_handle_write_file",
        "delete_file": "_handle_delete_file",
        "read_file": "_handle_read_file",
        "list_dir": "_handle_list_dir",
        "restore_file": "_handle_restore_file",
        "run_command": "_handle_run_command",
        "glob": "_handle_glob",
        "move_file": "_handle_move_file",
        "create_directory": "_handle_create_directory",
        "search_web": "_handle_search_web",
        "fetch_url": "_handle_fetch_url",
        "get_project_blueprint": "_handle_get_project_blueprint",
        "search_codebase": "_handle_search_codebase",
        "save_to_project_memory": "_handle_save_to_project_memory",
        "check_checklist_item": "_handle_check_checklist_item",
    }

    def _execute(self, action: Dict[str, Any], iteration: int = 0) -> Optional[str]:
        """Execute an action. Returns result string, or None for state-only actions."""
        t = action.get("type", "")
        handler_name = self._HANDLER_MAP.get(t)
        if handler_name is None:
            return f"Unknown action: {t}"
        return getattr(self, handler_name)(action, iteration)

    def _make_event(self, action: Dict[str, Any]) -> Dict[str, Any]:
        t = action.get("type", "")
        path = action.get("path", "")
        cmd = action.get("command", "")
        content = action.get("content", "")

        if t == "set_plan":
            steps = action.get("steps", [])
            return {"type": "thinking", "title": "Planning (set_plan)",
                    "detail": "\n".join(f"  - {s}" for s in steps)}

        if t == "mark_done":
            step = action.get("step", "")
            return {"type": "thinking", "title": "Planning (mark_done)",
                    "detail": f"Marked done: {step}"}

        if t == "add_note":
            note = action.get("note", "")
            return {"type": "thinking", "title": "Planning (add_note)",
                    "detail": note}

        if t == "observe":
            obs_content = action.get("content", "")
            return {"type": "observe", "title": "Observation", "detail": obs_content}

        if t == "write_file":
            fp_exists = (self.workspace / path).is_file()
            preview   = content[:400] + ("\u2026" if len(content) > 400 else "")
            diff_str  = self._compute_write_diff(path, content)
            return {"type": t, "title": f"Writing {path}", "path": path,
                    "detail": preview, "bytes": len(content.encode()),
                    "diff": diff_str, "has_backup": fp_exists}

        if t == "delete_file":
            fp_exists = (self.workspace / path).is_file()
            return {"type": "delete_file", "title": f"Deleting {path}", "path": path,
                    "detail": "", "has_backup": fp_exists}

        if t == "restore_file":
            return {"type": "restore_file", "title": f"Restoring {path}", "path": path, "detail": ""}

        if t == "read_file":
            return {"type": t, "title": f"Reading {path}", "path": path, "detail": ""}

        if t == "list_dir":
            return {"type": t, "title": f"Listing {path or 'workspace'}", "path": path, "detail": ""}

        if t == "run_command":
            return {"type": t, "title": f"$ {cmd[:80]}", "command": cmd, "detail": ""}

        if t == "glob":
            pattern = action.get("pattern", "")
            return {"type": t, "title": f"Glob: {pattern}", "pattern": pattern,
                    "path": path, "detail": ""}

        if t == "move_file":
            src = action.get("src", "")
            dst = action.get("dst", "")
            return {"type": t, "title": f"Move: {src} → {dst}", "src": src, "dst": dst, "detail": ""}

        if t == "create_directory":
            return {"type": t, "title": f"mkdir: {path}", "path": path, "detail": ""}

        if t == "search_web":
            query = action.get("query", "")
            return {"type": t, "title": f"Search: {query}", "query": query, "detail": ""}

        if t == "fetch_url":
            url = action.get("url", "")
            return {"type": "fetch_url", "title": f"Fetch: {url}", "url": url, "detail": ""}

        if t == "get_project_blueprint":
            sub = action.get("path", "")
            label = f"Blueprint: {sub}/" if sub else "Blueprint scan"
            return {"type": t, "title": label, "path": sub, "detail": ""}

        if t == "search_codebase":
            query = action.get("query", "")
            spath = action.get("path", "")
            label = f"Search: {query}" + (f" in {spath}" if spath else "")
            return {"type": t, "title": label, "query": query, "path": spath, "detail": ""}

        return {"type": t, "title": t, "detail": str(action)}

    # main loop

    # Iterations without a mark_done (with an active plan) before emitting a stall warning.
    _STALL_THRESHOLD = 8

    def run(self) -> str:
        self._emit({"type": "start", "title": "Starting task", "detail": self.task})

        # Resume: inject context so the agent knows it's continuing
        if self._resume and self.state.plan:
            incomplete = [s["text"] for s in self.state.plan if not s.get("done")]
            done_count = sum(1 for s in self.state.plan if s.get("done"))
            total = len(self.state.plan)
            resume_msg = (
                f"[System: Resuming from checkpoint — {done_count}/{total} steps completed. "
                f"Your plan is already loaded. Continue from the first incomplete step: "
                f"{incomplete[0] if incomplete else '(all done?)'}. "
                f"Do NOT call set_plan again unless the approach has changed.]"
            )
            self.conversation.append(resume_msg)
            self._emit({
                "type": "thinking",
                "title": "Resuming from checkpoint",
                "detail": f"{done_count}/{total} steps already done. Continuing from: {incomplete[0] if incomplete else '—'}",
            })
            # Stall clock starts at 0 so resume gets a full fresh window
            self._last_mark_done_iter = 0

        for iteration in range(MAX_ITERATIONS):
            # Token budget check (before LLM call)
            if self._token_budget is not None:
                used = self.run_input_tokens + self.run_output_tokens
                pct = used / self._token_budget
                if pct >= 1.0:
                    summary = (
                        f"Token budget of {self._token_budget:,} reached "
                        f"({used:,} tokens used). Task stopped to prevent overrun."
                    )
                    self._emit({
                        "type": "budget_exceeded",
                        "title": "Token budget reached",
                        "detail": summary,
                        "used": used,
                        "budget": self._token_budget,
                    })
                    self.state.record_task(self.task, f"[budget] {summary}")
                    self.state.save()
                    return summary
                elif pct >= 0.8 and not self._budget_warned:
                    self._budget_warned = True
                    self._emit({
                        "type": "budget_warning",
                        "title": "Approaching token budget",
                        "detail": f"{used:,} / {self._token_budget:,} tokens used ({int(pct*100)}%). Wrapping up soon.",
                        "used": used,
                        "budget": self._token_budget,
                        "pct": int(pct * 100),
                    })

            # Evict file_cache entries that haven't been accessed in the last 2 turns.
            # Files stay in workspace_map and file_digests — only the '(cached)' marker
            if iteration > 0:
                evicted = self.state.evict_stale_cache(current_turn=iteration)
                if evicted:
                    logger.debug(
                        f"[AgentRunner iter={iteration}] Cache-evicted {len(evicted)} idle file(s): "
                        + ", ".join(evicted)
                    )

            # Check for user-requested stop (sent via POST /api/tasks/{id}/cancel)
            if self.trace_id and is_agent_task_cancelled(self.trace_id):
                summary = "Task stopped by user."
                self._emit({"type": "done", "title": "Stopped", "detail": summary})
                self.state.record_task(self.task, f"[stopped] {summary}")
                self.state.save()
                return summary

            response = self._call_llm(iteration)

            thinking = self._thinking_text(response)
            if thinking:
                self._emit({
                    "type": "thinking",
                    "title": "Planning" if iteration == 0 else "Continuing",
                    "detail": thinking,
                })

            actions = self._parse_actions(response)

            if not actions:
                # No ACTION: lines in the response.
                # If the plan still has incomplete steps, this is likely a confused
                # mid-task response (e.g. the model wrote JSON in thinking text instead
                # of as an ACTION). Push back rather than auto-completing.
                incomplete = [s["text"] for s in self.state.plan if not s.get("done")]
                if incomplete:
                    self.conversation.append(
                        f"Assistant: {thinking or '(no actions)'}"
                    )
                    self.conversation.append(
                        "User: Your plan still has incomplete steps: "
                        + "; ".join(incomplete)
                        + ". Do NOT call done yet. Read the file if you need the current content, "
                        "then execute the remaining patches as ACTION: lines."
                    )
                    if len(self.conversation) > 16:
                        self.conversation = self.conversation[-16:]
                    continue
                self._emit({"type": "done", "title": "Complete", "detail": thinking or response})
                self.state.save()
                return thinking or response

            results: List[str] = []
            done_triggered = False
            done_summary = ""
            compact_actions: List[str] = []

            for action in actions:
                action_type = action.get("type", "")

                if action_type == "done":
                    # Hard enforcement gate
                    # Block `done` if any file still has an unresolved patch/write
                    # failure.  The agent claimed completion without actually fixing
                    # the file — force it to go back and repair.
                    if self._unresolved_failures:
                        failed_paths = ", ".join(sorted(self._unresolved_failures))
                        block_msg = (
                            f"[BLOCKED: cannot call done — unresolved edit failure(s) on: {failed_paths}. "
                            f"Re-read each file, verify the current content, and retry the edit. "
                            f"Only call done after a successful patch_file, write_file, or append_file "
                            f"on every failed path.]"
                        )
                        logger.warning(
                            f"[AgentRunner iter={iteration}] `done` blocked — "
                            f"unresolved failures: {failed_paths}"
                        )
                        self._emit({
                            "type":   "thinking",
                            "title":  f"⛔ done blocked — unresolved failures",
                            "detail": f"Agent tried to call done while {failed_paths} still has an unresolved patch failure. Forcing retry.",
                        })
                        results.append(f"done(): {block_msg}")
                        compact_actions.append("done(BLOCKED)")
                        # Don't set done_triggered — loop continues
                        continue

                    done_summary = action.get("summary", "Task complete.")
                    done_triggered = True
                    break

                # Emit event first (before executing so UI updates immediately)
                event = self._make_event(action)
                # Error-recovery wrapper
                # Catch unexpected exceptions inside _execute so a single bad
                # action doesn't terminate the entire task.  The error is fed
                # back to the LLM as a result string so it can self-correct.
                try:
                    result = self._execute(action, iteration)
                except Exception as exc:
                    logger.error(
                        f"[AgentRunner iter={iteration}] _execute raised: {exc}",
                        exc_info=True,
                    )
                    result = f"Error: action '{action.get('type', '?')}' raised exception: {exc}"
                    self._emit({
                        "type":   "thinking",
                        "title":  "⚠ Internal error — recovered",
                        "detail": str(exc),
                    })

                if result is None:
                    # State-only action — emit thinking event, skip LLM result
                    self._emit(event)
                    self.state.save()
                    continue

                event["result"] = result
                self._emit(event)
                self.state.save()

                path = action.get("path", "")
                cmd = action.get("command", "")
                short = path or (cmd[:30] if cmd else "")
                # Cap large results stored in conversation history.
                # 8k is enough to cover most individual functions the agent will need
                # to patch, while avoiding the full 50k file repeated every iteration.
                # The Knowledge block (in Context) carries structural info across iterations;
                # raw history carries the exact content needed for the next patch.
                MAX_HIST = 8_000
                hist_result = (
                    result if len(result) <= MAX_HIST
                    else result[:MAX_HIST]
                    + f"\n…[{len(result):,} chars total — see Knowledge block for full structure, "
                    f"or re-read with a specific offset for more content]"
                )
                results.append(f"{action_type}({short}): {hist_result}")
                compact_actions.append(f"{action_type}({short})")

            if done_triggered:
                # Use the pre-action thinking text as the detail (it's the actual answer).
                # Fall back to done_summary only when no thinking text was generated.
                result_detail = thinking or done_summary
                self._emit({"type": "done", "title": "Complete", "detail": result_detail})
                self.state.record_task(self.task, result_detail)
                self.state.save()
                return result_detail

            # Store as structured dicts so _render_conv_entry can evict stale
            # read_file payloads when building prompts in later iterations.
            agent_line = thinking or "(working)"
            if compact_actions:
                agent_line += "\nDid: " + ", ".join(compact_actions)
            self.conversation.append(
                {"role": "assistant", "text": agent_line, "turn": iteration}
            )
            if results:
                # Targeted recovery suffix
                # When one or more actions failed, replace the generic "keep
                # going" nudge with a focused repair instruction so the LLM
                # addresses the failure rather than blindly continuing.
                has_failure = any(
                    "patch_file FAILED" in r
                    or "FAILED:" in r
                    or r.split("): ", 1)[-1].strip().startswith("(exit ")
                    for r in results
                )
                if has_failure:
                    suffix = (
                        "\n⚠ One or more actions failed (see above). "
                        "Analyse each failure:\n"
                        "- patch_file FAILED → re-read that file section, use exact current text, then retry.\n"
                        "- (exit N) command → read the error output, fix the root cause, then retry.\n"
                        "- Error: ... → read the message, correct your approach.\n"
                        "Do NOT call done until every failure is resolved."
                    )
                else:
                    suffix = "\nKeep going until the task is fully complete."

                self.conversation.append({
                    "role":    "user",
                    "results": results,   # List[str] — each "action(path): content"
                    "turn":    iteration,
                    "header":  "User: Results:",
                    "suffix":  suffix,
                })
            # Dynamic replanning
            if has_failure:
                self._consecutive_failures += 1
                if self._consecutive_failures >= 2:
                    incomplete = [s["text"] for s in self.state.plan if not s.get("done")]
                    if incomplete:
                        self.conversation.append(
                            f"User: [Auto-recovery note] {self._consecutive_failures} consecutive "
                            f"failure rounds. If the current approach isn't working, call set_plan "
                            f"to revise your strategy — the plan may need a different approach."
                        )
                        self._emit({
                            "type":   "thinking",
                            "title":  "⚠ Dynamic replan suggested",
                            "detail": f"{self._consecutive_failures} consecutive failures — agent nudged to reconsider plan.",
                        })
            else:
                self._consecutive_failures = 0

            # Stall detection
            # If the agent has an active plan but hasn't marked any step done
            # in _STALL_THRESHOLD iterations, emit a warning once.
            iters_since_progress = iteration - self._last_mark_done_iter
            has_incomplete_plan = self.state.plan and any(not s.get("done") for s in self.state.plan)
            if (
                has_incomplete_plan
                and iters_since_progress >= self._STALL_THRESHOLD
                and not self._stall_warned
            ):
                self._stall_warned = True
                incomplete = [s["text"] for s in self.state.plan if not s.get("done")]
                self._emit({
                    "type": "stall_warning",
                    "title": "Agent may be stuck",
                    "detail": (
                        f"No plan progress in {iters_since_progress} steps. "
                        f"Remaining: {', '.join(incomplete[:3])}"
                        + (f" (+{len(incomplete)-3} more)" if len(incomplete) > 3 else "")
                    ),
                    "iterations_since_progress": iters_since_progress,
                    "incomplete_steps": incomplete,
                })

            # Keep conversation bounded to last 16 entries (8 round-trips).
            # When trimming, prepend a context note so the model knows history
            # was pruned — the Knowledge block and plan carry full task state.
            if len(self.conversation) > 16:
                n_pruned = len(self.conversation) - 14
                self.conversation = self.conversation[-14:]
                self.conversation.insert(0,
                    f"[System: {n_pruned} earlier conversation turn(s) trimmed. "
                    f"The Knowledge block and plan above preserve all task state.]"
                )

        summary = f"Reached {MAX_ITERATIONS} action limit."
        self._emit({"type": "done", "title": "Stopped (limit)", "detail": summary})
        self.state.record_task(self.task, f"[incomplete — hit limit] {summary}")
        self.state.save()
        return summary
