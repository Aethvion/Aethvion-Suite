"""
Agent Corp Manager — orchestrates multiple autonomous workers as a company team.

Each worker is a CorpWorkerRunner (AgentRunner subclass) with its own memory,
role, personality and stats. Workers communicate via shared .md files (task board
+ message log) rather than re-injecting full history, keeping token usage lean.

Workspaces are stored under:
  agent_corps/
    {corp_id}/
      config.json          Corp definition + worker list
      tasks.json           Task board
      shared_log.md        Inter-agent communication
      workers/
        {worker_id}/
          memory.md        Persistent context for this worker
          state.json       AgentState (plan, notes, prior_tasks…)
      workspace/           Shared file output (agents write here)
"""
import asyncio
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from core.utils.logger import get_logger

logger = get_logger(__name__)

CORP_ROOT = Path("agent_corps")


# ── Cost estimation ──────────────────────────────────────────────────────────

def _estimate_cost(tokens_in: int, tokens_out: int, model: str) -> float:
    """Approximate USD cost. Prices per 1 M tokens (input / output)."""
    pricing = {
        "claude-opus":   (15.0, 75.0),
        "claude-sonnet": (3.0,  15.0),
        "claude-haiku":  (0.25,  1.25),
    }
    key = "claude-sonnet"
    for k in pricing:
        if k in model.lower():
            key = k
            break
    in_p, out_p = pricing[key]
    return (tokens_in / 1_000_000) * in_p + (tokens_out / 1_000_000) * out_p


# ── Worker stats ─────────────────────────────────────────────────────────────

class WorkerStats:
    def __init__(self):
        self.tokens_in: int = 0
        self.tokens_out: int = 0
        self.files_created: int = 0
        self.files_updated: int = 0
        self.tasks_completed: int = 0
        self.tasks_failed: int = 0
        self.cost_usd: float = 0.0
        self.tokens_per_second: float = 0.0
        self.current_thought: str = "Waiting for tasks…"
        self.status: str = "idle"          # idle | running | stopped
        self.session_start: float = time.time()
        self._last_token_time: Optional[float] = None
        self._last_out_tokens: int = 0

    def add_tokens(self, in_tok: int, out_tok: int, model: str) -> None:
        self.tokens_in += in_tok
        self.tokens_out += out_tok
        self.cost_usd += _estimate_cost(in_tok, out_tok, model)
        now = time.time()
        if self._last_token_time:
            elapsed = now - self._last_token_time
            if elapsed > 0:
                self.tokens_per_second = round(out_tok / elapsed, 1)
        self._last_token_time = now

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tokens_in":        self.tokens_in,
            "tokens_out":       self.tokens_out,
            "files_created":    self.files_created,
            "files_updated":    self.files_updated,
            "tasks_completed":  self.tasks_completed,
            "tasks_failed":     self.tasks_failed,
            "cost_usd":         round(self.cost_usd, 5),
            "tokens_per_second": self.tokens_per_second,
            "current_thought":  self.current_thought,
            "status":           self.status,
            "uptime_s":         int(time.time() - self.session_start),
        }


# ── Corp Manager ─────────────────────────────────────────────────────────────

class CorpManager:
    """Singleton that manages all corps and their worker loops."""

    def __init__(self):
        # worker_id → WorkerStats
        self._stats: Dict[str, WorkerStats] = {}
        # corp_id → set of stopped flag (simpler than threading events for asyncio)
        self._stopped: set = set()
        # corp_id → list of asyncio.Task (one per worker)
        self._worker_tasks: Dict[str, List[asyncio.Task]] = {}
        # corp_id → list of asyncio.Queue (one per SSE subscriber)
        self._queues: Dict[str, List[asyncio.Queue]] = {}

    # ── path helpers ──────────────────────────────────────────────────────────

    def _corp_dir(self, corp_id: str) -> Path:
        return CORP_ROOT / corp_id

    def _config_path(self, corp_id: str) -> Path:
        return self._corp_dir(corp_id) / "config.json"

    def _tasks_path(self, corp_id: str) -> Path:
        return self._corp_dir(corp_id) / "tasks.json"

    def _log_path(self, corp_id: str) -> Path:
        return self._corp_dir(corp_id) / "shared_log.md"

    def _workspace_path(self, corp_id: str) -> Path:
        try:
            cfg = self.get_corp(corp_id)
            custom = cfg.get("workspace_path", "").strip()
            if custom:
                return Path(custom)
        except Exception:
            pass
        return self._corp_dir(corp_id) / "workspace"

    def _worker_dir(self, corp_id: str, worker_id: str) -> Path:
        return self._corp_dir(corp_id) / "workers" / worker_id

    def _memory_path(self, corp_id: str, worker_id: str) -> Path:
        return self._worker_dir(corp_id, worker_id) / "memory.md"

    def _state_path(self, corp_id: str, worker_id: str) -> Path:
        return self._worker_dir(corp_id, worker_id) / "state.json"

    # ── corp CRUD ─────────────────────────────────────────────────────────────

    def list_corps(self) -> List[Dict[str, Any]]:
        CORP_ROOT.mkdir(parents=True, exist_ok=True)
        result = []
        for p in sorted(CORP_ROOT.iterdir()):
            cfg_path = p / "config.json"
            if p.is_dir() and cfg_path.exists():
                try:
                    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                    # Enrich with live status
                    cfg["is_running"] = cfg.get("id", p.name) not in self._stopped and \
                                        bool(self._worker_tasks.get(cfg.get("id", p.name)))
                    result.append(cfg)
                except Exception:
                    pass
        return result

    def create_corp(self, name: str, description: str = "",
                    workspace_path: str = "") -> Dict[str, Any]:
        corp_id = str(uuid.uuid4())[:8]
        cfg = {
            "id":             corp_id,
            "name":           name,
            "description":    description,
            "workspace_path": workspace_path,
            "created_at":     datetime.utcnow().isoformat(),
            "status":         "stopped",
            "workers":        [],
        }
        d = self._corp_dir(corp_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "workspace").mkdir(exist_ok=True)
        self._config_path(corp_id).write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        self._tasks_path(corp_id).write_text("[]", encoding="utf-8")
        self._log_path(corp_id).write_text(f"# {name} — Team Log\n\n", encoding="utf-8")
        return cfg

    def get_corp(self, corp_id: str) -> Dict[str, Any]:
        path = self._config_path(corp_id)
        if not path.exists():
            raise FileNotFoundError(f"Corp {corp_id} not found")
        cfg = json.loads(path.read_text(encoding="utf-8"))
        cfg["is_running"] = corp_id not in self._stopped and \
                            bool(self._worker_tasks.get(corp_id))
        return cfg

    def _save_config(self, corp_id: str, cfg: Dict[str, Any]) -> None:
        self._config_path(corp_id).write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    def update_corp(self, corp_id: str, **fields) -> Dict[str, Any]:
        """Update top-level fields on a corp (name, description, workspace_path…)."""
        cfg = self.get_corp(corp_id)
        allowed = {"name", "description", "workspace_path"}
        for k, v in fields.items():
            if k in allowed:
                cfg[k] = v
        self._save_config(corp_id, cfg)
        return cfg

    def delete_corp(self, corp_id: str) -> None:
        import shutil
        d = self._corp_dir(corp_id)
        if d.exists():
            shutil.rmtree(d)

    # ── worker CRUD ───────────────────────────────────────────────────────────

    def add_worker(self, corp_id: str, name: str, role: str,
                   model: str, personality: str, color: str) -> Dict[str, Any]:
        cfg = self.get_corp(corp_id)
        worker = {
            "id":          str(uuid.uuid4())[:8],
            "name":        name,
            "role":        role,
            "model":       model,
            "personality": personality,
            "color":       color,
        }
        cfg["workers"].append(worker)
        self._save_config(corp_id, cfg)
        # Create worker dirs
        wd = self._worker_dir(corp_id, worker["id"])
        wd.mkdir(parents=True, exist_ok=True)
        mem = self._memory_path(corp_id, worker["id"])
        if not mem.exists():
            mem.write_text(
                f"# {name} — Memory\n\n## Role\n{role}\n\n## Notes\n(none yet)\n",
                encoding="utf-8",
            )
        return worker

    def remove_worker(self, corp_id: str, worker_id: str) -> None:
        cfg = self.get_corp(corp_id)
        cfg["workers"] = [w for w in cfg["workers"] if w["id"] != worker_id]
        self._save_config(corp_id, cfg)

    def update_worker(self, corp_id: str, worker_id: str, **fields) -> None:
        cfg = self.get_corp(corp_id)
        for w in cfg["workers"]:
            if w["id"] == worker_id:
                w.update(fields)
                break
        self._save_config(corp_id, cfg)

    # ── task management ───────────────────────────────────────────────────────

    def get_tasks(self, corp_id: str) -> List[Dict[str, Any]]:
        p = self._tasks_path(corp_id)
        if not p.exists():
            return []
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_tasks(self, corp_id: str, tasks: List[Dict]) -> None:
        self._tasks_path(corp_id).write_text(json.dumps(tasks, indent=2), encoding="utf-8")

    def add_task(self, corp_id: str, title: str, description: str,
                 assigned_to: str = "any", priority: str = "medium",
                 created_by: str = "user") -> Dict[str, Any]:
        tasks = self.get_tasks(corp_id)
        task_num = len(tasks) + 1
        task: Dict[str, Any] = {
            "task_id":      f"TASK-{task_num:03d}",
            "title":        title,
            "description":  description,
            "assigned_to":  assigned_to,
            "priority":     priority,
            "status":       "pending",
            "created_by":   created_by,
            "created_at":   datetime.utcnow().isoformat(),
            "started_at":   None,
            "completed_at": None,
            "worker_id":    None,
            "result_summary": None,
        }
        tasks.append(task)
        self._save_tasks(corp_id, tasks)
        # Broadcast to live subscribers
        self.emit(corp_id, {
            "type":     "task_update",
            "task_id":  task["task_id"],
            "title":    title,
            "status":   "pending",
            "assigned_to": assigned_to,
            "priority": priority,
        })
        return task

    def update_task(self, corp_id: str, task_id: str, **fields) -> None:
        tasks = self.get_tasks(corp_id)
        for t in tasks:
            if t["task_id"] == task_id:
                t.update(fields)
                break
        self._save_tasks(corp_id, tasks)

    def get_next_task_for_worker(self, corp_id: str, worker: Dict) -> Optional[Dict]:
        """Return the next pending task this worker can pick up, or None."""
        tasks = self.get_tasks(corp_id)
        worker_id   = worker["id"]
        worker_name = worker["name"].lower()
        for t in tasks:
            if t["status"] != "pending":
                continue
            assigned = str(t.get("assigned_to", "any")).lower()
            if assigned in ("any", worker_id, worker_name):
                return t
        return None

    # ── message log ──────────────────────────────────────────────────────────

    def post_to_log(self, corp_id: str, worker_id: str,
                    worker_name: str, message: str, to: str = "All") -> None:
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        line = f"[{ts}] [{worker_name} → {to}] {message}\n"
        log_path = self._log_path(corp_id)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
        # Get worker color for the broadcast
        color = "#7c3aed"
        try:
            cfg = self.get_corp(corp_id)
            for w in cfg.get("workers", []):
                if w["id"] == worker_id:
                    color = w.get("color", color)
                    break
        except Exception:
            pass
        self.emit(corp_id, {
            "type":        "worker_message",
            "worker_id":   worker_id,
            "worker_name": worker_name,
            "color":       color,
            "to":          to,
            "content":     message,
        })

    def read_log(self, corp_id: str, last_n: int = 30) -> str:
        p = self._log_path(corp_id)
        if not p.exists():
            return "(no messages yet)"
        lines = p.read_text(encoding="utf-8").splitlines()
        # Skip header lines
        content_lines = [l for l in lines if l.strip() and not l.startswith("#")]
        return "\n".join(content_lines[-last_n:])

    # ── worker memory ─────────────────────────────────────────────────────────

    def read_worker_memory(self, corp_id: str, worker_id: str) -> str:
        p = self._memory_path(corp_id, worker_id)
        if not p.exists():
            return ""
        return p.read_text(encoding="utf-8")

    def update_worker_memory(self, corp_id: str, worker_id: str, content: str) -> None:
        p = self._memory_path(corp_id, worker_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    # ── SSE broadcast ─────────────────────────────────────────────────────────

    def emit(self, corp_id: str, event: Dict[str, Any]) -> None:
        """Put event onto every subscriber queue for this corp (fire-and-forget)."""
        queues = self._queues.get(corp_id, [])
        for q in list(queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def subscribe(self, corp_id: str) -> AsyncGenerator[Dict, None]:
        """Async generator that yields events for one SSE client."""
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._queues.setdefault(corp_id, []).append(q)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=25)
                    yield event
                    if event.get("type") == "stream_end":
                        break
                except asyncio.TimeoutError:
                    yield {"type": "ping"}
        finally:
            try:
                self._queues[corp_id].remove(q)
            except (KeyError, ValueError):
                pass

    # ── corp control ──────────────────────────────────────────────────────────

    async def start_corp(self, corp_id: str) -> None:
        cfg = self.get_corp(corp_id)
        if corp_id in self._stopped:
            self._stopped.discard(corp_id)

        # Cancel existing worker tasks if any
        for t in self._worker_tasks.get(corp_id, []):
            t.cancel()
        self._worker_tasks[corp_id] = []

        cfg["status"] = "running"
        self._save_config(corp_id, cfg)

        for worker in cfg.get("workers", []):
            task = asyncio.create_task(
                self._run_worker_loop(corp_id, worker),
                name=f"corp-{corp_id}-{worker['id']}",
            )
            self._worker_tasks.setdefault(corp_id, []).append(task)

        self.emit(corp_id, {"type": "corp_status", "status": "running"})
        logger.info(f"[CorpManager] Started corp {corp_id} with {len(cfg['workers'])} workers")

    async def stop_corp(self, corp_id: str) -> None:
        self._stopped.add(corp_id)
        for t in self._worker_tasks.get(corp_id, []):
            t.cancel()
        self._worker_tasks[corp_id] = []

        try:
            cfg = self.get_corp(corp_id)
            cfg["status"] = "stopped"
            self._save_config(corp_id, cfg)
        except Exception:
            pass

        # Reset all worker stats for this corp
        try:
            cfg = self.get_corp(corp_id)
            for w in cfg.get("workers", []):
                if w["id"] in self._stats:
                    self._stats[w["id"]].status = "stopped"
        except Exception:
            pass

        self.emit(corp_id, {"type": "corp_status", "status": "stopped"})
        logger.info(f"[CorpManager] Stopped corp {corp_id}")

    # ── worker loop ───────────────────────────────────────────────────────────

    async def _run_worker_loop(self, corp_id: str, worker: Dict) -> None:
        worker_id   = worker["id"]
        worker_name = worker["name"]
        worker_col  = worker.get("color", "#7c3aed")

        stats = WorkerStats()
        self._stats[worker_id] = stats
        stats.status = "idle"

        self.emit(corp_id, {
            "type":        "worker_status",
            "worker_id":   worker_id,
            "worker_name": worker_name,
            "color":       worker_col,
            "status":      "idle",
        })

        logger.info(f"[CorpManager] Worker {worker_name} starting loop for corp {corp_id}")

        while corp_id not in self._stopped:
            try:
                task = self.get_next_task_for_worker(corp_id, worker)

                if task is None:
                    stats.current_thought = "Waiting for tasks…"
                    stats.status = "idle"
                    self.emit(corp_id, {
                        "type":        "worker_stats",
                        "worker_id":   worker_id,
                        "worker_name": worker_name,
                        "color":       worker_col,
                        "stats":       stats.to_dict(),
                    })
                    await asyncio.sleep(4)
                    continue

                # ── Mark task in-progress ──────────────────────────────────
                self.update_task(corp_id, task["task_id"],
                                 status="in_progress",
                                 worker_id=worker_id,
                                 started_at=datetime.utcnow().isoformat())
                stats.status = "running"
                self.emit(corp_id, {
                    "type":        "task_update",
                    "task_id":     task["task_id"],
                    "title":       task["title"],
                    "status":      "in_progress",
                    "worker_id":   worker_id,
                    "worker_name": worker_name,
                    "color":       worker_col,
                })

                # ── Build prompt ───────────────────────────────────────────
                prompt = self._build_worker_prompt(corp_id, worker, task)

                # ── Run the agent ──────────────────────────────────────────
                task_start = time.time()

                def step_cb(event: Dict) -> None:
                    et = event.get("type", "")
                    if et == "thinking":
                        thought = (event.get("detail") or "")[:120]
                        stats.current_thought = thought
                        self.emit(corp_id, {
                            "type":        "worker_thought",
                            "worker_id":   worker_id,
                            "worker_name": worker_name,
                            "color":       worker_col,
                            "thought":     thought,
                        })
                    elif et == "write_file":
                        path_str = event.get("path", "")
                        ws = str(self._workspace_path(corp_id))
                        full = os.path.join(ws, path_str)
                        if os.path.exists(full):
                            stats.files_updated += 1
                        else:
                            stats.files_created += 1
                        self.emit(corp_id, {
                            "type":        "worker_action",
                            "worker_id":   worker_id,
                            "worker_name": worker_name,
                            "color":       worker_col,
                            "action":      "write_file",
                            "path":        path_str,
                            "detail":      event.get("detail", "")[:200],
                        })
                    elif et in ("search_web", "fetch_url", "run_command",
                                "read_file", "list_dir", "delete_file"):
                        self.emit(corp_id, {
                            "type":        "worker_action",
                            "worker_id":   worker_id,
                            "worker_name": worker_name,
                            "color":       worker_col,
                            "action":      et,
                            "path":        event.get("path", event.get("query", event.get("url", ""))),
                            "detail":      event.get("detail", "")[:200],
                        })
                    elif et == "usage":
                        in_tok  = event.get("input_tokens", 0)
                        out_tok = event.get("output_tokens", 0)
                        stats.add_tokens(in_tok, out_tok, worker.get("model", ""))
                        self.emit(corp_id, {
                            "type":        "worker_stats",
                            "worker_id":   worker_id,
                            "worker_name": worker_name,
                            "color":       worker_col,
                            "stats":       stats.to_dict(),
                        })

                # Import lazily to avoid circular imports at module load time
                from core.orchestrator.corp_worker_runner import CorpWorkerRunner

                nexus = self._get_nexus()
                if nexus is None:
                    logger.error("[CorpManager] Cannot run worker — nexus not initialized yet")
                    await asyncio.sleep(10)
                    continue

                workspace_path = str(self._workspace_path(corp_id))
                os.makedirs(workspace_path, exist_ok=True)

                runner = CorpWorkerRunner(
                    task=prompt,
                    workspace_path=workspace_path,
                    nexus=nexus,
                    step_callback=step_cb,
                    model_id=worker.get("model"),
                    state_path=self._state_path(corp_id, worker_id),
                    corp_manager=self,
                    corp_id=corp_id,
                    worker_id=worker_id,
                    worker_name=worker_name,
                )

                try:
                    summary = await asyncio.to_thread(runner.run)
                    task_status = "done"
                    stats.tasks_completed += 1
                except Exception as e:
                    summary = f"[ERROR] {e}"
                    task_status = "failed"
                    stats.tasks_failed += 1
                    logger.error(f"[CorpManager] Worker {worker_name} task failed: {e}")

                # ── Mark task done ─────────────────────────────────────────
                self.update_task(corp_id, task["task_id"],
                                 status=task_status,
                                 completed_at=datetime.utcnow().isoformat(),
                                 result_summary=(summary or "")[:500])
                self.emit(corp_id, {
                    "type":        "task_update",
                    "task_id":     task["task_id"],
                    "title":       task["title"],
                    "status":      task_status,
                    "worker_id":   worker_id,
                    "worker_name": worker_name,
                    "color":       worker_col,
                })

                stats.current_thought = f"Finished: {task['title'][:60]}"
                stats.status = "idle"
                self.emit(corp_id, {
                    "type":        "worker_stats",
                    "worker_id":   worker_id,
                    "worker_name": worker_name,
                    "color":       worker_col,
                    "stats":       stats.to_dict(),
                })

                await asyncio.sleep(1)   # brief cooldown between tasks

            except asyncio.CancelledError:
                logger.info(f"[CorpManager] Worker {worker_name} loop cancelled")
                break
            except Exception as e:
                logger.error(f"[CorpManager] Worker {worker_name} loop error: {e}")
                await asyncio.sleep(5)

        stats.status = "stopped"
        self.emit(corp_id, {
            "type":        "worker_status",
            "worker_id":   worker_id,
            "worker_name": worker_name,
            "color":       worker_col,
            "status":      "stopped",
        })

    # ── prompt builder ────────────────────────────────────────────────────────

    def _build_worker_prompt(self, corp_id: str, worker: Dict, task: Dict) -> str:
        cfg       = self.get_corp(corp_id)
        memory    = self.read_worker_memory(corp_id, worker["id"])
        recent_log = self.read_log(corp_id, last_n=20)

        tasks = self.get_tasks(corp_id)
        board_lines = []
        for t in tasks:
            if t["status"] in ("pending", "in_progress"):
                board_lines.append(
                    f"[{t['status'].upper()}] {t['task_id']}: {t['title']} "
                    f"(assigned: {t['assigned_to']})"
                )
        board_summary = "\n".join(board_lines[:12]) or "No pending tasks."

        # Build names list for assigned_to hints
        worker_names = ", ".join(
            w["name"] for w in cfg.get("workers", [])
        ) or "any"

        return (
            f"You are {worker['name']}, a {worker['role']} at {cfg['name']}.\n\n"
            f"## Company\n"
            f"{cfg['name']}: {cfg.get('description', '')}\n\n"
            f"## Your Personality\n"
            f"{worker.get('personality', 'Professional and helpful.')}\n\n"
            f"## Your Persistent Memory\n"
            f"{memory or 'No memory yet — this is your first task.'}\n\n"
            f"## Task Board (reference — do not re-assign yourself; focus on YOUR task)\n"
            f"{board_summary}\n\n"
            f"## Recent Team Messages\n"
            f"{recent_log or 'No messages yet.'}\n\n"
            f"## Your Current Task\n"
            f"{task['description']}\n\n"
            f"## Corp-Specific Tools\n"
            f"Use these ACTION types in addition to the standard write_file, search_web, etc.:\n"
            f"  ACTION: {{\"type\": \"post_to_log\", \"message\": \"...\", \"to\": \"All\"}}\n"
            f"  ACTION: {{\"type\": \"create_task\", \"title\": \"...\", \"description\": \"...\", "
            f"\"assigned_to\": \"worker_name_or_any\", \"priority\": \"medium\"}}\n"
            f"  ACTION: {{\"type\": \"update_memory\", \"content\": \"full replacement memory text\"}}\n"
            f"  ACTION: {{\"type\": \"read_log\"}}\n"
            f"  ACTION: {{\"type\": \"read_task_board\"}}\n\n"
            f"Team members (for assigned_to): {worker_names}\n\n"
            f"Guidelines:\n"
            f"- Use post_to_log when you have findings relevant to teammates.\n"
            f"- Use create_task when you identify work for another team member.\n"
            f"- Use update_memory at the end of each task to capture key context "
            f"(keep under 400 words — be concise).\n"
            f"- Complete the task thoroughly, then call "
            f'ACTION: {{"type": "done", "summary": "brief summary"}}.\n'
        )

    # ── nexus accessor ────────────────────────────────────────────────────────

    def _get_nexus(self):
        """Get the provider nexus from the global task queue manager."""
        try:
            from core.orchestrator.task_queue import get_task_queue_manager
            mgr = get_task_queue_manager()
            if mgr and mgr.orchestrator:
                return mgr.orchestrator.nexus
        except Exception as e:
            logger.warning(f"[CorpManager] Could not get nexus: {e}")
        return None


# ── Global singleton ──────────────────────────────────────────────────────────

_corp_manager: Optional[CorpManager] = None


def get_corp_manager() -> CorpManager:
    global _corp_manager
    if _corp_manager is None:
        _corp_manager = CorpManager()
    return _corp_manager
