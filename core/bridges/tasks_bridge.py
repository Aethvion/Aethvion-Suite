"""
core/bridges/tasks_bridge.py
Co-Working Tasks, Timers & Reminders Connector.
Allows users (/remind) and companions to manage a shared co-working checklist
and set timed reminders that trigger a Companion Floating Popup when due.
"""

import datetime
import re
import time
import uuid
from pathlib import Path
from core.utils import load_json, atomic_json_write

PROJECT_ROOT = Path(__file__).parent.parent.parent
TASKS_FILE = PROJECT_ROOT / "data" / "bridges" / "companion_tasks.json"


def _load_tasks() -> list[dict]:
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = load_json(TASKS_FILE, default={"tasks": []})
    return data.get("tasks", [])


def _save_tasks(tasks: list[dict]) -> None:
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_json_write(TASKS_FILE, {"tasks": tasks})


def _parse_minutes_from_text(text: str) -> tuple[int, str]:
    """Extract leading or inline duration like 'in 15m', '20 min', '1h' from a reminder string."""
    m = re.match(r"^(?:in\s+)?(\d+)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours)\b\s*(.*)$", text.strip(), re.IGNORECASE)
    if m:
        val = int(m.group(1))
        unit = m.group(2).lower()
        mins = val * 60 if unit.startswith("h") else val
        rest = m.group(3).strip() or text.strip()
        return mins, rest
    return 0, text.strip()


def add_task(args: dict = None) -> str:
    """Add a co-working task or timed reminder. Args: 'text' (required), optional 'remind_in_minutes' (int)."""
    if args is None:
        args = {}
    raw_text = str(args.get("text") or args.get("task") or args.get("note") or args.get("query") or "").strip()
    if not raw_text:
        return list_tasks(args)

    remind_mins = int(args.get("remind_in_minutes") or args.get("minutes") or 0)
    if remind_mins <= 0:
        parsed_mins, cleaned = _parse_minutes_from_text(raw_text)
        if parsed_mins > 0:
            remind_mins = parsed_mins
            raw_text = cleaned

    now_ts = time.time()
    due_ts = (now_ts + remind_mins * 60) if remind_mins > 0 else None
    due_str = (
        datetime.datetime.fromtimestamp(due_ts).strftime("%H:%M")
        if due_ts
        else None
    )

    tasks = _load_tasks()
    item = {
        "id": uuid.uuid4().hex[:6],
        "text": raw_text,
        "done": False,
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "due_ts": due_ts,
        "due_str": due_str,
        "notified": False,
    }
    tasks.append(item)
    _save_tasks(tasks)

    if due_str:
        return f"Timer & Reminder set (#{item['id']}): '{raw_text}' — due in {remind_mins} min (at {due_str})."
    return f"Added co-working task (#{item['id']}): '{raw_text}'."


def list_tasks(args: dict = None) -> str:
    """List all active co-working tasks and pending reminders."""
    tasks = _load_tasks()
    open_tasks = [t for t in tasks if not t.get("done")]
    if not open_tasks:
        return "Co-Working Tasks & Reminders: All caught up! No active tasks or timers."

    lines = [f"Active Co-Working Tasks & Reminders ({len(open_tasks)}):"]
    for idx, t in enumerate(open_tasks, 1):
        due_badge = f" [Due at {t['due_str']}]" if t.get("due_str") else ""
        lines.append(f"  {idx}. [#{t['id']}] {t['text']}{due_badge}")
    return "\n".join(lines)


def complete_task(args: dict = None) -> str:
    """Mark a co-working task or reminder as completed by 'id' or 'text' match."""
    if args is None:
        args = {}
    target = str(args.get("id") or args.get("task") or args.get("text") or "").strip().lstrip("#").lower()
    if not target:
        return "Tasks Error: Provide 'id' or 'text' of the task to complete."

    tasks = _load_tasks()
    matched = None
    for t in tasks:
        if not t.get("done") and (t["id"].lower() == target or target in t["text"].lower()):
            t["done"] = True
            matched = t
            break

    if not matched:
        return f"No open task matching '{target}' found."
    _save_tasks(tasks)
    return f"Completed task #{matched['id']}: '{matched['text']}'."


def pop_due_reminders() -> list[dict]:
    """Return any reminders whose due_ts has passed and mark them notified."""
    tasks = _load_tasks()
    now_ts = time.time()
    due_list = []
    changed = False
    for t in tasks:
        if not t.get("done") and not t.get("notified") and t.get("due_ts"):
            if now_ts >= float(t["due_ts"]):
                t["notified"] = True
                due_list.append(t)
                changed = True
    if changed:
        _save_tasks(tasks)
    return due_list
