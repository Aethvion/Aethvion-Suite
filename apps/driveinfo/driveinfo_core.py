"""
Aethvion Drive Info — Core
Scans directory trees and saves / loads .eathscan files.
"""

import os
import json
import shutil
import string
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/apps/driveinfo")
EATHSCAN_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Scan state (shared between background thread and API)
# ---------------------------------------------------------------------------

class ScanState:
    def __init__(self):
        self.reset()

    def reset(self):
        self._lock        = threading.Lock()
        self.running      = False
        self.cancelled    = False
        self.files        = 0
        self.dirs         = 0
        self.bytes_total  = 0
        self.current_path = ""
        self.result       = None
        self.error        = None
        self.start_time   = None
        self.save_path    = None   # path of the auto-saved .eathscan

    def increment(self, *, files=0, dirs=0, size=0, path=""):
        with self._lock:
            self.files       += files
            self.dirs        += dirs
            self.bytes_total += size
            if path:
                self.current_path = path

    def to_dict(self) -> dict:
        with self._lock:
            elapsed = (time.time() - self.start_time) if self.start_time else 0
            return {
                "running":      self.running,
                "cancelled":    self.cancelled,
                "files":        self.files,
                "dirs":         self.dirs,
                "bytes_total":  self.bytes_total,
                "current_path": self.current_path,
                "error":        self.error,
                # done = finished successfully (save_path set, no error)
                "done":         not self.running and self.save_path is not None and not self.error,
                "elapsed":      round(elapsed, 1),
                "save_path":    str(self.save_path) if self.save_path else None,
            }


scan_state = ScanState()
_scan_lock  = threading.Lock()

# ---------------------------------------------------------------------------
# Directory scanner
# ---------------------------------------------------------------------------

def _scan_node(path: Path, state: ScanState) -> dict:
    """Recursively scan *path* and return a tree node dict."""
    node: dict = {
        "name":       path.name or str(path),
        "path":       str(path),
        "type":       "dir",
        "size":       0,
        "file_count": 0,
        "dir_count":  0,
        "children":   [],
    }

    state.increment(dirs=1, path=str(path))

    try:
        entries = list(os.scandir(path))
    except PermissionError:
        node["error"] = "permission_denied"
        return node
    except OSError as exc:
        node["error"] = str(exc)
        return node

    for entry in entries:
        if state.cancelled:
            break
        try:
            if entry.is_symlink():
                continue

            if entry.is_file(follow_symlinks=False):
                try:
                    size = entry.stat(follow_symlinks=False).st_size
                except OSError:
                    size = 0
                ext = Path(entry.name).suffix.lower()
                node["children"].append({
                    "name": entry.name,
                    "path": entry.path,
                    "type": "file",
                    "size": size,
                    "ext":  ext,
                })
                node["size"]       += size
                node["file_count"] += 1
                state.increment(files=1, size=size)

            elif entry.is_dir(follow_symlinks=False):
                child = _scan_node(Path(entry.path), state)
                node["children"].append(child)
                node["size"]       += child["size"]
                node["file_count"] += child["file_count"]
                node["dir_count"]  += child["dir_count"] + 1

        except Exception:
            continue

    # Sort: dirs first (largest first), then files (largest first)
    node["children"].sort(key=lambda c: (0 if c["type"] == "dir" else 1, -c["size"]))
    return node


def _collect_extensions(node: dict, ext_map: dict) -> None:
    """Walk the tree and accumulate per-extension statistics."""
    if node["type"] == "file":
        ext = node.get("ext", "")
        rec = ext_map.setdefault(ext, {"count": 0, "size": 0})
        rec["count"] += 1
        rec["size"]  += node.get("size", 0)
    else:
        for child in node.get("children", []):
            _collect_extensions(child, ext_map)


# ---------------------------------------------------------------------------
# Background scan thread
# ---------------------------------------------------------------------------

def _run_scan(root_path: str) -> None:
    try:
        root = Path(root_path)
        if not root.exists():
            scan_state.error   = f"Path does not exist: {root_path}"
            scan_state.running = False
            return

        tree = _scan_node(root, scan_state)

        if scan_state.cancelled:
            scan_state.running = False
            return

        ext_map = {}
        _collect_extensions(tree, ext_map)
        extensions = dict(
            sorted(ext_map.items(), key=lambda kv: -kv[1]["size"])
        )

        end_time = time.time()
        duration = end_time - scan_state.start_time

        result = {
            "meta": {
                "version":          EATHSCAN_VERSION,
                "app":              "Aethvion Drive Info",
                "scan_date":        datetime.now().isoformat(),
                "root_path":        str(root),
                "total_size":       tree["size"],
                "total_files":      tree["file_count"],
                "total_dirs":       tree["dir_count"],
                "duration_seconds": round(duration, 2),
            },
            "tree":       tree,
            "extensions": extensions,
        }

        # 1. Save the full .eathscan (source of truth)
        scan_state.save_path = save_scan(result)

        # 2. Build the display-optimised variant NOW while the tree is
        #    already in memory — much faster than re-parsing the file later.
        total_size = result["meta"]["total_size"] or 1
        min_bytes  = max(512 * 1024, total_size // 50_000)
        display = {
            "meta":               result["meta"],
            "tree":               build_display_tree(result["tree"], min_bytes),
            "extensions":         result["extensions"],
            "display_pruned":     True,
            "min_bytes_threshold": min_bytes,
        }
        disp_path = _display_path(scan_state.save_path)
        with open(disp_path, "w", encoding="utf-8") as fh:
            json.dump(display, fh, ensure_ascii=False, separators=(",", ":"))

        # 3. Free the huge in-memory tree; the API streams from disk.
        scan_state.result = None

    except Exception as exc:
        scan_state.error = str(exc)
    finally:
        scan_state.running = False


def start_scan(root_path: str) -> bool:
    """Launch a background scan.  Returns False if one is already running."""
    with _scan_lock:
        if scan_state.running:
            return False
        scan_state.reset()
        scan_state.running    = True
        scan_state.start_time = time.time()
        thread = threading.Thread(
            target=_run_scan, args=(root_path,), daemon=True
        )
    thread.start()
    return True


def cancel_scan() -> None:
    scan_state.cancelled = True


# ---------------------------------------------------------------------------
# Display-optimised tree pruning
# ---------------------------------------------------------------------------

def build_display_tree(node: dict, min_bytes: int) -> Optional[dict]:
    """Return a pruned copy of *node* for browser display.

    Entries whose ``size`` is below *min_bytes* are rolled up into a
    single ``[N smaller items]`` placeholder so the treemap keeps correct
    proportions while the JSON stays small enough for the browser.

    Returns ``None`` if the node itself is too small (caller aggregates it).
    """
    node_size = node.get("size", 0)

    if node.get("type") == "file":
        # Small files survive only when large enough
        return node if node_size >= min_bytes else None

    # Directory: prune if the whole subtree is tiny
    if node_size < min_bytes:
        return None

    agg_size  = 0
    agg_count = 0
    kept: list = []

    for child in node.get("children", []):
        child_size = child.get("size", 0)
        if child_size < min_bytes:
            agg_size  += child_size
            agg_count += 1
        elif child.get("type") == "file":
            kept.append(child)          # large file → keep as-is
        else:
            pruned = build_display_tree(child, min_bytes)
            if pruned is not None:
                kept.append(pruned)
            else:
                agg_size  += child_size
                agg_count += 1

    if agg_size > 0:
        kept.append({
            "name": f"[{agg_count:,} smaller items]",
            "path": node["path"] + "/~small~",
            "type": "file",
            "size": agg_size,
            "ext":  "~small~",
        })

    result = dict(node)
    result["children"] = sorted(kept, key=lambda c: -c.get("size", 0))
    return result


def _display_path(scan_path: Path) -> Path:
    """Companion display file path for a given .eathscan path."""
    return scan_path.with_name(scan_path.stem + "_display.eathscan")


def generate_display_scan(scan_path: Path) -> Optional[Path]:
    """Parse *scan_path* and write a pruned display variant next to it.

    Called once (at scan time or on first load of an existing file).
    Returns the path of the generated display file, or None on error.
    """
    out = _display_path(scan_path)
    try:
        with open(scan_path, "r", encoding="utf-8") as fh:
            scan = json.load(fh)
        total_size = scan.get("meta", {}).get("total_size", 1) or 1
        # Threshold: keep items that represent at least 1/50 000 of the drive
        # (minimum 512 KB so tiny folders are always pruned).
        min_bytes = max(512 * 1024, total_size // 50_000)
        display = {
            "meta":               scan.get("meta", {}),
            "tree":               build_display_tree(scan["tree"], min_bytes),
            "extensions":         scan.get("extensions", {}),
            "display_pruned":     True,
            "min_bytes_threshold": min_bytes,
        }
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(display, fh, ensure_ascii=False, separators=(",", ":"))
        return out
    except Exception:
        return None


# ---------------------------------------------------------------------------
# .eathscan file I/O
# ---------------------------------------------------------------------------

def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def save_scan(result: dict, name: Optional[str] = None) -> Path:
    """Persist *result* as a .eathscan file.  Returns the file path.

    Also writes a tiny companion  <name>.meta  file containing only the
    ``meta`` section so that list_scans() can enumerate scans quickly
    without parsing the full (potentially huge) .eathscan file.
    """
    _ensure_data_dir()
    if name is None:
        root = result["meta"]["root_path"]
        # Build a filesystem-safe stem from the scanned root
        safe = (
            root.replace(":", "")
                .replace("\\", "_")
                .replace("/", "_")
                .strip("_") or "scan"
        )
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"{safe}_{ts}"
    if not name.endswith(".eathscan"):
        name += ".eathscan"
    path = DATA_DIR / name
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, separators=(",", ":"))
    # Write tiny companion meta sidecar
    meta_path = path.with_suffix(".meta")
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(result.get("meta", {}), fh, ensure_ascii=False)
    return path


def list_scans() -> list:
    """Return metadata for every .eathscan file in DATA_DIR.

    Reads the tiny companion ``.meta`` sidecar when available so we
    never have to parse the full (potentially huge) scan file just to
    populate the UI dropdown.  Falls back to reading the first 4 KB of
    the .eathscan file for older scans that predate sidecars.
    """
    _ensure_data_dir()
    scans = []
    for p in sorted(
        DATA_DIR.glob("*.eathscan"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    ):
        meta: dict = {}
        # Preferred: tiny companion sidecar written by save_scan()
        sidecar = p.with_suffix(".meta")
        if sidecar.exists():
            try:
                with open(sidecar, "r", encoding="utf-8") as fh:
                    meta = json.load(fh)
            except Exception:
                pass
        else:
            # Fallback: read the first 4 KB and fish out the meta block
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    head = fh.read(4096)
                # The file starts with {"meta":{...},"tree": — grab just the meta
                meta_start = head.find('"meta":')
                if meta_start != -1:
                    # Find the closing brace of the meta object heuristically
                    bracket = 0
                    in_meta = False
                    meta_json = ""
                    for ch in head[meta_start + 7:]:
                        if ch == "{":
                            bracket += 1
                            in_meta = True
                        if in_meta:
                            meta_json += ch
                        if ch == "}" and in_meta:
                            bracket -= 1
                            if bracket == 0:
                                break
                    if meta_json:
                        meta = json.loads(meta_json)
            except Exception:
                pass
        scans.append({
            "filename":  p.name,
            "file_size": p.stat().st_size,
            "meta":      meta,
        })
    return scans


def load_scan(filename: str) -> dict:
    _ensure_data_dir()
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Scan not found: {filename}")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def delete_scan(filename: str) -> None:
    _ensure_data_dir()
    path = DATA_DIR / filename
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# Drive enumeration
# ---------------------------------------------------------------------------

def list_drives() -> list:
    """Return available drives (Windows) or mount points (POSIX)."""
    drives = []
    if sys.platform == "win32":
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if os.path.exists(root):
                try:
                    usage = shutil.disk_usage(root)
                    drives.append({
                        "path":  root,
                        "label": f"{letter}:",
                        "total": usage.total,
                        "used":  usage.used,
                        "free":  usage.free,
                    })
                except Exception:
                    drives.append({
                        "path": root, "label": f"{letter}:",
                        "total": 0, "used": 0, "free": 0,
                    })
    else:
        try:
            usage = shutil.disk_usage("/")
            drives.append({
                "path": "/", "label": "/ (root)",
                "total": usage.total, "used": usage.used, "free": usage.free,
            })
        except Exception:
            drives.append({
                "path": "/", "label": "/ (root)",
                "total": 0, "used": 0, "free": 0,
            })
    return drives
