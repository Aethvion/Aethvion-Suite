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

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

# Initialize Paths
REPORTS_DIR = PROJECT_ROOT / "data" / "devtools" / "suite_tester" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
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

def get_gpu_usage() -> Dict[str, Any]:
    """Helper to fetch GPU and VRAM usage on NVIDIA cards."""
    import shutil
    if not shutil.which("nvidia-smi"):
        return {"status": "N/A", "utilization": 0, "vram_used_mb": 0, "vram_total_mb": 0}
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000 # CREATE_NO_WINDOW
        )
        parts = [p.strip() for p in output.split(",")]
        if len(parts) >= 3:
            return {
                "status": "Available",
                "utilization": int(parts[0]),
                "vram_used_mb": int(parts[1]),
                "vram_total_mb": int(parts[2])
            }
    except Exception:
        pass
    return {"status": "Error reading GPU", "utilization": 0, "vram_used_mb": 0, "vram_total_mb": 0}

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
                # Fetch PID holding the port and terminate it
                for proc in psutil.process_iter(['pid', 'connections']):
                    try:
                        for conn in proc.connections(kind='inet'):
                            if conn.laddr.port == test_port:
                                add_log(run_id, f"Killing process {proc.pid} holding port {test_port}")
                                proc.kill()
                    except Exception:
                        pass
                time.sleep(1.0)
    except Exception as exc:
        add_log(run_id, f"Port check skipped: {exc}")

    # Build process execution env
    test_env = os.environ.copy()
    test_env["PORT"] = str(test_port)
    test_env["AETHVION_DEV"] = "1"
    test_env["AETHVION_NO_BROWSER"] = "1"
    test_env["PYTHONPATH"] = str(PROJECT_ROOT)
    test_env["PYTHONUNBUFFERED"] = "1"

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

    # Poll startup status
    startup_success = False
    startup_duration = 0.0
    
    # Wait up to 35 seconds
    poll_start = time.time()
    while time.time() - poll_start < 35:
        # Check if process died
        if suite_proc.poll() is not None:
            add_log(run_id, f"CRITICAL: Process terminated prematurely with exit code {suite_proc.returncode}")
            break
            
        res = make_http_request(f"{test_url}/api/system/startup-status", timeout=2.0)
        if res["success"]:
            body = res["body"]
            status_str = body.get("status", "Starting")
            progress_int = body.get("progress", 0)
            initialized = body.get("initialized", False)
            add_log(run_id, f"Suite startup status: {status_str} ({progress_int}%)")
            
            if initialized:
                startup_success = True
                startup_duration = time.time() - startup_start
                add_log(run_id, f"SUCCESS: Aethvion Suite is fully ready in {startup_duration:.2f} seconds!")
                break
        else:
            add_log(run_id, "Waiting for HTTP server to respond...")
            
        time.sleep(1.0)

    if not startup_success:
        add_log(run_id, "CRITICAL: Startup timeout or failure.")
        try:
            suite_proc.terminate()
            suite_proc.wait(timeout=3)
        except Exception:
            suite_proc.kill()
        with runs_lock:
            test_runs[run_id]["status"] = "failed"
            test_runs[run_id]["error"] = "Startup timed out or crashed"
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
    
    # Task state mapping
    task_submitted = False
    task_id = None
    task_success = False
    task_start_time = 0.0
    task_duration = 0.0
    ai_response = ""
    task_error = None
    temp_thread_id = f"perf_test_thread_{uuid.uuid4().hex[:6]}"

    # 60 seconds loop
    for sec in range(1, 61):
        if suite_proc.poll() is not None:
            add_log(run_id, "CRITICAL: Suite process died during profiling run.")
            break

        # Capture metrics
        proc_usage = get_process_resource_usage(suite_proc.pid)
        sys_usage = {
            "system_cpu": psutil.cpu_percent(),
            "system_mem": psutil.virtual_memory().percent
        }
        gpu_usage = get_gpu_usage()
        
        snapshot = {
            "second": sec,
            "process_cpu": proc_usage["cpu_percent"],
            "process_mem": proc_usage["memory_mb"],
            "system_cpu": sys_usage["system_cpu"],
            "system_mem": sys_usage["system_mem"],
            "gpu_util": gpu_usage["utilization"] if gpu_usage["status"] == "Available" else 0,
            "gpu_vram": gpu_usage["vram_used_mb"] if gpu_usage["status"] == "Available" else 0
        }
        timeseries_data.append(snapshot)

        # Print log message every 10 seconds
        if sec % 10 == 0:
            add_log(run_id, f"Profiling: Captured telemetry snapshot at second {sec}/60. (Proc Memory: {proc_usage['memory_mb']}MB, Sys CPU: {sys_usage['system_cpu']}%)")

        # Inject load: trigger LLM Task Routing at second 15
        if sec == 15 and not task_submitted:
            add_log(run_id, "Injecting Load: Submitting test prompt request to agent task queue...")
            task_prompt = "Respond with exactly the single word: ACKNOWLEDGED"
            submit_res = make_http_request(
                f"{test_url}/api/tasks/submit", 
                method="POST", 
                data={
                    "prompt": task_prompt,
                    "thread_id": temp_thread_id,
                    "mode": "chat_only"
                }
            )
            if submit_res["success"]:
                task_id = submit_res["body"].get("task_id")
                task_submitted = True
                task_start_time = time.time()
                add_log(run_id, f"Load Task submitted successfully (Task ID: {task_id}). Monitoring queue...")
            else:
                add_log(run_id, f"Load Injection Error: Failed to submit task: {submit_res['body']}")
                task_error = str(submit_res["body"])

        # Poll task status if active
        if task_submitted and not task_success and not task_error:
            status_res = make_http_request(f"{test_url}/api/tasks/status/{task_id}")
            if status_res["success"]:
                task_info = status_res["body"]
                status_str = task_info.get("status", "queued")
                if status_str in ["completed", "done", "success"]:
                    task_success = True
                    task_duration = time.time() - task_start_time
                    result_dict = task_info.get("result", {})
                    ai_response = result_dict.get("response", "")
                    add_log(run_id, f"Load Task finished in {task_duration:.2f}s with response: '{ai_response.strip()}'")
                elif status_str in ["failed", "cancelled", "error"]:
                    task_error = f"Orchestrator error status: {status_str}"
                    add_log(run_id, f"Load Task failed during execution: {task_info.get('error')}")
            else:
                add_log(run_id, f"Warning: Load Task polling failed: {status_res['body']}")

        time.sleep(1.0)

    # Clean up thread if it was created
    if task_submitted:
        make_http_request(f"{test_url}/api/tasks/thread/{temp_thread_id}", method="DELETE")

    # API Routing Health Check Latency Check
    add_log(run_id, "Checking server response latency...")
    health_latencies = []
    for _ in range(5):
        res = make_http_request(f"{test_url}/health")
        if res["success"]:
            health_latencies.append(res["latency_ms"])
        time.sleep(0.1)
    avg_health_latency = sum(health_latencies) / len(health_latencies) if health_latencies else 0.0

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

    if not graceful_success:
        add_log(run_id, "Force-killing suite process...")
        try:
            suite_proc.kill()
            suite_proc.wait(timeout=2)
            add_log(run_id, "Process killed forcefully.")
        except Exception as e:
            add_log(run_id, f"Error killing process: {e}")

    # Scan project source stats
    add_log(run_id, "Scanning repository codebase stats...")
    repo_stats = get_repository_stats()

    # Compile report and calculate averages
    p_cpus = [s["process_cpu"] for s in timeseries_data]
    p_mems = [s["process_mem"] for s in timeseries_data]
    s_cpus = [s["system_cpu"] for s in timeseries_data]
    s_mems = [s["system_mem"] for s in timeseries_data]
    gpu_utils = [s["gpu_util"] for s in timeseries_data]
    gpu_vrams = [s["gpu_vram"] for s in timeseries_data]

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
                "process_cpu_avg": round(sum(p_cpus)/len(p_cpus), 1) if p_cpus else 0.0,
                "process_cpu_max": round(max(p_cpus), 1) if p_cpus else 0.0,
                "process_cpu_min": round(min(p_cpus), 1) if p_cpus else 0.0,
                
                "process_mem_avg": round(sum(p_mems)/len(p_mems), 2) if p_mems else 0.0,
                "process_mem_max": round(max(p_mems), 2) if p_mems else 0.0,
                "process_mem_min": round(min(p_mems), 2) if p_mems else 0.0,
                
                "system_cpu_avg": round(sum(s_cpus)/len(s_cpus), 1) if s_cpus else 0.0,
                "system_cpu_max": round(max(s_cpus), 1) if s_cpus else 0.0,
                "system_cpu_min": round(min(s_cpus), 1) if s_cpus else 0.0,
                
                "system_mem_avg": round(sum(s_mems)/len(s_mems), 1) if s_mems else 0.0,
                "system_mem_max": round(max(s_mems), 1) if s_mems else 0.0,
                "system_mem_min": round(min(s_mems), 1) if s_mems else 0.0,
                
                "gpu_util_avg": round(sum(gpu_utils)/len(gpu_utils), 1) if gpu_utils else 0.0,
                "gpu_util_max": round(max(gpu_utils), 1) if gpu_utils else 0.0,
                "gpu_util_min": round(min(gpu_utils), 1) if gpu_utils else 0.0,
                
                "gpu_vram_avg": round(sum(gpu_vrams)/len(gpu_vrams), 2) if gpu_vrams else 0.0,
                "gpu_vram_max": round(max(gpu_vrams), 2) if gpu_vrams else 0.0,
                "gpu_vram_min": round(min(gpu_vrams), 2) if gpu_vrams else 0.0
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

    # Write report file
    report_file = REPORTS_DIR / f"{report_id}.json"
    try:
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=4)
        add_log(run_id, f"Saved performance report: {report_file.name}")
    except Exception as e:
        add_log(run_id, f"Error saving report file: {e}")

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
