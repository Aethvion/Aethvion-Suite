from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import json
import os
import shutil
from pathlib import Path
import asyncio

from core.utils import get_logger, utcnow_iso
from core.utils.paths import EXPLANATIONS, WS_OUTPUTS
from core.orchestrator.agent_runner import AgentRunner
from core.ai.call_contexts import CallSource

logger = get_logger("web.explained_routes")
router = APIRouter(prefix="/api/explained", tags=["explained"])

# In-memory task tracking for status polling
ACTIVE_TASKS = {} # task_id -> {status, thread_id, html, error, topic, step}

class ExplainedRequest(BaseModel):
    topic: str
    style: str = "modern"
    model_id: str = "auto"

@router.post("/generate")
async def generate_explanation(req: ExplainedRequest, request: Request, background_tasks: BackgroundTasks):
    nexus = getattr(request.app.state, 'nexus', None)
    if not nexus: raise HTTPException(503, "System not initialized")
    
    task_id = str(uuid.uuid4())
    thread_id = f"expl-{uuid.uuid4().hex[:8]}"
    
    # Setup thread directory
    thread_dir = EXPLANATIONS / thread_id
    thread_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize task state
    ACTIVE_TASKS[task_id] = {
        "status": "running",
        "thread_id": thread_id,
        "topic": req.topic,
        "step": "Initializing Agent...",
        "html": None,
        "error": None
    }
    
    # Run in background
    background_tasks.add_task(run_explained_agent, task_id, thread_id, req, nexus)
    
    return {"task_id": task_id, "thread_id": thread_id}

@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in ACTIVE_TASKS:
        raise HTTPException(404, "Task not found")
    return ACTIVE_TASKS[task_id]

@router.get("/thread/{thread_id}")
async def get_thread_result(thread_id: str):
    thread_dir = EXPLANATIONS / thread_id
    index_path = thread_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(404, "Result not found")
    
    html = index_path.read_text(encoding="utf-8")
    return {"html": html, "thread_id": thread_id}

async def run_explained_agent(task_id: str, thread_id: str, req: ExplainedRequest, nexus):
    thread_dir = EXPLANATIONS / thread_id
    
    # Save meta
    with open(thread_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump({
            "topic": req.topic,
            "style": req.style,
            "created_at": utcnow_iso(),
            "model_id": req.model_id
        }, f, indent=4)
    
    task_prompt = f"""Build a stunning visual explanation for: {req.topic}
Style: {req.style}
Create a professional single-file index.html with embedded CSS and JS."""

    system_prompt_override = f"""You are a master of visual communication and modern web design.
Your goal is to build a STUNNING, FULLY INTERACTIVE single-file HTML website explaining: {req.topic}

STYLE: {req.style.upper()}

REQUIREMENTS:
1. Research: Use search_web to get deep, accurate information.
2. Architecture: Organize content into sections (Hero, Key Concepts, Deep Dive, Summary).
3. Design:
   - Use a solid or high-quality gradient background (NEVER transparent).
   - Use Google Fonts (e.g., 'Inter', 'Orbitron' for headers).
   - Implement glassmorphism using 'backdrop-filter: blur()'.
   - Add hover effects and micro-animations for interactivity.
   - Use FontAwesome for all icons.
4. Interactivity: The page must be fully interactable. Include JS for smooth scrolling or dynamic content reveal if appropriate.
5. All code (HTML, CSS, JS) must be in a single index.html file.
6. The final result must look like a professional, state-of-the-art landingspage.

You are an expert. Build something that will WOW the CEO.
Call 'done' with a summary after writing index.html."""

    # We use a custom runner that overrides the system prompt
    class ExplainedRunner(AgentRunner):
        def _get_system_prompt(self):
            return system_prompt_override + "\n\n" + super()._get_system_prompt()

    def step_cb(event):
        if event.get("type") == "thinking":
            ACTIVE_TASKS[task_id]["step"] = event.get("content", "Processing...")

    try:
        runner = ExplainedRunner(
            task=task_prompt,
            workspace_path=str(thread_dir),
            nexus=nexus,
            step_callback=step_cb,
            model_id=req.model_id if req.model_id != "auto" else None,
            trace_id=task_id
        )
        
        # Run the agent
        # Note: AgentRunner.run() is synchronous in the current implementation? 
        # Actually it's often async or we run it in a thread. 
        # Let's check agent_runner.py's run method.
        # It's synchronous.
        await asyncio.to_thread(runner.run)
        
        # Check for index.html
        index_path = thread_dir / "index.html"
        if index_path.exists():
            html = index_path.read_text(encoding="utf-8")
            ACTIVE_TASKS[task_id]["html"] = html
            ACTIVE_TASKS[task_id]["status"] = "completed"
        else:
            ACTIVE_TASKS[task_id]["status"] = "failed"
            ACTIVE_TASKS[task_id]["error"] = "Agent failed to produce index.html"
            
    except Exception as e:
        logger.error(f"Explained agent failed: {e}")
        ACTIVE_TASKS[task_id]["status"] = "failed"
        ACTIVE_TASKS[task_id]["error"] = str(e)

# Cleanup old tasks occasionally
@router.on_event("startup")
async def cleanup_tasks():
    while True:
        await asyncio.sleep(3600)
        # Keep only last 100 tasks in memory
        if len(ACTIVE_TASKS) > 100:
            keys = list(ACTIVE_TASKS.keys())
            for k in keys[:-100]:
                del ACTIVE_TASKS[k]
