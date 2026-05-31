"""
Aethvion Suite - Memory API Routes
FastAPI routes for memory management and visualization
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from pathlib import Path
from pydantic import BaseModel

from core.utils import get_logger, utcnow_iso, atomic_json_write, load_json
from core.memory import get_episodic_memory, get_knowledge_graph
from core.utils.paths import PERSISTENT_MEMORY_JSON

logger = get_logger("web.memory_routes")

# Create router
router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/overview")
async def get_memory_overview(
    limit:  int = Query(default=50, ge=1, le=200, description="Max threads to return"),
    offset: int = Query(default=0,  ge=0,          description="Thread offset for pagination"),
):
    """
    Get comprehensive memory overview.
    Returns Permanent Memory (Core Insights) and a paginated slice of Thread Memory.
    """
    try:
        # 1. Fetch Permanent Memory (Core Insights)
        kg = get_knowledge_graph()
        permanent_memory = []
        try:
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

        # 2. Fetch Thread Memory (paginated)
        episodic = get_episodic_memory()
        threads_memory = []

        project_root  = Path(__file__).parent.parent.parent.parent
        workspaces_dir = project_root / "data" / "workspaces" / "projects"

        total_threads = 0
        if workspaces_dir.exists():
            all_thread_files = sorted(
                workspaces_dir.glob("thread-*/thread-*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            total_threads = len(all_thread_files)
            page_files    = all_thread_files[offset : offset + limit]

            for thread_file in page_files:
                try:
                    thread_data = load_json(thread_file, default={})
                    if not thread_data:
                        continue

                    task_ids      = thread_data.get('task_ids', [])
                    thread_memories = []
                    tasks_dir     = thread_file.parent / "tasks"

                    for task_id in task_ids:
                        task_found = False
                        task_path  = tasks_dir / f"{task_id}.json"
                        task_data  = load_json(task_path, default={})

                        if task_data:
                            result = task_data.get('result', {}) or {}
                            prompt = task_data.get('prompt', '') or ''
                            mode   = task_data.get('metadata', {}).get('mode', 'task')

                            if result.get('agents_spawned'):
                                summary = f"Spawned: {', '.join(result['agents_spawned'])}"
                            elif mode == 'chat_only':
                                summary = prompt[:80] + ('…' if len(prompt) > 80 else '')
                            else:
                                summary = f"Task: {prompt[:60]}{'…' if len(prompt) > 60 else ''}"

                            thread_memories.append({
                                "memory_id":  task_data.get('id'),
                                "trace_id":   task_data.get('id'),
                                "event_type": mode or "task_execution",
                                "summary":    summary,
                                "content":    f"Prompt: {prompt}\n\nResponse: {result.get('response', '')}",
                                "timestamp":  task_data.get('created_at', ''),
                                "domain":     mode.replace('_', ' ').title() if mode else 'Task',
                                "details":    task_data,
                            })
                            task_found = True

                        memories = episodic.get_by_trace_id(task_id)
                        if not task_found and not memories:
                            logger.warning(f"No data found for task {task_id}")

                        for mem in memories:
                            if task_found and mem.event_type == 'task_execution':
                                continue
                            thread_memories.append({
                                "memory_id":  mem.memory_id,
                                "trace_id":   mem.trace_id,
                                "event_type": mem.event_type,
                                "summary":    mem.summary,
                                "content":    mem.content,
                                "timestamp":  mem.timestamp,
                                "domain":     mem.domain,
                            })

                    thread_memories.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                    threads_memory.append({
                        "id":           thread_data.get('id'),
                        "title":        thread_data.get('title', 'Untitled Thread'),
                        "updated_at":   thread_data.get('updated_at'),
                        "memory_count": len(thread_memories),
                        "memories":     thread_memories,
                    })

                except Exception as e:
                    logger.warning(f"Error reading thread file {thread_file}: {e}")
                    continue

        return {
            "permanent": permanent_memory,
            "threads":   threads_memory,
            "pagination": {
                "total":  total_threads,
                "offset": offset,
                "limit":  limit,
            },
        }

    except Exception as e:
        logger.error(f"Error generating memory overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/persistent")
async def get_persistent_memory():
    """Retrieve the full persistent JSON memory store."""
    return load_json(PERSISTENT_MEMORY_JSON, default={})


class MemoryUpdateRequest(BaseModel):
    topic: str
    content: str


@router.post("/persistent/update")
async def update_persistent_memory(req: MemoryUpdateRequest):
    """Upsert a topic into the persistent memory store."""
    try:
        data = load_json(PERSISTENT_MEMORY_JSON, default={})
        
        # Store as object with timestamp
        data[req.topic] = {
            "content": req.content,
            "updated_at": utcnow_iso()
        }
        
        PERSISTENT_MEMORY_JSON.parent.mkdir(parents=True, exist_ok=True)
        atomic_json_write(PERSISTENT_MEMORY_JSON, data)
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
            
        data = load_json(PERSISTENT_MEMORY_JSON, default={})
        if topic in data:
            del data[topic]
            atomic_json_write(PERSISTENT_MEMORY_JSON, data)
            return {"status": "success", "topic": topic}
        
        return {"status": "skipped", "reason": "Topic not found"}
    except Exception as e:
        logger.error(f"Error deleting persistent memory topic '{topic}': {e}")
        raise HTTPException(status_code=500, detail=str(e))
