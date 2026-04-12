"""
Aethvion Suite - AI Explained Routes
Uses the identical Agent backend as the Agents tab.
Each explanation is a proper Agent workspace + thread, giving full
surgical-edit capabilities, persistent state, and file-awareness.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import uuid
import json
import shutil
from pathlib import Path

from core.utils import get_logger, utcnow_iso
from core.utils.paths import EXPLAINED, HISTORY_AGENTS
from core.memory.agent_workspace_manager import AgentWorkspaceManager

logger = get_logger("web.explained_routes")
router = APIRouter(prefix="/api/explained", tags=["explained"])

# Private workspace manager for Explained - keeps threads out of the main Agents tab
explained_manager = AgentWorkspaceManager(EXPLAINED)

# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #

class ExplainedRequest(BaseModel):
    topic: str
    model_id: str = "auto"
    thread_id: Optional[str] = None  # Our internal "explanation ID"
    deep_dive: bool = False           # When True: multi-page structure


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #

_NORMAL_NEW_PROMPT = """\
Create a rich, visually appealing, self-contained single-file HTML explanation about: {topic}

MODE: Standard — Single self-contained file
- Everything must be in ONE file called index.html
- Embed all CSS and JavaScript inside the file.
- Make it beautiful, well-structured, and detailed with sections, cards, and visuals.
- Focus on clarity, engagement, and shareability.
- Use search_web to research the topic thoroughly.
- NO footers, NO copyright notices, NO social links, NO 'built by' credits.

Goal: A beautiful standalone HTML file that can be shared easily.

Provide a short punchy TITLE (max 4 words) at the very end prefixed with 'TITLE: '.\
"""

_NORMAL_UPDATE_PROMPT = """\
Project: {topic}
New instruction: {instruction}

This is a Standard (single-file) explanation. Apply this instruction surgically to the existing index.html.
Read the file first if needed, then patch only what was asked.
Do NOT rewrite the entire file unless explicitly told to.
Keep all CSS and JS embedded inside the single HTML file.\
"""

_DEEP_DIVE_NEW_PROMPT = """\
Create an EXTREMELY DETAILED and deeply researched visual explanation about: {topic}

MODE: DEEP DIVE ENABLED — Use multi-file structure
- Create a main index.html as the hub / table of contents with clear navigation.
- Split major sections into separate HTML files (for example: main-lore.html, characters.html, timeline.html, etc. — choose names that fit the topic).
- Use one shared style.css and one shared script.js where possible.
- Make navigation clean (sidebar or top nav with links between the pages).
- Go extremely deep on every section — maximum length and research depth (use search_web).
- Use rich visuals, SVGs, timelines, tables, and interactive elements.
- Reference style.css as: <link rel="stylesheet" href="style.css">
- Reference script.js as: <script src="script.js"></script>
- NO footers, NO copyright, NO social links, NO 'built by' credits.

Goal: Build a comprehensive, well-organized knowledge base.

Provide a short punchy TITLE (max 4 words) at the very end prefixed with 'TITLE: '.\
"""

_DEEP_DIVE_UPDATE_PROMPT = """\
Project: {topic} (Deep Dive multi-page)
New instruction: {instruction}

This is a Deep Dive (multi-file) explanation.
The workspace contains index.html (hub), separate section HTML files, style.css, and script.js.
Apply this instruction surgically — read the relevant files first, patch only what was asked.
Maintain the shared style.css / script.js pattern. Do NOT collapse files into one.\
"""


# --------------------------------------------------------------------------- #
# Public endpoints
# --------------------------------------------------------------------------- #

@router.post("/generate")
async def generate_explanation(req: ExplainedRequest, request: Request):
    """
    Kick off an agent task using the same code-path as the Agents tab.
    Returns immediately with a task_id that the frontend can poll.
    """
    from core.orchestrator.task_queue import get_task_queue_manager

    nexus = getattr(request.app.state, 'nexus', None)
    if not nexus:
        raise HTTPException(503, "System not initialized")

    task_manager = get_task_queue_manager()

    # ── Resolve or create the underlying Agent workspace ─────────────────── #
    meta_path: Optional[Path] = None
    ws_id: Optional[str] = None
    ag_tid: Optional[str] = None
    original_topic: Optional[str] = None
    stored_deep_dive: Optional[bool] = None

    if req.thread_id:
        # UPDATE: reload stored workspace/thread IDs from meta
        meta_path = EXPLAINED / req.thread_id / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                ws_id = meta.get("ws_id")
                ag_tid = meta.get("ag_tid")
                original_topic = meta.get("topic")
                stored_deep_dive = meta.get("deep_dive", False)
            except Exception:
                pass

    is_new = not (ws_id and ag_tid)
    explanation_id = req.thread_id or f"expl-{uuid.uuid4().hex[:8]}"
    original_topic = original_topic or req.topic
    # Use the mode that was set when the thread was created (can't switch mid-thread)
    deep_dive = stored_deep_dive if not is_new and stored_deep_dive is not None else req.deep_dive

    expl_dir = EXPLAINED / explanation_id
    expl_dir.mkdir(parents=True, exist_ok=True)
    meta_path = expl_dir / "meta.json"

    if is_new:
        # Create an Agent workspace pointing at the explanation directory
        ws = explained_manager.create_workspace(
            path=str(expl_dir),
            name=f"Explained: {original_topic[:40]}",
            workspace_id=explanation_id
        )
        ws_id = ws["id"]
        # Create a thread inside it
        thread = explained_manager.create_thread(ws_id, name=original_topic[:60])
        ag_tid = thread["id"]

        # Persist metadata
        meta = {
            "topic": original_topic,
            "ws_id": ws_id,
            "ag_tid": ag_tid,
            "created_at": utcnow_iso(),
            "updated_at": utcnow_iso(),
            "model_id": req.model_id,
            "deep_dive": deep_dive,
            "display_title": original_topic[:25] + ("..." if len(original_topic) > 25 else ""),
            "display_id": _next_display_id(),
        }
        _write_meta(meta_path, meta)
    else:
        # Update meta timestamp
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["updated_at"] = utcnow_iso()
            _write_meta(meta_path, meta)
        except Exception:
            meta = {}

    # ── Build the prompt for the agent ───────────────────────────────────── #
    if is_new:
        if deep_dive:
            prompt = _DEEP_DIVE_NEW_PROMPT.format(topic=req.topic)
        else:
            prompt = _NORMAL_NEW_PROMPT.format(topic=req.topic)
    else:
        if deep_dive:
            prompt = _DEEP_DIVE_UPDATE_PROMPT.format(
                topic=original_topic, instruction=req.topic
            )
        else:
            prompt = _NORMAL_UPDATE_PROMPT.format(
                topic=original_topic, instruction=req.topic
            )

    # ── Submit to the real task queue (identical to Agents tab) ──────────── #
    task_id = await task_manager.submit_task(
        prompt=prompt,
        thread_id=f"explained-{explanation_id}",  # task queue thread (separate from agent thread)
        thread_title=original_topic[:60],
        model_id=req.model_id if req.model_id != "auto" else None,
        mode="auto",
        workspace_id=ws_id,
        agent_thread_id=ag_tid,
        storage_root=str(EXPLAINED)
    )

    return {
        "task_id": task_id,
        "thread_id": explanation_id,
        "ws_id": ws_id,
        "ag_tid": ag_tid,
        "deep_dive": deep_dive,
    }


@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """
    Poll the real task queue for status + latest HTML.
    Maps the task queue status to the format the Explained frontend expects.
    """
    from core.orchestrator.task_queue import get_task_queue_manager

    task_manager = get_task_queue_manager()
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    task_dict = task.to_dict()
    status = task_dict.get("status", "queued")  # queued / running / completed / failed

    # Map to our frontend statuses
    if status == "completed":
        fe_status = "completed"
    elif status == "failed":
        fe_status = "failed"
    else:
        fe_status = "running"

    # Try to read the latest HTML from the workspace
    ws_id = task_dict.get("metadata", {}).get("workspace_id")
    html_content = None
    if ws_id:
        ws_info = explained_manager.get_workspace(ws_id)
        if ws_info:
            ws_path = Path(ws_info["path"])
            # Find index.html first, then any other html file
            index_file = ws_path / "index.html"
            if index_file.exists():
                try:
                    html_content = index_file.read_text(encoding="utf-8")
                except Exception:
                    pass
            if not html_content:
                html_files = sorted(ws_path.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
                if html_files:
                    try:
                        html_content = html_files[0].read_text(encoding="utf-8")
                    except Exception:
                        pass

    # Extract logs from agent events
    logs = []
    try:
        from core.orchestrator.agent_events import get_snapshot
        snap = get_snapshot(task_id)
        if snap:
            for evt in snap.get("events", []):
                t = evt.get("type", "")
                if t == "thinking":
                    logs.append({"type": "step", "msg": evt.get("detail") or evt.get("title", "")})
                elif t in ("write_file", "patch_file", "append_file"):
                    logs.append({"type": "action", "msg": f"Editing {evt.get('path', '')}..."})
                elif t == "read_file":
                    logs.append({"type": "action", "msg": f"Reading {evt.get('path', '')}..."})
                elif t == "search_web":
                    logs.append({"type": "action", "msg": f"Searching: {evt.get('query', '')}..."})
                elif t == "done":
                    logs.append({"type": "step", "msg": "Done!"})
    except Exception:
        pass

    # Extract agent-generated TITLE from summary if completed
    display_title = None
    if fe_status == "completed":
        summary = task_dict.get("result", {}).get("response", "")
        for line in summary.splitlines():
            if line.strip().startswith("TITLE:"):
                display_title = line.replace("TITLE:", "").strip()
                break

    return {
        "status": fe_status,
        "step": logs[-1]["msg"] if logs else ("Working..." if fe_status == "running" else ""),
        "logs": logs[-50:],  # cap at 50 for the UI
        "html": html_content,
        "display_title": display_title,
        "error": task_dict.get("error") if fe_status == "failed" else None,
        "thread_id": task_dict.get("metadata", {}).get("workspace_id"),
    }


@router.get("/thread/{thread_id}")
async def get_thread_result(thread_id: str):
    """Return stored HTML + meta for a past explanation."""
    expl_dir = EXPLAINED / thread_id
    meta_path = expl_dir / "meta.json"

    if not expl_dir.exists():
        raise HTTPException(404, "Explanation not found")

    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Find latest HTML in the agent workspace (prefer index.html)
    ws_id = meta.get("ws_id")
    html_content = None
    if ws_id:
        ws_info = explained_manager.get_workspace(ws_id)
        if ws_info:
            ws_path = Path(ws_info["path"])
            index_file = ws_path / "index.html"
            if index_file.exists():
                try:
                    html_content = index_file.read_text(encoding="utf-8")
                except Exception:
                    pass
            if not html_content:
                html_files = sorted(ws_path.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
                if html_files:
                    try:
                        html_content = html_files[0].read_text(encoding="utf-8")
                    except Exception:
                        pass

    if not html_content:
        raise HTTPException(404, "No HTML result found yet")

    return {
        "html": html_content,
        "thread_id": thread_id,
        "display_title": meta.get("display_title", thread_id),
        "topic": meta.get("topic", ""),
        "deep_dive": meta.get("deep_dive", False),
    }


@router.get("/thread/{thread_id}/folder-path")
async def get_thread_folder_path(thread_id: str):
    """Return the absolute workspace folder path for the given explanation thread."""
    expl_dir = EXPLAINED / thread_id
    meta_path = expl_dir / "meta.json"

    if not expl_dir.exists():
        raise HTTPException(404, "Explanation not found")

    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    ws_id = meta.get("ws_id")
    folder_path = None
    if ws_id:
        ws_info = explained_manager.get_workspace(ws_id)
        if ws_info:
            folder_path = ws_info.get("path")

    if not folder_path:
        # Fall back to the explanation meta directory
        folder_path = str(expl_dir)

    return {"path": folder_path}


@router.get("/thread/{thread_id}/pages")
async def get_thread_pages(thread_id: str):
    """
    For Deep Dive threads: return a list of available page filenames
    (HTML files in the workspace, excluding the shared assets).
    """
    expl_dir = EXPLAINED / thread_id
    meta_path = expl_dir / "meta.json"

    if not expl_dir.exists():
        raise HTTPException(404, "Explanation not found")

    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    ws_id = meta.get("ws_id")
    if not ws_id:
        return {"pages": []}

    ws_info = explained_manager.get_workspace(ws_id)
    if not ws_info:
        return {"pages": []}

    ws_path = Path(ws_info["path"])

    # Preferred order for Deep Dive pages
    _ORDER = ["index.html", "overview.html", "core.html", "deepdive.html", "summary.html"]
    _LABELS = {
        "index.html":    "🏠 Home",
        "overview.html": "📖 Overview",
        "core.html":     "⚙️ Core",
        "deepdive.html": "🔬 Deep Dive",
        "summary.html":  "📋 Summary",
    }

    found = [f.name for f in ws_path.glob("*.html") if f.is_file()]
    ordered = [f for f in _ORDER if f in found]
    # Append any extra HTML files not in the preferred order
    ordered += sorted(f for f in found if f not in _ORDER)

    pages = [
        {"filename": fn, "label": _LABELS.get(fn, fn.replace(".html", "").capitalize())}
        for fn in ordered
    ]
    return {"pages": pages, "deep_dive": meta.get("deep_dive", False)}


@router.get("/thread/{thread_id}/raw")
async def get_thread_raw_html(thread_id: str):
    """Serve index.html directly so iframes can load it cleanly."""
    expl_dir = EXPLAINED / thread_id
    meta_path = expl_dir / "meta.json"

    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    ws_id = meta.get("ws_id")
    if ws_id:
        ws_info = explained_manager.get_workspace(ws_id)
        if ws_info:
            ws_path = Path(ws_info["path"])
            index_file = ws_path / "index.html"
            if index_file.exists():
                try:
                    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            # Fallback to newest HTML file
            html_files = sorted(ws_path.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
            if html_files:
                try:
                    return HTMLResponse(content=html_files[0].read_text(encoding="utf-8"))
                except Exception:
                    pass

    return HTMLResponse("<html><body><p>Preparing immersion…</p></body></html>")


@router.get("/thread/{thread_id}/page/{filename}")
async def get_thread_page(thread_id: str, filename: str):
    """
    Serve a specific page from a Deep Dive workspace.
    Cross-page hrefs in the output HTML use relative paths (e.g. overview.html)
    which won't resolve through this API — the frontend navigates explicitly
    using this endpoint via the page navigator tabs.
    """
    # Security: only allow safe filenames
    if not filename.endswith(".html") or "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")

    expl_dir = EXPLAINED / thread_id
    meta_path = expl_dir / "meta.json"

    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    ws_id = meta.get("ws_id")
    if not ws_id:
        raise HTTPException(404, "Workspace not found")

    ws_info = explained_manager.get_workspace(ws_id)
    if not ws_info:
        raise HTTPException(404, "Workspace not found")

    page_path = Path(ws_info["path"]) / filename
    if not page_path.exists():
        raise HTTPException(404, f"Page '{filename}' not found")

    try:
        content = page_path.read_text(encoding="utf-8")
        # Inline the shared style.css and script.js into each served page so
        # the iframe works without a running file server resolving relative paths.
        ws_path = Path(ws_info["path"])
        css_path = ws_path / "style.css"
        js_path  = ws_path / "script.js"

        if css_path.exists():
            css_text = css_path.read_text(encoding="utf-8")
            content = content.replace(
                '<link rel="stylesheet" href="style.css">',
                f'<style>{css_text}</style>'
            ).replace(
                "<link rel='stylesheet' href='style.css'>",
                f'<style>{css_text}</style>'
            )

        if js_path.exists():
            js_text = js_path.read_text(encoding="utf-8")
            content = content.replace(
                '<script src="script.js"></script>',
                f'<script>{js_text}</script>'
            ).replace(
                "<script src='script.js'></script>",
                f'<script>{js_text}</script>'
            )

        return HTMLResponse(content=content)
    except Exception as e:
        raise HTTPException(500, f"Could not read page: {e}")


@router.delete("/thread/{thread_id}")
async def delete_thread(thread_id: str):
    """Delete explanation data and its agent workspace."""
    expl_dir = EXPLAINED / thread_id
    meta_path = expl_dir / "meta.json"

    ws_id = None
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            ws_id = meta.get("ws_id")
        except Exception:
            pass

    # Remove agent workspace
    if ws_id:
        try:
            explained_manager.delete_workspace(ws_id)
        except Exception as e:
            logger.warning(f"Could not delete agent workspace {ws_id}: {e}")

    # Remove explanation meta directory
    if expl_dir.exists():
        try:
            shutil.rmtree(expl_dir)
        except Exception as e:
            raise HTTPException(500, f"Delete failed: {e}")

    return {"status": "success"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _write_meta(path: Path, meta: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=4), encoding="utf-8")


def _next_display_id() -> int:
    try:
        return len([d for d in EXPLAINED.iterdir() if d.is_dir()])
    except Exception:
        return 1
