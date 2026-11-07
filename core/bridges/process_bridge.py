"""
core/bridges/process_bridge.py
Process & GPU/VRAM Sentinel Connector.
Reports NVIDIA GPU utilization, VRAM usage, temperature, and top CPU/RAM processes.
"""

import subprocess
import psutil


def _get_gpu_stats() -> str:
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=4,
        )
        if res.returncode == 0 and res.stdout.strip():
            lines = []
            for row in res.stdout.strip().splitlines():
                parts = [p.strip() for p in row.split(",")]
                if len(parts) >= 6:
                    name, util, mem_u, mem_t, temp, pwr = parts[:6]
                    lines.append(
                        f"GPU: {name} | Load: {util}% | VRAM: {mem_u}/{mem_t} MB | Temp: {temp}°C | Power: {pwr}W"
                    )
            if lines:
                return "\n".join(lines)
    except Exception:
        pass
    return "GPU: No NVIDIA GPU telemetry available (or nvidia-smi not on PATH)."


def get_gpu_and_processes(args: dict = None) -> str:
    """Return live GPU/VRAM stats and the top RAM/CPU consuming processes."""
    if args is None:
        args = {}
    top_n = min(20, max(3, int(args.get("limit", 8) or 8)))

    gpu_block = _get_gpu_stats()

    procs = []
    for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
        try:
            mem_mb = (p.info["memory_info"].rss / (1024 * 1024)) if p.info.get("memory_info") else 0.0
            procs.append({
                "pid": p.info["pid"],
                "name": p.info["name"] or "unknown",
                "mem_mb": mem_mb,
                "cpu": p.info.get("cpu_percent") or 0.0,
            })
        except Exception:
            continue

    by_ram = sorted(procs, key=lambda x: x["mem_mb"], reverse=True)[:top_n]
    ram_lines = [
        f"  - {item['name']} (PID {item['pid']}): {item['mem_mb']:.0f} MB RAM"
        for item in by_ram
    ]

    return (
        f"{gpu_block}\n\n"
        f"Top {top_n} Processes by Memory Usage:\n" + "\n".join(ram_lines)
    )
