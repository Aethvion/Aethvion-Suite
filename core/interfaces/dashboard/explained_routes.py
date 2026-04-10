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
from core.utils.paths import EXPLANATIONS, HISTORY_AGENTS

logger = get_logger("web.explained_routes")
router = APIRouter(prefix="/api/explained", tags=["explained"])

# Reuse the same workspace manager used by the Agents tab
from core.interfaces.dashboard.agent_workspace_routes import workspace_manager as _aws_mgr

# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #

class ExplainedRequest(BaseModel):
    topic: str
    model_id: str = "auto"
    thread_id: Optional[str] = None  # Our internal "explanation ID"


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

    if req.thread_id:
        # UPDATE: reload stored workspace/thread IDs from meta
        meta_path = EXPLANATIONS / req.thread_id / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                ws_id = meta.get("ws_id")
                ag_tid = meta.get("ag_tid")
                original_topic = meta.get("topic")
            except Exception:
                pass

    is_new = not (ws_id and ag_tid)
    explanation_id = req.thread_id or f"expl-{uuid.uuid4().hex[:8]}"
    original_topic = original_topic or req.topic
    
    expl_dir = EXPLANATIONS / explanation_id
    expl_dir.mkdir(parents=True, exist_ok=True)
    meta_path = expl_dir / "meta.json"

    if is_new:
        # Create an Agent workspace pointing at the explanation directory
        ws = _aws_mgr.create_workspace(
            path=str(expl_dir),
            name=f"Explained: {original_topic[:40]}"
        )
        ws_id = ws["id"]
        # Create a thread inside it
        thread = _aws_mgr.create_thread(ws_id, name=original_topic[:60])
        ag_tid = thread["id"]

        # Persist metadata
        meta = {
            "topic": original_topic,
            "ws_id": ws_id,
            "ag_tid": ag_tid,
            "created_at": utcnow_iso(),
            "updated_at": utcnow_iso(),
            "model_id": req.model_id,
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
        prompt = (
            f"Create a stunning, thematic, single-file HTML visual explanation for: {req.topic}\n\n"
            "Design Guidelines:\n"
            "- Choose a visual theme that perfectly matches the topic (e.g. dark fantasy for Elden Ring, blocky for Minecraft, sci-fi for quantum computing).\n"
            "- Use Google Fonts, glassmorphism, smooth CSS animations, and FontAwesome icons.\n"
            "- Organize content: Hero section, Key Concepts, Deep Dive, Summary.\n"
            "- Make it LONG and DETAILED with deep researched content (use search_web).\n"
            "- Embed all CSS and JS inside the HTML file.\n"
            "- NO footers, NO copyright notices, NO social links, NO 'built by' credits.\n"
            "- The file MUST be saved as 'index.html'.\n\n"
            "Provide a short punchy TITLE (max 4 words) at the very end prefixed with 'TITLE: '."
        )
    else:
        prompt = (
            f"Project: {original_topic}\n"
            f"New instruction: {req.topic}\n\n"
            "Apply this instruction surgically to the existing index.html. "
            "Read the file first if needed, then patch only what was asked. "
            "Do NOT rewrite the entire file unless explicitly told to."
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
    )

    return {
        "task_id": task_id,
        "thread_id": explanation_id,
        "ws_id": ws_id,
        "ag_tid": ag_tid,
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
        ws_info = _aws_mgr.get_workspace(ws_id)
        if ws_info:
            ws_path = Path(ws_info["path"])
            # Find any .html file — agent picks the name, don't force index.html
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
    expl_dir = EXPLANATIONS / thread_id
    meta_path = expl_dir / "meta.json"

    if not expl_dir.exists():
        raise HTTPException(404, "Explanation not found")

    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Find latest HTML in the agent workspace
    ws_id = meta.get("ws_id")
    html_content = None
    if ws_id:
        ws_info = _aws_mgr.get_workspace(ws_id)
        if ws_info:
            ws_path = Path(ws_info["path"])
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
    }


@router.get("/thread/{thread_id}/raw")
async def get_thread_raw_html(thread_id: str):
    """Serve latest HTML directly so iframes can load it cleanly."""
    expl_dir = EXPLANATIONS / thread_id
    meta_path = expl_dir / "meta.json"

    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    ws_id = meta.get("ws_id")
    if ws_id:
        ws_info = _aws_mgr.get_workspace(ws_id)
        if ws_info:
            ws_path = Path(ws_info["path"])
            html_files = sorted(ws_path.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
            if html_files:
                try:
                    return HTMLResponse(content=html_files[0].read_text(encoding="utf-8"))
                except Exception:
                    pass

    return HTMLResponse("<html><body><p>Preparing immersion…</p></body></html>")


@router.delete("/thread/{thread_id}")
async def delete_thread(thread_id: str):
    """Delete explanation data and its agent workspace."""
    expl_dir = EXPLANATIONS / thread_id
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
            _aws_mgr.delete_workspace(ws_id)
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
        return len([d for d in EXPLANATIONS.iterdir() if d.is_dir()])
    except Exception:
        return 1
