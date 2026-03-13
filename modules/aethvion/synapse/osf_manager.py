"""
OsfManager — download, install, launch and stop the OpenSeeFace binary.

Installation path: <synapse_module>/openseeface/
Executable:        <synapse_module>/openseeface/facetracker.exe  (Windows)
                   <synapse_module>/openseeface/facetracker      (Linux/macOS)
"""

import asyncio
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import AsyncGenerator, Optional

MODULE_DIR = Path(__file__).parent
OSF_DIR    = MODULE_DIR / "openseeface"

# Executable name varies by platform
_EXE_NAME  = "facetracker.exe" if sys.platform == "win32" else "facetracker"

# The zip ships a Python source stub at the root AND a full PyInstaller bundle
# in Binary/ with all DLLs.  Always prefer the Binary/ version.
OSF_BIN_DIR = OSF_DIR / "Binary"
OSF_EXE     = OSF_BIN_DIR / _EXE_NAME   # primary — full bundle with DLLs
OSF_EXE_FALLBACK = OSF_DIR / _EXE_NAME  # fallback — root stub

GITHUB_API_URL = "https://api.github.com/repos/emilianavt/OpenSeeFace/releases/latest"

# ---------------------------------------------------------------------------

class OsfManager:

    def __init__(self):
        self._process:  Optional[subprocess.Popen] = None
        self._log_file  = None
        self._installing = False

    # ── Status ──────────────────────────────────────────────────────────────

    @property
    def is_installed(self) -> bool:
        return OSF_EXE.exists() or OSF_EXE_FALLBACK.exists()

    def _resolve_exe(self) -> Path:
        """Return the best available facetracker executable."""
        return OSF_EXE if OSF_EXE.exists() else OSF_EXE_FALLBACK

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def get_status(self) -> dict:
        exe = self._resolve_exe() if self.is_installed else None
        return {
            "installed":    self.is_installed,
            "running":      self.is_running,
            "installing":   self._installing,
            "install_path": str(OSF_DIR),
            "exe_path":     str(exe) if exe else None,
        }

    # ── Install (SSE-friendly async generator) ───────────────────────────────

    async def install(self) -> AsyncGenerator[str, None]:
        """
        Async generator that yields SSE-formatted progress events while
        downloading and extracting OpenSeeFace in a background thread.
        """
        if self._installing:
            yield _sse({"step": "error", "msg": "Install already in progress."})
            return

        self._installing = True
        progress_q: queue.Queue = queue.Queue()

        thread = threading.Thread(
            target=self._install_thread,
            args=(progress_q,),
            daemon=True,
        )
        thread.start()

        loop = asyncio.get_event_loop()
        try:
            while True:
                item = await loop.run_in_executor(None, progress_q.get)
                if item is None:          # sentinel — done
                    break
                yield _sse(item)
        finally:
            self._installing = False

    def _install_thread(self, q: queue.Queue):
        try:
            # ── 1. Fetch release metadata ────────────────────────────────────
            q.put({"step": "fetch", "pct": 0,
                   "msg": "Fetching latest release info from GitHub…"})

            req = urllib.request.Request(
                GITHUB_API_URL,
                headers={"User-Agent": "Misaka-Cipher/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                release = json.loads(r.read())

            tag = release.get("tag_name", "unknown")

            # Find a suitable zip asset (prefer Windows zip on win32)
            assets = release.get("assets", [])
            asset  = None

            if sys.platform == "win32":
                # Prefer assets with "win" in the name, fall back to any zip
                asset = next((a for a in assets
                              if a["name"].endswith(".zip")
                              and "win" in a["name"].lower()), None)

            if asset is None:
                asset = next((a for a in assets
                              if a["name"].endswith(".zip")), None)

            if asset is None:
                q.put({"step": "error",
                       "msg": f"No zip release asset found for {tag}. "
                              "Visit github.com/emilianavt/OpenSeeFace/releases."})
                q.put(None)
                return

            download_url = asset["browser_download_url"]
            total_bytes  = asset.get("size", 0)
            size_mb      = f"{total_bytes / 1024 / 1024:.1f}" if total_bytes else "?"

            q.put({"step": "download", "pct": 0,
                   "msg": f"Downloading {asset['name']}  ({size_mb} MB)…"})

            # ── 2. Download ──────────────────────────────────────────────────
            zip_path   = MODULE_DIR / "_osf_tmp.zip"
            downloaded = 0
            last_pct   = -1

            req2 = urllib.request.Request(
                download_url,
                headers={"User-Agent": "Misaka-Cipher/1.0"},
            )
            with urllib.request.urlopen(req2, timeout=300) as r, \
                 open(zip_path, "wb") as f:
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_bytes:
                        pct = int(downloaded / total_bytes * 100)
                        if pct != last_pct and pct % 5 == 0:
                            q.put({"step": "download", "pct": pct,
                                   "msg": f"Downloading… {pct}%"})
                            last_pct = pct

            # ── 3. Extract ───────────────────────────────────────────────────
            q.put({"step": "extract", "pct": 95,
                   "msg": "Extracting archive…"})

            if OSF_DIR.exists():
                shutil.rmtree(OSF_DIR)
            OSF_DIR.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_path) as zf:
                members = zf.namelist()

                # Detect a single top-level folder and strip it
                top_dirs = {m.split("/")[0] for m in members
                            if "/" in m and not m.endswith("/")}
                top_dirs |= {m.rstrip("/") for m in members
                             if m.count("/") == 1 and m.endswith("/")}
                prefix = (next(iter(top_dirs)) + "/") \
                         if len(top_dirs) == 1 else ""

                for member in members:
                    rel = member[len(prefix):] if prefix and member.startswith(prefix) else member
                    if not rel:
                        continue
                    dest = OSF_DIR / rel
                    if member.endswith("/"):
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as src, open(dest, "wb") as dst:
                            shutil.copyfileobj(src, dst)

            zip_path.unlink(missing_ok=True)

            # ── 4. Verify ────────────────────────────────────────────────────
            if not OSF_EXE.exists():
                # Try to find facetracker binary anywhere under OSF_DIR
                candidates = list(OSF_DIR.rglob(_EXE_NAME))
                if candidates:
                    # Move it up to OSF_DIR root
                    shutil.copy2(candidates[0], OSF_EXE)
                else:
                    found = [p.name for p in OSF_DIR.iterdir()]
                    q.put({"step": "error",
                           "msg": f"{_EXE_NAME} not found after extraction. "
                                  f"Contents: {found[:8]}"})
                    q.put(None)
                    return

            # Make executable on Unix
            if sys.platform != "win32":
                OSF_EXE.chmod(OSF_EXE.stat().st_mode | 0o111)

            q.put({"step": "done", "pct": 100,
                   "msg": f"OpenSeeFace {tag} installed successfully."})

        except Exception as exc:
            safe = str(exc).replace('"', "'")
            q.put({"step": "error", "msg": safe})
        finally:
            q.put(None)  # always send sentinel

    # ── Launch / Stop ────────────────────────────────────────────────────────

    @property
    def log_path(self) -> Path:
        return MODULE_DIR / "osf_process.log"

    def get_log_tail(self, lines: int = 30) -> str:
        """Return the last N lines of the facetracker process log."""
        try:
            text = self.log_path.read_text(encoding="utf-8", errors="replace")
            return "\n".join(text.splitlines()[-lines:])
        except FileNotFoundError:
            return ""

    def launch(self, camera_index: int = 0, port: int = 11573,
               host: str = "127.0.0.1") -> dict:
        if not self.is_installed:
            return {"success": False, "error": "OpenSeeFace is not installed."}
        if self.is_running:
            return {"success": False, "error": "OpenSeeFace is already running."}

        exe     = self._resolve_exe()
        exe_dir = exe.parent   # Binary/ for bundled, OSF_DIR for fallback

        # Correct OpenSeeFace CLI:
        #   -c  = camera index
        #   -P  = UDP port  (NOT a protocol toggle)
        #   -i  = destination IP
        cmd = [
            str(exe),
            "-c", str(camera_index),
            "-P", str(port),
            "-i", host,
        ]

        # Run from the exe's own directory so all sibling DLLs are on the
        # Windows loader search path (exe directory is always searched first).
        env = os.environ.copy()
        env["PATH"] = str(exe_dir) + os.pathsep + env.get("PATH", "")

        log_file = open(self.log_path, "w", encoding="utf-8")
        kwargs: dict = {
            "cwd":    str(exe_dir),
            "env":    env,
            "stdout": log_file,
            "stderr": log_file,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            self._process  = subprocess.Popen(cmd, **kwargs)
            self._log_file = log_file
            return {"success": True, "pid": self._process.pid}
        except Exception as exc:
            log_file.close()
            return {"success": False, "error": str(exc)}

    def stop_process(self) -> dict:
        if not self.is_running:
            return {"success": False, "error": "OpenSeeFace is not running."}
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
        self._process = None
        if self._log_file:
            try: self._log_file.close()
            except Exception: pass
            self._log_file = None
        return {"success": True}

    def uninstall(self) -> dict:
        if self.is_running:
            self.stop_process()
        try:
            if OSF_DIR.exists():
                shutil.rmtree(OSF_DIR)
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

osf_manager = OsfManager()
