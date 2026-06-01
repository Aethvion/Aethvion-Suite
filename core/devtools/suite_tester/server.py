"""
core/devtools/suite_tester/server.py
────────────────────────────────────
Aethvion DevTool — Suite Tester Server (Port: 8004)

Starts up a temporary Aethvion Suite instance on port 18080, launches a browser
window to render the suite front-end, profiles resource usage at 1-second intervals
for 60 seconds, executes a validation task load injection, and compiles performance reports
detailing delta charts and repository statistics.
"""
from __future__ import annotations

import os
import sys
import json
import time
import uuid
import socket
import logging
import threading
import subprocess
import webbrowser
from pathlib import Path
from typing import Dict, Any, List, Optional
import psutil
import urllib.request
import urllib.error

# GPU backend — initialised once per test run via _init_gpu_backend()
_gpu_backend: str = "none"   # "pynvml" | "nvidia-smi" | "none"
_nvml_handle = None          # pynvml device handle
_nvidia_smi_path: Optional[str] = None  # cached path so shutil.which runs once

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

# Initialize Paths
REPORTS_DIR = PROJECT_ROOT / "core" / "tests" / "performance" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
TRACKED_DIR = PROJECT_ROOT / "core" / "tests" / "performance"
TRACKED_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Aethvion Suite Tester - Devtool")

# Active test runs registry
# test_runs[run_id] = { status, progress, logs: [], metrics: {}, error }
test_runs: Dict[str, Dict[str, Any]] = {}
runs_lock = threading.Lock()

def add_log(run_id: str, message: str):
    with runs_lock:
        if run_id in test_runs:
            timestamp = time.strftime("%H:%M:%S")
            test_runs[run_id]["logs"].append(f"[{timestamp}] {message}")
            try:
                print(f"[SuiteTester - {run_id[-6:]}] {message}")
            except UnicodeEncodeError:
                safe_msg = message.replace("──", "==").replace("—", "-")
                try:
                    print(f"[SuiteTester - {run_id[-6:]}] {safe_msg}")
                except Exception:
                    pass

def get_git_info() -> Dict[str, str]:
    from core.version import get_version_parts
    parts = get_version_parts()
    
    commit_msg = "Unknown"
    try:
        commit_msg = subprocess.check_output(
            ["git", "log", "-1", "--format=%s"],
            cwd=str(PROJECT_ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000 # CREATE_NO_WINDOW
        ).strip()
    except Exception:
        pass

    return {
        "version": parts.get("string", "unknown"),
        "commit_hash": parts.get("short", "unknown"),
        "commit_msg": commit_msg
    }

def _init_gpu_backend() -> None:
    """Detect the best GPU query method once per test run.

    Tries pynvml (in-process, zero subprocess overhead) first.
    Falls back to nvidia-smi with the path cached so shutil.which
    is only called once instead of 60 times during profiling.
    """
    global _gpu_backend, _nvml_handle, _nvidia_smi_path
    try:
        import pynvml
        pynvml.nvmlInit()
        _nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        _gpu_backend = "pynvml"
        return
    except Exception:
        pass

    import shutil
    path = shutil.which("nvidia-smi")
    if path:
        _nvidia_smi_path = path
        _gpu_backend = "nvidia-smi"
    else:
        _gpu_backend = "none"


def get_gpu_usage() -> Dict[str, Any]:
    """Query GPU utilisation and VRAM using whichever backend was initialised."""
    _empty = {"status": "N/A", "utilization": 0, "vram_used_mb": 0, "vram_total_mb": 0}

    if _gpu_backend == "pynvml":
        try:
            import pynvml
            util = pynvml.nvmlDeviceGetUtilizationRates(_nvml_handle)
            mem  = pynvml.nvmlDeviceGetMemoryInfo(_nvml_handle)
            return {
                "status":       "Available",
                "utilization":  util.gpu,
                "vram_used_mb": mem.used  // (1024 * 1024),
                "vram_total_mb": mem.total // (1024 * 1024),
            }
        except Exception:
            return _empty

    if _gpu_backend == "nvidia-smi":
        try:
            kwargs: Dict[str, Any] = {
                "text": True, "stderr": subprocess.DEVNULL,
            }
            if os.name == "nt":
                kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
            output = subprocess.check_output(
                [_nvidia_smi_path,
                 "--query-gpu=utilization.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                **kwargs,
            )
            parts = [p.strip() for p in output.split(",")]
            if len(parts) >= 3:
                return {
                    "status":        "Available",
                    "utilization":   int(parts[0]),
                    "vram_used_mb":  int(parts[1]),
                    "vram_total_mb": int(parts[2]),
                }
        except Exception:
            pass

    return _empty

def get_process_resource_usage(pid: int) -> Dict[str, Any]:
    """Recursively calculates CPU and Memory footprint for a parent PID and children."""
    try:
        parent = psutil.Process(pid)
        processes = [parent] + parent.children(recursive=True)
        total_rss = 0
        total_cpu = 0.0
        for p in processes:
            try:
                total_rss += p.memory_info().rss
                total_cpu += p.cpu_percent()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return {
            "memory_mb": round(total_rss / (1024 * 1024), 2),
            "cpu_percent": round(total_cpu, 1)
        }
    except Exception:
        return {"memory_mb": 0.0, "cpu_percent": 0.0}

def kill_process_tree(pid: int):
    """Recursively terminates a process and all its children to prevent orphaned tasks."""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        # Send terminate signal to children first
        for child in children:
            try:
                child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        # Terminate parent
        try:
            parent.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
            
        # Wait up to 3 seconds for graceful exit
        gone, alive = psutil.wait_procs(children + [parent], timeout=3)
        
        # Force kill any remaining alive processes
        for p in alive:
            try:
                p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass

def get_repository_stats() -> Dict[str, Any]:
    """Scans the repository to compile file counts and lines of code by language."""
    extensions = {
        ".py": "Python",
        ".js": "JavaScript",
        ".html": "HTML",
        ".css": "CSS",
        ".cs": "C#",
        ".bat": "Batch"
    }
    
    total_files = 0
    total_loc = 0
    by_lang = {}
    
    for lang in extensions.values():
        by_lang[lang] = {"files": 0, "loc": 0}
        
    exclude_dirs = {".venv", ".git", ".pytest_cache", "dist", "setup", "__pycache__", "node_modules"}
    
    try:
        for root, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                file_path = Path(root) / file
                ext = file_path.suffix.lower()
                if ext in extensions:
                    lang = extensions[ext]
                    by_lang[lang]["files"] += 1
                    total_files += 1
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            loc = sum(1 for _ in f)
                            by_lang[lang]["loc"] += loc
                            total_loc += loc
                    except Exception:
                        pass
    except Exception:
        pass
        
    return {
        "total_files": total_files,
        "total_loc": total_loc,
        "by_language": by_lang
    }

def make_http_request(url: str, method: str = "GET", data: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
    """Performs HTTP calls without external requests dependencies to keep devtool selfcontained."""
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "AethvionSuiteTester/1.0")
    
    payload = None
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        
    start_time = time.time()
    try:
        with urllib.request.urlopen(req, data=payload, timeout=timeout) as response:
            resp_body = response.read().decode("utf-8")
            latency_ms = (time.time() - start_time) * 1000
            try:
                parsed_json = json.loads(resp_body)
            except json.JSONDecodeError:
                parsed_json = resp_body
            return {
                "success": True,
                "status_code": response.status,
                "body": parsed_json,
                "latency_ms": round(latency_ms, 2)
            }
    except urllib.error.HTTPError as e:
        latency_ms = (time.time() - start_time) * 1000
        try:
            err_body = e.read().decode("utf-8")
            parsed_json = json.loads(err_body)
        except Exception:
            err_body = str(e)
            parsed_json = err_body
        return {
            "success": False,
            "status_code": e.code,
            "body": parsed_json,
            "latency_ms": round(latency_ms, 2)
        }
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        return {
            "success": False,
            "status_code": 0,
            "body": str(e),
            "latency_ms": round(latency_ms, 2)
        }

def generate_markdown_report(report_data: Dict[str, Any]) -> str:
    """Generates a clean, human-readable markdown summary of a performance report."""
    git_meta = report_data.get("git", {})
    vitals = report_data.get("vitals", {})
    avgs = vitals.get("averages", {})
    baseline = vitals.get("pre_test_baseline", {})
    gpu_baseline = baseline.get("gpu", {})
    
    # Format startup duration
    startup_s = vitals.get("startup_duration_s", 0.0)
    
    # Process vitals
    p_cpu_avg = avgs.get("process_cpu_avg", 0.0)
    p_cpu_max = avgs.get("process_cpu_max", 0.0)
    p_mem_avg = avgs.get("process_mem_avg", 0.0)
    p_mem_max = avgs.get("process_mem_max", 0.0)
    
    # System vitals pre vs during
    sys_cpu_pre = baseline.get("system_cpu_percent", 0.0)
    sys_cpu_avg = avgs.get("system_cpu_avg", 0.0)
    sys_cpu_max = avgs.get("system_cpu_max", 0.0)
    
    sys_mem_pre = baseline.get("system_memory_percent", 0.0)
    sys_mem_avg = avgs.get("system_mem_avg", 0.0)
    sys_mem_max = avgs.get("system_mem_max", 0.0)
    
    # GPU pre vs during
    gpu_status = gpu_baseline.get("status", "N/A")
    gpu_pre_util = gpu_baseline.get("utilization", 0) if gpu_status == "Available" else 0
    gpu_pre_vram = gpu_baseline.get("vram_used_mb", 0) if gpu_status == "Available" else 0
    
    gpu_avg_util = avgs.get("gpu_util_avg", 0.0)
    gpu_max_util = avgs.get("gpu_util_max", 0.0)
    gpu_avg_vram = avgs.get("gpu_vram_avg", 0.0)
    gpu_max_vram = avgs.get("gpu_vram_max", 0.0)
    
    # Health checks
    health_latency = 0.0
    for r in report_data.get("api_routing", []):
        if r.get("test") == "health_check":
            health_latency = r.get("avg_latency_ms", 0.0)
            
    # Task queue
    tasks_meta = report_data.get("tasks", {})
    task_success = tasks_meta.get("success", False)
    task_duration = tasks_meta.get("duration_s", 0.0)
    task_correct = tasks_meta.get("correct", False)
    
    repo_stats = report_data.get("repository_stats", {})
    total_files = repo_stats.get("total_files", 0)
    total_loc = repo_stats.get("total_loc", 0)
    
    md = []
    md.append(f"# Aethvion Suite Tester - Performance Report")
    md.append(f"")
    md.append(f"- **Report ID**: `{report_data.get('id')}`")
    md.append(f"- **Timestamp**: `{report_data.get('timestamp')}`")
    md.append(f"- **Commit**: `{git_meta.get('commit_hash', 'unknown')}`")
    md.append(f"- **Commit Message**: `{git_meta.get('commit_msg', 'unknown')}`")
    md.append(f"- **Version**: `{git_meta.get('version', 'unknown')}`")
    md.append(f"")
    md.append(f"## 📊 Telemetry Summary")
    md.append(f"")
    md.append(f"| Metric Stream | Offline Baseline | Active Test Average | Active Test Peak (Max) |")
    md.append(f"| :--- | :---: | :---: | :---: |")
    md.append(f"| **Process CPU** | — | {p_cpu_avg:.1f}% | {p_cpu_max:.1f}% |")
    md.append(f"| **Process Memory (RAM)** | — | {p_mem_avg:.2f} MB | {p_mem_max:.2f} MB |")
    md.append(f"| **System CPU** | {sys_cpu_pre:.1f}% | {sys_cpu_avg:.1f}% | {sys_cpu_max:.1f}% |")
    md.append(f"| **System Memory (RAM)** | {sys_mem_pre:.1f}% | {sys_mem_avg:.1f}% | {sys_mem_max:.1f}% |")
    
    if gpu_status == "Available":
        md.append(f"| **GPU Utilization** | {gpu_pre_util:.1f}% | {gpu_avg_util:.1f}% | {gpu_max_util:.1f}% |")
        md.append(f"| **GPU VRAM** | {gpu_pre_vram:,} MB | {gpu_avg_vram:,.2f} MB | {gpu_max_vram:,.2f} MB |")
    else:
        md.append(f"| **GPU / VRAM** | N/A | N/A | N/A |")
        
    md.append(f"")
    md.append(f"## ⏱️ Orchestration & Stress Tests")
    md.append(f"")
    md.append(f"- **Startup Duration**: `{startup_s:.2f} seconds`")
    md.append(f"- **API Health Check Average Latency**: `{health_latency:.2f} ms`")
    
    if task_success:
        status_text = "Passed" if task_correct else "Response Mismatch"
        md.append(f"- **LLM Task Queue Routing Stress**: `{status_text}` (took `{task_duration:.2f}s`)")
    else:
        md.append(f"- **LLM Task Queue Routing Stress**: `Failed/Timeout` (error: `{tasks_meta.get('error', 'N/A')}`)")
        
    md.append(f"")
    md.append(f"## 📁 Repository Codebase Stats")
    md.append(f"")
    md.append(f"- **Total Files Tracked**: `{total_files:,}`")
    md.append(f"- **Total Lines of Code (LOC)**: `{total_loc:,}`")
    md.append(f"")
    md.append(f"### Language Breakdown")
    md.append(f"")
    md.append(f"| Language | Files | Lines of Code (LOC) | Code Ratio |")
    md.append(f"| :--- | :---: | :---: | :---: |")
    
    by_lang = repo_stats.get("by_language", {})
    for lang, stats in sorted(by_lang.items(), key=lambda x: x[1].get("loc", 0), reverse=True):
        l_files = stats.get("files", 0)
        l_loc = stats.get("loc", 0)
        if l_files == 0:
            continue
        ratio = (l_loc / total_loc * 100) if total_loc > 0 else 0.0
        md.append(f"| **{lang}** | {l_files:,} | {l_loc:,} | {ratio:.1f}% |")
        
    return "\n".join(md)

def run_test_orchestrator(run_id: str, python_exe: str):
    """Orchestrates the entire automated test lifecycle."""
    add_log(run_id, "Initializing test orchestrator...")
    
    test_port = 18080
    test_url = f"http://127.0.0.1:{test_port}"
    
    # 1. Clean up potential stale port
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(('127.0.0.1', test_port)) == 0:
                add_log(run_id, f"WARNING: Port {test_port} is already in use. Cleaning registry...")
                try:
                    # Instantly find the process holding the port using system-wide net connections
                    for conn in psutil.net_connections(kind='inet'):
                        if conn.laddr.port == test_port and conn.pid:
                            try:
                                proc = psutil.Process(conn.pid)
                                add_log(run_id, f"Killing process {proc.pid} ({proc.name()}) holding port {test_port}")
                                kill_process_tree(proc.pid)
                            except Exception as e:
                                add_log(run_id, f"Error terminating process tree for PID {conn.pid}: {e}")
                except Exception as net_exc:
                    add_log(run_id, f"System-wide net connection query failed: {net_exc}. Falling back to connection iterator...")
                    # Fallback if net_connections requires administrator permissions on some setups
                    for proc in psutil.process_iter(['pid', 'connections']):
                        try:
                            for conn in proc.connections(kind='inet'):
                                if conn.laddr.port == test_port:
                                    add_log(run_id, f"Killing process {proc.pid} holding port {test_port}")
                                    kill_process_tree(proc.pid)
                        except Exception:
                            pass
                # Wait until the port is actually free (up to 5s)
                for _ in range(10):
                    time.sleep(0.5)
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as chk:
                        chk.settimeout(0.2)
                        if chk.connect_ex(('127.0.0.1', test_port)) != 0:
                            add_log(run_id, f"Port {test_port} is now free.")
                            break
                else:
                    add_log(run_id, f"WARNING: Port {test_port} may still be in use after cleanup.")
    except Exception as exc:
        add_log(run_id, f"Port check skipped: {exc}")

    # Build process execution env
    test_env = os.environ.copy()
    test_env["PORT"] = str(test_port)
    test_env["AETHVION_DEV"] = "1"
    test_env["AETHVION_NO_BROWSER"] = "1"
    test_env["PYTHONPATH"] = str(PROJECT_ROOT)
    test_env["PYTHONUNBUFFERED"] = "1"

    # Initialise GPU backend once — pynvml if available, nvidia-smi otherwise
    _init_gpu_backend()

    # Capture absolute baseline (Pre-Test System state while Aethvion is Offline)
    pre_test_sys_cpu = psutil.cpu_percent(interval=0.1)
    pre_test_sys_mem = psutil.virtual_memory().percent
    pre_test_gpu = get_gpu_usage()

    # == Phase 1: Startup ==
    add_log(run_id, "== Phase 1: Starting Aethvion Suite ==")
    with runs_lock:
        test_runs[run_id]["progress"] = 10
        test_runs[run_id]["phase"] = "Startup"

    suite_proc = None
    startup_start = time.time()
    try:
        main_script = PROJECT_ROOT / "core" / "main.py"
        cmd = [python_exe, str(main_script)]
        
        # Start the suite as a background child process
        kwargs: Dict[str, Any] = {"cwd": str(PROJECT_ROOT), "env": test_env}
        if os.name == 'nt':
            kwargs["creationflags"] = 0x08000000 # CREATE_NO_WINDOW
            
        suite_proc = subprocess.Popen(cmd, **kwargs)
        add_log(run_id, f"Spawned suite process (PID: {suite_proc.pid})")
    except Exception as e:
        add_log(run_id, f"CRITICAL: Failed to launch suite process: {e}")
        with runs_lock:
            test_runs[run_id]["status"] = "failed"
            test_runs[run_id]["error"] = f"Launch failed: {str(e)}"
        return

    # Poll startup status — wait up to 60 seconds
    startup_success  = False
    startup_duration = 0.0
    last_status      = "not started"
    last_progress    = 0
    http_reachable   = False

    poll_start = time.time()
    while time.time() - poll_start < 60:
        if suite_proc.poll() is not None:
            add_log(run_id, f"CRITICAL: Process terminated prematurely (exit code {suite_proc.returncode})")
            break

        elapsed = round(time.time() - poll_start, 1)
        res = make_http_request(f"{test_url}/api/system/startup-status", timeout=2.0)
        if res["success"]:
            http_reachable = True
            body          = res["body"]
            last_status   = body.get("status", "Starting")
            last_progress = body.get("progress", 0)
            initialized   = body.get("initialized", False)
            error_msg     = body.get("error")

            add_log(run_id, f"[{elapsed}s] Startup: {last_status} ({last_progress}%)")

            if error_msg:
                add_log(run_id, f"CRITICAL: Suite reported init error: {error_msg}")
                break

            if initialized:
                startup_success  = True
                startup_duration = time.time() - startup_start
                add_log(run_id, f"SUCCESS: Ready in {startup_duration:.2f}s")
                break
        else:
            add_log(run_id, f"[{elapsed}s] Waiting for HTTP server...")

        time.sleep(1.0)

    if not startup_success:
        reason = (
            f"last status: '{last_status}' ({last_progress}%)"
            if http_reachable else "HTTP server never responded"
        )
        add_log(run_id, f"CRITICAL: Startup timeout after 60s — {reason}")
        try:
            suite_proc.terminate()
            suite_proc.wait(timeout=3)
        except Exception:
            suite_proc.kill()
        with runs_lock:
            test_runs[run_id]["status"] = "failed"
            test_runs[run_id]["error"]  = f"Startup timed out — {reason}"
        return

    # Launch browser window to render the suite front-end and trigger JS executions
    add_log(run_id, f"Launching browser tab at {test_url} to render client dashboard...")
    try:
        webbrowser.open(test_url)
    except Exception as e:
        add_log(run_id, f"Warning: Failed to launch browser tab: {e}")

    # Track resources post-initialization
    startup_resources = get_process_resource_usage(suite_proc.pid)
    add_log(run_id, f"Startup resource usage: Memory: {startup_resources['memory_mb']} MB, CPU: {startup_resources['cpu_percent']}%")

    # == Phase 2: 60-Second Performance Profiling ==
    add_log(run_id, "== Phase 2: 60-Second Real-Time Telemetry Profiling ==")
    with runs_lock:
        test_runs[run_id]["progress"] = 30
        test_runs[run_id]["phase"] = "Performance Profiling"

    timeseries_data = []
    health_latencies: List[float] = []   # sampled during the window, not after

    # Task state
    task_submitted  = False
    task_id         = None
    task_success    = False
    task_start_time = 0.0
    task_duration   = 0.0
    ai_response     = ""
    task_error      = None
    temp_thread_id  = f"perf_test_thread_{uuid.uuid4().hex[:6]}"

    # ── 60-second profiling loop ───────────────────────────────────────────────
    for sec in range(1, 61):
        if suite_proc.poll() is not None:
            add_log(run_id, "CRITICAL: Suite process died during profiling run.")
            break

        # Capture system snapshot at the top of each second
        proc_usage = get_process_resource_usage(suite_proc.pid)
        sys_usage  = {
            "system_cpu": psutil.cpu_percent(),
            "system_mem": psutil.virtual_memory().percent,
        }
        gpu_usage   = get_gpu_usage()
        gpu_avail   = gpu_usage["status"] == "Available"
        raw_gpu_util = gpu_usage["utilization"]  if gpu_avail else 0
        raw_gpu_vram = gpu_usage["vram_used_mb"] if gpu_avail else 0

        # Net metrics: subtract the pre-test offline baseline so that other
        # programs running on the machine don't inflate the suite's numbers.
        # Clamped to 0 — negative means the suite freed resources vs baseline.
        net_sys_cpu  = max(0.0, round(sys_usage["system_cpu"] - pre_test_sys_cpu, 1))
        net_sys_mem  = max(0.0, round(sys_usage["system_mem"] - pre_test_sys_mem, 1))
        net_gpu_util = max(0, raw_gpu_util - pre_test_gpu.get("utilization",  0))
        net_gpu_vram = max(0, raw_gpu_vram - pre_test_gpu.get("vram_used_mb", 0))

        snapshot = {
            "second":        sec,
            "process_cpu":   proc_usage["cpu_percent"],
            "process_mem":   proc_usage["memory_mb"],
            # Raw absolute values (affected by other programs open on the machine)
            "system_cpu":    sys_usage["system_cpu"],
            "system_mem":    sys_usage["system_mem"],
            "gpu_util":      raw_gpu_util,
            "gpu_vram":      raw_gpu_vram,
            # Net suite-attributable values (baseline subtracted)
            "net_system_cpu":  net_sys_cpu,
            "net_system_mem":  net_sys_mem,
            "net_gpu_util":    net_gpu_util,
            "net_gpu_vram":    net_gpu_vram,
        }
        timeseries_data.append(snapshot)

        if sec % 10 == 0:
            add_log(run_id, f"Profiling: second {sec}/60 — RAM {proc_usage['memory_mb']}MB, Sys CPU {sys_usage['system_cpu']}%")

        # Sample health latency during the window at seconds 10,20,30,40,50
        # (measured under real load conditions, not after shutdown)
        if sec in (10, 20, 30, 40, 50):
            h_res = make_http_request(f"{test_url}/health", timeout=5.0)
            if h_res["success"]:
                health_latencies.append(h_res["latency_ms"])

        # Submit load task at second 15
        if sec == 15 and not task_submitted:
            add_log(run_id, "Injecting Load: Submitting test prompt to agent task queue...")
            submit_res = make_http_request(
                f"{test_url}/api/tasks/submit",
                method="POST",
                data={
                    "prompt":    "Respond with exactly the single word: ACKNOWLEDGED",
                    "thread_id": temp_thread_id,
                    "mode":      "chat_only",
                },
            )
            if submit_res["success"]:
                task_id         = submit_res["body"].get("task_id")
                task_submitted  = True
                task_start_time = time.time()
                add_log(run_id, f"Task submitted (ID: {task_id}). Polling at 200ms resolution...")
            else:
                add_log(run_id, f"Load Injection Error: {submit_res['body']}")
                task_error = str(submit_res["body"])

        # ── Fill the remaining second with 200ms poll ticks ────────────────────
        # This catches task completion within 200ms instead of up to 1s.
        for _tick in range(5):
            if task_submitted and not task_success and not task_error:
                status_res = make_http_request(
                    f"{test_url}/api/tasks/status/{task_id}", timeout=2.0
                )
                if status_res["success"]:
                    task_info  = status_res["body"]
                    status_str = task_info.get("status", "queued")
                    if status_str in ("completed", "done", "success"):
                        task_success  = True
                        task_duration = time.time() - task_start_time
                        ai_response   = (task_info.get("result") or {}).get("response", "")
                        add_log(run_id, f"Task done in {task_duration:.2f}s — '{ai_response.strip()}'")
                    elif status_str in ("failed", "cancelled", "error"):
                        task_error = f"Orchestrator status: {status_str}"
                        add_log(run_id, f"Task failed: {task_info.get('error')}")
            time.sleep(0.2)

    # Clean up the temporary thread
    if task_submitted:
        make_http_request(f"{test_url}/api/tasks/thread/{temp_thread_id}", method="DELETE")

    avg_health_latency = round(sum(health_latencies) / len(health_latencies), 2) if health_latencies else 0.0
    add_log(run_id, f"Avg health latency (sampled during load): {avg_health_latency}ms over {len(health_latencies)} samples")

    # == Phase 3: Graceful Shutdown & Cleanup ==
    add_log(run_id, "== Phase 3: Graceful Shutdown & Cleanup ==")
    with runs_lock:
        test_runs[run_id]["progress"] = 90
        test_runs[run_id]["phase"] = "Shutdown & Clean"

    peak_resources = get_process_resource_usage(suite_proc.pid)
    
    add_log(run_id, "Triggering graceful system shutdown...")
    shutdown_res = make_http_request(f"{test_url}/api/system/shutdown", method="POST")
    
    graceful_success = False
    if shutdown_res["success"]:
        shutdown_start = time.time()
        while time.time() - shutdown_start < 5:
            if suite_proc.poll() is not None:
                graceful_success = True
                add_log(run_id, f"Suite process terminated gracefully (exit code: {suite_proc.returncode})")
                break
            time.sleep(0.5)

    # Always ensure the entire process tree (including orphaned child browser windows or server threads) is terminated
    try:
        add_log(run_id, "Ensuring all suite subprocesses are terminated recursively...")
        kill_process_tree(suite_proc.pid)
    except Exception as e:
        add_log(run_id, f"Error during process tree cleanup: {e}")

    # Scan project source stats
    add_log(run_id, "Scanning repository codebase stats...")
    repo_stats = get_repository_stats()

    # Compile report and calculate averages
    p_cpus    = [s["process_cpu"] for s in timeseries_data]
    p_mems    = [s["process_mem"] for s in timeseries_data]
    # Raw system/GPU (absolute — varies with what else is open on the machine)
    s_cpus    = [s["system_cpu"]  for s in timeseries_data]
    s_mems    = [s["system_mem"]  for s in timeseries_data]
    gpu_utils = [s["gpu_util"]    for s in timeseries_data]
    gpu_vrams = [s["gpu_vram"]    for s in timeseries_data]
    # Net system/GPU (baseline-subtracted — suite-attributable only)
    n_cpus    = [s["net_system_cpu"]  for s in timeseries_data]
    n_mems    = [s["net_system_mem"]  for s in timeseries_data]
    n_gutls   = [s["net_gpu_util"]    for s in timeseries_data]
    n_gvrams  = [s["net_gpu_vram"]    for s in timeseries_data]

    git_meta = get_git_info()
    report_id = f"report_{int(time.time())}_{git_meta['commit_hash']}"
    
    report_data = {
        "id": report_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "epoch": int(time.time()),
        "status": "passed" if startup_success and graceful_success else "failed",
        "git": git_meta,
        "repository_stats": repo_stats,
        "vitals": {
            "startup_duration_s": round(startup_duration, 2),
            "pre_test_baseline": {
                "system_cpu_percent": pre_test_sys_cpu,
                "system_memory_percent": pre_test_sys_mem,
                "gpu": pre_test_gpu
            },
            "startup_resources": startup_resources,
            "peak_resources": peak_resources,
            "averages": {
                # Process metrics are already suite-specific (psutil measures the process tree)
                "process_cpu_avg": round(sum(p_cpus)/len(p_cpus), 1) if p_cpus else 0.0,
                "process_cpu_max": round(max(p_cpus), 1) if p_cpus else 0.0,
                "process_cpu_min": round(min(p_cpus), 1) if p_cpus else 0.0,

                "process_mem_avg": round(sum(p_mems)/len(p_mems), 2) if p_mems else 0.0,
                "process_mem_max": round(max(p_mems), 2) if p_mems else 0.0,
                "process_mem_min": round(min(p_mems), 2) if p_mems else 0.0,

                # System/GPU — net (baseline-subtracted, suite-attributable only).
                # Used for comparisons so other programs don't skew the delta.
                "system_cpu_avg": round(sum(n_cpus)/len(n_cpus), 1) if n_cpus else 0.0,
                "system_cpu_max": round(max(n_cpus), 1) if n_cpus else 0.0,
                "system_cpu_min": round(min(n_cpus), 1) if n_cpus else 0.0,

                "system_mem_avg": round(sum(n_mems)/len(n_mems), 1) if n_mems else 0.0,
                "system_mem_max": round(max(n_mems), 1) if n_mems else 0.0,
                "system_mem_min": round(min(n_mems), 1) if n_mems else 0.0,

                "gpu_util_avg": round(sum(n_gutls)/len(n_gutls), 1) if n_gutls else 0.0,
                "gpu_util_max": round(max(n_gutls), 1) if n_gutls else 0.0,
                "gpu_util_min": round(min(n_gutls), 1) if n_gutls else 0.0,

                "gpu_vram_avg": round(sum(n_gvrams)/len(n_gvrams), 2) if n_gvrams else 0.0,
                "gpu_vram_max": round(max(n_gvrams), 2) if n_gvrams else 0.0,
                "gpu_vram_min": round(min(n_gvrams), 2) if n_gvrams else 0.0,

                # Raw absolute values stored for reference (not used in comparison matrix)
                "system_cpu_raw_avg": round(sum(s_cpus)/len(s_cpus), 1) if s_cpus else 0.0,
                "system_mem_raw_avg": round(sum(s_mems)/len(s_mems), 1) if s_mems else 0.0,
                "gpu_util_raw_avg":   round(sum(gpu_utils)/len(gpu_utils), 1) if gpu_utils else 0.0,
                "gpu_vram_raw_avg":   round(sum(gpu_vrams)/len(gpu_vrams), 2) if gpu_vrams else 0.0,
            }
        },
        "api_routing": [
            {
                "test": "health_check",
                "status": "passed" if health_latencies else "failed",
                "avg_latency_ms": round(avg_health_latency, 2)
            }
        ],
        "tasks": {
            "success": task_success,
            "task_id": task_id,
            "duration_s": round(task_duration, 2) if task_success else 0.0,
            "ai_response": ai_response.strip(),
            "correct": "ACKNOWLEDGED" in ai_response.upper() if task_success else False,
            "error": task_error
        },
        "timeseries": timeseries_data
    }

    # Write report files
    report_file_json = REPORTS_DIR / f"{report_id}.json"
    report_file_md = REPORTS_DIR / f"{report_id}.md"
    latest_file_json = TRACKED_DIR / "latest_report.json"
    latest_file_md = TRACKED_DIR / "latest_report.md"
    
    # 1. Save historical JSON report (gitignored)
    try:
        with open(report_file_json, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=4)
        add_log(run_id, f"Saved historical JSON report: {report_file_json.name}")
    except Exception as e:
        add_log(run_id, f"Error saving historical JSON report: {e}")
        
    # 2. Generate and save historical Markdown report (gitignored)
    md_content = ""
    try:
        md_content = generate_markdown_report(report_data)
        with open(report_file_md, "w", encoding="utf-8") as f:
            f.write(md_content)
        add_log(run_id, f"Saved historical Markdown report: {report_file_md.name}")
    except Exception as e:
        add_log(run_id, f"Error generating historical Markdown report: {e}")
        
    # 3. Save latest JSON report under Git version control (tracked)
    try:
        with open(latest_file_json, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=4)
        add_log(run_id, "Updated git-tracked latest_report.json")
    except Exception as e:
        add_log(run_id, f"Error updating tracked latest_report.json: {e}")
        
    # 4. Save latest Markdown report under Git version control (tracked)
    if md_content:
        try:
            with open(latest_file_md, "w", encoding="utf-8") as f:
                f.write(md_content)
            add_log(run_id, "Updated git-tracked latest_report.md")
        except Exception as e:
            add_log(run_id, f"Error updating tracked latest_report.md: {e}")

    with runs_lock:
        test_runs[run_id]["status"] = "completed"
        test_runs[run_id]["progress"] = 100
        test_runs[run_id]["phase"] = "Finished"
        test_runs[run_id]["metrics"] = report_data


@app.post("/api/tests/run")
async def trigger_tests_run(background_tasks: BackgroundTasks):
    """Triggers the automated suite integration test run in a background thread."""
    run_id = str(uuid.uuid4())
    python_exe = sys.executable
    
    with runs_lock:
        test_runs[run_id] = {
            "id": run_id,
            "status": "running",
            "progress": 0,
            "phase": "Initialization",
            "logs": [],
            "metrics": {},
            "error": None
        }
        
    background_tasks.add_task(run_test_orchestrator, run_id, python_exe)
    return {"run_id": run_id, "status": "started"}


@app.get("/api/tests/status/{run_id}")
async def get_test_run_status(run_id: str):
    """Poll the live status and logs of a running test."""
    with runs_lock:
        if run_id not in test_runs:
            raise HTTPException(404, "Test run not found")
        return test_runs[run_id]


@app.get("/api/tests/reports")
async def list_reports():
    """Lists historical test reports, ordered newest first."""
    reports = []
    for file in REPORTS_DIR.glob("*.json"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                reports.append({
                    "id": data.get("id"),
                    "timestamp": data.get("timestamp"),
                    "epoch": data.get("epoch", 0),
                    "status": data.get("status"),
                    "commit_hash": data.get("git", {}).get("commit_hash", "unknown"),
                    "commit_msg": data.get("git", {}).get("commit_msg", "unknown"),
                    "startup_s": data.get("vitals", {}).get("startup_duration_s", 0.0),
                    "peak_mem_mb": data.get("vitals", {}).get("peak_resources", {}).get("memory_mb", 0.0)
                })
        except Exception:
            continue
            
    reports.sort(key=lambda x: x["epoch"], reverse=True)
    return {"reports": reports}


@app.get("/api/tests/reports/{report_id}")
async def get_report(report_id: str):
    """Retrieves a specific test report's full JSON."""
    report_file = REPORTS_DIR / f"{report_id}.json"
    if not report_file.exists():
        raise HTTPException(404, "Report not found")
    try:
        with open(report_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(500, f"Error loading report: {e}")


@app.get("/api/tests/compare")
async def compare_reports(base_id: str, compare_id: str):
    """Calculates performance and codebase deltas (lows, highs, averages) between two runs."""
    base_file = REPORTS_DIR / f"{base_id}.json"
    compare_file = REPORTS_DIR / f"{compare_id}.json"
    
    if not base_file.exists() or not compare_file.exists():
        raise HTTPException(404, "One or both reports not found")
        
    try:
        with open(base_file, "r", encoding="utf-8") as f:
            base = json.load(f)
        with open(compare_file, "r", encoding="utf-8") as f:
            comp = json.load(f)
            
        def pct_diff(b_val, c_val):
            if b_val == 0:
                return 0.0
            return round(((c_val - b_val) / b_val) * 100, 2)
            
        b_vitals = base.get("vitals", {})
        c_vitals = comp.get("vitals", {})
        
        # 1. Startup & Task Turnaround & Health Checks deltas
        b_startup = b_vitals.get("startup_duration_s", 0.0)
        c_startup = c_vitals.get("startup_duration_s", 0.0)
        
        b_health = next((x.get("avg_latency_ms", 0.0) for x in base.get("api_routing", []) if x.get("test") == "health_check"), 0.0)
        c_health = next((x.get("avg_latency_ms", 0.0) for x in comp.get("api_routing", []) if x.get("test") == "health_check"), 0.0)
        
        b_task = base.get("tasks", {}).get("duration_s", 0.0)
        c_task = comp.get("tasks", {}).get("duration_s", 0.0)
        
        # 2. Codebase stats delta comparison
        b_repo = base.get("repository_stats", {})
        c_repo = comp.get("repository_stats", {})
        
        b_tot_files = b_repo.get("total_files", 0)
        c_tot_files = c_repo.get("total_files", 0)
        b_tot_loc = b_repo.get("total_loc", 0)
        c_tot_loc = c_repo.get("total_loc", 0)
        
        repo_compare = {
            "total_files": {
                "base": b_tot_files,
                "comp": c_tot_files,
                "delta": c_tot_files - b_tot_files
            },
            "total_loc": {
                "base": b_tot_loc,
                "comp": c_tot_loc,
                "delta": c_tot_loc - b_tot_loc
            },
            "languages": {}
        }
        
        b_langs = b_repo.get("by_language", {})
        c_langs = c_repo.get("by_language", {})
        all_langs = set(list(b_langs.keys()) + list(c_langs.keys()))
        for lang in all_langs:
            bl = b_langs.get(lang, {"files": 0, "loc": 0})
            cl = c_langs.get(lang, {"files": 0, "loc": 0})
            repo_compare["languages"][lang] = {
                "files_base": bl.get("files", 0),
                "files_comp": cl.get("files", 0),
                "files_delta": cl.get("files", 0) - bl.get("files", 0),
                "loc_base": bl.get("loc", 0),
                "loc_comp": cl.get("loc", 0),
                "loc_delta": cl.get("loc", 0) - bl.get("loc", 0)
            }

        # Helper to structure min / max / avg deltas for telemetry keys
        def compare_telemetry_metric(metric_name: str, key_base: str):
            b_avg_dict = b_vitals.get("averages", {})
            c_avg_dict = c_vitals.get("averages", {})
            
            b_min = b_avg_dict.get(f"{key_base}_min", b_avg_dict.get(f"{key_base}_avg", 0.0))
            c_min = c_avg_dict.get(f"{key_base}_min", c_avg_dict.get(f"{key_base}_avg", 0.0))
            
            b_max = b_avg_dict.get(f"{key_base}_max", b_avg_dict.get(f"{key_base}_avg", 0.0))
            c_max = c_avg_dict.get(f"{key_base}_max", c_avg_dict.get(f"{key_base}_avg", 0.0))
            
            b_avg = b_avg_dict.get(f"{key_base}_avg", 0.0)
            c_avg = c_avg_dict.get(f"{key_base}_avg", 0.0)
            
            return {
                "min": {
                    "base": round(b_min, 2),
                    "comp": round(c_min, 2),
                    "delta": round(c_min - b_min, 2),
                    "pct": pct_diff(b_min, c_min)
                },
                "max": {
                    "base": round(b_max, 2),
                    "comp": round(c_max, 2),
                    "delta": round(c_max - b_max, 2),
                    "pct": pct_diff(b_max, c_max)
                },
                "avg": {
                    "base": round(b_avg, 2),
                    "comp": round(c_avg, 2),
                    "delta": round(c_avg - b_avg, 2),
                    "pct": pct_diff(b_avg, c_avg)
                }
            }

        telemetry_deltas = {
            "process_cpu": compare_telemetry_metric("Process CPU", "process_cpu"),
            "process_mem": compare_telemetry_metric("Process RAM", "process_mem"),
            "system_cpu": compare_telemetry_metric("System CPU", "system_cpu"),
            "system_mem": compare_telemetry_metric("System RAM", "system_mem"),
            "gpu_util": compare_telemetry_metric("GPU Util", "gpu_util"),
            "gpu_vram": compare_telemetry_metric("GPU VRAM", "gpu_vram")
        }

        return {
            "base": {
                "id": base_id,
                "timestamp": base.get("timestamp"),
                "commit": base.get("git", {}).get("commit_hash")
            },
            "compare": {
                "id": compare_id,
                "timestamp": comp.get("timestamp"),
                "commit": comp.get("git", {}).get("commit_hash")
            },
            "deltas": {
                "startup_duration": {
                    "base": b_startup,
                    "comp": c_startup,
                    "delta": round(c_startup - b_startup, 2),
                    "pct": pct_diff(b_startup, c_startup)
                },
                "health_avg_latency_ms": {
                    "base": b_health,
                    "comp": c_health,
                    "delta": round(c_health - b_health, 2),
                    "pct": pct_diff(b_health, c_health)
                },
                "task_queue_duration_s": {
                    "base": b_task,
                    "comp": c_task,
                    "delta": round(c_task - b_task, 2),
                    "pct": pct_diff(b_task, c_task)
                }
            },
            "repository_compare": repo_compare,
            "telemetry_deltas": telemetry_deltas
        }
    except Exception as e:
        raise HTTPException(500, f"Error building comparison: {e}")


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serve the main tester UI page."""
    idx = STATIC_DIR / "index.html"
    if not idx.exists():
        return HTMLResponse("<h1>Aethvion Suite Tester</h1><p>UI File index.html not found</p>")
    return FileResponse(str(idx))

if __name__ == "__main__":
    port = 8004
    print("\n" + "=" * 60)
    print("  Aethvion Dev Tool — Suite Tester Server Active")
    print(f"  URL : http://localhost:{port}")
    print("=" * 60 + "\n")
    
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=port)
