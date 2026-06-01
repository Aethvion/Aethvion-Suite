"""
core/orchestrator/workspace_tools.py
═════════════════════════════════════
Blueprint generation and workspace scanning utilities.
Extracted from agent_runner.py — shared by AgentRunner and CorpManager.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

# ── Blueprint / search constants ──────────────────────────────────────────────
BLUEPRINT_IGNORE_DIRS = frozenset({
    '.git', 'node_modules', '__pycache__', '.next', 'dist', 'build',
    '.venv', 'venv', 'env', '.tox', '.pytest_cache', '.mypy_cache',
    'coverage', '.cache', 'tmp', 'temp', '.idea', '.vscode',
})
BLUEPRINT_SKIP_EXTS = frozenset({
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.webp', '.avif', '.tif', '.tiff',
    '.ttf', '.woff', '.woff2', '.eot', '.otf',
    '.mp4', '.mp3', '.wav', '.webm', '.avi', '.mov', '.ogg', '.flac',
    '.zip', '.gz', '.tar', '.rar', '.7z', '.bz2',
    '.pyc', '.pyo', '.so', '.dll', '.exe', '.bin', '.class',
    '.map',
})
BLUEPRINT_MAX_FILES_PER_DIR = 20   # show first N files per directory, summarise the rest
BLUEPRINT_MAX_DEPTH         = 6    # max folder depth to recurse
BLUEPRINT_MAX_LINES         = 500  # hard cap on output lines
BLUEPRINT_CACHE_SECS        = 120  # seconds before cached _blueprint.txt is stale


def _bp_fmt_size(n: int) -> str:
    if n < 1024:       return f"{n}B"
    if n < 1_048_576:  return f"{n // 1024}k"
    return f"{n / 1_048_576:.1f}M"


def build_workspace_blueprint(
    workspace: Path,
    sub_path: str = "",
    cache_path: Optional[Path] = None,
) -> str:
    """Walk the workspace once and return a compact hierarchical file map.

    • ``cache_path`` — where to write the cached snapshot.  Corp callers pass a
      path inside ``data/agent_corps/{id}/`` so the file never appears in the
      user's project.  Standalone agents default to ``workspace/_blueprint.txt``.
    • Pass ``sub_path`` to get an expanded view of a specific subdirectory.
    • Binary assets (images, fonts, video…) and tooling dirs (.git, node_modules…)
      are silently excluded so the output stays focused on source files.
    """
    import time

    root = workspace / sub_path if sub_path else workspace
    if not root.exists():
        return f"Error: path '{sub_path}' not found in workspace."

    effective_cache = cache_path or (workspace / "_blueprint.txt")

    # When a custom cache_path is provided (i.e. data dir, not the workspace),
    # an older code path.  Do this once, silently.
    if cache_path is not None:
        _old_ws_bp = workspace / "_blueprint.txt"
        if _old_ws_bp.exists() and _old_ws_bp != effective_cache:
            try:
                _old_ws_bp.unlink()
            except Exception:
                pass

    if not sub_path and effective_cache.exists():
        try:
            if time.time() - effective_cache.stat().st_mtime < BLUEPRINT_CACHE_SECS:
                return effective_cache.read_text(encoding="utf-8")
        except Exception:
            pass

    lines: list[str] = []

    def walk(path: Path, prefix: str, depth: int) -> None:
        if depth > BLUEPRINT_MAX_DEPTH:
            lines.append(f"{prefix}… (depth limit)")
            return
        try:
            entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        except PermissionError:
            return

        dirs = [
            e for e in entries
            if e.is_dir() and e.name not in BLUEPRINT_IGNORE_DIRS and not e.name.startswith(".")
        ]
        files = [
            e for e in entries
            if e.is_file()
            and e.suffix.lower() not in BLUEPRINT_SKIP_EXTS
            and e.name != "_blueprint.txt"
        ]

        shown  = files[:BLUEPRINT_MAX_FILES_PER_DIR]
        hidden = files[BLUEPRINT_MAX_FILES_PER_DIR:]

        items = dirs + shown
        for i, item in enumerate(items):
            last_visible = (i == len(items) - 1) and not hidden
            conn      = "└── " if last_visible else "├── "
            child_pfx = prefix + ("    " if last_visible else "│   ")

            if item.is_dir():
                try:
                    sub = list(item.iterdir())
                    n_f = sum(1 for e in sub if e.is_file() and e.suffix.lower() not in BLUEPRINT_SKIP_EXTS)
                    n_d = sum(1 for e in sub if e.is_dir()
                              and e.name not in BLUEPRINT_IGNORE_DIRS and not e.name.startswith("."))
                    ext_ctr: dict[str, int] = {}
                    for e in sub:
                        if e.is_file() and e.suffix.lower() not in BLUEPRINT_SKIP_EXTS:
                            ext = e.suffix.lower() or "(no ext)"
                            ext_ctr[ext] = ext_ctr.get(ext, 0) + 1
                    top = sorted(ext_ctr.items(), key=lambda x: -x[1])[:3]
                    ext_str = ", ".join(f"{c}×{e}" for e, c in top)
                    meta = f"{n_f} files" + (f" [{ext_str}]" if ext_str else "") + (f", {n_d} subdirs" if n_d else "")
                except Exception:
                    meta = ""
                lines.append(f"{prefix}{conn}{item.name}/  ({meta})")
                walk(item, child_pfx, depth + 1)
            else:
                try:
                    sz = _bp_fmt_size(item.stat().st_size)
                except Exception:
                    sz = ""
                lines.append(f"{prefix}{conn}{item.name}  {sz}")

        if hidden:
            ext_ctr2: dict[str, int] = {}
            for f in hidden:
                ext = f.suffix.lower() or "(no ext)"
                ext_ctr2[ext] = ext_ctr2.get(ext, 0) + 1
            top2 = sorted(ext_ctr2.items(), key=lambda x: -x[1])[:3]
            ext_str2 = ", ".join(f"{c}×{e}" for e, c in top2)
            lines.append(f"{prefix}└── … {len(hidden)} more [{ext_str2}]  "
                         f"(use get_project_blueprint with path=\"{path.relative_to(workspace)}\" for full list)")

    walk(root, "", 0)

    if len(lines) > BLUEPRINT_MAX_LINES:
        lines = lines[:BLUEPRINT_MAX_LINES]
        lines.append("… [truncated — use path= parameter to explore a specific subdirectory]")

    header = f"# Blueprint: {sub_path or workspace.name}/  ({len(lines)} entries)\n"
    result = header + "\n".join(lines)

    if not sub_path:
        try:
            effective_cache.parent.mkdir(parents=True, exist_ok=True)
            effective_cache.write_text(result, encoding="utf-8")
        except Exception:
            pass

    return result

