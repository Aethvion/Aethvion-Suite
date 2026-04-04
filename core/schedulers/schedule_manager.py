"""
Aethvion Suite - Schedule Manager
Manages recurring AI tasks with cron-based scheduling.
Stores each task as data/scheduled_tasks/{task_id}.json.
No external scheduler dependencies — uses a polling background thread.
"""
import json
import re
import uuid
import threading
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # type: ignore

_UTC = ZoneInfo('UTC')

from core.utils.logger import get_logger
from core.utils import utcnow_iso

logger = get_logger(__name__)

MAX_RUNS_STORED = 50   # keep last N run records per task
POLL_INTERVAL   = 30   # seconds between scheduler checks


# ── Cron utilities ─────────────────────────────────────────────────────────────

def _field_matches(field: str, value: int, allow_7_as_0: bool = False) -> bool:
    """Return True if `value` satisfies the cron field expression."""
    if field == '*':
        return True
    # Comma-separated list
    if ',' in field:
        return any(_field_matches(f.strip(), value, allow_7_as_0) for f in field.split(','))
    # Step (e.g. */5, 0-30/5)
    if '/' in field:
        base, step_str = field.split('/', 1)
        step = int(step_str)
        if '-' in base:
            lo, hi = (int(x) for x in base.split('-', 1))
            return lo <= value <= hi and (value - lo) % step == 0
        base_val = 0 if base == '*' else int(base)
        return value >= base_val and (value - base_val) % step == 0
    # Range (e.g. 1-5)
    if '-' in field:
        lo, hi = (int(x) for x in field.split('-', 1))
        return lo <= value <= hi
    # Literal
    fv = int(field)
    if allow_7_as_0 and fv == 7:
        fv = 0
    return fv == value


def cron_matches(cron_expr: str, dt: datetime) -> bool:
    """Return True if *dt* matches a 5-field cron expression (min hr dom mon dow).

    DOW convention: 0 = Sunday … 6 = Saturday (standard cron), 7 also = Sunday.
    """
    try:
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return False
        min_f, hr_f, dom_f, mon_f, dow_f = parts
        # Python isoweekday: 1=Mon … 7=Sun  →  cron: 0=Sun,1=Mon … 6=Sat
        cron_dow = dt.isoweekday() % 7
        return (
            _field_matches(min_f, dt.minute) and
            _field_matches(hr_f, dt.hour) and
            _field_matches(dom_f, dt.day) and
            _field_matches(mon_f, dt.month) and
            _field_matches(dow_f, cron_dow, allow_7_as_0=True)
        )
    except Exception:
        return False


def _utcnow_iso() -> str:
    """Return current UTC time as an ISO-8601 string with 'Z' suffix."""
    return utcnow_iso()


def next_run_after(cron_expr: str, after: datetime = None, tz_name: str = 'UTC') -> Optional[datetime]:
    """Return the next UTC datetime matching *cron_expr* when evaluated in *tz_name*.

    The cron expression is interpreted in the task's local timezone so that e.g.
    "0 9 * * *" means 9 AM local — not 9 AM UTC.
    Returns a naive UTC datetime for storage (with 'Z' appended when serialised).
    """
    if not cron_expr:
        return None
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = _UTC

    # Start searching 1 minute after *after* (UTC), expressed in task's local timezone
    after_utc = (after or datetime.now(timezone.utc))
    if after_utc.tzinfo is None:
        after_utc = after_utc.replace(tzinfo=_UTC)
    dt_local = after_utc.astimezone(tz).replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = dt_local + timedelta(days=366 * 2)
    while dt_local <= limit:
        if cron_matches(cron_expr, dt_local):
            # Return as naive UTC datetime
            return dt_local.astimezone(_UTC).replace(tzinfo=None)
        dt_local += timedelta(minutes=1)
    return None


# ── Schedule Manager ───────────────────────────────────────────────────────────

class ScheduleManager:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.nexus = None
        self._lock = threading.Lock()
        self._stop_evt = threading.Event()
        self._checked: set = set()   # minute-keys already processed
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="ScheduleManager"
        )
        self._thread.start()
        logger.info("[ScheduleManager] Started — polling every %ds", POLL_INTERVAL)
        # Run catch-up in background so nexus can be attached first
        threading.Thread(target=self._startup_catchup, daemon=True,
                         name="ScheduleManager-catchup").start()

    def set_nexus(self, nexus) -> None:
        self.nexus = nexus

    # ── Startup catch-up ───────────────────────────────────────────

    def _startup_catchup(self):
        """On startup, fire missed runs for active tasks whose next_run_at is in the past.

        The number of immediate runs is capped by queue_max (0 = unlimited → 1 catch-up run).
        This means:
          queue_max=1  → execute once, no matter how many slots were missed
          queue_max=2  → execute twice (two back-to-back catch-up runs)
          queue_max=0  → execute once (unlimited queue, but one catch-up is enough)
        """
        # Wait briefly so nexus can be set before we try to call the AI
        import time
        time.sleep(5)

        for p in self.data_dir.glob('*.json'):
            try:
                task = json.loads(p.read_text(encoding='utf-8'))
                if task.get('status') != 'active' or not task.get('cron'):
                    continue

                nxt_iso = task.get('next_run_at')
                if not nxt_iso:
                    continue

                # Parse next_run_at as UTC
                normalised = nxt_iso if re.search(r'[Zz]$|[+-]\d{2}:\d{2}$', nxt_iso) else nxt_iso + 'Z'
                nxt_dt = datetime.fromisoformat(normalised.replace('Z', '+00:00'))
                if nxt_dt > datetime.now(timezone.utc):
                    continue   # not missed — nothing to catch up

                # Determine how many catch-up runs to fire
                qmax = task.get('queue_max', 1)
                catch_up_runs = qmax if qmax and qmax > 0 else 1
                logger.info(
                    "[ScheduleManager] Catch-up: '%s' missed run(s) — firing %d time(s)",
                    task.get('name'), catch_up_runs,
                )
                for _ in range(catch_up_runs):
                    self._execute(task, manual=False)
            except Exception as exc:
                logger.warning("[ScheduleManager] Catch-up error for %s: %s", p.name, exc)

    # ── Storage helpers ────────────────────────────────────────────

    def _path(self, task_id: str) -> Path:
        return self.data_dir / f"{task_id}.json"

    def _load(self, task_id: str) -> Optional[dict]:
        p = self._path(task_id)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            return None

    def _save(self, task: dict) -> None:
        task['updated_at'] = _utcnow_iso()
        self._path(task['id']).write_text(
            json.dumps(task, indent=2, ensure_ascii=False),
            encoding='utf-8',
        )

    # ── CRUD ──────────────────────────────────────────────────────

    def _refresh_next_run(self, task: dict) -> bool:
        """If the task is active and next_run_at is stale (in the past or missing),
        recalculate and persist it.  Returns True if the task was updated."""
        if task.get('status') != 'active' or not task.get('cron'):
            return False

        # Parse the stored next_run_at as UTC
        nxt_iso = task.get('next_run_at')
        stale = True
        if nxt_iso:
            try:
                # Normalise: add 'Z' if no timezone marker present
                normalised = nxt_iso if re.search(r'[Zz]$|[+-]\d{2}:\d{2}$', nxt_iso) else nxt_iso + 'Z'
                nxt_dt = datetime.fromisoformat(normalised.replace('Z', '+00:00'))
                stale = nxt_dt <= datetime.now(timezone.utc)
            except Exception:
                stale = True

        if not stale:
            return False

        # Recalculate from now
        new_nxt = next_run_after(task['cron'], tz_name=task.get('timezone', 'UTC'))
        task['next_run_at'] = (new_nxt.isoformat() + 'Z') if new_nxt else None
        try:
            self._save(task)
        except Exception:
            pass
        return True

    def list_tasks(self) -> list:
        out = []
        for p in self.data_dir.glob('*.json'):
            try:
                t = json.loads(p.read_text(encoding='utf-8'))
                self._refresh_next_run(t)   # heal stale next_run_at on every read
                # Strip heavy fields from list view
                out.append({k: v for k, v in t.items() if k not in ('thread', 'runs')})
            except Exception:
                pass
        return sorted(out, key=lambda x: x.get('updated_at', ''), reverse=True)

    def get_task(self, task_id: str) -> Optional[dict]:
        task = self._load(task_id)
        if task:
            self._refresh_next_run(task)
        return task

    def create_task(self, model_id: str = None) -> dict:
        now = _utcnow_iso()
        task = {
            'id': str(uuid.uuid4()),
            'name': 'New Schedule',
            'status': 'draft',          # draft → active once cron is set
            'cron': None,
            'cron_human': None,
            'timezone': 'UTC',
            'prompt': None,
            'model_id': model_id,
            'queue_max': 1,             # 0 = unlimited
            'created_at': now,
            'updated_at': now,
            'last_run_at': None,
            'next_run_at': None,
            'thread': [],
            'runs': [],
        }
        self._save(task)
        return task

    def update_task(self, task_id: str, **kwargs) -> Optional[dict]:
        with self._lock:
            task = self._load(task_id)
            if not task:
                return None
            protected = {'id', 'created_at', 'thread', 'runs'}
            for k, v in kwargs.items():
                if k not in protected:
                    task[k] = v
            # Recalculate next_run and auto-activate when cron is set/changed
            if 'cron' in kwargs and task.get('cron'):
                nxt = next_run_after(task['cron'], tz_name=task.get('timezone', 'UTC'))
                task['next_run_at'] = (nxt.isoformat() + 'Z') if nxt else None
                if task.get('status') == 'draft':
                    task['status'] = 'active'
            self._save(task)
            return task

    def add_message(self, task_id: str, role: str, content: str) -> Optional[dict]:
        with self._lock:
            task = self._load(task_id)
            if not task:
                return None
            task['thread'].append({
                'role': role,
                'content': content,
                'ts': _utcnow_iso(),
            })
            self._save(task)
            return task

    def delete_task(self, task_id: str) -> bool:
        p = self._path(task_id)
        if p.exists():
            p.unlink()
            return True
        return False

    # ── Execution ──────────────────────────────────────────────────

    def run_now(self, task_id: str) -> dict:
        """Manually trigger a run — ignores queue_max."""
        task = self._load(task_id)
        if not task:
            return {'error': 'Task not found'}
        return self._execute(task, manual=True)

    def _execute(self, task: dict, manual: bool = False) -> dict:
        task_id = task['id']
        run_id  = str(uuid.uuid4())
        now_iso = _utcnow_iso()

        run = {
            'id':           run_id,
            'triggered_at': now_iso,
            'completed_at': None,
            'manual':       manual,
            'result':       None,
            'status':       'running',
        }

        with self._lock:
            t = self._load(task_id)
            if not t:
                return {'error': 'Task not found'}

            # Queue check (automatic runs only)
            if not manual and t.get('queue_max', 1) > 0:
                pending = [r for r in t.get('runs', []) if r.get('status') in ('running', 'queued')]
                if len(pending) >= t['queue_max']:
                    logger.info(
                        "[ScheduleManager] '%s' skipped — queue full (%d/%d)",
                        t.get('name'), len(pending), t['queue_max'],
                    )
                    skip = {**run, 'status': 'skipped', 'completed_at': now_iso}
                    t.setdefault('runs', []).append(skip)
                    t['last_run_at'] = now_iso
                    t['runs'] = t['runs'][-MAX_RUNS_STORED:]
                    self._save(t)
                    return skip

            t.setdefault('runs', []).append(run)
            t['last_run_at'] = now_iso
            if t.get('cron'):
                nxt = next_run_after(t['cron'], tz_name=t.get('timezone', 'UTC'))
                t['next_run_at'] = (nxt.isoformat() + 'Z') if nxt else None
            t['runs'] = t['runs'][-MAX_RUNS_STORED:]
            self._save(t)

        # Run AI call in a thread so we don't block the caller
        def _do():
            # Lazy import to avoid circular deps at module load time
            try:
                from core.interfaces.dashboard.notification_routes import notify as _notify
            except Exception:
                _notify = None  # Notifications not available yet (early startup)

            task_name = task.get('name', 'Scheduled Task')
            task_id   = task['id']
            nav_target = {"tab": "schedule", "context": task_id}

            nav_target = {"tab": "schedule", "context": task_id}

            result_text = None
            status = 'failed'
            try:
                prompt = task.get('prompt') or f"[No prompt configured for task: {task.get('name')}]"
                if self.nexus:
                    response = self.nexus.provider_manager.call_with_failover(
                        prompt=prompt,
                        trace_id=f"sched-{run_id}",
                        temperature=0.7,
                        model=task.get('model_id'),
                        request_type='generation',
                        source='schedule',
                    )
                    result_text = response.content
                    status = 'success'
                else:
                    result_text = '(System not yet initialised — try again after startup)'
            except Exception as exc:
                result_text = f'Error: {exc}'
                logger.error("[ScheduleManager] Run %s failed: %s", run_id, exc)

            completed = _utcnow_iso()
            with self._lock:
                t2 = self._load(task_id)
                if t2:
                    for r in t2.get('runs', []):
                        if r['id'] == run_id:
                            r['result']       = result_text
                            r['status']       = status
                            r['completed_at'] = completed
                            break
                    self._save(t2)
            logger.info("[ScheduleManager] Run %s → %s", run_id, status)

            # ── Notify: task completed ─────────────────────────────────
            if _notify:
                try:
                    # Truncate result to a readable preview
                    preview = (result_text or '').strip()
                    if len(preview) > 160:
                        preview = preview[:157] + "…"

                    if status == 'success':
                        _notify(
                            title=f"✓ {task_name} — Done",
                            message=preview or "Task completed with no output.",
                            source="schedule",
                            level="success",
                            target=nav_target,
                        )
                    else:
                        _notify(
                            title=f"✗ {task_name} — Failed",
                            message=preview or "Task encountered an error.",
                            source="schedule",
                            level="error",
                            target=nav_target,
                        )
                except Exception:
                    pass

        threading.Thread(target=_do, daemon=True, name=f"sched-run-{run_id[:8]}").start()
        return run

    # ── Background loop ────────────────────────────────────────────

    def _loop(self):
        while not self._stop_evt.is_set():
            try:
                now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
                key = now_utc.strftime('%Y%m%d%H%M')
                if key not in self._checked:
                    self._checked.add(key)
                    if len(self._checked) > 20:
                        self._checked = set(sorted(self._checked)[-10:])
                    self._check_and_fire(now_utc)
            except Exception as exc:
                logger.error("[ScheduleManager] Loop error: %s", exc)
            self._stop_evt.wait(POLL_INTERVAL)

    def _check_and_fire(self, now_utc: datetime):
        """Check all active tasks and fire those whose cron matches the current local time."""
        for p in self.data_dir.glob('*.json'):
            try:
                task = json.loads(p.read_text(encoding='utf-8'))
                if task.get('status') != 'active':
                    continue
                cron = task.get('cron')
                if not cron:
                    continue
                # Convert UTC now to the task's local timezone before matching
                tz_name = task.get('timezone', 'UTC')
                try:
                    tz = ZoneInfo(tz_name)
                except Exception:
                    tz = _UTC
                now_local = now_utc.astimezone(tz)
                if cron_matches(cron, now_local):
                    logger.info("[ScheduleManager] Firing '%s' (tz=%s)", task.get('name'), tz_name)
                    threading.Thread(
                        target=self._execute,
                        args=(task, False),
                        daemon=True,
                    ).start()
            except Exception as exc:
                logger.warning("[ScheduleManager] Error checking %s: %s", p.name, exc)

    def stop(self):
        self._stop_evt.set()


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[ScheduleManager] = None


def get_schedule_manager(nexus=None) -> ScheduleManager:
    global _instance
    if _instance is None:
        from core.utils.paths import SCHEDULED_TASKS
        _instance = ScheduleManager(SCHEDULED_TASKS)
    if nexus is not None and _instance.nexus is None:
        _instance.set_nexus(nexus)
    return _instance
