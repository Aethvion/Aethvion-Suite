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

from core.utils.logger import get_logger
from core.ai.call_contexts import CallSource, build_overlay_prompt, validate_call_context

logger = get_logger(__name__)

router = APIRouter(prefix="/api/overlay", tags=["overlay"])

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT   = Path(__file__).parent.parent.parent.parent
OVERLAY_DIR    = PROJECT_ROOT / "data" / "overlay"
CONFIG_PATH    = OVERLAY_DIR / "config.json"
OVERLAY_SCRIPT = PROJECT_ROOT / "apps" / "overlay" / "main.py"

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
    try:
        if CONFIG_PATH.exists():
            return {**_DEFAULT_CONFIG, **json.loads(CONFIG_PATH.read_text("utf-8"))}
    except Exception:
        pass
    return dict(_DEFAULT_CONFIG)


def _save_config(cfg: dict) -> None:
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


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


# ── Models ────────────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question:       str
    screenshot_b64: Optional[str] = None   # base64-encoded PNG
    model:          Optional[str] = None   # optional model override


class OverlayConfigIn(BaseModel):
    enabled:            Optional[bool]  = None
    hotkey:             Optional[str]   = None
    model:              Optional[str]   = None
    launch_with_suite:  Optional[bool]  = None
    bg_opacity:         Optional[float] = None   # 0.1 – 1.0  background opacity
    text_opacity:       Optional[float] = None   # 0.3 – 1.0  text opacity
    font_size:          Optional[int]   = None   # 8 – 18


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/ask")
async def overlay_ask(req: AskRequest):
    """Answer a question, optionally using a screenshot for visual context."""
    try:
        from core.providers.provider_manager import ProviderManager
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
        pm         = ProviderManager()
        trace_id   = f"overlay-{uuid.uuid4().hex[:12]}"
        extra_kwargs: dict = {}

        if req.screenshot_b64:
            try:
                img_data = base64.b64decode(req.screenshot_b64)
                extra_kwargs["images"] = [{"data": img_data, "mime_type": "image/png"}]
            except Exception as decode_err:
                raise ValueError(f"Could not decode screenshot: {decode_err}") from decode_err

        system_prompt = build_overlay_prompt()
        validate_call_context(CallSource.OVERLAY, system_prompt, trace_id)

        # call_with_failover is synchronous — run in a thread to avoid blocking the event loop
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: pm.call_with_failover(
                prompt=req.question,
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
        env  = __import__("os").environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        kwargs: dict = {"env": env, "cwd": str(PROJECT_ROOT)}
        if sys.platform == "win32":
            # pythonw.exe so no black console window
            venv_pyw = PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe"
            py = str(venv_pyw) if venv_pyw.exists() else "pythonw"
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            venv_py = PROJECT_ROOT / ".venv" / "bin" / "python"
            py = str(venv_py) if venv_py.exists() else "python"

        subprocess.Popen([py, str(OVERLAY_SCRIPT)], **kwargs)
        return {"status": "launched"}
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
