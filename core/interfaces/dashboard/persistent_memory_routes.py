from fastapi import APIRouter, HTTPException
from typing import Dict
from core.memory.persistent_memory import get_persistent_memory
from core.utils import get_logger

logger = get_logger("web.persistent_memory_routes")

router = APIRouter(prefix="/api/memory/persistent", tags=["persistent_memory"])

@router.get("")
async def get_all_persistent_memory():
    """Get all persistent memory topics."""
    memory = get_persistent_memory()
    return memory.memory

@router.post("/update")
async def update_persistent_memory_topic(request: Dict[str, str]):
    """Update or add a topic to persistent memory."""
    topic = request.get('topic')
    content = request.get('content')
    if not topic or content is None:
        raise HTTPException(status_code=400, detail="Topic and content are required")
    
    memory = get_persistent_memory()
    memory.update_topic(topic, content)
    return {"status": "success", "topic": topic}

@router.delete("/{topic}")
async def delete_persistent_memory_topic(topic: str):
    """Delete a topic from persistent memory."""
    memory = get_persistent_memory()
    memory.delete_topic(topic)
    return {"status": "success", "topic": topic}

@router.delete("/")
async def clear_all_persistent_memory():
    """Clear all persistent memory."""
    memory = get_persistent_memory()
    memory.clear_all()
    return {"status": "success"}
