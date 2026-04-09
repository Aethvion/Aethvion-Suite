"""
Aethvion Suite - Agent Runner
Multi-step ReAct-style execution loop with persistent state.
"""
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, List, Dict, Any

from core.utils.logger import get_logger
from core.utils import utcnow_iso
from core.orchestrator.task_queue import is_agent_task_cancelled
from core.ai.call_contexts import CallSource

logger = get_logger(__name__)

# Safety backstop — effectively unlimited; the Stop button is the user's control.
MAX_ITERATIONS = 200

# ── Blueprint / search constants ──────────────────────────────────────────────
BLUEPRINT_IGNORE_DIRS = frozenset({
    '.git', 'node_modules', '__pycache__', '.next', 'dist', 'build',
    '.venv', 'venv', 'env', '.tox', '.pytest_cache', '.mypy_cache',
    'coverage', '.cache', 'tmp', 'temp', '.idea', '.vscode',
})
BLUEPRINT_SKIP_EXTS = frozenset({
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.webp', '.avif', '.tif', '.tiff',
    '.ttf', '.woff', '.woff2', '.eot', '.otf',
    '.mp4', '.mp3', '.wav', '.webm', '.avi', '.mov', '.ogg', '.flac',
    '.zip', '.gz', '.tar', '.rar', '.7z', '.bz2',
    '.pyc', '.pyo', '.so', '.dll', '.exe', '.bin', '.class',
    '.map',
})
BLUEPRINT_MAX_FILES_PER_DIR = 20   # show first N files per directory, summarise the rest
BLUEPRINT_MAX_DEPTH         = 6    # max folder depth to recurse
BLUEPRINT_MAX_LINES         = 500  # hard cap on output lines
BLUEPRINT_CACHE_SECS        = 120  # seconds before cached _blueprint.txt is stale


def _bp_fmt_size(n: int) -> str:
    if n < 1024:       return f"{n}B"
    if n < 1_048_576:  return f"{n // 1024}k"
    return f"{n / 1_048_576:.1f}M"


def build_workspace_blueprint(
    workspace: Path,
    sub_path: str = "",
    cache_path: Optional[Path] = None,
) -> str:
    """Walk the workspace once and return a compact hierarchical file map.

    • ``cache_path`` — where to write the cached snapshot.  Corp callers pass a
      path inside ``data/agent_corps/{id}/`` so the file never appears in the
      user's project.  Standalone agents default to ``workspace/_blueprint.txt``.
    • Pass ``sub_path`` to get an expanded view of a specific subdirectory.
    • Binary assets (images, fonts, video…) and tooling dirs (.git, node_modules…)
      are silently excluded so the output stays focused on source files.
    """
    import time

    root = workspace / sub_path if sub_path else workspace
    if not root.exists():
        return f"Error: path '{sub_path}' not found in workspace."

    effective_cache = cache_path or (workspace / "_blueprint.txt")

    # When a custom cache_path is provided (i.e. data dir, not the workspace),
    # evict any stale _blueprint.txt that may have been left in the workspace by
    # an older code path.  Do this once, silently.
    if cache_path is not None:
        _old_ws_bp = workspace / "_blueprint.txt"
        if _old_ws_bp.exists() and _old_ws_bp != effective_cache:
            try:
                _old_ws_bp.unlink()
            except Exception:
                pass

    if not sub_path and effective_cache.exists():
        try:
            if time.time() - effective_cache.stat().st_mtime < BLUEPRINT_CACHE_SECS:
                return effective_cache.read_text(encoding="utf-8")
        except Exception:
            pass

    lines: list[str] = []

    def walk(path: Path, prefix: str, depth: int) -> None:
        if depth > BLUEPRINT_MAX_DEPTH:
            lines.append(f"{prefix}… (depth limit)")
            return
        try:
            entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        except PermissionError:
            return

        dirs = [
            e for e in entries
            if e.is_dir() and e.name not in BLUEPRINT_IGNORE_DIRS and not e.name.startswith(".")
        ]
        files = [
            e for e in entries
            if e.is_file()
            and e.suffix.lower() not in BLUEPRINT_SKIP_EXTS
            and e.name != "_blueprint.txt"
        ]

        shown  = files[:BLUEPRINT_MAX_FILES_PER_DIR]
        hidden = files[BLUEPRINT_MAX_FILES_PER_DIR:]

        items = dirs + shown
        for i, item in enumerate(items):
            last_visible = (i == len(items) - 1) and not hidden
            conn      = "└── " if last_visible else "├── "
            child_pfx = prefix + ("    " if last_visible else "│   ")

            if item.is_dir():
                try:
                    sub = list(item.iterdir())
                    n_f = sum(1 for e in sub if e.is_file() and e.suffix.lower() not in BLUEPRINT_SKIP_EXTS)
                    n_d = sum(1 for e in sub if e.is_dir()
                              and e.name not in BLUEPRINT_IGNORE_DIRS and not e.name.startswith("."))
                    ext_ctr: dict[str, int] = {}
                    for e in sub:
                        if e.is_file() and e.suffix.lower() not in BLUEPRINT_SKIP_EXTS:
                            ext = e.suffix.lower() or "(no ext)"
                            ext_ctr[ext] = ext_ctr.get(ext, 0) + 1
                    top = sorted(ext_ctr.items(), key=lambda x: -x[1])[:3]
                    ext_str = ", ".join(f"{c}×{e}" for e, c in top)
                    meta = f"{n_f} files" + (f" [{ext_str}]" if ext_str else "") + (f", {n_d} subdirs" if n_d else "")
                except Exception:
                    meta = ""
                lines.append(f"{prefix}{conn}{item.name}/  ({meta})")
                walk(item, child_pfx, depth + 1)
            else:
                try:
                    sz = _bp_fmt_size(item.stat().st_size)
                except Exception:
                    sz = ""
                lines.append(f"{prefix}{conn}{item.name}  {sz}")

        if hidden:
            ext_ctr2: dict[str, int] = {}
            for f in hidden:
                ext = f.suffix.lower() or "(no ext)"
                ext_ctr2[ext] = ext_ctr2.get(ext, 0) + 1
            top2 = sorted(ext_ctr2.items(), key=lambda x: -x[1])[:3]
            ext_str2 = ", ".join(f"{c}×{e}" for e, c in top2)
            lines.append(f"{prefix}└── … {len(hidden)} more [{ext_str2}]  "
                         f"(use get_project_blueprint with path=\"{path.relative_to(workspace)}\" for full list)")

    walk(root, "", 0)

    if len(lines) > BLUEPRINT_MAX_LINES:
        lines = lines[:BLUEPRINT_MAX_LINES]
        lines.append("… [truncated — use path= parameter to explore a specific subdirectory]")

    header = f"# Blueprint: {sub_path or workspace.name}/  ({len(lines)} entries)\n"
    result = header + "\n".join(lines)

    if not sub_path:
        try:
            effective_cache.parent.mkdir(parents=True, exist_ok=True)
            effective_cache.write_text(result, encoding="utf-8")
        except Exception:
            pass

    return result

SYSTEM_PROMPT = """\
You are an expert software engineer completing coding tasks with surgical precision.

Working directory: {workspace}
Current date: {current_date}

HOW TO TAKE ACTIONS (write ACTION: followed by JSON, multiple per response allowed):

ACTION: {{"type": "patch_file", "path": "relative/file.txt", "old": "exact text to replace", "new": "replacement text"}}
ACTION: {{"type": "append_file", "path": "relative/file.txt", "content": "content to add at end of file"}}
ACTION: {{"type": "write_file", "path": "relative/path.txt", "content": "FULL file content here"}}
ACTION: {{"type": "delete_file", "path": "relative/file.txt"}}
ACTION: {{"type": "read_file", "path": "relative/file.txt"}}
ACTION: {{"type": "read_file", "path": "relative/file.txt", "offset": 300}}           ← start at line 300
ACTION: {{"type": "read_file", "path": "relative/file.txt", "offset": 300, "limit": 200}}  ← lines 300–500
ACTION: {{"type": "get_project_blueprint"}}                                                    ← full workspace tree, zero reads needed
ACTION: {{"type": "get_project_blueprint", "path": "subdir"}}                                 ← expanded view of one subdirectory
ACTION: {{"type": "search_codebase", "query": "text or regex", "path": "dir/or/file.html"}}  ← find text without reading whole files; add "context": 2 for extra lines
ACTION: {{"type": "list_dir", "path": ""}}
ACTION: {{"type": "run_command", "command": "npm install"}}
ACTION: {{"type": "search_web", "query": "your search query", "max_results": 6}}
ACTION: {{"type": "fetch_url", "url": "https://api.github.com/repos/owner/repo"}}
ACTION: {{"type": "set_plan", "steps": ["step 1", "step 2", "step 3"]}}
ACTION: {{"type": "mark_done", "step": "exact step text"}}  ← call this AFTER the real action succeeds, never instead of it
ACTION: {{"type": "add_note", "note": "important context to remember"}}
ACTION: {{"type": "observe", "content": "I see a screenshot showing X, Y, Z. The error is on line N."}}  ← describe images or key findings
ACTION: {{"type": "done", "summary": "brief summary of what was accomplished"}}

SURGICAL EDIT RULES (most important):
1. PATCH, DON'T REWRITE: When modifying an existing file, ALWAYS use patch_file — never rewrite the whole file just to change one thing. patch_file replaces only the exact "old" string with "new". The rest of the file is untouched.
2. READ BEFORE PATCHING: Always read_file before patch_file so your "old" string exactly matches the current content. A single character difference will cause the patch to fail.
3. MINIMAL CHANGES: Only change what the user asked for. Do not reformat, restructure, restyle, or "clean up" anything that wasn't part of the request. If the user says "add a button", add the button — nothing else changes.
4. PRESERVE EVERYTHING: When adding to existing code, preserve the existing indentation, style, variable names, class names, comments, and structure. Never rename, reorder, or reorganise untouched sections.
5. write_file is for NEW files or for cases where the user explicitly asks for a full rewrite. Never use write_file on an existing file just to make a small change.
6. ADDING NEW FUNCTIONS/SECTIONS: Use append_file to add new functions, classes, or CSS rules to the end of an existing file. This requires no "old" string matching and cannot fail due to content mismatch. Prefer this over write_file for "add X to the file" tasks.

EFFICIENCY RULES:
7. Write REAL, COMPLETE file content — never stubs or placeholders. (For new files via write_file.)
8. Before every response that takes actions, write 1–2 sentences describing what you're about to do and why. This reasoning appears before any ACTION: lines.
9. SIMPLE QUESTIONS: If the user asks a conversational follow-up — read the relevant file(s), then immediately call done with the answer. Never paginate or loop.
10. WORKSPACE CONTEXT: If "Files:" are already listed in the Context block above, you already know what exists — skip list_dir and proceed directly.
11. If images are attached to the task, use observe as your FIRST action to describe exactly what you see in each image before doing anything else.
12. When switching tech stack or approach (e.g. React → plain HTML/CSS/JS), use delete_file to remove ALL old files that no longer belong BEFORE writing new ones.
13. Start complex tasks with set_plan. Call mark_done only AFTER the real action for that step has executed and returned a result.
14. BATCH EVERYTHING: Issue all independent ACTION lines in a single response. Multiple patch_file/append_file calls for different files are fine in one response.
15. KNOWLEDGE BLOCK: The Context section contains a "Knowledge" block listing every file you have ever read or modified, with function names and their exact line numbers (e.g. handleMouseMove@L145). Use this to jump directly to the right section: read_file with offset=145 to see that function. Check the Knowledge block before deciding to read a file at all — you may already know what you need.
16. FILE READING: read_file returns up to 50,000 chars per call — enough for most files in one shot. If a result ends with [TRUNCATED], use the exact offset shown to continue. If you see a [NOTE] about reading a section multiple times, check the Knowledge block — it has the function locations. Use offset-based reads to jump directly to the function you need.
17. PATCH FAILURES: If patch_file returns "FAILED: exact 'old' string not found", the file was likely changed since you last read it. Re-read the file (or the relevant section using offset) to get the current exact content, then retry. If you see a [NOTE] about repeated attempts, switch to append_file for new functions or write_file for a full replacement.
18. Be strategic: prefer targeted offset reads and append_file over full-file reads. Read only the section you need.
19. SEARCH LIMIT: You may call search_web at most 3 times per task. After 2 searches without data, switch to fetch_url or proceed with what you have.
20. For fetching a specific URL or API use fetch_url. NEVER use curl, wget, or write scripts to fetch web data.
21. Write ALL deliverable files BEFORE writing or running verification/test scripts.
22. Before calling done, check your plan — every [ ] step must have a corresponding action result. Complete any unmarked steps first.
23. NAMING: Never name user projects, games, apps, or deliverables after the workspace directory path. Use the name the user specified, or a descriptive/generic name if none was given.
24. NAVIGATE SMART: On any unfamiliar workspace, call get_project_blueprint FIRST — it gives the full folder/file tree instantly without a single list_dir. Use list_dir only for a targeted spot-check of one directory.
25. FIND, DON'T READ: Use search_codebase(query, path) to locate a string, class, or link in seconds. Only call read_file after you know exactly which file and roughly which line you need.
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
        self.prior_tasks: List[Dict[str, str]] = []  # [{task, summary}] across the thread
        # Semantic memory: compact structural digest for every file ever read/modified.
        # Persists across iterations and tasks so the agent always knows what's in each file
        # without having to re-read raw content that long-since scrolled out of history.
        self.file_digests: Dict[str, str] = {}      # path -> digest string

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
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[AgentState] Could not save state to {self.state_path}: {e}")

    # ── file cache ────────────────────────────────────────────────

    def is_cached(self, path: str) -> bool:
        return path in self.file_cache

    def cache_file(self, path: str, size: int, turn: int = 0) -> None:
        self.file_cache[path] = {
            "size": size,
            "cached_at": utcnow_iso(),
            "turn": turn,
        }
        if path not in self.workspace_map:
            self.workspace_map.append(path)

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

    # ── prior task history ────────────────────────────────────────

    def record_task(self, task: str, summary: str) -> None:
        """Append a completed task to the thread history (capped at 20)."""
        self.prior_tasks.append({
            "task": task[:300],
            "summary": summary[:500],
        })
        if len(self.prior_tasks) > 20:
            self.prior_tasks = self.prior_tasks[-20:]

    # ── notes ─────────────────────────────────────────────────────

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

    # ── action log ────────────────────────────────────────────────

    def log_action(self, iteration: int, action_type: str, detail: str) -> None:
        self.action_log.append({
            "i": iteration,
            "type": action_type,
            "detail": detail,
            "at": utcnow_iso(),
        })
        if len(self.action_log) > self._MAX_LOG:
            self.action_log = self.action_log[-self._MAX_LOG:]

    # ── context builder ───────────────────────────────────────────

    def build_context(self) -> str:
        """Return a compact context string injected into every prompt."""
        parts: List[str] = []

        # Prior task history (most recent last so it's closest to the current task).
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
        # Hard cap at 1 500 chars so a session touching 30+ files stays lean.
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
        # Subclasses override these to control per-prompt cost without touching run():
        #   _conv_window  — recent conversation entries to keep in each prompt
        #   _task_short   — compact reminder used for iterations 1+ (None = repeat full task)
        self._conv_window: int = 8
        self._task_short: Optional[str] = None
        # Corp workers set this to their corp data dir so _blueprint.txt is written
        # there instead of into the user's project workspace.
        self._blueprint_cache_path: Optional[Path] = None
        # Reset only per-task planning state between tasks.
        # file_cache and workspace_map are intentionally KEPT so the agent knows
        # what files it already created in this thread — follow-up tasks can skip
        # list_dir and re-reading files it already has in context.
        # The list_dir-first rule handles any genuinely stale workspace state.
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

    # ── cache helpers ─────────────────────────────────────────────

    def _invalidate_read_cache(self, path: str) -> None:
        """Remove all read-dedup entries for `path` so the agent can re-read
        it after a write/patch without being blocked by the duplicate guard."""
        keys = [k for k in list(self._read_cache) if k.startswith(path + ":") or k == path]
        for k in keys:
            del self._read_cache[k]

    def _generate_digest(self, path: str, content: str,
                         last_action: Optional[str] = None) -> str:
        """Build a rich semantic digest of a file's structure.

        Includes function/selector names WITH line numbers so the agent can jump
        directly to `offset=N` for any function without scanning the whole file.
        Stored in AgentState.file_digests; injected into every prompt as the
        Knowledge block.  Target size: ~400 chars per file.
        """
        ext   = Path(path).suffix.lower()
        lines = content.splitlines()
        ts    = datetime.utcnow().strftime("%H:%M")
        header = f"{path} [{len(lines)}L, {len(content):,}ch]"

        entries: List[str] = []   # "name@line" or "name@line: first-sig"

        if ext in (".js", ".ts", ".jsx", ".tsx", ".mjs"):
            seen: set = set()
            globals_top: List[str] = []
            fns_with_lines: List[str] = []

            for i, line in enumerate(lines, 1):
                # function declarations
                m = re.match(r"\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*(\([^)]*\))?", line)
                if m and m.group(1) not in seen:
                    sig = m.group(2) or "()"
                    fns_with_lines.append(f"{m.group(1)}@L{i}{sig}")
                    seen.add(m.group(1))
                    continue
                # const/let/var arrow functions
                m = re.match(r"\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)", line)
                if m and m.group(1) not in seen:
                    fns_with_lines.append(f"{m.group(1)}@L{i}({m.group(2)})")
                    seen.add(m.group(1))
                    continue
                # top-of-file globals (first 30 lines only)
                if i <= 30:
                    m = re.match(r"^\s*(?:const|let|var)\s+(\w+)\s*=\s*([^;]{0,40})", line)
                    if m and m.group(1) not in seen:
                        globals_top.append(f"{m.group(1)}={m.group(2).strip()[:20]}")

            if fns_with_lines:
                entries.append("functions:\n    " + "\n    ".join(fns_with_lines[:30]))
            if globals_top:
                entries.append("globals: " + ", ".join(globals_top[:8]))

        elif ext == ".css":
            sel_with_lines: List[str] = []
            seen_sel: set = set()
            for i, line in enumerate(lines, 1):
                m = re.match(r"^([.#]?[\w][\w\s.#:>+~\[\]\"'=*-]*?)\s*\{", line)
                if m:
                    sel = m.group(1).strip()
                    if sel and sel not in seen_sel:
                        sel_with_lines.append(f"{sel}@L{i}")
                        seen_sel.add(sel)
            if sel_with_lines:
                entries.append("selectors:\n    " + "\n    ".join(sel_with_lines[:30]))

        elif ext in (".html", ".htm"):
            ids = re.findall(r'\bid=["\']([^"\']+)["\']', content)
            unique_ids = list(dict.fromkeys(ids))
            if unique_ids:
                entries.append("ids: " + ", ".join(unique_ids[:20]))
            # key script/link/meta tags summary
            scripts = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', content)
            if scripts:
                entries.append("scripts: " + ", ".join(scripts[:6]))

        elif ext == ".py":
            cls_with_lines: List[str] = []
            fn_with_lines:  List[str] = []
            for i, line in enumerate(lines, 1):
                m = re.match(r"^class (\w+)", line)
                if m:
                    cls_with_lines.append(f"{m.group(1)}@L{i}")
                m = re.match(r"^\s*def (\w+)\s*(\([^)]*\))?", line)
                if m:
                    sig = (m.group(2) or "()").replace("\n", "")[:40]
                    fn_with_lines.append(f"{m.group(1)}@L{i}{sig}")
            if cls_with_lines:
                entries.append("classes: " + ", ".join(cls_with_lines[:10]))
            if fn_with_lines:
                entries.append("functions:\n    " + "\n    ".join(fn_with_lines[:25]))

        body = ""
        if entries:
            body = "\n  " + "\n  ".join(entries)

        last = f"\n  last: {last_action} @ {ts}" if last_action else ""
        return f"{header}{body}{last}"

    # ── emit ──────────────────────────────────────────────────────

    def _emit(self, event: Dict[str, Any]) -> None:
        self.step_callback(event)

    # ── LLM call ──────────────────────────────────────────────────

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

        ctx = self.state.build_context()
        if ctx:
            parts.append(f"Context:\n{ctx}")

        # For iterations 1+ use a compact task reminder when _task_short is set.
        # The full context was in iteration 0 which is stored in conversation history.
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
        return SYSTEM_PROMPT.format(
            workspace=str(self.workspace),
            current_date=datetime.utcnow().strftime("%B %d, %Y"),
        )

    def _call_llm(self, iteration: int = 0) -> str:
        """Use streaming — same path as the working Code IDE — for reliability."""
        prompt = self._build_prompt(current_turn=iteration)
        logger.info(f"[AgentRunner iter={iteration}] prompt_chars={len(prompt)}")

        # Pass images only on the first LLM call so vision context is available
        # for the initial plan; subsequent iterations are text-only to save tokens
        call_images = None
        if self._images and not self._images_sent:
            call_images = self._images
            self._images_sent = True

        try:
            chunks: list[str] = []
            _llm_start = datetime.utcnow()
            for chunk in self.nexus.provider_manager.call_with_failover_stream(
                prompt=prompt,
                trace_id=f"{self.trace_id}-i{iteration}",
                temperature=0.2,
                model=self.model_id,
                request_type="generation",
                source=CallSource.AGENT,
                max_tokens=8192,
                images=call_images,
            ):
                chunks.append(chunk)
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
            run_elapsed = (datetime.utcnow() - self._start_time).total_seconds()
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

        if t == "observe":
            # Observation action — purely informational, emitted to the UI.
            # Return the observation text so the LLM keeps context of what it said.
            content = action.get("content", "")
            self.state.log_action(iteration, "observe", content[:60])
            return content  # returned to LLM as confirmation

        if t == "patch_file":
            path = action.get("path", "")
            old  = action.get("old", "")
            new  = action.get("new", "")
            repeat_key = f"patch_file:{path}:{old[:60]}"
            self._action_repeats[repeat_key] = self._action_repeats.get(repeat_key, 0) + 1
            attempt = self._action_repeats[repeat_key]

            result = self._patch_file(path, old, new)
            self.state.log_action(iteration, "patch_file", path)
            self._emit({"type": "write_file", "path": path, "detail": f"patch: {len(old)}→{len(new)} chars"})
            if not result.startswith("patch_file FAILED"):
                # Successful patch — reset the repeat counter and clear read dedup
                self._action_repeats.pop(repeat_key, None)
                self._invalidate_read_cache(path)
                # Update digest to reflect the change
                try:
                    fp = self.workspace / path
                    full = fp.read_text(encoding="utf-8", errors="replace")
                    summary = f"patched ({len(old)}→{len(new)} chars)"
                    digest = self._generate_digest(path, full, last_action=summary)
                    self.state.update_file_digest(path, digest)
                except Exception:
                    pass
            # Soft nudge on repeated failed patches — never block, just guide
            if result.startswith("patch_file FAILED") and attempt >= 2:
                result += (
                    f"\n[NOTE: This is attempt {attempt} with the same 'old' string. "
                    f"Use read_file to get the exact current content of {path} — "
                    f"the file may have changed since you last read it. "
                    f"Or use append_file to add the new code at the end of the file.]"
                )
            return result

        if t == "append_file":
            path    = action.get("path", "")
            content = action.get("content", "")
            result  = self._append_file(path, content)
            self.state.log_action(iteration, "append_file", path)
            self._emit({"type": "write_file", "path": path, "detail": f"append: {len(content)} chars"})
            self._invalidate_read_cache(path)
            if not result.startswith("Error:"):
                try:
                    fp = self.workspace / path
                    full = fp.read_text(encoding="utf-8", errors="replace")
                    digest = self._generate_digest(path, full, last_action=f"appended {len(content)} chars")
                    self.state.update_file_digest(path, digest)
                except Exception:
                    pass
            return result

        if t == "write_file":
            path = action.get("path", "")
            content = action.get("content", "")
            result = self._write_file(path, content)
            self.state.cache_file(path, len(content.encode()), turn=iteration)
            self.state.log_action(iteration, "write_file", path)
            # File was written — clear its read-dedup entries.
            self._invalidate_read_cache(path)
            # Generate digest for the newly written content
            if not result.startswith("Error:"):
                try:
                    digest = self._generate_digest(path, content, last_action="written")
                    self.state.update_file_digest(path, digest)
                except Exception:
                    pass
            return result

        if t == "delete_file":
            path = action.get("path", "")
            result = self._delete_file(path)
            # Remove from state caches on success
            if not result.startswith("Error:") and not result.startswith("Not found:"):
                self.state.file_cache.pop(path, None)
                if path in self.state.workspace_map:
                    self.state.workspace_map.remove(path)
            self.state.log_action(iteration, "delete_file", path)
            return result

        if t == "read_file":
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
                # need to re-read just to find out what functions are in the file.
                if offset == 0:
                    try:
                        fp = self.workspace / path
                        full = fp.read_text(encoding="utf-8", errors="replace")
                        digest = self._generate_digest(path, full)
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
            result = self._search_web(query, max_results)
            self._search_cache[query] = result
            self.state.log_action(iteration, "search_web", query[:40])
            return result

        if t == "fetch_url":
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
            result = self._fetch_url(url)
            # Only cache successful responses — never cache 429/5xx errors so
            # the agent can retry after a rate-limit window passes.
            if not result.startswith("HTTP 429") and not result.startswith("HTTP 5"):
                self._fetch_cache[url] = result
            self.state.log_action(iteration, "fetch_url", url[:40])
            return result

        if t == "get_project_blueprint":
            sub_path = action.get("path", "")
            result = build_workspace_blueprint(
                self.workspace, sub_path, cache_path=self._blueprint_cache_path
            )
            self.state.log_action(iteration, "get_project_blueprint", sub_path or "workspace")
            return result

        if t == "search_codebase":
            query = action.get("query", "")
            path  = action.get("path", "")
            ctx   = int(action.get("context", 1))
            max_r = int(action.get("max_results", 30))
            if not query:
                return "[search_codebase] 'query' is required."
            result = self._search_codebase(query, path, ctx, max_r)
            self.state.log_action(iteration, "search_codebase", query[:40])
            self._emit({"type": "read_file", "path": path or "workspace", "detail": f"search: {query[:40]}"})
            return result

        return f"Unknown action: {t}"

    def _search_codebase(self, query: str, path: str = "", context_lines: int = 1, max_results: int = 30) -> str:
        """Search for a literal string or regex pattern across workspace source files.

        Much cheaper than reading whole files: returns only matching lines with
        a small context window, and the file + line number so the agent can jump
        straight to the right offset with read_file.
        """
        search_root = self.workspace / path if path else self.workspace
        if not search_root.exists():
            return f"Error: path '{path}' does not exist in workspace."

        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        if search_root.is_file():
            files: List[Path] = [search_root]
        else:
            files = sorted(
                f for f in search_root.rglob("*")
                if f.is_file()
                and f.suffix.lower() not in BLUEPRINT_SKIP_EXTS
                and not any(part in BLUEPRINT_IGNORE_DIRS
                            for part in f.relative_to(self.workspace).parts)
            )

        results: List[str] = []
        total_matches = 0

        for filepath in files:
            if total_matches >= max_results:
                break
            try:
                text = filepath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            file_lines = text.splitlines()
            file_hits: List[str] = []

            for lineno, line in enumerate(file_lines, 1):
                if total_matches >= max_results:
                    break
                if pattern.search(line):
                    total_matches += 1
                    ctx_start = max(0, lineno - 1 - context_lines)
                    ctx_end   = min(len(file_lines), lineno + context_lines)
                    block = []
                    for j in range(ctx_start, ctx_end):
                        marker = "→" if j == lineno - 1 else " "
                        block.append(f"  {marker} L{j + 1}: {file_lines[j].rstrip()}")
                    file_hits.append("\n".join(block))

            if file_hits:
                rel = str(filepath.relative_to(self.workspace))
                results.append(f"{rel}:\n" + "\n".join(file_hits))

        if not results:
            scope = f" in '{path}'" if path else ""
            return f"No matches for '{query}'{scope}."

        more = f" (first {max_results} shown)" if total_matches >= max_results else ""
        header = f"Found {total_matches} match{'es' if total_matches != 1 else ''}{more} for '{query}':\n\n"
        return header + "\n\n".join(results)

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

    def _patch_file(self, path: str, old: str, new: str) -> str:
        """Replace the first exact occurrence of `old` with `new` in the file."""
        try:
            fp = self.workspace / path
            if not fp.exists():
                return f"Error: {path} does not exist — use write_file to create it first."
            if not old:
                return "Error: patch_file requires a non-empty 'old' string."
            content = fp.read_text(encoding="utf-8", errors="replace")
            if old not in content:
                return (
                    f"patch_file FAILED: exact 'old' string not found in {path}. "
                    f"Use read_file to get the current contents, then retry with the exact matching text."
                )
            count = content.count(old)
            updated = content.replace(old, new, 1)
            fp.write_text(updated, encoding="utf-8")
            suffix = f" (note: {count} occurrences found, replaced the first one)" if count > 1 else ""
            return f"Patched {path}: replaced {len(old):,} chars with {len(new):,} chars.{suffix}"
        except Exception as e:
            return f"Error: {e}"

    def _write_file(self, path: str, content: str) -> str:
        try:
            fp = self.workspace / path
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
            return f"Written {len(content.encode()):,} bytes"
        except Exception as e:
            return f"Error: {e}"

    def _append_file(self, path: str, content: str) -> str:
        """Append `content` to the end of a file (creates it if it doesn't exist)."""
        try:
            fp = self.workspace / path
            fp.parent.mkdir(parents=True, exist_ok=True)
            with open(fp, "a", encoding="utf-8") as f:
                # Ensure we start on a new line if the file already has content
                if fp.stat().st_size > 0:
                    f.write("\n")
                f.write(content)
            return f"Appended {len(content.encode()):,} bytes to {path}"
        except Exception as e:
            return f"Error: {e}"

    def _delete_file(self, path: str) -> str:
        try:
            fp = self.workspace / path
            if not fp.exists():
                return f"Not found: {path}"
            if fp.is_dir():
                import shutil
                shutil.rmtree(fp)
                return f"Deleted directory {path}"
            fp.unlink()
            return f"Deleted {path}"
        except Exception as e:
            return f"Error: {e}"

    def _read_file(self, path: str, offset: int = 0, limit: Optional[int] = None) -> str:
        """Read a file, optionally starting at line `offset` and capping at `limit` lines.

        The per-chunk char cap is 50,000 — large enough to read most source files in
        a single call.  If a chunk is still truncated, the response says exactly what
        offset to use next so the agent can continue without shell-command workarounds.
        """
        MAX_CHARS = 50_000
        try:
            fp = self.workspace / path
            if not fp.exists():
                return f"Not found: {path}"
            content = fp.read_text(encoding="utf-8", errors="replace")
            lines   = content.splitlines(keepends=True)
            total   = len(lines)

            # Apply line-based offset / limit
            if offset:
                lines = lines[offset:]
            if limit is not None:
                lines = lines[:limit]

            chunk = "".join(lines)

            if len(chunk) <= MAX_CHARS:
                # Entire requested slice fits — include a summary footer so the agent
                # knows whether it has the whole file or just a slice.
                end_line = offset + len(lines)
                if end_line < total:
                    return (
                        chunk
                        + f"\n\n[File: {total} total lines. Showing lines {offset}–{end_line}. "
                        f"To read more use: ACTION: {{\"type\": \"read_file\", \"path\": \"{path}\", \"offset\": {end_line}}}]"
                    )
                return chunk  # whole file (or final slice) — no footer needed

            # Chunk itself is too large: trim to MAX_CHARS and tell agent the next offset
            trimmed = chunk[:MAX_CHARS]
            lines_returned = trimmed.count("\n")
            next_offset = offset + lines_returned
            return (
                trimmed
                + f"\n\n[TRUNCATED at {MAX_CHARS:,} chars. "
                f"File has {total} lines. Next offset: {next_offset}. "
                f"Continue with: ACTION: {{\"type\": \"read_file\", \"path\": \"{path}\", \"offset\": {next_offset}}}]"
            )
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

        if t == "observe":
            obs_content = action.get("content", "")
            return {"type": "observe", "title": "Observation", "detail": obs_content}

        if t == "write_file":
            preview = content[:400] + ("\u2026" if len(content) > 400 else "")
            return {"type": t, "title": f"Writing {path}", "path": path,
                    "detail": preview, "bytes": len(content.encode())}

        if t == "delete_file":
            return {"type": "delete_file", "title": f"Deleting {path}", "path": path, "detail": ""}

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
            # Evict file_cache entries that haven't been accessed in the last 2 turns.
            # Files stay in workspace_map and file_digests — only the '(cached)' marker
            # is dropped, so the agent knows to re-read if it needs fresh content.
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
                    if len(self.conversation) > 8:
                        self.conversation = self.conversation[-8:]
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
                self._emit({"type": "done", "title": "Complete", "detail": done_summary})
                self.state.record_task(self.task, done_summary)
                self.state.save()
                return done_summary

            # Store as structured dicts so _render_conv_entry can evict stale
            # read_file payloads when building prompts in later iterations.
            agent_line = thinking or "(working)"
            if compact_actions:
                agent_line += "\nDid: " + ", ".join(compact_actions)
            self.conversation.append(
                {"role": "assistant", "text": agent_line, "turn": iteration}
            )
            if results:
                self.conversation.append({
                    "role":    "user",
                    "results": results,   # List[str] — each "action(path): content"
                    "turn":    iteration,
                    "header":  "User: Results:",
                    "suffix":  "\nKeep going until the task is fully complete.",
                })
            # Keep conversation bounded to last 8 entries (4 round-trips)
            if len(self.conversation) > 8:
                self.conversation = self.conversation[-8:]

        summary = f"Reached {MAX_ITERATIONS} action limit."
        self._emit({"type": "done", "title": "Stopped (limit)", "detail": summary})
        self.state.record_task(self.task, f"[incomplete — hit limit] {summary}")
        self.state.save()
        return summary
