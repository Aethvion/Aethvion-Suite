"""
core/bridges/companion_timer_bridge.py
Companion Self-Scheduled Proactive Timers & Follow-ups Connector.
Allows companions (and users via /timer or /followup) to schedule intelligent,
context-aware check-ins and follow-ups dynamically rather than waiting for static intervals.
"""

from __future__ import annotations
import datetime
import re
import time
import uuid
from pathlib import Path
from typing import Any, Optional
from core.utils import load_json, atomic_json_write, get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
TIMERS_FILE = PROJECT_ROOT / "data" / "bridges" / "companion_timers.json"


def _load_timers() -> list[dict]:
    TIMERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = load_json(TIMERS_FILE, default={"timers": []})
    return data.get("timers", [])


def _save_timers(timers: list[dict]) -> None:
    TIMERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_json_write(TIMERS_FILE, {"timers": timers})


def parse_duration_minutes(raw: Any) -> float:
    """Parse float minutes from numbers or strings like '5m', '10 mins', '1.5h', '30s', 'in 5 minutes'."""
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    
    s = str(raw).strip().lower()
    if not s:
        return 0.0
    
    # Try direct float
    try:
        return float(s)
    except ValueError:
        pass
    
    m = re.match(r"^(?:in\s+)?(\d+(?:\.\d+)?)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours)\b", s)
    if m:
        val = float(m.group(1))
        unit = m.group(2)
        if unit.startswith("s"):
            return round(val / 60.0, 3)
        if unit.startswith("h"):
            return val * 60.0
        return val
    
    # Extract any first number found
    m_num = re.search(r"\b(\d+(?:\.\d+)?)\b", s)
    if m_num:
        return float(m_num.group(1))
    
    return 0.0


def set_timer(args: dict = None) -> str:
    """
    Schedule a companion proactive follow-up timer.
    Args:
      - companion_id: ID of the companion setting the timer (defaults to active/caller)
      - minutes / delay_minutes: How many minutes until the timer triggers (float or string e.g. '5', '10m', '0.5')
      - reason / topic: Brief label or reason for the timer
      - context / prompt: What the companion should follow up on when the timer expires
    """
    if args is None:
        args = {}
    
    companion_id = str(args.get("companion_id") or "misakacipher").strip()
    raw_duration = (
        args.get("delay_minutes")
        or args.get("minutes")
        or args.get("duration")
        or args.get("time")
        or args.get("text")
        or 5.0
    )
    
    mins = parse_duration_minutes(raw_duration)
    if mins <= 0:
        mins = 5.0
    
    reason = str(args.get("reason") or args.get("topic") or args.get("task") or "Proactive follow-up").strip()
    context = str(
        args.get("context")
        or args.get("prompt")
        or args.get("instruction")
        or reason
    ).strip()
    
    # If the user passed everything in text (e.g. via slash command "/timer 5m check shader compile")
    raw_text = str(args.get("text") or "").strip()
    if raw_text and not args.get("reason"):
        parsed_mins = parse_duration_minutes(raw_text)
        if parsed_mins > 0:
            mins = parsed_mins
            cleaned = re.sub(r"^(?:in\s+)?\d+(?:\.\d+)?\s*(?:s|sec|secs|m|min|mins|minute|minutes|h|hr|hrs|hour|hours)?\s*", "", raw_text, flags=re.IGNORECASE).strip()
            if cleaned:
                reason = cleaned
                context = cleaned

    now_ts = time.time()
    due_ts = now_ts + (mins * 60.0)
    due_str = datetime.datetime.fromtimestamp(due_ts).strftime("%H:%M")
    timer_id = f"tm_{uuid.uuid4().hex[:6]}"
    
    item = {
        "id": timer_id,
        "companion_id": companion_id,
        "reason": reason,
        "context": context,
        "minutes": mins,
        "created_at": datetime.datetime.now().isoformat(),
        "due_ts": due_ts,
        "due_str": due_str,
        "status": "pending",
        "triggered_at": None,
        "response": None,
    }
    
    timers = _load_timers()
    timers.append(item)
    _save_timers(timers)
    
    return (
        f"Timer scheduled (#{timer_id}): Proactive follow-up in {mins:g} min (at {due_str}) "
        f"for companion '{companion_id}' on '{reason}'. "
        f"I'll proactively check back in when the timer arrives!"
    )


def list_timers(args: dict = None) -> str:
    """List pending proactive follow-up timers."""
    timers = _load_timers()
    now_ts = time.time()
    target_cid = str(args.get("companion_id") or "").strip() if args else ""
    
    pending = [
        t for t in timers
        if t.get("status") == "pending"
        and (not target_cid or t.get("companion_id") == target_cid)
    ]
    
    if not pending:
        return "No pending companion follow-up timers."
    
    lines = [f"Active Companion Follow-Up Timers ({len(pending)}):"]
    for idx, t in enumerate(pending, 1):
        rem_sec = max(0, float(t.get("due_ts", 0)) - now_ts)
        rem_min = round(rem_sec / 60.0, 1)
        lines.append(
            f"  {idx}. [#{t['id']}] {t.get('companion_id')} — '{t.get('reason')}' "
            f"(in ~{rem_min} min at {t.get('due_str')}) — Context: {t.get('context', '')[:60]}"
        )
    return "\n".join(lines)


def cancel_timer(args: dict = None) -> str:
    """Cancel a pending timer by 'id'."""
    if args is None:
        args = {}
    target_id = str(args.get("id") or args.get("timer_id") or args.get("text") or "").strip().lstrip("#").lower()
    if not target_id:
        return "Timer Error: Provide 'id' of the timer to cancel."
    
    timers = _load_timers()
    matched = None
    for t in timers:
        if t.get("status") == "pending" and (t["id"].lower() == target_id or target_id in t["id"].lower()):
            t["status"] = "cancelled"
            matched = t
            break
            
    if not matched:
        return f"No pending timer matching '{target_id}' found."
        
    _save_timers(timers)
    return f"Cancelled companion follow-up timer #{matched['id']} ('{matched.get('reason')}')."


def get_due_timers(companion_id: Optional[str] = None) -> list[dict]:
    """Peek at all pending timers whose due_ts has arrived."""
    timers = _load_timers()
    now_ts = time.time()
    due = []
    for t in timers:
        if t.get("status") == "pending" and now_ts >= float(t.get("due_ts", 0)):
            if not companion_id or t.get("companion_id") == companion_id:
                due.append(t)
    return due


def pop_due_companion_timers(companion_id: Optional[str] = None) -> list[dict]:
    """Atomically find and mark pending timers whose due_ts has passed as 'processing'."""
    timers = _load_timers()
    now_ts = time.time()
    due = []
    changed = False
    
    for t in timers:
        if t.get("status") == "pending" and now_ts >= float(t.get("due_ts", 0)):
            if not companion_id or t.get("companion_id") == companion_id:
                t["status"] = "processing"
                due.append(t)
                changed = True
                
    if changed:
        _save_timers(timers)
        
    return due


def mark_timer_completed(timer_id: str, response: str = "") -> bool:
    """Mark a timer completed with generated companion response."""
    timers = _load_timers()
    changed = False
    for t in timers:
        if t.get("id") == timer_id:
            t["status"] = "completed"
            t["triggered_at"] = datetime.datetime.now().isoformat()
            t["response"] = response
            changed = True
            break
    if changed:
        _save_timers(timers)
    return changed
