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

# ── Digest + search utilities ────────────────────────────────────────────────
import re as _ws_re  # noqa: E402 (appended section)
from datetime import datetime as _ws_dt
from typing import List as _WsList


def generate_file_digest(path: str, content: str,
                     last_action: Optional[str] = None) -> str:
    """Build a rich semantic digest of a file's structure.

    Includes function/selector names WITH line numbers so the agent can jump
    directly to `offset=N` for any function without scanning the whole file.
    Stored in AgentState.file_digests; injected into every prompt as the
    Knowledge block.  Target size: ~400 chars per file.
    """
    ext   = Path(path).suffix.lower()
    lines = content.splitlines()
    ts    = _ws_dt.utcnow().strftime("%H:%M")
    header = f"{path} [{len(lines)}L, {len(content):,}ch]"

    entries: _WsList[str] = []   # "name@line" or "name@line: first-sig"

    if ext in (".js", ".ts", ".jsx", ".tsx", ".mjs"):
        seen: set = set()
        globals_top: _WsList[str] = []
        fns_with_lines: _WsList[str] = []

        for i, line in enumerate(lines, 1):
            # function declarations
            m = _ws_re.match(r"\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*(\([^)]*\))?", line)
            if m and m.group(1) not in seen:
                sig = m.group(2) or "()"
                fns_with_lines.append(f"{m.group(1)}@L{i}{sig}")
                seen.add(m.group(1))
                continue
            # const/let/var arrow functions
            m = _ws_re.match(r"\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)", line)
            if m and m.group(1) not in seen:
                fns_with_lines.append(f"{m.group(1)}@L{i}({m.group(2)})")
                seen.add(m.group(1))
                continue
            # top-of-file globals (first 30 lines only)
            if i <= 30:
                m = _ws_re.match(r"^\s*(?:const|let|var)\s+(\w+)\s*=\s*([^;]{0,40})", line)
                if m and m.group(1) not in seen:
                    globals_top.append(f"{m.group(1)}={m.group(2).strip()[:20]}")

        if fns_with_lines:
            entries.append("functions:\n    " + "\n    ".join(fns_with_lines[:30]))
        if globals_top:
            entries.append("globals: " + ", ".join(globals_top[:8]))

    elif ext == ".css":
        sel_with_lines: _WsList[str] = []
        seen_sel: set = set()
        for i, line in enumerate(lines, 1):
            m = _ws_re.match(r"^([.#]?[\w][\w\s.#:>+~\[\]\"'=*-]*?)\s*\{", line)
            if m:
                sel = m.group(1).strip()
                if sel and sel not in seen_sel:
                    sel_with_lines.append(f"{sel}@L{i}")
                    seen_sel.add(sel)
        if sel_with_lines:
            entries.append("selectors:\n    " + "\n    ".join(sel_with_lines[:30]))

    elif ext in (".html", ".htm"):
        ids = _ws_re.findall(r'\bid=["\']([^"\']+)["\']', content)
        unique_ids = list(dict.fromkeys(ids))
        if unique_ids:
            entries.append("ids: " + ", ".join(unique_ids[:20]))
        # key script/link/meta tags summary
        scripts = _ws_re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', content)
        if scripts:
            entries.append("scripts: " + ", ".join(scripts[:6]))

    elif ext == ".py":
        cls_with_lines: _WsList[str] = []
        fn_with_lines:  List[str] = []
        for i, line in enumerate(lines, 1):
            m = _ws_re.match(r"^class (\w+)", line)
            if m:
                cls_with_lines.append(f"{m.group(1)}@L{i}")
            m = _ws_re.match(r"^\s*def (\w+)\s*(\([^)]*\))?", line)
            if m:
                sig = (m.group(2) or "()").replace("\n", "")[:40]
                fn_with_lines.append(f"{m.group(1)}@L{i}{sig}")
        if cls_with_lines:
            entries.append("classes: " + ", ".join(cls_with_lines[:10]))
        if fn_with_lines:
            entries.append("functions:\n    " + "\n    ".join(fn_with_lines[:25]))

    body = ""
    if entries:
        body = "\n  " + "\n  ".join(entries)

    last = f"\n  last: {last_action} @ {ts}" if last_action else ""
    return f"{header}{body}{last}"

# ── emit ──────────────────────────────────────────────────────


def search_codebase(workspace: Path, query: str, path: str = "", context_lines: int = 1, max_results: int = 30) -> str:
    """Search for a literal string or regex pattern across workspace source files.

    Much cheaper than reading whole files: returns only matching lines with
    a small context window, and the file + line number so the agent can jump
    straight to the right offset with read_file.
    """
    search_root = workspace / path if path else workspace
    if not search_root.exists():
        return f"Error: path '{path}' does not exist in workspace."

    try:
        pattern = _ws_re.compile(query, _ws_re.IGNORECASE)
    except _ws_re.error:
        pattern = _ws_re.compile(_ws_re.escape(query), _ws_re.IGNORECASE)

    if search_root.is_file():
        files: _WsList[Path] = [search_root]
    else:
        files = sorted(
            f for f in search_root.rglob("*")
            if f.is_file()
            and f.suffix.lower() not in BLUEPRINT_SKIP_EXTS
            and not any(part in BLUEPRINT_IGNORE_DIRS
                        for part in f.relative_to(workspace).parts)
        )

    results: _WsList[str] = []
    total_matches = 0

    for filepath in files:
        if total_matches >= max_results:
            break
        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        file_lines = text.splitlines()
        file_hits: _WsList[str] = []

        for lineno, line in enumerate(file_lines, 1):
            if total_matches >= max_results:
                break
            if pattern.search(line):
                total_matches += 1
                ctx_start = max(0, lineno - 1 - context_lines)
                ctx_end   = min(len(file_lines), lineno + context_lines)
                block = []
                for j in range(ctx_start, ctx_end):
                    marker = "→" if j == lineno - 1 else " "
                    block.append(f"  {marker} L{j + 1}: {file_lines[j].rstrip()}")
                file_hits.append("\n".join(block))

        if file_hits:
            rel = str(filepath.relative_to(workspace))
            results.append(f"{rel}:\n" + "\n".join(file_hits))

    if not results:
        scope = f" in '{path}'" if path else ""
        return f"No matches for '{query}'{scope}."

    more = f" (first {max_results} shown)" if total_matches >= max_results else ""
    header = f"Found {total_matches} match{'es' if total_matches != 1 else ''}{more} for '{query}':\n\n"
    return header + "\n\n".join(results)


def parse_dir_entries(listing: str) -> List[str]:
    """Extract bare filenames from _list_dir output (strips emoji prefix)."""
    entries = []
    for line in listing.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip folder/file emoji prefixes added by _list_dir
        for prefix in ("\U0001f4c1 ", "\U0001f4c4 "):
            if line.startswith(prefix):
                line = line[len(prefix):]
                break
        if line:
            entries.append(line)
    return entries

