"""
Aethvion Suite — Notification Routes
Provides GET/POST endpoints for the in-app notification system.
Notifications are persisted in data/notifications/pending.json.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pathlib import Path
from datetime import datetime, timezone
import json
import uuid

router = APIRouter()

# ── Storage path ──────────────────────────────────────────────────────────────
_PROJECT = Path(__file__).parent.parent.parent.parent  # project root
NOTIF_DIR  = _PROJECT / "data" / "notifications"
NOTIF_FILE = NOTIF_DIR / "pending.json"


def _load() -> list:
    """Load notifications from disk, returning an empty list on any failure."""
    try:
        if NOTIF_FILE.exists():
            return json.loads(NOTIF_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to load notifications: %s", exc)
    return []


def _save(notifications: list) -> None:
    """Persist notifications list to disk."""
    NOTIF_DIR.mkdir(parents=True, exist_ok=True)
    NOTIF_FILE.write_text(json.dumps(notifications, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/api/notifications")
async def get_notifications():
    """Return all notifications and unread count."""
    notifications = _load()
    unread = sum(1 for n in notifications if not n.get("read", False))
    return JSONResponse({"notifications": notifications, "unread_count": unread})


@router.post("/api/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: str):
    """Mark a single notification as read."""
    notifications = _load()
    changed = False
    for n in notifications:
        if n.get("id") == notif_id and not n.get("read", False):
            n["read"] = True
            changed = True
            break
    if changed:
        _save(notifications)
    return JSONResponse({"ok": True})


@router.post("/api/notifications/read-all")
async def mark_all_read():
    """Mark every notification as read."""
    notifications = _load()
    for n in notifications:
        n["read"] = True
    _save(notifications)
    return JSONResponse({"ok": True})


# ── Helper for other modules to push notifications ────────────────────────────

def push_notification(title: str, body: str, icon: str = "info", action_url: str | None = None) -> dict:
    """
    Append a new notification and return it.
    Safe to call from any route module.
    """
    n = {
        "id": str(uuid.uuid4()),
        "title": title,
        "body": body,
        "icon": icon,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "read": False,
        "action_url": action_url,
    }
    notifications = _load()
    notifications.insert(0, n)          # newest first
    notifications = notifications[:200]  # cap at 200 entries
    _save(notifications)
    return n
