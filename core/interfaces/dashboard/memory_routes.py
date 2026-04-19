"""
Aethvion Suite - Memory API Routes
FastAPI routes for memory management and visualization
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import asyncio
from pydantic import BaseModel

from core.utils import get_logger, utcnow_iso
from core.memory import get_episodic_memory, get_knowledge_graph
from core.utils.paths import PERSISTENT_MEMORY_JSON

logger = get_logger("web.memory_routes")

# Create router
router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/overview")
async def get_memory_overview():
    """
    Get comprehensive memory overview.
    Returns Permanent Memory (Core Insights) and Thread Memory.
    """
    try:
        # 1. Fetch Permanent Memory (Core Insights)
        kg = get_knowledge_graph()
        permanent_memory = []
        
        try:
            # Iterate graph nodes to find core insights
            for node, data in kg.graph.nodes(data=True):
                if data.get('node_type') == 'core_insight':
                    permanent_memory.append({
                        "id": node,
                        "summary": data.get('summary', 'No summary'),
                        "created_at": data.get('created', ''),
                        "confidence": data.get('confidence', 0.0),
                        "tags": data.get('tags', [])
                    })
        except Exception as e:
            logger.error(f"Error fetching permanent memory: {e}")
            
        # 2. Fetch Thread Memory
        episodic = get_episodic_memory()
        threads_memory = []
        
        # Path to threads directory
        # __file__ = core/interfaces/dashboard/memory_routes.py → parent.parent.parent.parent = project root
        project_root = Path(__file__).parent.parent.parent.parent
        workspaces_dir = project_root / "data" / "workspaces" / "projects"
        
        if workspaces_dir.exists():
            # Get all thread JSON files inside hierarchical folders
            thread_files = sorted(workspaces_dir.glob("thread-*/thread-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            
            for thread_file in thread_files:
                try:
                    with open(thread_file, 'r') as f:
                        thread_data = json.load(f)
                        
                    task_ids = thread_data.get('task_ids', [])
                    thread_memories = []
                    
                    logger.info(f"Loading thread {thread_data.get('id')} with tasks: {task_ids}")
                    
                    # Dynamically get tasks_dir from the thread's own workspace folder
                    tasks_dir = thread_file.parent / "tasks"
                    
                    # Fetch data for each task
                    for task_id in task_ids:
                        task_found = False
                        
                        # 1. Try to load from Task JSON (Primary Source)
                        task_path = tasks_dir / f"{task_id}.json"
                        if task_path.exists():
                            try:
                                with open(task_path, 'r', encoding='utf-8') as tf:
                                    task_data = json.load(tf)
                                    
                                # Create memory entry from Task Data
                                result = task_data.get('result', {}) or {}
                                prompt = task_data.get('prompt', '') or ''
                                mode = task_data.get('metadata', {}).get('mode', 'task')

                                # Build a meaningful summary depending on task type
                                if result.get('agents_spawned'):
                                    summary = f"Spawned: {', '.join(result['agents_spawned'])}"
                                elif mode == 'chat_only':
                                    summary = prompt[:80] + ('…' if len(prompt) > 80 else '')
                                else:
                                    summary = f"Task: {prompt[:60]}{'…' if len(prompt) > 60 else ''}"

                                memory_entry = {
                                    "memory_id": task_data.get('id'),
                                    "trace_id": task_data.get('id'),
                                    "event_type": mode if mode else "task_execution",
                                    "summary": summary,
                                    "content": f"Prompt: {prompt}\n\nResponse: {result.get('response', '')}",
                                    "timestamp": task_data.get('created_at', ''),
                                    "domain": task_data.get('metadata', {}).get('mode', 'task').replace('_', ' ').title(),
                                    "details": task_data
                                }
                                thread_memories.append(memory_entry)
                                task_found = True
                            except Exception as te:
                                logger.error(f"Failed to load task file {task_path}: {te}")

                        # 2. If not found or if we want semantic info, check Episodic Store (Secondary/Fallback)
                        # We query this regardless to see if there are *additional* related memories (like sub-steps),
                        # but we dedup based on trace_id if we already loaded the main task.
                        memories = episodic.get_by_trace_id(task_id)
                        
                        if not task_found and not memories:
                             logger.warning(f"No data found for task {task_id}")
                        
                        for mem in memories:
                            # Avoid duplicates if we already loaded this task from file
                            # (unless it's a distinct memory event for the same trace)
                            if task_found and mem.event_type == 'task_execution': 
                                continue
                                
                            thread_memories.append({
                                "memory_id": mem.memory_id,
                                "trace_id": mem.trace_id,
                                "event_type": mem.event_type,
                                "summary": mem.summary,
                                "content": mem.content,
                                "timestamp": mem.timestamp,
                                "domain": mem.domain
                            })
                            
                    # Sort memories by timestamp
                    thread_memories.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                    
                    threads_memory.append({
                        "id": thread_data.get('id'),
                        "title": thread_data.get('title', 'Untitled Thread'),
                        "updated_at": thread_data.get('updated_at'),
                        "memory_count": len(thread_memories),
                        "memories": thread_memories
                    })
                    
                except Exception as e:
                    logger.warning(f"Error reading thread file {thread_file}: {e}")
                    continue
        
        return {
            "permanent": permanent_memory,
            "threads": threads_memory
        }

    except Exception as e:
        logger.error(f"Error generating memory overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/persistent")
async def get_persistent_memory():
    """Retrieve the full persistent JSON memory store."""
    if not PERSISTENT_MEMORY_JSON.exists():
        return {}
    try:
        return json.loads(PERSISTENT_MEMORY_JSON.read_text(encoding='utf-8'))
    except Exception as e:
        logger.error(f"Error reading persistent memory: {e}")
        return {}


class MemoryUpdateRequest(BaseModel):
    topic: str
    content: str


@router.post("/persistent/update")
async def update_persistent_memory(req: MemoryUpdateRequest):
    """Upsert a topic into the persistent memory store."""
    try:
        data = {}
        if PERSISTENT_MEMORY_JSON.exists():
            data = json.loads(PERSISTENT_MEMORY_JSON.read_text(encoding='utf-8'))
        
        # Store as object with timestamp
        data[req.topic] = {
            "content": req.content,
            "updated_at": utcnow_iso()
        }
        
        PERSISTENT_MEMORY_JSON.parent.mkdir(parents=True, exist_ok=True)
        PERSISTENT_MEMORY_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        return {"status": "success", "topic": req.topic}
    except Exception as e:
        logger.error(f"Error updating persistent memory topic '{req.topic}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/persistent/{topic}")
async def delete_persistent_memory_topic(topic: str):
    """Remove a topic from the persistent memory store."""
    try:
        if not PERSISTENT_MEMORY_JSON.exists():
            return {"status": "skipped", "reason": "File not found"}
            
        data = json.loads(PERSISTENT_MEMORY_JSON.read_text(encoding='utf-8'))
        if topic in data:
            del data[topic]
            PERSISTENT_MEMORY_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
            return {"status": "success", "topic": topic}
        
        return {"status": "skipped", "reason": "Topic not found"}
    except Exception as e:
        logger.error(f"Error deleting persistent memory topic '{topic}': {e}")
        raise HTTPException(status_code=500, detail=str(e))
