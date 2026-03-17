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


async def _sse(provider, messages: list, model_id: str, system: str,
               max_tokens: int = 2048) -> AsyncGenerator[str, None]:
    """
    Run provider.stream() in a background thread and yield SSE chunks.
    Needed because provider.stream() is a synchronous generator.
    """
    prompt = _messages_to_prompt(messages, system)
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

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
            yield f"data: {json.dumps({'done': True})}\n\n"
            break
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

# ── /api/ai/* ─────────────────────────────────────────────────────────────────
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

class ChatMsg(BaseModel):
    role:    str
    content: str

class ChatReq(BaseModel):
    messages:  List[ChatMsg]
    model:     Optional[str] = None
    system:    Optional[str] = None
    workspace: Optional[str] = None   # current IDE workspace for context

def _build_chat_system(workspace: Optional[str] = None) -> str:
    """Build a rich system prompt, optionally injecting project context."""
    base = (
        "You are an expert programming assistant embedded in the Aethvion IDE. "
        "Be concise, accurate, and practical. Use markdown for code blocks.\n\n"
        "IMPORTANT — When asked to create files, output EVERY file using this EXACT format "
        "(no exceptions, no skipping files):\n\n"
        "### FILE: path/to/file.ext\n"
        "```language\n"
        "complete file contents here\n"
        "```\n\n"
        "Rules for file creation:\n"
        "- Use the path the user specifies (e.g. /test/index.html).\n"
        "- Always output COMPLETE file contents — never truncate or use placeholders.\n"
        "- Create ALL requested files in one response.\n"
        "- After the files, you may add a brief explanation."
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
    return StreamingResponse(_sse(prov, msgs, mid, system),
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
    return StreamingResponse(_sse(prov, msgs, mid, system),
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
    return StreamingResponse(_sse(prov, msgs, mid, system),
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
    return StreamingResponse(_sse(prov, msgs, mid, system),
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
