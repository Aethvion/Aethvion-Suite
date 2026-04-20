"""
core/launcher.py
----------------
Aethvion Suite - Master Process Launcher

Starts every app server as a child process, tracks their PIDs, and cleans them
all up on exit (Ctrl-C, SIGTERM, window-close, or normal return).

On Windows a Job Object with KillOnJobClose is installed so that all child
processes are automatically killed even if the launcher is force-killed by the
task manager or by closing the console window.

Modes
-----
  --consumer   Silent consumer mode.  Uses pythonw.exe + CREATE_NO_WINDOW so
               no black CMD windows are visible anywhere.

  --dev        Developer mode.  Uses python.exe so each server gets its own
               visible console window with live log output.

Browser flags
-------------
  --browser app   Open the dashboard in Chrome/Edge --app= mode (no URL bar).
  --browser web   Open the dashboard in a normal browser tab.
  --browser none  Do not open any browser automatically.

Optional flags
--------------
  --apps all                Start every optional app (default).
  --apps none               Start only the dashboard, no optional apps.
  --apps code,hardwareinfo  Start only the listed optional apps.

Usage
-----
  # Consumer (silent, app-mode window):
  pythonw core\\launcher.py --consumer --browser app

  # Developer (visible consoles, regular tab):
  python core\\launcher.py --dev --browser web
"""

from __future__ import annotations

import argparse
import atexit
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
import psutil

# Diagnostic logging for silent failures (pythonw)
ROOT      = Path(__file__).parent.parent
from core.utils.paths import ensure_all, LAUNCHER_LOG, PORTS_JSON, LOCK_FILE
ensure_all()  # Ensure all data directories exist
_diag_log = LAUNCHER_LOG
_diag_log.parent.mkdir(parents=True, exist_ok=True)

def _log(msg):
    try:
        with open(_diag_log, "a", encoding="utf-8") as f:
            f.write(f"[{time.ctime()}] {msg}\n")
    except Exception:
        pass

_log("--- Launcher script loaded ---")

# -- Paths ---------------------------------------------------------------------

ROOT      = Path(__file__).parent.parent
VENV_DIR  = ROOT / ".venv" / "Scripts"
VENV_PY   = VENV_DIR / "python.exe"
VENV_PYW  = VENV_DIR / "pythonw.exe"
RESTART_EXIT_CODE = 42

# -- App registry --------------------------------------------------------------
# Each entry describes one server process.
#   module   : run as `python -m <module>` (mutually exclusive with script)
#   script   : path relative to ROOT, run as `python <script>`
#   port     : default port (informational - actual port decided by PortManager)
#   title    : human-readable label
#   required : if True, always started; if False, only when requested

APP_REGISTRY: dict[str, dict] = {
    "dashboard": {
        "module":   "core.main",
        "port":     8080,
        "title":    "Nexus Dashboard",
        "required": True,
    },
    "vtuber": {
        "script":   "apps/vtuber/vtuber_server.py",
        "port":     8081,
        "title":    "VTuber",
        "required": False,
    },
    "tracking": {
        "script":   "apps/tracking/tracking_server.py",
        "port":     8082,
        "title":    "Tracking",
        "required": False,
    },
    "code": {
        "script":   "apps/code/code_server.py",
        "port":     8083,
        "title":    "Code IDE",
        "required": False,
    },
    "hardwareinfo": {
        "script":   "apps/hardwareinfo/hardware_server.py",
        "port":     8084,
        "title":    "Hardware Info",
        "required": False,
    },
    "audio": {
        "script":   "apps/audio/audio_server.py",
        "port":     8085,
        "title":    "Audio Studio",
        "required": False,
    },
    "photo": {
        "script":   "apps/photo/photo_server.py",
        "port":     8086,
        "title":    "Photo Studio",
        "required": False,
    },
    "finance": {
        "script":   "apps/finance/finance_server.py",
        "port":     8087,
        "title":    "Finance",
        "required": False,
    },
    "driveinfo": {
        "script":   "apps/driveinfo/driveinfo_server.py",
        "port":     8088,
        "title":    "Drive Info",
        "required": False,
    },
    "overlay": {
        "script":   "apps/overlay/main.py",
        "port":     None,   # sidecar - no web server, lives in system tray
        "title":    "Desktop Overlay",
        "required": False,
    },
}

# -- Windows Job Object (KillOnJobClose) ---------------------------------------

def _install_job_object() -> None:
    """
    On Windows: assign the launcher process to a Job Object with the
    KillOnJobClose flag.  When the launcher exits for ANY reason - including
    being force-killed or the console window being closed - Windows
    automatically terminates every process in the job.

    Child processes inherit the job assignment, so all app servers die with us.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        import ctypes.wintypes as wt

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
        JobObjectExtendedLimitInformation   = 9

        class _BasicLimit(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit",     ctypes.c_longlong),
                ("LimitFlags",             wt.DWORD),
                ("MinimumWorkingSetSize",   ctypes.c_size_t),
                ("MaximumWorkingSetSize",   ctypes.c_size_t),
                ("ActiveProcessLimit",      wt.DWORD),
                ("Affinity",               ctypes.c_size_t),
                ("PriorityClass",          wt.DWORD),
                ("SchedulingClass",        wt.DWORD),
            ]

        class _IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount",  ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount",   ctypes.c_ulonglong),
                ("WriteTransferCount",  ctypes.c_ulonglong),
                ("OtherTransferCount",  ctypes.c_ulonglong),
            ]

        class _ExtLimit(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", _BasicLimit),
                ("IoInfo",               _IoCounters),
                ("ProcessMemoryLimit",   ctypes.c_size_t),
                ("JobMemoryLimit",       ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed",    ctypes.c_size_t),
            ]

        k32 = ctypes.windll.kernel32
        job = k32.CreateJobObjectW(None, None)
        if not job:
            return

        info = _ExtLimit()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        ok = k32.SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            k32.CloseHandle(job)
            return

        # Assign THIS process to the job - children inherit automatically
        k32.AssignProcessToJobObject(job, k32.GetCurrentProcess())
        _install_job_object._job_handle = job  # type: ignore[attr-defined]
        print("[Launcher] Windows Job Object active - all child processes will die with the launcher.")
    except Exception as exc:
        # Non-critical; fall through to atexit/signal cleanup
        print(f"[Launcher] Job Object setup skipped ({exc}); using atexit cleanup instead.")


# -- Process Management Extras -------------------------------------------------

def _is_running_aethvion(proc: psutil.Process) -> bool:
    """Check if a process looks like an Aethvion Suite component (excluding this launcher)."""
    try:
        cmdline = proc.cmdline()
        cmdline_str = " ".join(cmdline)
        
        # If this is the launcher itself, skip
        if "launcher.py" in cmdline_str:
            return False
            
        # Check for core modules or specific app servers
        targets = ["core.main", "vtuber_server.py", "tracking_server.py", "code_server.py",
                   "hardware_server.py", "audio_server.py", "photo_server.py",
                   "finance_server.py", "driveinfo_server.py", "apps/overlay/main.py"]
        return any(t in cmdline_str for t in targets)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False

def _cleanup_stale_processes() -> None:
    """Kill any existing Python processes that look like Aethvion Suite."""
    print("[Launcher] Cleaning up stale Aethvion processes...")
    mypid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['pid'] == mypid:
                continue
            if "python" in proc.info['name'].lower() and _is_running_aethvion(proc):
                print(f"[Launcher] Terminating stale process: {proc.info['pid']}")
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except psutil.TimeoutExpired:
                    proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

def _try_reopen_dashboard() -> None:
    """Attempt to find the port of the running instance and open the browser."""
    try:
        registry_path = PORTS_JSON
        _log(f"Attempting re-open. Registry: {registry_path}")
        
        target_port = None

        if registry_path.exists():
            import json
            try:
                with open(registry_path, "r", encoding="utf-8") as f:
                    registry = json.load(f)
                
                target_names = ["Aethvion Suite Nexus Dashboard", "Aethvion Suite Nexus", "Nexus Dashboard"]
                for p, module in registry.items():
                    if module in target_names:
                        target_port = int(p)
                        break
            except Exception as e:
                _log(f"Registry read failed: {e}")

        # Fallback: Find the process and its listening port
        if not target_port:
            _log("Dashboard not in registry, searching via process connections...")
            # We don't want to re-import psutil as it's at the top level
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    name = proc.info.get('name') or ""
                    if "python" in name.lower() and _is_running_aethvion(proc):
                        # Find a listening port
                        conns = proc.connections(kind='inet')
                        for conn in conns:
                            if conn.status == 'LISTEN' and conn.laddr.port >= 8080:
                                target_port = conn.laddr.port
                                _log(f"Found listening port {target_port} on PID {proc.info['pid']}")
                                break
                        if target_port: break
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue

        if target_port:
            from core.utils.browser import open_app_window
            _log(f"Re-opening browser on port {target_port}")
            open_app_window(f"http://localhost:{target_port}", delay=0, background=True)
            time.sleep(0.5)
        else:
            _log("Could not find dashboard port via registry or process scan.")
    except Exception as e:
        _log(f"Re-open failed: {e}")

def _ensure_singleton() -> None:
    """Ensure only one instance of the launcher is running."""
    lock_file = LOCK_FILE
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        if lock_file.exists():
            try:
                old_pid = int(lock_file.read_text().strip())
                if psutil.pid_exists(old_pid):
                    proc = psutil.Process(old_pid)
                    if "python" in proc.name().lower():
                        print(f"\n[Launcher] Aethvion Suite is already running (PID {old_pid}).")
                        _try_reopen_dashboard()
                        sys.exit(0)
            except Exception:
                pass # Corrupt or missing PID, ignore and overwrite
        
        lock_file.write_text(str(os.getpid()))
        # Clean up lock file on exit
        def _remove_lock():
            if lock_file.exists():
                lock_file.unlink()
        atexit.register(_remove_lock)
        
    except Exception as e:
        print(f"[Launcher] Singleton check failed: {e}")


# -- Child-process tracking -----------------------------------------------------

_child_procs: list[subprocess.Popen] = []
_child_lock  = threading.Lock()


def _register(proc: subprocess.Popen) -> None:
    with _child_lock:
        _child_procs.append(proc)


def _cleanup() -> None:
    """Terminate all child processes, then kill any that refuse to stop."""
    with _child_lock:
        procs = list(_child_procs)

    if not procs:
        return

    print("\n[Launcher] Sending SIGTERM to all child processes...")
    for proc in procs:
        try:
            proc.terminate()
        except Exception:
            pass

    deadline = time.time() + 4.0
    for proc in procs:
        remaining = max(0.0, deadline - time.time())
        try:
            proc.wait(timeout=remaining)
        except Exception:
            pass

    for proc in procs:
        try:
            if proc.poll() is None:
                proc.kill()
                print(f"[Launcher] Force-killed PID {proc.pid}")
        except Exception:
            pass

    print("[Launcher] All child processes stopped.")
    
def _restart_suite() -> None:
    """Safely shut down all processes and re-launch the launcher."""
    print("\n" + "!" * 60)
    print("  SYSTEM RESTART INITIATED (EXIT CODE 42)  ")
    print("!" * 60 + "\n")
    
    _cleanup()
    print("[Launcher] Waiting 2 seconds before system reload...")
    time.sleep(2.0)
    
    # Replace the current process with a new instance of the launcher
    # This ensures a fresh start with updated code
    print("[Launcher] Executing system reload...")
    try:
        if os.name == "nt":
            # On Windows, os.execv doesn't always behave perfectly with consoles
            # subprocess.Popen + sys.exit is often more reliable for "replacing"
            subprocess.Popen([sys.executable] + sys.argv)
            os._exit(0)
        else:
            os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"[Launcher] Restart failed: {e}")
        sys.exit(1)

atexit.register(_cleanup)


def _signal_handler(sig: int, frame) -> None:  # type: ignore[type-arg]
    print(f"\n[Launcher] Caught signal {sig}. Shutting down...")
    _cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT,  _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

# -- Helpers --------------------------------------------------------------------

def _get_python(consumer: bool) -> str:
    if consumer:
        return str(VENV_PYW) if VENV_PYW.exists() else "pythonw"
    return str(VENV_PY) if VENV_PY.exists() else "python"


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    env["AETHVION_NO_BROWSER"] = "1"   # servers must not open their own browser
    env["PYTHONPATH"]          = str(ROOT)
    env["PYTHONUNBUFFERED"]    = "1"
    env["AETHVION_DEV"]        = "1"
    return env


def _launch_process(name: str, cfg: dict, consumer: bool) -> subprocess.Popen | None:
    # Check the script exists before trying to launch
    if "script" in cfg:
        script_path = ROOT / cfg["script"]
        if not script_path.exists():
            print(f"[Launcher]  [!!]  {cfg['title']:<20} script not found - skipping")
            return None

    python = _get_python(consumer)
    env    = _build_env()

    cmd: list[str]
    if "module" in cfg:
        cmd = [python, "-m", cfg["module"]]
    else:
        cmd = [python, str(ROOT / cfg["script"])]

    popen_kwargs: dict = {"cwd": str(ROOT), "env": env}

    if consumer:
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        popen_kwargs["stdout"]        = subprocess.DEVNULL
        popen_kwargs["stderr"]        = subprocess.DEVNULL
    elif os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE

    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
        _register(proc)
        if cfg.get("port"):
            print(f"[Launcher]  [OK]  {cfg['title']:<20} PID {proc.pid:<6}  ->  http://localhost:{cfg['port']}")
        else:
            print(f"[Launcher]  [OK]  {cfg['title']:<20} PID {proc.pid:<6}  (tray sidecar)")
        return proc
    except FileNotFoundError:
        print(f"[Launcher]  [FAIL]  {cfg['title']} - executable not found: {python}")
        return None
    except Exception as exc:
        print(f"[Launcher]  [FAIL]  {cfg['title']} - {exc}")
        return None


def _monitor_dashboard(proc: subprocess.Popen, consumer: bool) -> None:
    """Restart the dashboard if it crashes (daemon thread)."""
    while True:
        time.sleep(2)
        code = proc.poll()
        if code is not None:
            if code == RESTART_EXIT_CODE:
                _restart_suite()
                return
            
            if code == 0:
                _log("Dashboard exited gracefully (code 0). Shutting down suite...")
                print("\n[Launcher] Dashboard shut down gracefully. Cleaning up...")
                _cleanup()
                os._exit(0)
            
            print("[Launcher] Dashboard crashed - restarting...")
            new = _launch_process("dashboard", APP_REGISTRY["dashboard"], consumer)
            if new:
                proc = new


# -- Main -----------------------------------------------------------------------

def main() -> None:
    _log("Main function entered")
    
    parser = argparse.ArgumentParser(
        description="Aethvion Suite Master Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--consumer",
        action="store_true",
        help="Silent mode: pythonw.exe, no visible windows",
    )
    mode_group.add_argument(
        "--dev",
        action="store_true",
        help="Developer mode: python.exe, each server gets its own console",
    )
    parser.add_argument(
        "--apps",
        default="none",
        metavar="all|none|NAME[,NAME]",
        help=(
            "Which optional apps to start alongside the dashboard.\n"
            "  all           - start every optional app (default)\n"
            "  none          - start only the dashboard\n"
            "  code,hwinfo   - start only the listed apps"
        ),
    )
    parser.add_argument(
        "--browser",
        choices=["app", "web", "none"],
        default="app",
        help=(
            "How to open the dashboard after launch.\n"
            "  app  - Chrome/Edge --app= mode (no URL bar)\n"
            "  web  - normal browser tab\n"
            "  none - do not open any browser"
        ),
    )
    args = parser.parse_args()

    consumer    = args.consumer and not args.dev
    mode_label  = "CONSUMER" if consumer else "DEV"
    browser_mode: str = args.browser

    # -- Ensure singleton and clean up ------------------------------------------
    _log("Checking singleton and cleaning stale processes...")
    _ensure_singleton()
    _cleanup_stale_processes()

    # -- Install Windows Job Object for reliable cleanup ------------------------
    _log("Installing Job Object...")
    _install_job_object()

    # -- Banner ----------------------------------------------------------------
    print()
    print("=" * 60)
    print(f"  AETHVION SUITE LAUNCHER  [{mode_label} MODE]")
    print("=" * 60)

    # -- Load .env -------------------------------------------------------------
    env_path = ROOT / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
        except ImportError:
            pass

    # -- Resolve which optional apps to start ----------------------------------
    optional_keys = [k for k, v in APP_REGISTRY.items() if not v.get("required", False)]

    apps_arg = args.apps.strip().lower()
    if apps_arg == "all":
        extra_names = optional_keys
    elif apps_arg == "none":
        extra_names = []
    else:
        extra_names = []
        for name in args.apps.split(","):
            name = name.strip()
            if not name:
                continue
            if name in APP_REGISTRY and not APP_REGISTRY[name].get("required"):
                extra_names.append(name)
            else:
                print(f"[Launcher] Unknown app '{name}'. Known: {', '.join(optional_keys)}")

    # -- Launch dashboard first -------------------------------------------------
    _log("Launching dashboard...")
    print()
    dashboard_proc = _launch_process("dashboard", APP_REGISTRY["dashboard"], consumer)
    if not dashboard_proc:
        _log("ERROR: Dashboard process failed to launch.")
    else:
        _log(f"Dashboard launched with PID {dashboard_proc.pid}")

    # -- Stagger optional app launches (avoid port-registry race) --------------
    for i, app_name in enumerate(extra_names):
        if i > 0:
            time.sleep(0.5)          # 500 ms gap between launches
        _launch_process(app_name, APP_REGISTRY[app_name], consumer)

    # -- Auto-start overlay sidecar if configured ------------------------------
    try:
        import json as _json
        _overlay_cfg_path = ROOT / "data" / "overlay" / "config.json"
        if _overlay_cfg_path.exists():
            _overlay_cfg = _json.loads(_overlay_cfg_path.read_text(encoding="utf-8"))
            if _overlay_cfg.get("launch_with_suite"):
                _launch_process("overlay", APP_REGISTRY["overlay"], consumer)
    except Exception as _oe:
        print(f"[Launcher] Could not check overlay auto-start config: {_oe}")

    print()

    # -- Open browser ----------------------------------------------------------
    if dashboard_proc and browser_mode != "none":
        dashboard_port = int(os.environ.get("PORT", APP_REGISTRY["dashboard"]["port"]))

        def _open_browser() -> None:
            # 1. Wait for dashboard to be ready (port bind)
            _log(f"Waiting for dashboard port {dashboard_port} to be active...")
            start_wait = time.time()
            port_ready = False
            while time.time() - start_wait < 30: # 30s timeout
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.5)
                        if s.connect_ex(('127.0.0.1', dashboard_port)) == 0:
                            port_ready = True
                            break
                except OSError:
                    pass
                time.sleep(0.5)

            if not port_ready:
                _log("Dashboard port not ready after 30s. Attempting browser open anyway.")
            else:
                _log(f"Dashboard port {dashboard_port} is active.")

            saved = os.environ.pop("AETHVION_NO_BROWSER", None)
            try:
                from core.utils.browser import open_app_window
                open_app_window(
                    f"http://localhost:{dashboard_port}",
                    delay=0.1,
                    background=True,   # Reverting to background=True (manual shutdown mode)
                    app_mode=(browser_mode == "app"),
                )
                _log("Browser open command sent. Launcher continuing in background.")
            finally:
                if saved is not None:
                    os.environ["AETHVION_NO_BROWSER"] = saved

        threading.Thread(target=_open_browser, daemon=True).start()

        # Auto-restart dashboard on crash
        threading.Thread(
            target=_monitor_dashboard,
            args=(dashboard_proc, consumer),
            daemon=True,
        ).start()

    # -- Keep launcher alive ---------------------------------------------------
    if consumer:
        try:
            while True:
                time.sleep(10)
        except (KeyboardInterrupt, SystemExit):
            pass
    else:
        print("[Launcher] All processes running. Press Ctrl+C to stop all.\n")
        try:
            while True:
                time.sleep(2)  # Check more frequently for restart signals
                alive = []
                with _child_lock:
                    for proc in list(_child_procs):
                        code = proc.poll()
                        if code == RESTART_EXIT_CODE:
                            _restart_suite()
                            return
                        if code is None:
                            alive.append(proc.pid)
                # print(f"[Launcher] Alive PIDs: {alive}") # Keep it quiet
        except (KeyboardInterrupt, SystemExit):
            pass


if __name__ == "__main__":
    main()
