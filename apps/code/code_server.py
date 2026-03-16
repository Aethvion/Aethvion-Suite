"""
Aethvion Code IDE — FastAPI backend v1.0.0

Provides file-system access, code execution, and AI assistant endpoints.
Runs on port 8083 by default (CODE_PORT env var).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
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

# Workspace exposed in the file tree
WORKSPACE = Path(PROJECT_ROOT)

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
def build_tree(root: Path, depth: int = 0, max_depth: int = 6) -> dict | None:
    if depth > max_depth:
        return None
    try:
        entries = sorted(root.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    except PermissionError:
        return None

    children = []
    for entry in entries:
        if entry.name.startswith(".") and entry.name not in {".env", ".env.example", ".gitignore"}:
            continue
        if entry.name in TREE_SKIP_DIRS:
            continue
        if entry.is_dir():
            sub = build_tree(entry, depth + 1, max_depth)
            if sub is not None:
                children.append(sub)
        elif entry.is_file():
            children.append({
                "type":     "file",
                "name":     entry.name,
                "path":     str(entry).replace("\\", "/"),
                "language": get_language(entry.name),
                "size":     entry.stat().st_size,
            })

    return {
        "type":     "dir",
        "name":     root.name or str(root),
        "path":     str(root).replace("\\", "/"),
        "children": children,
    }

# ── SSE streaming helper ──────────────────────────────────────────────────────
async def _sse(provider, messages: list, model_id: str, system: str) -> AsyncGenerator[str, None]:
    """
    Run provider.stream() in a background thread and yield SSE chunks.
    Needed because provider.stream() is a synchronous generator.
    """
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    def _worker():
        try:
            for chunk in provider.stream(messages, model_id, system=system):
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

# ── /api/fs/* ─────────────────────────────────────────────────────────────────
@app.get("/api/fs/roots")
async def fs_roots():
    return JSONResponse({
        "workspace": str(WORKSPACE).replace("\\", "/"),
        "roots": [
            {"label": "Project Root", "path": str(WORKSPACE).replace("\\", "/")},
            {"label": "Home",         "path": str(Path.home()).replace("\\", "/")},
        ],
    })


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
    messages: List[ChatMsg]
    model:    Optional[str] = None
    system:   Optional[str] = None

@app.post("/api/ai/chat")
async def ai_chat(req: ChatReq):
    prov, mid = _get_provider(req.model)
    msgs   = [{"role": m.role, "content": m.content} for m in req.messages]
    system = req.system or (
        "You are an expert programming assistant embedded in the Aethvion IDE. "
        "Be concise, accurate, and practical. Use markdown for code blocks."
    )
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
    msgs   = [{"role": "user", "content": prompt}]
    system = "You are a code completion engine. Output ONLY the raw code to insert. No markdown. No explanations."
    try:
        result = prov.generate(msgs, mid, system=system)
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
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    launch()
