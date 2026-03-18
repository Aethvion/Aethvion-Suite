"""
Aethvion Code IDE — FastAPI backend v1.0.0

Provides file-system access, code execution, and AI assistant endpoints.
Runs on port 8083 by default (CODE_PORT env var).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid as _uuid_mod
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, List, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Path setup ──────────────────────────────────────────────────────────────
MODULE_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(MODULE_DIR, "..", ".."))
for _p in (MODULE_DIR, PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# ── Provider integration ─────────────────────────────────────────────────────
try:
    from core.providers.provider_manager import ProviderManager
    pm = ProviderManager()
    HAS_PROVIDERS = True
except Exception as _e:
    print(f"[Code IDE] Provider manager unavailable: {_e}")
    pm   = None
    HAS_PROVIDERS = False

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="Aethvion Code IDE", version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

BASE_DIR   = Path(__file__).parent
VIEWER_DIR = BASE_DIR / "viewer"
ROOT       = Path(PROJECT_ROOT)

# Workspace exposed in the file tree
WORKSPACE = ROOT

# ── Persistence helpers ────────────────────────────────────────────────────────
DATA_DIR      = ROOT / "data" / "apps" / "code"
PROJECTS_DIR  = DATA_DIR / "projects"
SETTINGS_FILE = DATA_DIR / "settings.json"
USAGE_LOG_DIR    = ROOT / "data" / "ai" / "logs" / "usage"
MODEL_REGISTRY   = ROOT / "data" / "config" / "model_registry.json"

def _ensure_data_dirs():
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.exists():
        SETTINGS_FILE.write_text(json.dumps(
            {"last_workspace": str(ROOT).replace("\\", "/"),
             "recent_workspaces": []}, indent=2))

_ensure_data_dirs()

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _project_key(path: str) -> str:
    """Derive a safe filesystem name from a workspace path."""
    clean = re.sub(r'[^a-zA-Z0-9]', '_', path)
    return clean[:80]

def _project_file(workspace: str) -> Path:
    return PROJECTS_DIR / (_project_key(workspace) + ".json")

def _read_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"last_workspace": str(ROOT).replace("\\", "/"),
                "recent_workspaces": []}

def _write_settings(data: dict):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def _read_project(workspace: str) -> dict:
    f = _project_file(workspace)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "workspace":   workspace,
        "name":        Path(workspace).name,
        "last_opened": _now_iso(),
        "open_tabs":   [],
        "active_tab":  None,
        "structure":   [],
        "ai_context":  "",
    }

def _write_project(data: dict):
    workspace = data.get("workspace", "")
    if not workspace:
        return
    data.setdefault("name", Path(workspace).name)
    data["last_opened"] = _now_iso()
    _project_file(workspace).write_text(json.dumps(data, indent=2), encoding="utf-8")
    # Keep recent_workspaces in settings up to date
    settings = _read_settings()
    settings["last_workspace"] = workspace
    recent = [r for r in settings.get("recent_workspaces", [])
              if r["path"] != workspace]
    recent.insert(0, {
        "path":        workspace,
        "name":        data.get("name", Path(workspace).name),
        "last_opened": data["last_opened"],
    })
    settings["recent_workspaces"] = recent[:12]
    _write_settings(settings)

def _scan_structure(workspace: str, max_files: int = 300) -> list[str]:
    """Return a flat list of relative paths for AI context (dirs end with /)."""
    SKIP = {".git", "__pycache__", "node_modules", ".venv", "venv",
            "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
            "LocalModels", ".claude"}
    root = Path(workspace)
    result: list[str] = []

    def _walk(p: Path, prefix: str = ""):
        if len(result) >= max_files:
            return
        try:
            entries = sorted(p.iterdir(), key=lambda e: (_safe_is_file(e), e.name.lower()))
        except (PermissionError, OSError):
            return
        for entry in entries:
            if entry.name.startswith(".") or entry.name in SKIP:
                continue
            rel = prefix + entry.name
            if _safe_is_dir(entry):
                result.append(rel + "/")
                _walk(entry, rel + "/")
            elif _safe_is_file(entry):
                result.append(rel)

    _walk(root)
    return result

# ── Language detection ────────────────────────────────────────────────────────
LANG_MAP: dict[str, str] = {
    ".py": "python",    ".pyw": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".html": "html",    ".htm": "html",
    ".css": "css",      ".scss": "scss",     ".less": "less",
    ".json": "json",    ".jsonc": "json",
    ".yaml": "yaml",    ".yml": "yaml",
    ".toml": "ini",
    ".md": "markdown",  ".mdx": "markdown",
    ".sh": "shell",     ".bash": "shell",    ".zsh": "shell",
    ".bat": "bat",      ".cmd": "bat",
    ".ps1": "powershell",
    ".c": "c",          ".h": "c",
    ".cpp": "cpp",      ".cc": "cpp",        ".cxx": "cpp",    ".hpp": "cpp",
    ".cs": "csharp",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".sql": "sql",
    ".xml": "xml",
    ".svg": "xml",
    ".ini": "ini",      ".cfg": "ini",
    ".txt": "plaintext",
    ".env": "plaintext", ".gitignore": "plaintext",
}

def get_language(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return LANG_MAP.get(suffix, "plaintext")

# Directories / names to skip in the file tree
TREE_SKIP_DIRS  = {".git", "__pycache__", "node_modules", ".venv", "venv",
                   ".mypy_cache", ".pytest_cache", "dist", "build", ".tox"}
TREE_SKIP_FILES = set()

# ── File tree builder ─────────────────────────────────────────────────────────
def _safe_is_file(entry: Path) -> bool:
    try:
        return entry.is_file()
    except OSError:
        return False

def _safe_is_dir(entry: Path) -> bool:
    try:
        return entry.is_dir()
    except OSError:
        return False

def build_tree(root: Path, depth: int = 0, max_depth: int = 6) -> dict | None:
    if depth > max_depth:
        return None
    try:
        entries = sorted(root.iterdir(),
                         key=lambda e: (_safe_is_file(e), e.name.lower()))
    except (PermissionError, OSError):
        return None

    children = []
    for entry in entries:
        if entry.name.startswith(".") and entry.name not in {".env", ".env.example", ".gitignore"}:
            continue
        if entry.name in TREE_SKIP_DIRS:
            continue
        try:
            is_dir  = entry.is_dir()
            is_file = entry.is_file()
        except OSError:
            continue
        if is_dir:
            sub = build_tree(entry, depth + 1, max_depth)
            if sub is not None:
                children.append(sub)
        elif is_file:
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            children.append({
                "type":     "file",
                "name":     entry.name,
                "path":     str(entry).replace("\\", "/"),
                "language": get_language(entry.name),
                "size":     size,
            })

    return {
        "type":     "dir",
        "name":     root.name or str(root),
        "path":     str(root).replace("\\", "/"),
        "children": children,
    }

# ── SSE streaming helper ──────────────────────────────────────────────────────
def _messages_to_prompt(messages: list, system: str = "") -> str:
    """
    Convert a list of {role, content} dicts to a flat text prompt.
    All core providers take prompt: str, not a message list.
    """
    parts: list[str] = []
    if system:
        parts.append(system)
    for m in messages:
        role    = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in content
            )
        if role == "system":
            pass  # system already prepended above
        elif role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
    return "\n\n".join(parts)


def _get_model_pricing(model_id: str) -> tuple[float, float]:
    """Return (input_cost_per_1m, output_cost_per_1m) from model registry, or (0, 0)."""
    try:
        registry = json.loads(MODEL_REGISTRY.read_text("utf-8"))
        for config in registry.get("providers", {}).values():
            model_info = config.get("models", {}).get(model_id)
            if isinstance(model_info, dict):
                return (
                    model_info.get("input_cost_per_1m_tokens", 0),
                    model_info.get("output_cost_per_1m_tokens", 0),
                )
    except Exception:
        pass
    return (0.0, 0.0)


def _log_ai_usage(model: str, provider_name: str, endpoint: str,
                  input_chars: int, output_chars: int) -> None:
    """Append one usage entry to data/ai/logs/usage/YYYY-MM/usage_YYYY-MM-DD.json."""
    import random, string
    try:
        now = datetime.utcnow()
        month_dir = USAGE_LOG_DIR / now.strftime("%Y-%m")
        month_dir.mkdir(parents=True, exist_ok=True)
        day_file = month_dir / now.strftime("usage_%Y-%m-%d.json")

        prompt_tokens     = round(input_chars / 4)
        completion_tokens = round(output_chars / 4)
        rand_suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        trace_id    = f"ASTR-{now.strftime('%Y%m%d%H%M%S')}-{rand_suffix}"

        in_cost_per_1m, out_cost_per_1m = _get_model_pricing(model)
        input_cost  = round(prompt_tokens     / 1_000_000 * in_cost_per_1m,  8)
        output_cost = round(completion_tokens / 1_000_000 * out_cost_per_1m, 8)

        op_map = {
            "/api/ai/chat":     "chat",
            "/api/ai/explain":  "explain",
            "/api/ai/fix":      "fix",
            "/api/ai/refactor": "refactor",
        }
        operation = op_map.get(endpoint, "chat")

        entry = {
            "timestamp":         now.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z",
            "provider":          provider_name,
            "model":             model,
            "prompt_tokens":     prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens":      prompt_tokens + completion_tokens,
            "input_cost":        input_cost,
            "output_cost":       output_cost,
            "estimated_cost":    round(input_cost + output_cost, 8),
            "operation":         operation,
            "trace_id":          trace_id,
            "success":           True,
            "tokens_estimated":  True,
            "source":            "code_ide",
        }

        records: list = []
        if day_file.exists():
            try:
                records = json.loads(day_file.read_text("utf-8"))
            except Exception:
                records = []
        records.append(entry)
        day_file.write_text(json.dumps(records, indent=2), encoding="utf-8")
    except Exception as exc:
        logging.warning("Usage log write failed: %s", exc)


async def _sse(provider, messages: list, model_id: str, system: str,
               max_tokens: int = 8192,
               endpoint: str = "/api/ai/chat") -> AsyncGenerator[str, None]:
    """
    Run provider.stream() in a background thread and yield SSE chunks.
    Needed because provider.stream() is a synchronous generator.
    """
    prompt = _messages_to_prompt(messages, system)
    provider_name = (pm.model_to_provider_map.get(model_id) if pm else None) \
                    or getattr(getattr(provider, "config", None), "provider", None) \
                    or type(provider).__name__
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()
    output_chunks: list[str] = []

    def _worker():
        try:
            for chunk in provider.stream(prompt, "ide", model=model_id,
                                         max_tokens=max_tokens):
                loop.call_soon_threadsafe(q.put_nowait, {"text": chunk})
        except Exception as exc:
            loop.call_soon_threadsafe(q.put_nowait, {"error": str(exc)})
        loop.call_soon_threadsafe(q.put_nowait, None)  # sentinel

    threading.Thread(target=_worker, daemon=True).start()

    while True:
        item = await q.get()
        if item is None:
            _log_ai_usage(model_id, provider_name, endpoint,
                          len(prompt), sum(len(c) for c in output_chunks))
            yield f"data: {json.dumps({'done': True})}\n\n"
            break
        if "text" in item:
            output_chunks.append(item["text"])
        yield f"data: {json.dumps(item)}\n\n"

def _get_provider(model_id: Optional[str] = None):
    if not HAS_PROVIDERS or not pm:
        raise HTTPException(503, "AI providers not available. Check your .env configuration.")
    prov = (
        pm.get_provider("google_ai") or
        pm.get_provider("openai")    or
        pm.get_provider("anthropic") or
        pm.get_provider("local")
    )
    if not prov:
        raise HTTPException(503, "No AI provider configured.")
    mid = model_id or getattr(getattr(prov, "config", None), "model", None) or ""
    return prov, mid

# ── /api/providers ────────────────────────────────────────────────────────────
@app.get("/api/providers")
async def get_providers():
    if not HAS_PROVIDERS or not pm:
        return JSONResponse({"models": [], "available": False})
    models = []
    for mid, info in pm.model_descriptor_map.items():
        caps = [c.upper() for c in info.get("capabilities", [])]
        if "CHAT" in caps:
            models.append({
                "id":          mid,
                "provider":    info.get("provider", ""),
                "description": info.get("description", ""),
            })
    return JSONResponse({"models": models, "available": bool(models)})

# ── /api/registry/models ──────────────────────────────────────────────────────
@app.get("/api/registry/models")
async def get_registry_models():
    """Return chat models from the shared model registry (same format as dashboard)."""
    try:
        registry = json.loads(MODEL_REGISTRY.read_text("utf-8"))
        chat_models = []
        for provider_name, config in registry.get("providers", {}).items():
            for model_id, model_info in config.get("models", {}).items():
                if not isinstance(model_info, dict):
                    continue
                caps = [c.lower() for c in model_info.get("capabilities", [])]
                if "chat" not in caps:
                    continue
                chat_models.append({
                    "id":                       model_id,
                    "provider":                 provider_name,
                    "capabilities":             model_info.get("capabilities", []),
                    "input_cost_per_1m_tokens": model_info.get("input_cost_per_1m_tokens", 0),
                    "output_cost_per_1m_tokens":model_info.get("output_cost_per_1m_tokens", 0),
                    "description":              model_info.get("description", model_info.get("notes", "")),
                })
        chat_models.sort(key=lambda m: m["id"])
        profiles = registry.get("profiles", {})
        return JSONResponse({
            "models":        chat_models,
            "chat_profiles": profiles.get("chat_profiles", {}),
            "agent_profiles":profiles.get("agent_profiles", {}),
        })
    except Exception as exc:
        raise HTTPException(500, str(exc))

# ── /api/settings ─────────────────────────────────────────────────────────────
@app.get("/api/settings")
async def get_settings():
    return JSONResponse(_read_settings())

class SettingsSaveReq(BaseModel):
    last_workspace:    Optional[str]  = None
    recent_workspaces: Optional[list] = None

@app.post("/api/settings")
async def save_settings(req: SettingsSaveReq):
    s = _read_settings()
    if req.last_workspace is not None:
        s["last_workspace"] = req.last_workspace
    if req.recent_workspaces is not None:
        s["recent_workspaces"] = req.recent_workspaces
    _write_settings(s)
    return JSONResponse({"status": "ok"})

# ── /api/project ───────────────────────────────────────────────────────────────
@app.get("/api/project")
async def get_project(workspace: str = ""):
    if not workspace:
        workspace = _read_settings().get("last_workspace", str(ROOT).replace("\\", "/"))
    data = _read_project(workspace)
    # Lazily populate structure if missing
    if not data.get("structure"):
        data["structure"] = _scan_structure(workspace)
    return JSONResponse(data)

class ProjectSaveReq(BaseModel):
    workspace:  str
    open_tabs:  Optional[List[str]] = None
    active_tab: Optional[str]       = None
    ai_context: Optional[str]       = None
    name:       Optional[str]       = None

@app.post("/api/project")
async def save_project(req: ProjectSaveReq):
    data = _read_project(req.workspace)
    if req.open_tabs  is not None: data["open_tabs"]  = req.open_tabs
    if req.active_tab is not None: data["active_tab"] = req.active_tab
    if req.ai_context is not None: data["ai_context"] = req.ai_context
    if req.name       is not None: data["name"]        = req.name
    # Always refresh structure on save
    data["structure"] = _scan_structure(req.workspace)
    _write_project(data)
    return JSONResponse({"status": "ok"})

@app.post("/api/project/scan")
async def scan_project(req: ProjectSaveReq):
    """Re-scan workspace structure and persist."""
    data = _read_project(req.workspace)
    data["structure"] = _scan_structure(req.workspace)
    _write_project(data)
    return JSONResponse({"status": "ok", "files": len(data["structure"])})

# ── /api/threads/* ────────────────────────────────────────────────────────────
def _threads_dir(workspace: str) -> Path:
    return DATA_DIR / "projects" / _project_key(workspace or str(WORKSPACE)) / "threads"

class ThreadSaveReq(BaseModel):
    workspace:  str
    id:         Optional[str]  = None   # omit to create new
    name:       Optional[str]  = None
    messages:   Optional[List] = None

@app.get("/api/threads")
async def list_threads(workspace: str = ""):
    d = _threads_dir(workspace or str(WORKSPACE))
    if not d.exists():
        return JSONResponse({"threads": []})
    threads = []
    for f in sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            threads.append({
                "id":            data.get("id", f.stem),
                "name":          data.get("name", "Untitled"),
                "message_count": len(data.get("messages", [])),
                "updated_at":    data.get("updated_at", ""),
            })
        except Exception:
            pass
    return JSONResponse({"threads": threads})

@app.get("/api/threads/{tid}")
async def get_thread(tid: str, workspace: str = ""):
    path = _threads_dir(workspace or str(WORKSPACE)) / f"{tid}.json"
    if not path.exists():
        raise HTTPException(404, "Thread not found")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))

@app.post("/api/threads")
async def save_thread(req: ThreadSaveReq):
    d = _threads_dir(req.workspace or str(WORKSPACE))
    d.mkdir(parents=True, exist_ok=True)
    tid   = req.id or _uuid_mod.uuid4().hex[:8]
    path  = d / f"{tid}.json"
    existing: dict = {}
    if path.exists():
        try: existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception: pass
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "id":         tid,
        "name":       req.name if req.name is not None else existing.get("name", "New Chat"),
        "workspace":  req.workspace or str(WORKSPACE),
        "created_at": existing.get("created_at", now),
        "updated_at": now,
        "messages":   req.messages if req.messages is not None else existing.get("messages", []),
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return JSONResponse(data)

@app.delete("/api/threads/{tid}")
async def delete_thread(tid: str, workspace: str = ""):
    path = _threads_dir(workspace or str(WORKSPACE)) / f"{tid}.json"
    if path.exists():
        path.unlink()
    return JSONResponse({"ok": True})

# ── /api/fs/* ─────────────────────────────────────────────────────────────────
@app.get("/api/fs/roots")
async def fs_roots():
    settings = _read_settings()
    last     = settings.get("last_workspace", str(ROOT).replace("\\", "/"))
    recent   = settings.get("recent_workspaces", [])
    return JSONResponse({
        "workspace": last,
        "last_workspace": last,
        "recent_workspaces": recent,
        "roots": [
            {"label": "Project Root", "path": str(ROOT).replace("\\", "/")},
            {"label": "Home",         "path": str(Path.home()).replace("\\", "/")},
        ],
    })

@app.post("/api/fs/browse")
async def fs_browse():
    """Open a native OS folder-picker dialog (requires tkinter on the server)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        _root = tk.Tk()
        _root.withdraw()
        _root.attributes("-topmost", True)
        folder = filedialog.askdirectory(parent=_root, title="Select Workspace Folder")
        _root.destroy()
        return JSONResponse({"path": folder.replace("\\", "/") if folder else ""})
    except Exception as exc:
        raise HTTPException(500, f"Folder picker unavailable: {exc}")


@app.get("/api/fs/tree")
async def fs_tree(path: str = ""):
    base = Path(path) if path else WORKSPACE
    if not base.exists():
        raise HTTPException(404, "Path not found.")
    if not base.is_dir():
        raise HTTPException(400, "Not a directory.")
    tree = build_tree(base)
    return JSONResponse(tree)


@app.get("/api/fs/read")
async def fs_read(path: str):
    target = Path(path)
    if not target.exists():
        raise HTTPException(404, "File not found.")
    if not target.is_file():
        raise HTTPException(400, "Not a file.")
    if target.stat().st_size > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (> 10 MB).")
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return JSONResponse({
        "path":     str(target).replace("\\", "/"),
        "name":     target.name,
        "content":  content,
        "language": get_language(target.name),
    })


class WriteReq(BaseModel):
    path: str
    content: str

@app.post("/api/fs/write")
async def fs_write(req: WriteReq):
    target = Path(req.path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(req.content, encoding="utf-8")
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return JSONResponse({"status": "success", "path": str(target).replace("\\", "/")})


class MkdirReq(BaseModel):
    path: str

@app.post("/api/fs/mkdir")
async def fs_mkdir(req: MkdirReq):
    try:
        Path(req.path).mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return JSONResponse({"status": "success"})


class RenameReq(BaseModel):
    old_path: str
    new_path: str

@app.post("/api/fs/rename")
async def fs_rename(req: RenameReq):
    src, dst = Path(req.old_path), Path(req.new_path)
    if not src.exists():
        raise HTTPException(404, "Source not found.")
    try:
        src.rename(dst)
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return JSONResponse({"status": "success", "new_path": str(dst).replace("\\", "/")})


class MoveReq(BaseModel):
    src: str
    dst_dir: str

@app.post("/api/fs/move")
async def fs_move(req: MoveReq):
    src = Path(req.src)
    dst_dir = Path(req.dst_dir)
    if not src.exists():
        raise HTTPException(404, "Source not found.")
    if not dst_dir.is_dir():
        raise HTTPException(400, "Destination is not a directory.")
    try:
        result = shutil.move(str(src), str(dst_dir))
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return JSONResponse({"status": "success", "new_path": str(result).replace("\\", "/")})


class ExecReq(BaseModel):
    code: str
    workspace: str = ""

@app.post("/api/fs/exec")
async def fs_exec(req: ExecReq):
    """Execute a Python snippet in the workspace directory and return stdout/stderr."""
    workspace = req.workspace or str(WORKSPACE)
    import tempfile
    # Write a temp script that chdirs into workspace first
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", encoding="utf-8", delete=False) as f:
        f.write(f"import os as _os\n_os.chdir({repr(workspace)})\n")
        f.write(req.code)
        tmp_path = Path(f.name)
    try:
        result = subprocess.run(
            [sys.executable, str(tmp_path)],
            capture_output=True, text=True, timeout=30,
            cwd=workspace,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        return JSONResponse({
            "stdout":     result.stdout,
            "stderr":     result.stderr,
            "returncode": result.returncode,
        })
    except subprocess.TimeoutExpired:
        return JSONResponse({"stdout": "", "stderr": "Timeout (30 s)", "returncode": -1})
    except Exception as exc:
        return JSONResponse({"stdout": "", "stderr": str(exc), "returncode": -1})
    finally:
        tmp_path.unlink(missing_ok=True)


class RevealReq(BaseModel):
    path: str

@app.post("/api/fs/reveal")
async def fs_reveal(req: RevealReq):
    """Open the file/folder in the OS file explorer."""
    target = Path(req.path)
    if not target.exists():
        raise HTTPException(404, "Path not found.")
    try:
        if os.name == "nt":
            # Windows: open Explorer and select the item
            if target.is_file():
                subprocess.Popen(["explorer", "/select,", str(target)], creationflags=0x08000000)
            else:
                subprocess.Popen(["explorer", str(target)], creationflags=0x08000000)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R" if target.is_file() else "", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target.parent if target.is_file() else target)])
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return JSONResponse({"status": "ok"})


class DuplicateReq(BaseModel):
    path: str

@app.post("/api/fs/duplicate")
async def fs_duplicate(req: DuplicateReq):
    src = Path(req.path)
    if not src.exists():
        raise HTTPException(404, "Source not found.")
    try:
        stem, suffix, parent = src.stem, src.suffix, src.parent
        counter = 1
        while True:
            dst = parent / f"{stem}_copy{counter}{suffix}"
            if not dst.exists():
                break
            counter += 1
        shutil.copy2(str(src), str(dst))
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return JSONResponse({"status": "success", "new_path": str(dst).replace("\\", "/")})


class DeleteReq(BaseModel):
    path: str

@app.delete("/api/fs/delete")
async def fs_delete(req: DeleteReq):
    target = Path(req.path)
    if not target.exists():
        raise HTTPException(404, "Not found.")
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return JSONResponse({"status": "success"})

# ── /api/code/run ─────────────────────────────────────────────────────────────
class RunReq(BaseModel):
    path:     Optional[str] = None   # run a saved file
    code:     Optional[str] = None   # run an inline snippet
    language: str = "python"
    stdin:    str = ""
    timeout:  int = 30

@app.post("/api/code/run")
async def run_code(req: RunReq):
    lang = req.language.lower()
    tmp_path: Optional[Path] = None

    # Build command
    if lang == "python":
        interp = sys.executable
        if req.path:
            cmd = [interp, req.path]
        else:
            tmp = tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                              delete=False, encoding="utf-8")
            tmp.write(req.code or "")
            tmp.close()
            tmp_path = Path(tmp.name)
            cmd = [interp, str(tmp_path)]

    elif lang in ("javascript", "js", "node"):
        node = shutil.which("node") or shutil.which("node.exe")
        if not node:
            return JSONResponse({"stdout": "", "returncode": 1, "elapsed": 0,
                "stderr": "Node.js not found. Install Node.js to run JavaScript."})
        if req.path:
            cmd = [node, req.path]
        else:
            tmp = tempfile.NamedTemporaryFile(suffix=".js", mode="w",
                                              delete=False, encoding="utf-8")
            tmp.write(req.code or "")
            tmp.close()
            tmp_path = Path(tmp.name)
            cmd = [node, str(tmp_path)]

    elif lang in ("bash", "sh", "shell"):
        bash = shutil.which("bash") or shutil.which("bash.exe")
        if bash:
            if req.path:
                cmd = [bash, req.path]
            else:
                tmp = tempfile.NamedTemporaryFile(suffix=".sh", mode="w",
                                                  delete=False, encoding="utf-8")
                tmp.write(req.code or "")
                tmp.close()
                tmp_path = Path(tmp.name)
                cmd = [bash, str(tmp_path)]
        else:
            # Windows fallback: cmd /c
            if req.path:
                cmd = ["cmd", "/c", req.path]
            else:
                tmp = tempfile.NamedTemporaryFile(suffix=".bat", mode="w",
                                                  delete=False, encoding="utf-8")
                tmp.write(req.code or "")
                tmp.close()
                tmp_path = Path(tmp.name)
                cmd = ["cmd", "/c", str(tmp_path)]
    else:
        return JSONResponse({"stdout": "", "returncode": 1, "elapsed": 0,
            "stderr": f"Execution not supported for language '{req.language}'."})

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=req.timeout,
            cwd=str(WORKSPACE),
            input=req.stdin or None,
        )
        return JSONResponse({
            "stdout":     proc.stdout,
            "stderr":     proc.stderr,
            "returncode": proc.returncode,
            "elapsed":    round(time.time() - t0, 3),
        })
    except subprocess.TimeoutExpired:
        return JSONResponse({"stdout": "", "returncode": -1,
            "elapsed": req.timeout,
            "stderr":  f"Execution timed out after {req.timeout} s."})
    except Exception as exc:
        return JSONResponse({"stdout": "", "returncode": -1, "elapsed": 0, "stderr": str(exc)})
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)

# ── /api/code/run/stream ──────────────────────────────────────────────────────
async def _run_sse(cmd: list, cwd: str, timeout: int,
                   stdin_data: Optional[str]) -> AsyncGenerator[str, None]:
    """Run a subprocess and stream stdout/stderr line-by-line as SSE events."""
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()
    flags = 0x08000000 if os.name == "nt" else 0

    def _worker():
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.PIPE if stdin_data else subprocess.DEVNULL,
                cwd=cwd, text=True, bufsize=1,
                encoding="utf-8", errors="replace",
                creationflags=flags,
            )
            if stdin_data:
                try: proc.stdin.write(stdin_data); proc.stdin.close()
                except Exception: pass

            def _read(stream, ch):
                for line in stream:
                    loop.call_soon_threadsafe(q.put_nowait, {"ch": ch, "text": line})
                stream.close()

            t1 = threading.Thread(target=_read, args=(proc.stdout, "stdout"), daemon=True)
            t2 = threading.Thread(target=_read, args=(proc.stderr, "stderr"), daemon=True)
            t1.start(); t2.start()

            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()
                loop.call_soon_threadsafe(
                    q.put_nowait, {"ch": "stderr", "text": f"\n[Timed out after {timeout}s]\n"})

            t1.join(timeout=5); t2.join(timeout=5)
            loop.call_soon_threadsafe(
                q.put_nowait, {"done": True, "returncode": proc.returncode or -1})
        except Exception as exc:
            loop.call_soon_threadsafe(q.put_nowait, {"ch": "stderr", "text": str(exc)})
            loop.call_soon_threadsafe(q.put_nowait, {"done": True, "returncode": -1})

    threading.Thread(target=_worker, daemon=True).start()
    while True:
        item = await q.get()
        yield f"data: {json.dumps(item)}\n\n"
        if "done" in item:
            break


@app.post("/api/code/run/stream")
async def run_code_stream(req: RunReq):
    """Like /api/code/run but streams output line-by-line as SSE."""
    lang = req.language.lower()
    tmp_path: Optional[Path] = None

    async def _unsupported(msg: str):
        yield f"data: {json.dumps({'ch': 'stderr', 'text': msg})}\n\n"
        yield f"data: {json.dumps({'done': True, 'returncode': 1})}\n\n"

    if lang == "python":
        if req.path:
            cmd = [sys.executable, req.path]
        else:
            tmp = tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8")
            tmp.write(req.code or ""); tmp.close()
            tmp_path = Path(tmp.name); cmd = [sys.executable, str(tmp_path)]

    elif lang in ("javascript", "js", "node"):
        node = shutil.which("node") or shutil.which("node.exe")
        if not node:
            return StreamingResponse(_unsupported("Node.js not found. Install Node.js to run JavaScript."),
                                     media_type="text/event-stream", headers=SSE_HEADERS)
        if req.path:
            cmd = [node, req.path]
        else:
            tmp = tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False, encoding="utf-8")
            tmp.write(req.code or ""); tmp.close()
            tmp_path = Path(tmp.name); cmd = [node, str(tmp_path)]

    elif lang in ("bash", "sh", "shell"):
        bash = shutil.which("bash") or shutil.which("bash.exe")
        if bash:
            if req.path: cmd = [bash, req.path]
            else:
                tmp = tempfile.NamedTemporaryFile(suffix=".sh", mode="w", delete=False, encoding="utf-8")
                tmp.write(req.code or ""); tmp.close()
                tmp_path = Path(tmp.name); cmd = [bash, str(tmp_path)]
        else:
            if req.path: cmd = ["cmd", "/c", req.path]
            else:
                tmp = tempfile.NamedTemporaryFile(suffix=".bat", mode="w", delete=False, encoding="utf-8")
                tmp.write(req.code or ""); tmp.close()
                tmp_path = Path(tmp.name); cmd = ["cmd", "/c", str(tmp_path)]
    else:
        return StreamingResponse(
            _unsupported(f"Execution not supported for language '{req.language}'."),
            media_type="text/event-stream", headers=SSE_HEADERS)

    async def _wrapped():
        async for chunk in _run_sse(cmd, str(WORKSPACE), req.timeout, req.stdin or None):
            yield chunk
        if tmp_path:
            tmp_path.unlink(missing_ok=True)

    return StreamingResponse(_wrapped(), media_type="text/event-stream", headers=SSE_HEADERS)


# ── /api/git/branch ───────────────────────────────────────────────────────────
@app.get("/api/git/branch")
async def git_branch(workspace: str = ""):
    base = workspace or str(WORKSPACE)
    try:
        flags = 0x08000000 if os.name == "nt" else 0
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=base, timeout=3,
            creationflags=flags,
        )
        branch = result.stdout.strip() if result.returncode == 0 else ""
        return JSONResponse({"branch": branch})
    except Exception:
        return JSONResponse({"branch": ""})


# ── /api/ai/* ─────────────────────────────────────────────────────────────────
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

class ChatMsg(BaseModel):
    role:    str
    content: str

class ChatReq(BaseModel):
    messages:   List[ChatMsg]
    model:      Optional[str] = None
    system:     Optional[str] = None
    workspace:  Optional[str] = None   # current IDE workspace for context
    max_tokens: int = 8192             # raised default; frontend can override

def _build_chat_system(workspace: Optional[str] = None) -> str:
    """Build a rich system prompt, optionally injecting project context."""
    base = (
        "You are an expert programming assistant embedded in the Aethvion Code IDE. "
        "Be concise, accurate, and practical. Use markdown for code blocks.\n\n"

        "━━━ FILE WRITING PROTOCOL ━━━\n"
        "When the user asks you to create, update, or modify ANY files, you MUST output "
        "each file using this EXACT format — copy it precisely, including the ### prefix:\n\n"

        "### FILE: filename.ext\n"
        "```language\n"
        "... complete file contents ...\n"
        "```\n\n"

        "CRITICAL RULES (the IDE auto-writes files based on this exact format):\n"
        "1. Always start file blocks with exactly '### FILE: ' (three hashes, space, FILE:, space).\n"
        "2. Follow immediately with the filename on the same line — no extra text.\n"
        "3. Open the code fence on the very next line with the language tag.\n"
        "4. Always include COMPLETE file contents — never truncate, never use '...' or '# rest stays the same'.\n"
        "5. Output ALL files needed to complete the task.\n"
        "6. You may add explanation text before or after the file blocks, never inside them.\n"
        "7. If you cannot fit all files in one response, end your response with exactly '### CONTINUE' "
        "on its own line. The IDE agent loop will send a 'continue' message and you MUST resume "
        "outputting the remaining files immediately — no re-introduction, no summary, just the next FILE block.\n\n"

        "━━━ FILE OPERATIONS PROTOCOL ━━━\n"
        "For ANY file operation that is NOT creating/editing content "
        "(move, delete, rename, copy, mkdir, etc.), output a python-exec block.\n"
        "The IDE will execute it automatically in the workspace and show the result.\n\n"
        "```python-exec\n"
        "import shutil, os\n"
        "# Move a file\n"
        "shutil.move('test.txt', 'TestingFolder/')\n"
        "```\n\n"
        "```python-exec\n"
        "import os\n"
        "os.remove('old_file.txt')\n"
        "```\n\n"
        "NEVER use FILE: blocks for move/delete/rename/mkdir — only for creating or editing file content.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "Example FILE output:\n"
        "### FILE: index.html\n"
        "```html\n"
        "<!DOCTYPE html>\n"
        "<html><body><h1>Hello</h1></body></html>\n"
        "```\n\n"
        "### FILE: styles.css\n"
        "```css\n"
        "body { margin: 0; }\n"
        "```\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    if not workspace:
        return base

    proj = _read_project(workspace)
    # Use cached structure, or scan now
    structure = proj.get("structure") or _scan_structure(workspace)
    parts = [base, f"\n\nCurrent workspace: {workspace}"]
    if structure:
        # Limit to 150 lines to keep prompt manageable
        shown   = structure[:150]
        skipped = len(structure) - len(shown)
        parts.append("Project file structure:\n" + "\n".join(shown) +
                     (f"\n… and {skipped} more files" if skipped else ""))
    if proj.get("ai_context"):
        parts.append(f"Project notes:\n{proj['ai_context']}")
    return "\n".join(parts)

@app.post("/api/ai/chat")
async def ai_chat(req: ChatReq):
    prov, mid = _get_provider(req.model)
    msgs   = [{"role": m.role, "content": m.content} for m in req.messages]
    system = req.system or _build_chat_system(req.workspace)
    return StreamingResponse(_sse(prov, msgs, mid, system, max_tokens=req.max_tokens,
                                   endpoint="/api/ai/chat"),
                             media_type="text/event-stream", headers=SSE_HEADERS)


class ExplainReq(BaseModel):
    code:     str
    language: str = "python"
    model:    Optional[str] = None

@app.post("/api/ai/explain")
async def ai_explain(req: ExplainReq):
    prov, mid = _get_provider(req.model)
    msgs = [{"role": "user", "content":
        f"Explain this {req.language} code clearly and concisely. "
        f"Use bullet points for key points.\n\n"
        f"```{req.language}\n{req.code}\n```"}]
    system = "You are a code explainer. Be clear, structured, and concise."
    return StreamingResponse(_sse(prov, msgs, mid, system, endpoint="/api/ai/explain"),
                             media_type="text/event-stream", headers=SSE_HEADERS)


class FixReq(BaseModel):
    code:     str
    error:    str
    language: str = "python"
    model:    Optional[str] = None

@app.post("/api/ai/fix")
async def ai_fix(req: FixReq):
    prov, mid = _get_provider(req.model)
    msgs = [{"role": "user", "content":
        f"Fix this {req.language} code that produces an error.\n\n"
        f"**Code:**\n```{req.language}\n{req.code}\n```\n\n"
        f"**Error:**\n```\n{req.error}\n```\n\n"
        f"Return the complete fixed code in a ```{req.language}...``` block, "
        f"then briefly explain what was wrong."}]
    system = "You are a debugging expert. Fix the code and explain the bug clearly."
    return StreamingResponse(_sse(prov, msgs, mid, system, endpoint="/api/ai/fix"),
                             media_type="text/event-stream", headers=SSE_HEADERS)


class CompleteReq(BaseModel):
    code_before: str
    code_after:  str = ""
    language:    str = "python"
    model:       Optional[str] = None

@app.post("/api/ai/complete")
async def ai_complete(req: CompleteReq):
    prov, mid = _get_provider(req.model)
    after_section = (f"\n\nCode after cursor:\n```{req.language}\n{req.code_after}\n```"
                     if req.code_after.strip() else "")
    prompt = (
        f"Complete this {req.language} code at the cursor position. "
        f"Output ONLY the raw text to insert — no markdown fences, no explanation.\n\n"
        f"Code before cursor:\n```{req.language}\n{req.code_before}\n```"
        f"{after_section}"
    )
    system = "You are a code completion engine. Output ONLY the raw code to insert. No markdown. No explanations."
    full_prompt = _messages_to_prompt([{"role": "user", "content": prompt}], system)
    try:
        resp   = prov.generate(full_prompt, "ide", model=mid)
        result = resp.content if hasattr(resp, "content") else str(resp)
        # Strip markdown fences if model included them despite instructions
        result = result.strip()
        for fence in (f"```{req.language}", "```"):
            if result.startswith(fence):
                result = result[len(fence):].lstrip("\n")
                break
        if result.endswith("```"):
            result = result[:-3].rstrip()
        return JSONResponse({"completion": result})
    except Exception as exc:
        raise HTTPException(500, str(exc))


class RefactorReq(BaseModel):
    code:         str
    instructions: str
    language:     str = "python"
    model:        Optional[str] = None

@app.post("/api/ai/refactor")
async def ai_refactor(req: RefactorReq):
    prov, mid = _get_provider(req.model)
    msgs = [{"role": "user", "content":
        f"Refactor this {req.language} code according to these instructions: "
        f"{req.instructions}\n\n"
        f"```{req.language}\n{req.code}\n```\n\n"
        f"Return the complete refactored code in a ```{req.language}...``` block, "
        f"then list the changes you made."}]
    system = "You are a refactoring expert. Improve the code exactly as instructed."
    return StreamingResponse(_sse(prov, msgs, mid, system, endpoint="/api/ai/refactor"),
                             media_type="text/event-stream", headers=SSE_HEADERS)

# ── Static files + root ───────────────────────────────────────────────────────
app.mount("/viewer", StaticFiles(directory=str(VIEWER_DIR)), name="viewer")

@app.get("/", response_class=HTMLResponse)
async def index():
    return (VIEWER_DIR / "index.html").read_text(encoding="utf-8")

@app.get("/favicon.ico")
async def favicon():
    return JSONResponse({"ok": True})

# ── Launch ────────────────────────────────────────────────────────────────────
def launch():
    from core.utils.port_manager import PortManager
    base_port = int(os.getenv("CODE_PORT", "8083"))
    port = PortManager.bind_port("Aethvion Code IDE", base_port)
    print(f"[Code IDE] Aethvion Code IDE v1.0.0 -> http://localhost:{port}")

    # Open in browser app-mode unless the master launcher already handles it
    try:
        from core.utils.browser import open_app_window
        open_app_window(f"http://localhost:{port}", delay=1.5)
    except Exception:
        pass

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    launch()
