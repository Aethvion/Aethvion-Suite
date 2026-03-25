"""Agent Runner — multi-step ReAct-style execution loop with persistent state."""
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, List, Dict, Any

from core.utils.logger import get_logger

logger = get_logger(__name__)

MAX_ITERATIONS = 20

SYSTEM_PROMPT = """\
You are an expert software engineer completing coding tasks efficiently.

Working directory: {workspace}

HOW TO TAKE ACTIONS (write ACTION: followed by JSON, multiple per response allowed):

ACTION: {{"type": "write_file", "path": "relative/path.txt", "content": "FULL file content here"}}
ACTION: {{"type": "read_file", "path": "relative/file.txt"}}
ACTION: {{"type": "list_dir", "path": ""}}
ACTION: {{"type": "run_command", "command": "npm install"}}
ACTION: {{"type": "search_web", "query": "your search query", "max_results": 6}}
ACTION: {{"type": "fetch_url", "url": "https://api.github.com/repos/owner/repo"}}
ACTION: {{"type": "set_plan", "steps": ["step 1", "step 2", "step 3"]}}
ACTION: {{"type": "mark_done", "step": "exact step text"}}  ← call this AFTER the real action succeeds, never instead of it
ACTION: {{"type": "add_note", "note": "important context to remember"}}
ACTION: {{"type": "done", "summary": "brief summary of what was accomplished"}}

EFFICIENCY RULES:
1. Write REAL, COMPLETE file content — never stubs or placeholders.
2. WORKSPACE STATE (shown below) lists all known files. Files marked [cached] have known content — do NOT re-read them unless you need to modify them.
3. Start complex tasks with set_plan. Call mark_done only AFTER the real action for that step has executed and returned a result — mark_done does NOT create files or run code, it is a tracker only.
4. Batch multiple ACTION lines per response to minimize round-trips.
5. You have up to {max_iterations} actions — be strategic.
6. For internet research use search_web. For fetching a specific URL or API (e.g. GitHub API, JSON endpoints) use fetch_url. NEVER use curl, wget, or write scripts to fetch web data.
7. Do NOT repeat the same search more than twice. If a search doesn't give you the exact data you need, use fetch_url with a known API URL or proceed with the best available information — never loop on searches.
8. Write ALL deliverable files (reports, analysis, code output) BEFORE writing or running any verification/test scripts. A script that checks a file's existence must run AFTER that file is written.
9. Before calling done, check your plan — every [ ] step must have a corresponding write_file or run_command result in this conversation. If any step is unmarked, complete it first.
"""


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

        self._load()

    # ── persistence ───────────────────────────────────────────────

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
            }
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[AgentState] Could not save state to {self.state_path}: {e}")

    # ── file cache ────────────────────────────────────────────────

    def is_cached(self, path: str) -> bool:
        return path in self.file_cache

    def cache_file(self, path: str, size: int) -> None:
        self.file_cache[path] = {
            "size": size,
            "cached_at": datetime.utcnow().isoformat(),
        }
        if path not in self.workspace_map:
            self.workspace_map.append(path)

    def update_workspace_map(self, entries: List[str]) -> None:
        """Replace workspace_map with entries from list_dir, evicting stale cache."""
        self.workspace_map = list(entries)
        stale = [p for p in list(self.file_cache.keys()) if p not in entries]
        for p in stale:
            del self.file_cache[p]

    # ── plan ──────────────────────────────────────────────────────

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

    # ── notes ─────────────────────────────────────────────────────

    def add_note(self, note: str) -> None:
        self.notes.append(note)
        if len(self.notes) > self._MAX_NOTES:
            self.notes = self.notes[-self._MAX_NOTES:]

    # ── action log ────────────────────────────────────────────────

    def log_action(self, iteration: int, action_type: str, detail: str) -> None:
        self.action_log.append({
            "i": iteration,
            "type": action_type,
            "detail": detail,
            "at": datetime.utcnow().isoformat(),
        })
        if len(self.action_log) > self._MAX_LOG:
            self.action_log = self.action_log[-self._MAX_LOG:]

    # ── context builder ───────────────────────────────────────────

    def build_context(self) -> str:
        """Return a compact context string injected into every prompt."""
        parts: List[str] = []

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

        # Recent actions
        if self.action_log:
            recent = self.action_log[-6:]
            tokens = [f"{e['type']}({e['detail']})" for e in recent]
            parts.append("Recent: " + ", ".join(tokens))

        return "\n".join(parts)


class AgentRunner:
    def __init__(
        self,
        task: str,
        workspace_path: str,
        nexus,
        step_callback: Callable[[Dict[str, Any]], None],
        model_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        state_path: Optional[Path] = None,
        images: Optional[List[Dict]] = None,
    ):
        self.task = task
        self.workspace = Path(workspace_path) if workspace_path else Path.cwd()
        self.nexus = nexus
        self.step_callback = step_callback
        self.model_id = model_id
        self.trace_id = trace_id
        self.conversation: List[str] = []
        self.state = AgentState(state_path)
        self._start_time = datetime.utcnow()
        self.run_input_tokens = 0
        self.run_output_tokens = 0
        # Images attached to this task — consumed on first LLM call only
        self._images: Optional[List[Dict]] = images or None
        self._images_sent: bool = False

    # ── emit ──────────────────────────────────────────────────────

    def _emit(self, event: Dict[str, Any]) -> None:
        self.step_callback(event)

    # ── LLM call ──────────────────────────────────────────────────

    def _build_prompt(self) -> str:
        """Mirror the exact format used by the working Code IDE (_messages_to_prompt):
        system + double-newline-separated 'User:' / 'Assistant:' blocks."""
        system = SYSTEM_PROMPT.format(
            workspace=str(self.workspace),
            max_iterations=MAX_ITERATIONS,
        )
        parts = [system]

        ctx = self.state.build_context()
        if ctx:
            parts.append(f"Context:\n{ctx}")

        parts.append(f"User: {self.task}")

        # Last 4 conversation entries (2 round-trips) stored as role-prefixed blocks
        recent = self.conversation[-4:] if len(self.conversation) > 4 else self.conversation
        parts.extend(recent)

        return "\n\n".join(parts)

    def _call_llm(self, iteration: int = 0) -> str:
        """Use streaming — same path as the working Code IDE — for reliability."""
        prompt = self._build_prompt()
        logger.info(f"[AgentRunner iter={iteration}] prompt_chars={len(prompt)}")

        # Pass images only on the first LLM call so vision context is available
        # for the initial plan; subsequent iterations are text-only to save tokens
        call_images = None
        if self._images and not self._images_sent:
            call_images = self._images
            self._images_sent = True

        try:
            chunks: list[str] = []
            for chunk in self.nexus.provider_manager.call_with_failover_stream(
                prompt=prompt,
                trace_id=f"{self.trace_id}-i{iteration}",
                temperature=0.2,
                model=self.model_id,
                request_type="generation",
                source="agent",
                max_tokens=8192,
                images=call_images,
            ):
                chunks.append(chunk)
            full = "".join(chunks).strip()
            if not full:
                return "(LLM error: Provider returned empty response)"

            # Estimate token usage (~4 chars/token) and emit for the UI
            est_in  = len(prompt) // 4
            est_out = len(full)   // 4
            self.run_input_tokens  += est_in
            self.run_output_tokens += est_out
            elapsed = (datetime.utcnow() - self._start_time).total_seconds()
            total   = self.run_input_tokens + self.run_output_tokens
            self._emit({
                "type":          "usage",
                "input_tokens":  est_in,
                "output_tokens": est_out,
                "run_input":     self.run_input_tokens,
                "run_output":    self.run_output_tokens,
                "run_total":     total,
                "tok_per_sec":   round(total / elapsed, 1) if elapsed > 0 else 0,
            })

            return full
        except Exception as e:
            logger.error(f"AgentRunner LLM call failed: {e}")
            return f"(Error calling LLM: {e})"

    # ── parsing ───────────────────────────────────────────────────

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

    # ── tool execution ────────────────────────────────────────────

    def _execute(self, action: Dict[str, Any], iteration: int = 0) -> Optional[str]:
        """Execute an action. Returns result string, or None for state-only actions."""
        t = action.get("type", "")

        if t == "set_plan":
            steps = action.get("steps", [])
            self.state.set_plan(steps)
            return None  # state-only, not sent to LLM

        if t == "mark_done":
            step = action.get("step", "")
            self.state.mark_done(step)
            return None  # state-only

        if t == "add_note":
            note = action.get("note", "")
            self.state.add_note(note)
            return None  # state-only

        if t == "write_file":
            path = action.get("path", "")
            content = action.get("content", "")
            result = self._write_file(path, content)
            self.state.cache_file(path, len(content.encode()))
            self.state.log_action(iteration, "write_file", path)
            return result

        if t == "read_file":
            path = action.get("path", "")
            result = self._read_file(path)
            # Cache with actual byte size of result if successful
            if not result.startswith("Error:") and not result.startswith("Not found:"):
                self.state.cache_file(path, len(result.encode()))
            self.state.log_action(iteration, "read_file", path)
            return result

        if t == "list_dir":
            path = action.get("path", "")
            result = self._list_dir(path)
            # Parse flat filenames from result to update workspace map
            if result and result != "(empty)" and not result.startswith("Error:"):
                entries = self._parse_list_dir_entries(result)
                if entries:
                    self.state.update_workspace_map(entries)
            self.state.log_action(iteration, "list_dir", path or ".")
            return result

        if t == "run_command":
            cmd = action.get("command", "")
            result = self._run_command(cmd)
            short_cmd = cmd[:40] if len(cmd) > 40 else cmd
            self.state.log_action(iteration, "run_command", short_cmd)
            return result

        if t == "search_web":
            query = action.get("query", "")
            max_results = int(action.get("max_results", 6))
            result = self._search_web(query, max_results)
            self.state.log_action(iteration, "search_web", query[:40])
            return result

        if t == "fetch_url":
            url = action.get("url", "")
            result = self._fetch_url(url)
            self.state.log_action(iteration, "fetch_url", url[:40])
            return result

        return f"Unknown action: {t}"

    def _parse_list_dir_entries(self, listing: str) -> List[str]:
        """Extract bare filenames from _list_dir output (strips emoji prefix)."""
        entries = []
        for line in listing.splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip folder/file emoji prefixes added by _list_dir
            for prefix in ("\U0001f4c1 ", "\U0001f4c4 "):
                if line.startswith(prefix):
                    line = line[len(prefix):]
                    break
            if line:
                entries.append(line)
        return entries

    def _write_file(self, path: str, content: str) -> str:
        try:
            fp = self.workspace / path
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
            return f"Written {len(content.encode()):,} bytes"
        except Exception as e:
            return f"Error: {e}"

    def _read_file(self, path: str) -> str:
        try:
            fp = self.workspace / path
            if not fp.exists():
                return f"Not found: {path}"
            content = fp.read_text(encoding="utf-8", errors="replace")
            if len(content) > 6000:
                return content[:6000] + f"\n...(truncated, {len(content):,} total chars)"
            return content
        except Exception as e:
            return f"Error: {e}"

    def _list_dir(self, path: str) -> str:
        try:
            target = self.workspace / path if path else self.workspace
            if not target.exists():
                return f"Not found: {path}"
            entries = [
                ("\U0001f4c1 " if e.is_dir() else "\U0001f4c4 ") + e.name
                for e in sorted(target.iterdir())
            ]
            return "\n".join(entries) if entries else "(empty)"
        except Exception as e:
            return f"Error: {e}"

    def _fetch_url(self, url: str) -> str:
        try:
            import urllib.request
            import urllib.error
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/plain, */*",
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.status
                body = resp.read().decode("utf-8", errors="replace")
            if len(body) > 6000:
                body = body[:6000] + "\n...(truncated)"
            return f"HTTP {status}\n{body}"
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            return f"HTTP {e.code} {e.reason}: {body}"
        except Exception as e:
            return f"Fetch error: {e}"

    def _search_web(self, query: str, max_results: int = 6) -> str:
        try:
            from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    title = r.get("title", "")
                    href  = r.get("href", "")
                    body  = r.get("body", "")
                    results.append(f"[{title}]\n{href}\n{body}")
            if not results:
                return "No results found."
            return "\n\n---\n\n".join(results)
        except Exception as e:
            return f"Search error: {e}"

    def _run_command(self, command: str) -> str:
        try:
            res = subprocess.run(
                command, shell=True, cwd=str(self.workspace),
                capture_output=True, text=True, timeout=60,
            )
            out = ((res.stdout or "") + (res.stderr or "")).strip()
            if len(out) > 3000:
                out = out[:3000] + "\n...(truncated)"
            return out or f"(exit {res.returncode})"
        except subprocess.TimeoutExpired:
            return "Timed out (60s)"
        except Exception as e:
            return f"Error: {e}"

    # ── event builder ─────────────────────────────────────────────

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

        if t == "write_file":
            preview = content[:400] + ("\u2026" if len(content) > 400 else "")
            return {"type": t, "title": f"Writing {path}", "path": path,
                    "detail": preview, "bytes": len(content.encode())}

        if t == "read_file":
            return {"type": t, "title": f"Reading {path}", "path": path, "detail": ""}

        if t == "list_dir":
            return {"type": t, "title": f"Listing {path or 'workspace'}", "path": path, "detail": ""}

        if t == "run_command":
            return {"type": t, "title": f"$ {cmd[:80]}", "command": cmd, "detail": ""}

        if t == "search_web":
            query = action.get("query", "")
            return {"type": t, "title": f"Search: {query}", "query": query, "detail": ""}

        if t == "fetch_url":
            url = action.get("url", "")
            return {"type": "fetch_url", "title": f"Fetch: {url}", "url": url, "detail": ""}

        return {"type": t, "title": t, "detail": str(action)}

    # ── main loop ─────────────────────────────────────────────────

    def run(self) -> str:
        self._emit({"type": "start", "title": "Starting task", "detail": self.task})

        for iteration in range(MAX_ITERATIONS):
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
                    done_summary = action.get("summary", "Task complete.")
                    done_triggered = True
                    break

                # Emit event first (before executing so UI updates immediately)
                event = self._make_event(action)
                result = self._execute(action, iteration)

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
                results.append(f"{action_type}({short}): {result}")
                compact_actions.append(f"{action_type}({short})")

            if done_triggered:
                self._emit({"type": "done", "title": "Complete", "detail": done_summary})
                self.state.save()
                return done_summary

            # Store as "Assistant:" / "User:" to match Code IDE _messages_to_prompt format
            agent_line = thinking or "(working)"
            if compact_actions:
                agent_line += "\nDid: " + ", ".join(compact_actions)
            self.conversation.append(f"Assistant: {agent_line}")
            if results:
                self.conversation.append(
                    "User: Results:\n" + "\n".join(results) +
                    "\nKeep going until the task is fully complete."
                )
            # Keep conversation bounded to last 4 entries (2 round-trips)
            if len(self.conversation) > 4:
                self.conversation = self.conversation[-4:]

        summary = f"Reached {MAX_ITERATIONS} action limit."
        self._emit({"type": "done", "title": "Stopped (limit)", "detail": summary})
        self.state.save()
        return summary
