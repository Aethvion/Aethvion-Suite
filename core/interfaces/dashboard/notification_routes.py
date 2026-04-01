"""
Aethvion Suite - Notification Routes
REST API for the in-app notification system.
Push, fetch, and dismiss notifications. Persisted per-day in data/logs/notifications/.
"""

import json
import uuid
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.utils import get_logger
from core.utils.paths import LOGS_NOTIFICATIONS

logger = get_logger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

# ── Storage path ──────────────────────────────────────────────────────────────
NOTIFICATIONS_DIR = LOGS_NOTIFICATIONS
_lock = threading.Lock()

# ── In-memory active (unseen) store — loaded from disk on first access ────────
_active: Dict[str, Dict[str, Any]] = {}   # id -> notification
_loaded_today = False


# ── Pydantic models ───────────────────────────────────────────────────────────

class NotificationTarget(BaseModel):
    """Optional navigation target — what to open when the notification is clicked."""
    tab: Optional[str] = None          # e.g. "agents", "schedule", "chat"
    context: Optional[str] = None      # e.g. a thread_id or agent_id


class PushNotificationRequest(BaseModel):
    title: str
    message: str
    source: str = "system"             # e.g. "agents", "schedule", "system"
    level: str = "info"                # info | success | warning | error
    target: Optional[NotificationTarget] = None


# ── Storage helpers ───────────────────────────────────────────────────────────

def _day_path(dt: Optional[datetime] = None) -> Path:
    dt = dt or datetime.utcnow()
    month_str = dt.strftime("%Y-%m")
    day_str = dt.strftime("%Y-%m-%d")
    dir_path = NOTIFICATIONS_DIR / month_str
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / f"{day_str}.json"


def _load_day(dt: Optional[datetime] = None) -> List[Dict[str, Any]]:
    path = _day_path(dt)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to load notifications from {path}: {e}")
    return []


def _save_day(entries: List[Dict[str, Any]], dt: Optional[datetime] = None) -> None:
    path = _day_path(dt)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save notifications to {path}: {e}")


def _ensure_loaded() -> None:
    """Load today's unseen notifications into memory on first call."""
    global _loaded_today
    if _loaded_today:
        return
    with _lock:
        if _loaded_today:
            return
        entries = _load_day()
        for entry in entries:
            if not entry.get("seen", False):
                _active[entry["id"]] = entry
        _loaded_today = True
        logger.info(f"Loaded {len(_active)} active notifications from disk")


def _append_to_day(notification: Dict[str, Any]) -> None:
    """Append a single notification to today's file."""
    with _lock:
        entries = _load_day()
        # Replace if id already exists (e.g. dismissal update), else append
        existing_ids = {e["id"] for e in entries}
        if notification["id"] in existing_ids:
            entries = [notification if e["id"] == notification["id"] else e for e in entries]
        else:
            entries.append(notification)
        _save_day(entries)


def _update_in_day(notification_id: str, updates: Dict[str, Any]) -> None:
    """Update specific fields of a notification in today's file."""
    with _lock:
        entries = _load_day()
        for entry in entries:
            if entry["id"] == notification_id:
                entry.update(updates)
                break
        _save_day(entries)


# ── Internal Python API — call this from other modules ────────────────────────

def notify(
    title: str,
    message: str,
    source: str = "system",
    level: str = "info",
    target: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Push a notification directly in-process (no HTTP round-trip).

    Usage from any module::

        from core.interfaces.dashboard.notification_routes import notify
        notify(
            title="Task Done",
            message="MyTask completed successfully.",
            source="schedule",
            level="success",
            target={"tab": "schedule"},
        )

    ``target`` keys:
        tab      — dashboard tab to navigate to (e.g. "schedule", "agents", "chat")
        context  — optional sub-context (e.g. task_id, thread_id)
    """
    _ensure_loaded()

    now = datetime.utcnow()
    notif_id = f"notif-{int(now.timestamp() * 1000)}-{uuid.uuid4().hex[:6]}"

    notification: Dict[str, Any] = {
        "id":        notif_id,
        "timestamp": now.isoformat() + "Z",
        "title":     title,
        "message":   message,
        "source":    source,
        "level":     level,
        "target":    target,
        "seen":      False,
    }

    with _lock:
        _active[notif_id] = notification

    _append_to_day(notification)
    logger.info("Notification pushed: [%s] %s (source=%s)", level, title, source)
    return notification


# ── API Endpoints ─────────────────────────────────────────────────────────────

@router.post("/", response_model=Dict[str, Any], summary="Push a new notification")
async def push_notification(req: PushNotificationRequest):
    """
    Push a new notification into the system.
    Called by any feature that wants to surface information to the user.
    """
    _ensure_loaded()

    now = datetime.utcnow()
    notif_id = f"notif-{int(now.timestamp() * 1000)}-{uuid.uuid4().hex[:6]}"

    notification = {
        "id": notif_id,
        "timestamp": now.isoformat() + "Z",
        "title": req.title,
        "message": req.message,
        "source": req.source,
        "level": req.level,
        "target": req.target.model_dump() if req.target else None,
        "seen": False,
    }

    with _lock:
        _active[notif_id] = notification

    _append_to_day(notification)
    logger.info(f"Notification pushed: [{req.level}] {req.title} (source={req.source})")

    return notification


@router.get("/active", response_model=List[Dict[str, Any]], summary="Get all active (unseen) notifications")
async def get_active_notifications():
    """Returns all unseen notifications, newest first."""
    _ensure_loaded()
    with _lock:
        items = list(_active.values())
    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return items


@router.post("/{notification_id}/dismiss", response_model=Dict[str, Any], summary="Dismiss a notification")
async def dismiss_notification(notification_id: str):
    """
    Mark a notification as seen. It is removed from the active list
    but remains in the per-day backlog file.
    """
    _ensure_loaded()
    with _lock:
        notif = _active.pop(notification_id, None)

    if notif is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif["seen"] = True
    notif["dismissed_at"] = datetime.utcnow().isoformat() + "Z"
    _update_in_day(notification_id, {"seen": True, "dismissed_at": notif["dismissed_at"]})

    return {"status": "dismissed", "id": notification_id}


@router.get("/history", response_model=List[Dict[str, Any]], summary="Get notification backlog")
async def get_notification_history(
    days: int = Query(default=7, ge=1, le=90, description="Number of past days to include"),
    source: Optional[str] = Query(default=None, description="Filter by source"),
    level: Optional[str] = Query(default=None, description="Filter by level"),
):
    """
    Returns all notifications (seen + unseen) from the last N days, newest first.
    Useful for the backlog / history view.
    """
    from datetime import timedelta
    now = datetime.utcnow()
    all_entries: List[Dict[str, Any]] = []

    for i in range(days):
        dt = now - timedelta(days=i)
        entries = _load_day(dt)
        all_entries.extend(entries)

    # Apply filters
    if source:
        all_entries = [e for e in all_entries if e.get("source") == source]
    if level:
        all_entries = [e for e in all_entries if e.get("level") == level]

    all_entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return all_entries


@router.delete("/active/clear", summary="Clear all active notifications")
async def clear_all_active():
    """Dismiss all active notifications at once."""
    _ensure_loaded()
    now_str = datetime.utcnow().isoformat() + "Z"
    with _lock:
        ids_to_clear = list(_active.keys())
        _active.clear()

    for notif_id in ids_to_clear:
        _update_in_day(notif_id, {"seen": True, "dismissed_at": now_str})

    return {"status": "cleared", "count": len(ids_to_clear)}
