"""
Aethvion Suite - Overlay Sidecar Routes
Backend endpoints for the desktop overlay "Ask about screen" feature.

  POST /api/overlay/ask           — answer a question with optional screenshot
  GET  /api/overlay/config        — read overlay settings
  POST /api/overlay/config        — save overlay settings
  GET  /api/overlay/status        — check if the overlay sidecar is running
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import psutil
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.utils import get_logger, atomic_json_write, load_json
from core.utils.paths import OVERLAY_DIR, OVERLAY_CONFIG, OVERLAY_SCRIPT
from core.ai.call_contexts import CallSource, build_overlay_prompt, validate_call_context

_HISTORY_DIR = OVERLAY_DIR / "history"

logger = get_logger(__name__)

router = APIRouter(prefix="/api/overlay", tags=["overlay"])

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent   # used for .venv, cwd, logs

_DEFAULT_CONFIG = {
    "enabled": False,
    "hotkey":  "ctrl+shift+space",
    "model":   None,        # None = use system.info_model
    "launch_with_suite": False,
    "bg_opacity":   0.93,   # container background opacity (0.1 – 1.0)
    "text_opacity": 1.0,    # text / content opacity (0.3 – 1.0)
    "font_size": 11,        # response/input font size in pt
}


def _load_config() -> dict:
    return {**_DEFAULT_CONFIG, **load_json(OVERLAY_CONFIG, default={})}


def _save_config(cfg: dict) -> None:
    atomic_json_write(OVERLAY_CONFIG, cfg)


def _overlay_running() -> bool:
    """Return True if the overlay sidecar process is currently running."""
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if "apps/overlay/main.py" in cmdline or "apps\\overlay\\main.py" in cmdline:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


# Models

class HistoryPair(BaseModel):
    q: str
    a: str

class AskRequest(BaseModel):
    question:       str
    screenshot_b64: Optional[str]        = None   # base64-encoded PNG (current screenshot)
    model:          Optional[str]        = None   # optional model override
    history:        Optional[list[HistoryPair]] = None  # prior Q/A pairs (same-thread mode)


class OverlayConfigIn(BaseModel):
    enabled:            Optional[bool]  = None
    hotkey:             Optional[str]   = None
    model:              Optional[str]   = None
    launch_with_suite:  Optional[bool]  = None
    bg_opacity:         Optional[float] = None   # 0.1 – 1.0  background opacity
    text_opacity:       Optional[float] = None   # 0.3 – 1.0  text opacity
    font_size:          Optional[int]   = None   # 8 – 18


# Routes

@router.post("/ask")
async def overlay_ask(req: AskRequest):
    """Answer a question, optionally using a screenshot for visual context."""
    try:
        from core.providers.provider_manager import get_provider_manager
        from core.workspace.preferences_manager import get_preferences_manager

        prefs = get_preferences_manager()
        cfg   = _load_config()

        model_id = (
            req.model
            or cfg.get("model")
            or prefs.get("system.info_model")
            or prefs.get("ai.default_model")
            or "flash"
        )

        logger.info(f"Overlay ask — model: {model_id!r}, has_screenshot: {bool(req.screenshot_b64)}")

        import asyncio, uuid
        pm         = get_provider_manager()
        trace_id   = f"overlay-{uuid.uuid4().hex[:12]}"
        extra_kwargs: dict = {}

        if req.screenshot_b64:
            try:
                img_data = base64.b64decode(req.screenshot_b64)
                extra_kwargs["images"] = [{"data": img_data, "mime_type": "image/png"}]
            except Exception as decode_err:
                raise ValueError(f"Could not decode screenshot: {decode_err}") from decode_err

        # Build the prompt — prepend conversation history when in same-thread mode
        question = req.question
        if req.history:
            history_lines = []
            for pair in req.history:
                history_lines.append(f"User: {pair.q}")
                history_lines.append(f"Assistant: {pair.a}")
            history_block = "\n\n".join(history_lines)
            question = (
                f"[Previous conversation in this session — a new screenshot has been taken:]\n"
                f"{history_block}\n\n"
                f"[Current question about the new screenshot:]\n{req.question}"
            )

        system_prompt = build_overlay_prompt()
        validate_call_context(CallSource.OVERLAY, system_prompt, trace_id)

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: pm.call_with_failover(
                prompt=question,
                trace_id=trace_id,
                system_prompt=system_prompt,
                model=model_id,
                max_tokens=1024,
                source=CallSource.OVERLAY,
                **extra_kwargs,
            ),
        )
        return {"answer": response.content, "model_used": model_id}

    except Exception as e:
        logger.error(f"Overlay ask error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"[model: {model_id if 'model_id' in dir() else 'unknown'}] {e}")


@router.get("/config")
async def overlay_get_config():
    """Return the current overlay configuration."""
    return _load_config()


@router.post("/config")
async def overlay_save_config(body: OverlayConfigIn):
    """Persist overlay configuration changes."""
    cfg = _load_config()
    if body.enabled            is not None: cfg["enabled"]            = body.enabled
    if body.hotkey             is not None: cfg["hotkey"]             = body.hotkey.strip()
    if body.model              is not None: cfg["model"]              = body.model or None
    if body.launch_with_suite  is not None: cfg["launch_with_suite"]  = body.launch_with_suite
    if body.bg_opacity         is not None: cfg["bg_opacity"]         = max(0.1, min(1.0, body.bg_opacity))
    if body.text_opacity       is not None: cfg["text_opacity"]       = max(0.3, min(1.0, body.text_opacity))
    if body.font_size          is not None: cfg["font_size"]          = max(8, min(18, body.font_size))
    # Back-compat: migrate legacy "opacity" key to "bg_opacity"
    if "opacity" in cfg and "bg_opacity" not in cfg:
        cfg["bg_opacity"] = cfg.pop("opacity")
    elif "opacity" in cfg:
        del cfg["opacity"]
    _save_config(cfg)
    return cfg


@router.get("/status")
async def overlay_status():
    """Check whether the overlay sidecar process is currently running."""
    running = _overlay_running()
    deps    = _check_deps()
    return {
        "running":      running,
        "script_exists": OVERLAY_SCRIPT.exists(),
        "deps":         deps,
    }


@router.post("/launch")
async def overlay_launch():
    """Start the overlay sidecar process (non-blocking)."""
    if not OVERLAY_SCRIPT.exists():
        raise HTTPException(status_code=404, detail="Overlay script not found.")
    if _overlay_running():
        return {"status": "already_running"}

    try:
        import os
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)

        # Always redirect stdout/stderr to a log file so crashes are never silent
        log_dir  = PROJECT_ROOT / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "overlay.log"
        log_file = open(log_path, "a", encoding="utf-8")

        kwargs: dict = {
            "env": env,
            "cwd": str(PROJECT_ROOT),
            "stdout": log_file,
            "stderr": log_file,
        }

        if sys.platform == "win32":
            # Use regular python.exe (not pythonw.exe) with CREATE_NO_WINDOW so
            # there's no black console window but stderr is still captured to log.
            venv_py = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
            py = str(venv_py) if venv_py.exists() else "python"
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            venv_py = PROJECT_ROOT / ".venv" / "bin" / "python"
            py = str(venv_py) if venv_py.exists() else "python"

        subprocess.Popen([py, str(OVERLAY_SCRIPT)], **kwargs)
        logger.info(f"Overlay launched — log: {log_path}")
        return {"status": "launched", "log": str(log_path)}
    except Exception as e:
        logger.error(f"Overlay launch error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def overlay_stop():
    """Terminate the running overlay sidecar process."""
    stopped = 0
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if "apps/overlay/main.py" in cmdline or "apps\\overlay\\main.py" in cmdline:
                proc.terminate()
                stopped += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return {"stopped": stopped}


def _check_deps() -> dict:
    """Report which optional overlay dependencies are importable."""
    results = {}
    for pkg, import_name in [
        ("PyQt6",    "PyQt6"),
        ("pystray",  "pystray"),
        ("Pillow",   "PIL"),
        ("mss",      "mss"),
        ("keyboard", "keyboard"),
    ]:
        try:
            __import__(import_name)
            results[pkg] = True
        except ImportError:
            results[pkg] = False
    return results


def _find_venv_pip() -> str:
    """Return the pip executable inside the project's .venv, falling back to sys.executable -m pip."""
    pip_win  = PROJECT_ROOT / ".venv" / "Scripts" / "pip.exe"
    pip_unix = PROJECT_ROOT / ".venv" / "bin" / "pip"
    if pip_win.exists():
        return str(pip_win)
    if pip_unix.exists():
        return str(pip_unix)
    # Fallback: use the currently running Python's pip module
    return None   # signal to caller to use `sys.executable -m pip`


@router.post("/install-deps")
async def overlay_install_deps():
    """
    Install the overlay's required Python packages into the project .venv.
    Returns combined stdout/stderr from pip so the frontend can display it.
    """
    import asyncio

    packages = ["PyQt6", "pystray", "Pillow", "mss", "keyboard"]

    pip_exe = _find_venv_pip()
    if pip_exe:
        cmd = [pip_exe, "install"] + packages
    else:
        cmd = [sys.executable, "-m", "pip", "install"] + packages

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
        output    = stdout.decode("utf-8", errors="replace")
        success   = proc.returncode == 0
        return {
            "success":   success,
            "returncode": proc.returncode,
            "output":    output,
            "deps":      _check_deps(),   # re-check after install
        }
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="pip install timed out after 5 minutes.")
    except Exception as e:
        logger.error(f"overlay install-deps error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── History API ────────────────────────────────────────────────────────────────

_HIST_PAGE_SIZE = 15


def _month_dir_for(session_id: str) -> Path:
    return _HISTORY_DIR / f"{session_id[:4]}-{session_id[4:6]}"


def _list_all_sessions(pinned_only: bool = False) -> list[dict]:
    """Aggregate all month index entries, newest first."""
    entries: list[dict] = []
    if not _HISTORY_DIR.exists():
        return entries
    for md in sorted(_HISTORY_DIR.iterdir(), reverse=True):
        if not md.is_dir():
            continue
        ip = md / "index.json"
        if not ip.exists():
            continue
        try:
            for e in json.loads(ip.read_text("utf-8")):
                e["_month_dir"] = str(md)
                entries.append(e)
        except Exception:
            pass
    entries.sort(key=lambda e: e.get("id", ""), reverse=True)
    if pinned_only:
        entries = [e for e in entries if e.get("is_pinned")]
    return entries


def _read_session_json(session_id: str) -> Optional[dict]:
    sp = _month_dir_for(session_id) / "sessions" / f"{session_id}.json"
    if not sp.exists():
        return None
    try:
        return json.loads(sp.read_text("utf-8"))
    except Exception:
        return None


def _write_session_json(session_id: str, data: dict) -> bool:
    sp = _month_dir_for(session_id) / "sessions" / f"{session_id}.json"
    if not sp.exists():
        return False
    try:
        sp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def _update_index_entry(session_id: str, **fields) -> None:
    """Patch specific fields on the month index entry for a session (best-effort)."""
    ip = _month_dir_for(session_id) / "index.json"
    if not ip.exists():
        return
    try:
        index: list = json.loads(ip.read_text("utf-8"))
        for entry in index:
            if entry.get("id") == session_id:
                entry.update(fields)
                break
        ip.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"overlay: could not update index entry {session_id}: {e}")


def _attach_thumb(entry: dict) -> None:
    """Inject thumb_b64 into an index entry dict if the file exists."""
    md_str = entry.pop("_month_dir", None)
    sid = entry.get("id", "")
    if md_str and sid:
        tp = Path(md_str) / "thumbs" / f"{sid}.jpg"
        if tp.exists():
            try:
                entry["thumb_b64"] = base64.b64encode(tp.read_bytes()).decode("utf-8")
            except Exception:
                pass


def _create_chat_thread_from_overlay(session: dict) -> str:
    """Seed a new ChatThread with the overlay session's Q/A pairs as completed tasks."""
    import uuid
    from datetime import datetime, timezone
    from core.orchestrator.task_queue import get_task_queue_manager
    from core.orchestrator.task_models import Task, TaskStatus

    tm = get_task_queue_manager()
    sid = session.get("id", uuid.uuid4().hex)
    thread_id = f"overlay-{sid}"

    pairs = [p for p in session.get("pairs", []) if isinstance(p, dict) and p.get("q")]
    first_q = pairs[0]["q"] if pairs else "Overlay Session"
    title = (first_q[:57] + "…") if len(first_q) > 60 else first_q

    tm.create_thread(thread_id, title=title, mode="chat_only")
    thread = tm.threads.get(thread_id)
    if not thread:
        raise RuntimeError(f"Failed to create thread {thread_id}")

    now = datetime.now(timezone.utc)
    for i, pair in enumerate(pairs):
        task_id = f"ovl-{sid}-{i}"
        task = Task(
            id=task_id,
            thread_id=thread_id,
            prompt=pair["q"],
            status=TaskStatus.COMPLETED,
            created_at=now,
            started_at=now,
            completed_at=now,
            result={
                "response":      pair.get("a") or "",
                "actions_taken": [],
                "model_id":      "overlay",
            },
            metadata={
                "source":             "overlay",
                "overlay_session_id": sid,
            },
        )
        tm.tasks[task_id] = task
        thread.task_ids.append(task_id)
        tm._save_task(task)

    tm._save_thread(thread_id)
    return thread_id


# History endpoints

@router.get("/history")
async def overlay_history(page: int = 0, pinned: bool = False):
    """
    List overlay sessions, newest first.
    ?pinned=true returns only pinned sessions.
    """
    entries = _list_all_sessions(pinned_only=pinned)
    total   = len(entries)
    total_pages = max(1, (total + _HIST_PAGE_SIZE - 1) // _HIST_PAGE_SIZE)
    page    = max(0, min(page, total_pages - 1))
    page_entries = entries[page * _HIST_PAGE_SIZE : (page + 1) * _HIST_PAGE_SIZE]
    for e in page_entries:
        _attach_thumb(e)
    return {
        "sessions":    page_entries,
        "page":        page,
        "total_pages": total_pages,
        "total":       total,
    }


@router.get("/history/{session_id}")
async def overlay_get_session(session_id: str):
    """Return a single overlay session with full Q/A pairs and thumbnail."""
    data = _read_session_json(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    md = _month_dir_for(session_id)
    tp = md / "thumbs" / f"{session_id}.jpg"
    if tp.exists():
        try:
            data["thumb_b64"] = base64.b64encode(tp.read_bytes()).decode("utf-8")
        except Exception:
            pass
    return data


@router.post("/history/{session_id}/pin")
async def overlay_pin_session(session_id: str):
    """Toggle the pin state of an overlay session."""
    data = _read_session_json(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    new_state = not bool(data.get("is_pinned", False))
    data["is_pinned"] = new_state
    if not _write_session_json(session_id, data):
        raise HTTPException(status_code=500, detail="Could not persist session")
    _update_index_entry(session_id, is_pinned=new_state)
    return {"session_id": session_id, "is_pinned": new_state}


@router.post("/history/{session_id}/promote")
async def overlay_promote_session(session_id: str):
    """
    Promote an overlay session to a proper Chat thread.
    If already promoted, returns the existing thread ID without recreating it.
    """
    data = _read_session_json(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")

    if data.get("promoted") and data.get("promoted_thread_id"):
        return {
            "session_id":      session_id,
            "thread_id":       data["promoted_thread_id"],
            "already_promoted": True,
        }

    try:
        thread_id = _create_chat_thread_from_overlay(data)
    except Exception as e:
        logger.error(f"overlay promote error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    data["promoted"]           = True
    data["promoted_thread_id"] = thread_id
    _write_session_json(session_id, data)
    _update_index_entry(session_id, promoted=True, promoted_thread_id=thread_id)

    return {
        "session_id":       session_id,
        "thread_id":        thread_id,
        "already_promoted": False,
    }
