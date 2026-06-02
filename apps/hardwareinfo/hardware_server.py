"""
Aethvion Hardware Info — FastAPI backend v1.0.0

Real-time hardware monitoring: CPU, memory, GPU, storage, network, battery.
WebSocket at /ws/live streams a JSON payload every second.
Static snapshot at GET /api/info.
Port 8084 by default (HWINFO_PORT env var).
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Optional

import uvicorn
import psutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from core.utils import fastapi_utils

# Path setup
MODULE_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(MODULE_DIR, "..", ".."))
for _p in (MODULE_DIR, PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# Optional dependencies
try:
    import cpuinfo as _cpuinfo
    HAS_CPUINFO = True
except ImportError:
    HAS_CPUINFO = False

try:
    import GPUtil as _gputil
    HAS_GPUTIL = True
except ImportError:
    HAS_GPUTIL = False

# Subprocess helper: suppress CMD flashes on Windows
# GPUtil calls nvidia-smi via subprocess.Popen every poll cycle.  Without this
# fix each call briefly flashes a black CMD window on Windows.
import contextlib as _contextlib

@_contextlib.contextmanager
def _no_window():
    """Temporarily patch subprocess.Popen to add CREATE_NO_WINDOW on Windows."""
    if os.name != "nt":
        yield
        return
    import subprocess as _sp
    _orig = _sp.Popen
    _CREATE_NO_WINDOW = 0x08000000
    class _Patched(_orig):
        def __init__(self, *a, **kw):
            kw["creationflags"] = kw.get("creationflags", 0) | _CREATE_NO_WINDOW
            super().__init__(*a, **kw)
    _sp.Popen = _Patched
    try:
        yield
    finally:
        _sp.Popen = _orig

try:
    import wmi as _wmi_mod
    _wmi = _wmi_mod.WMI()
    HAS_WMI = True
except Exception:
    HAS_WMI  = False
    _wmi     = None

# FastAPI app
app = FastAPI(title="Aethvion Hardware Info", version="1.0.0")
fastapi_utils.add_dev_cache_control(app)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

BASE_DIR   = Path(__file__).parent
VIEWER_DIR = BASE_DIR / "viewer"

# Static system info (gathered once at startup)
def _get_static_info() -> dict:
    uname = platform.uname()

    # CPU
    cpu_name = uname.processor or platform.processor() or "Unknown CPU"
    cpu: dict = {
        "name":           cpu_name,
        "physical_cores": psutil.cpu_count(logical=False) or 1,
        "logical_cores":  psutil.cpu_count(logical=True)  or 1,
        "arch":           uname.machine,
        "max_freq_mhz":   None,
        "min_freq_mhz":   None,
        "l2_cache":       "",
        "l3_cache":       "",
    }
    try:
        freq = psutil.cpu_freq()
        if freq:
            cpu["max_freq_mhz"] = round(freq.max) if freq.max else None
            cpu["min_freq_mhz"] = round(freq.min) if freq.min else None
    except Exception:
        pass
    if HAS_CPUINFO:
        try:
            ci = _cpuinfo.get_cpu_info()
            cpu["name"]     = ci.get("brand_raw", cpu["name"])
            cpu["arch"]     = ci.get("arch",           cpu["arch"])
            cpu["l2_cache"] = ci.get("l2_cache_size",  "")
            cpu["l3_cache"] = ci.get("l3_cache_size",  "")
        except Exception:
            pass
    elif HAS_WMI:
        try:
            wmi_cpu = _wmi.Win32_Processor()[0]
            cpu["name"] = wmi_cpu.Name.strip()
        except Exception:
            pass

    # Memory
    vm   = psutil.virtual_memory()
    swap = psutil.swap_memory()
    memory = {
        "total_bytes":    vm.total,
        "total_gb":       round(vm.total / 1073741824, 1),
        "swap_total_gb":  round(swap.total / 1073741824, 1),
    }

    # Disks
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "device":     part.device,
                "mountpoint": part.mountpoint,
                "fstype":     part.fstype,
                "total_gb":   round(usage.total / 1073741824, 1),
                "used_gb":    round(usage.used  / 1073741824, 1),
                "free_gb":    round(usage.free  / 1073741824, 1),
                "percent":    usage.percent,
            })
        except (PermissionError, OSError):
            pass

    # GPU
    gpus = []
    if HAS_GPUTIL:
        try:
            with _no_window():
                for g in _gputil.getGPUs():
                    gpus.append({
                        "id":           g.id,
                        "name":         g.name,
                        "driver":       g.driver,
                        "mem_total_mb": int(g.memoryTotal),
                    })
        except Exception:
            pass
    if not gpus and HAS_WMI:
        try:
            for g in _wmi.Win32_VideoController():
                if g.Name:
                    gpus.append({
                        "id":           len(gpus),
                        "name":         g.Name.strip(),
                        "driver":       getattr(g, "DriverVersion", ""),
                        "mem_total_mb": round(int(g.AdapterRAM or 0) / 1048576) if g.AdapterRAM else 0,
                    })
        except Exception:
            pass

    # Network interfaces
    nets = []
    addrs_map = psutil.net_if_addrs()
    stats_map = psutil.net_if_stats()
    for name, stats in stats_map.items():
        if not stats.isup:
            continue
        ipv4 = [a.address for a in addrs_map.get(name, []) if a.family == 2]
        nets.append({
            "name":       name,
            "speed_mbps": stats.speed,
            "ipv4":       ipv4[0] if ipv4 else "",
        })

    # Motherboard / OS
    board = {}
    if HAS_WMI:
        try:
            mb = _wmi.Win32_BaseBoard()[0]
            board = {"manufacturer": mb.Manufacturer, "product": mb.Product}
        except Exception:
            pass

    return {
        "os": {
            "system":    uname.system,
            "release":   uname.release,
            "version":   uname.version,
            "hostname":  uname.node,
            "boot_time": psutil.boot_time(),
        },
        "cpu":    cpu,
        "memory": memory,
        "disks":  disks,
        "gpus":   gpus,
        "nets":   nets,
        "board":  board,
    }

STATIC_INFO: dict = {}

# Live data collector
class LiveCollector:
    """Collects a live hardware snapshot (non-blocking, uses delta since last call)."""

    def __init__(self):
        self._prev_net   = psutil.net_io_counters()
        self._prev_disk  = self._safe_disk_io()
        self._prev_time  = time.monotonic()
        # Prime cpu_percent so first real call returns valid data
        psutil.cpu_percent(percpu=True)
        try:
            psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"])
        except Exception:
            pass

    @staticmethod
    def _safe_disk_io():
        try:
            return psutil.disk_io_counters()
        except Exception:
            return None

    def collect(self) -> dict:
        now = time.monotonic()
        dt  = max(now - self._prev_time, 0.001)
        self._prev_time = now

        # CPU
        per_core = psutil.cpu_percent(percpu=True)
        total_pct = round(sum(per_core) / len(per_core), 1) if per_core else 0.0
        cpu_freq_mhz = 0
        try:
            freq = psutil.cpu_freq()
            if freq:
                cpu_freq_mhz = round(freq.current)
        except Exception:
            pass

        # Temperatures
        cpu_temp = None
        all_temps: dict[str, list] = {}
        try:
            raw = psutil.sensors_temperatures()
            if raw:
                for key, readings in raw.items():
                    all_temps[key] = [
                        {"label":    r.label or key,
                         "current":  round(r.current, 1),
                         "high":     r.high,
                         "critical": r.critical}
                        for r in readings
                    ]
                # Best-guess CPU temp
                for k in ("coretemp", "k10temp", "cpu_thermal", "cpu-thermal",
                          "zenpower", "acpitz"):
                    if k in all_temps and all_temps[k]:
                        cpu_temp = all_temps[k][0]["current"]
                        break
        except Exception:
            pass
        # WMI thermal zone fallback (Windows)
        if cpu_temp is None and HAS_WMI:
            try:
                zones = _wmi.MSAcpi_ThermalZoneTemperature()
                if zones:
                    cpu_temp = round((zones[0].CurrentTemperature / 10) - 273.15, 1)
            except Exception:
                pass

        # Memory
        vm   = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # Disk I/O
        disk_r = disk_w = 0.0
        curr_disk = self._safe_disk_io()
        if curr_disk and self._prev_disk:
            disk_r = max(0.0, (curr_disk.read_bytes  - self._prev_disk.read_bytes)  / dt / 1048576)
            disk_w = max(0.0, (curr_disk.write_bytes - self._prev_disk.write_bytes) / dt / 1048576)
        self._prev_disk = curr_disk

        # Network I/O
        net_up = net_down = 0.0
        try:
            curr_net = psutil.net_io_counters()
            net_up   = max(0.0, (curr_net.bytes_sent - self._prev_net.bytes_sent) / dt / 1048576)
            net_down = max(0.0, (curr_net.bytes_recv - self._prev_net.bytes_recv) / dt / 1048576)
            self._prev_net = curr_net
        except Exception:
            pass

        # GPU
        gpus = []
        if HAS_GPUTIL:
            try:
                with _no_window():
                    for g in _gputil.getGPUs():
                        gpus.append({
                            "id":           g.id,
                            "load_pct":     round(g.load * 100, 1),
                            "mem_used_mb":  int(g.memoryUsed),
                            "mem_total_mb": int(g.memoryTotal),
                            "mem_pct":      round(g.memoryUsed / g.memoryTotal * 100, 1) if g.memoryTotal else 0,
                            "temp_c":       g.temperature,
                        })
            except Exception:
                pass

        # Battery
        battery = None
        try:
            bat = psutil.sensors_battery()
            if bat:
                secs = bat.secsleft
                battery = {
                    "percent": round(bat.percent, 1),
                    "plugged": bat.power_plugged,
                    "secs_left": int(secs) if secs not in (
                        psutil.POWER_TIME_UNLIMITED,
                        psutil.POWER_TIME_UNKNOWN,
                        -1,
                    ) else None,
                }
        except Exception:
            pass

        # Top processes
        procs = []
        try:
            raw_procs = sorted(
                psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                key=lambda p: p.info.get("cpu_percent") or 0.0,
                reverse=True,
            )[:15]
            for p in raw_procs:
                procs.append({
                    "pid":     p.info["pid"],
                    "name":    p.info["name"] or "?",
                    "cpu_pct": round(p.info.get("cpu_percent") or 0.0, 1),
                    "mem_pct": round(p.info.get("memory_percent") or 0.0, 2),
                })
        except Exception:
            pass

        return {
            "ts":          time.time(),
            "uptime_secs": time.time() - psutil.boot_time(),
            "cpu": {
                "total_pct":  total_pct,
                "per_core":   [round(p, 1) for p in per_core],
                "freq_mhz":   cpu_freq_mhz,
                "temp_c":     cpu_temp,
            },
            "memory": {
                "used_gb":      round(vm.used      / 1073741824, 2),
                "available_gb": round(vm.available / 1073741824, 2),
                "total_gb":     round(vm.total     / 1073741824, 1),
                "percent":      vm.percent,
                "swap_used_gb": round(swap.used    / 1073741824, 2),
                "swap_pct":     swap.percent,
            },
            "disk_io": {
                "read_mb_s":  round(disk_r, 2),
                "write_mb_s": round(disk_w, 2),
            },
            "network": {
                "up_mb_s":   round(net_up,   3),
                "down_mb_s": round(net_down, 3),
            },
            "gpus":      gpus,
            "battery":   battery,
            "processes": procs,
            "temps":     all_temps,
        }


# Shared collector instance (one per server process)
_collector: Optional[LiveCollector] = None

def _get_collector() -> LiveCollector:
    global _collector
    if _collector is None:
        _collector = LiveCollector()
    return _collector

# Endpoints
@app.get("/api/info")
async def get_info():
    return JSONResponse(STATIC_INFO)

@app.get("/api/live")
async def get_live_once():
    """Single live snapshot (REST fallback if WS is unavailable)."""
    data = await asyncio.to_thread(_get_collector().collect)
    return JSONResponse(data)

@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await ws.accept()
    collector = _get_collector()
    try:
        while True:
            await asyncio.sleep(1)
            data = await asyncio.to_thread(collector.collect)
            await ws.send_text(json.dumps(data))
    except (WebSocketDisconnect, Exception):
        pass

# Static files + root
app.mount("/viewer", StaticFiles(directory=str(VIEWER_DIR)), name="viewer")

@app.get("/", response_class=HTMLResponse)
async def index():
    return (VIEWER_DIR / "index.html").read_text(encoding="utf-8")

@app.get("/favicon.ico")
async def favicon():
    return JSONResponse({"ok": True})

# Launch
def launch():
    global STATIC_INFO
    print("[Hardware Info] Gathering static system info…")
    STATIC_INFO = _get_static_info()
    # Prime the live collector
    _get_collector()

    from core.utils.port_manager import PortManager
    base_port = int(os.getenv("HWINFO_PORT", "8084"))
    port = PortManager.bind_port("Aethvion Hardware Info", base_port)
    print(f"[Hardware Info] Aethvion Hardware Info v1.0.0 -> http://localhost:{port}")

    # Open in browser app-mode unless the master launcher already handles it
    try:
        from core.utils.browser import open_app_window
        open_app_window(f"http://localhost:{port}", delay=1.5)
    except Exception:
        pass

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    launch()
