"""
core/bridges/flow_state_bridge.py
Proactive Flow State & Vibe Management Connector.
Monitors user deep work/flow states, continuous session focus duration,
and ambient music vibes to empower companions with intelligent, natural
proactive check-ins (e.g. suggesting cozy music, stretch breaks, or follow-ups).
"""

from __future__ import annotations
import datetime
import time
from pathlib import Path
from typing import Any, Dict
from core.utils import load_json, atomic_json_write, get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
FLOW_STATE_FILE = PROJECT_ROOT / "data" / "bridges" / "flow_state.json"

APP_CATEGORIES = {
    "coding": [
        "code.exe", "cursor.exe", "pycharm64.exe", "idea64.exe",
        "devenv.exe", "sublime_text.exe", "nvim.exe", "windowsterminal.exe",
        "powershell.exe", "cmd.exe"
    ],
    "game_dev": [
        "unity.exe", "unrealeditor.exe", "godot.exe", "godot_v4.exe"
    ],
    "3d_art": [
        "blender.exe", "substance3d.exe", "photoshop.exe", "aseprite.exe",
        "krita.exe", "illustrator.exe"
    ],
    "browsing": [
        "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"
    ]
}


def _categorize_process(proc_name: str, title: str) -> tuple[str, str]:
    """Map process name and window title to a human-readable activity category."""
    p = proc_name.lower()
    t = title.lower()

    if any(app in p for app in APP_CATEGORIES["game_dev"]) or "unity" in t:
        return "Game Development (Unity/Engine)", "game_dev"
    if any(app in p for app in APP_CATEGORIES["3d_art"]) or "blender" in t:
        return "3D Art & Modeling (Blender)", "3d_art"
    if any(app in p for app in APP_CATEGORIES["coding"]) or "visual studio code" in t:
        return "Coding & Software Engineering", "coding"
    if any(app in p for app in APP_CATEGORIES["browsing"]):
        return "Web Research & Browsing", "browsing"
    
    return "Desktop & Multitasking", "general"


def _update_and_get_session(category_id: str, app_title: str) -> Dict[str, Any]:
    """Track continuous focus session duration across heartbeat updates."""
    FLOW_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = load_json(FLOW_STATE_FILE, default={
        "category_id": "general",
        "category_name": "General",
        "app_title": "",
        "session_start_ts": time.time(),
        "total_active_mins": 0.0,
        "last_updated_ts": time.time(),
    })

    now_ts = time.time()
    last_cat = state.get("category_id", "general")
    start_ts = state.get("session_start_ts", now_ts)
    last_updated = state.get("last_updated_ts", now_ts)

    # If gap is larger than 10 minutes, user was away/paused; reset session
    gap_minutes = (now_ts - last_updated) / 60.0
    if gap_minutes > 10.0 or last_cat != category_id:
        start_ts = now_ts
        total_mins = 0.0
    else:
        total_mins = max(0.0, (now_ts - start_ts) / 60.0)

    state["category_id"] = category_id
    state["app_title"] = app_title
    state["session_start_ts"] = start_ts
    state["total_active_mins"] = round(total_mins, 1)
    state["last_updated_ts"] = now_ts

    atomic_json_write(FLOW_STATE_FILE, state)
    return state


def _get_current_media_vibe() -> Dict[str, Any]:
    """Check whether music is currently playing via media_sentinel or spotify."""
    try:
        from core.bridges import media_sentinel
        info = media_sentinel.get_current_media()
        if info and (info.get("title") or info.get("artist")):
            return {
                "playing": True,
                "title": info.get("title", ""),
                "artist": info.get("artist", ""),
                "source": info.get("source", "Media Player"),
            }
    except Exception:
        pass
    return {"playing": False, "title": "", "artist": "", "source": ""}


def get_flow_state(args: dict = None) -> str:
    """
    Get user's current flow state, active application, focus duration,
    and ambient music vibe with tailored companion guidance.
    """
    fg_title = ""
    fg_proc = ""
    try:
        from core.bridges.window_focus_bridge import _get_windows_focus_info
        w_info = _get_windows_focus_info(max_windows=5)
        fg_title = w_info.get("foreground", {}).get("title", "")
        fg_proc = w_info.get("foreground", {}).get("process", "")
    except Exception as e:
        logger.debug(f"Window focus read failed in flow_state: {e}")

    cat_name, cat_id = _categorize_process(fg_proc, fg_title)
    session = _update_and_get_session(cat_id, fg_title)
    active_mins = session.get("total_active_mins", 0.0)

    media = _get_current_media_vibe()
    music_desc = (
        f"Playing '{media['title']}' by {media['artist']}"
        if media.get("playing")
        else "Silent (no music currently playing)"
    )

    # Vibe recommendation logic
    if active_mins >= 60.0:
        if not media.get("playing"):
            advice = (
                f"User has been focused on {cat_name} for ~{int(active_mins)} minutes in silence. "
                "Suggest a short 2-minute stretch or offer to spin up some relaxing/comfy music (e.g. via Spotify) "
                "to keep the flow enjoyable."
            )
        else:
            advice = (
                f"Deep in the zone with {cat_name} for ~{int(active_mins)} minutes with music on. "
                "Keep check-in super low-friction; a warm encouraging word or asking about current progress is ideal."
            )
    elif active_mins >= 25.0:
        advice = f"Steady flow state in {cat_name} (~{int(active_mins)} mins). Support their momentum."
    else:
        advice = f"Just settling into {cat_name} (~{int(active_mins)} mins). Ready for co-working."

    return (
        f"Flow State: {cat_name}\n"
        f"Active Window: {fg_title or fg_proc or 'Desktop'}\n"
        f"Continuous Session: ~{int(active_mins)} minutes\n"
        f"Music Vibe: {music_desc}\n"
        f"Vibe Guidance: {advice}"
    )


def suggest_vibe(args: dict = None) -> str:
    """Suggest music, energy, or rest adjustments based on current flow state."""
    return get_flow_state(args)


def get_flow_state_summary() -> str:
    """Compact summary formatted for prompt injection during proactive check-ins."""
    try:
        return get_flow_state()
    except Exception as e:
        logger.debug(f"Flow state summary error: {e}")
        return ""
