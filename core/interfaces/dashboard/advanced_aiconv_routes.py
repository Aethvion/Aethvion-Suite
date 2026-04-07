"""
Aethvion Suite - Advanced AI Conversation (Research Mode) API
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import uuid
import time
import asyncio
from datetime import datetime

from core.utils import get_logger, utcnow_iso
from core.utils.paths import HISTORY_ADVANCED
from core.ai.call_contexts import CallSource

logger = get_logger("web.advanced_aiconv_routes")

router = APIRouter(prefix="/api/research", tags=["research"])

STORAGE_DIR = HISTORY_ADVANCED
PEOPLE_DIR = HISTORY_ADVANCED / "people"
THREADS_DIR = HISTORY_ADVANCED / "threads"

# Ensure dirs exist
PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
THREADS_DIR.mkdir(parents=True, exist_ok=True)

class PersonaCreate(BaseModel):
    name: str
    gender: str
    traits: Dict[str, int]
    memory: str
    background: str
    model: Optional[str] = None

class PersonaUpdate(BaseModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    traits: Optional[Dict[str, int]] = None
    memory: Optional[str] = None
    background: Optional[str] = None
    model: Optional[str] = None

class ThreadCreate(BaseModel):
    name: str
    topic: str
    participants: List[str]

class SystemMessage(BaseModel):
    message: str

class GenerateRequest(BaseModel):
    person_id: str
    model_id: str
    max_context: int = 20

@router.get("/people")
async def get_people():
    people = []
    for f in PEOPLE_DIR.glob("*.json"):
        try:
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)
                data['id'] = f.stem
                people.append(data)
        except Exception as e:
            logger.error(f"Failed to read persona {f}: {e}")
    return people

@router.post("/people")
async def create_person(req: PersonaCreate):
    pid = uuid.uuid4().hex[:8]
    data = req.dict()
    data['original_traits'] = data['traits'].copy()
    data['original_memory'] = data['memory']
    data['message_count'] = 0
    with open(PEOPLE_DIR / f"{pid}.json", 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    data['id'] = pid
    return data

@router.delete("/people/{person_id}")
async def delete_person(person_id: str):
    p = PEOPLE_DIR / f"{person_id}.json"
    if p.exists():
        p.unlink()
        return {"success": True}
    raise HTTPException(404, "Person not found")

@router.put("/people/{person_id}")
async def update_person(person_id: str, req: PersonaUpdate):
    p_file = PEOPLE_DIR / f"{person_id}.json"
    if not p_file.exists():
        raise HTTPException(404, "Person not found")
        
    with open(p_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    update_data = req.dict(exclude_unset=True)
    for k, v in update_data.items():
        data[k] = v
        
    with open(p_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
        
    data['id'] = person_id
    return data

@router.get("/threads")
async def get_threads():
    threads = []
    for d in THREADS_DIR.iterdir():
        if d.is_dir():
            meta_file = d / "meta.json"
            if meta_file.exists():
                with open(meta_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    data['id'] = d.name
                    threads.append(data)
    # sort by updated desc
    threads.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
    return threads

@router.post("/threads")
async def create_thread(req: ThreadCreate):
    tid = f"thread-{uuid.uuid4().hex[:8]}"
    t_dir = THREADS_DIR / tid
    t_dir.mkdir(parents=True, exist_ok=True)
    
    meta = {
        "name": req.name,
        "topic": req.topic,
        "participants": req.participants,
        "created_at": utcnow_iso(),
        "updated_at": utcnow_iso()
    }
    with open(t_dir / "meta.json", "w", encoding='utf-8') as f:
        json.dump(meta, f, indent=4)
        
    with open(t_dir / "messages.json", "w", encoding='utf-8') as f:
        json.dump([], f)
        
    with open(t_dir / "snapshots.json", "w", encoding='utf-8') as f:
        json.dump([], f)
        
    meta['id'] = tid
    return meta

@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str):
    t_dir = THREADS_DIR / thread_id
    if not t_dir.exists():
        raise HTTPException(404, "Thread not found")
        
    meta_file = t_dir / "meta.json"
    msg_file = t_dir / "messages.json"
    snap_file = t_dir / "snapshots.json"
    
    with open(meta_file, 'r', encoding='utf-8') as f:
        meta = json.load(f)
    meta['id'] = thread_id
    
    messages = []
    if msg_file.exists():
        with open(msg_file, 'r', encoding='utf-8') as f:
            messages = json.load(f)
            
    snapshots = []
    if snap_file.exists():
        with open(snap_file, 'r', encoding='utf-8') as f:
            snapshots = json.load(f)
            
    return {"meta": meta, "messages": messages, "snapshots": snapshots}

@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str):
    import shutil
    t_dir = THREADS_DIR / thread_id
    if t_dir.exists():
        shutil.rmtree(t_dir)
        return {"success": True}
    raise HTTPException(404, "Thread not found")

class ThreadNameUpdate(BaseModel):
    name: str

@router.put("/threads/{thread_id}/name")
async def update_thread_name(thread_id: str, req: ThreadNameUpdate):
    t_dir = THREADS_DIR / thread_id
    meta_file = t_dir / "meta.json"
    if not meta_file.exists():
        raise HTTPException(404, "Thread not found")
        
    with open(meta_file, 'r', encoding='utf-8') as f:
        meta = json.load(f)
        
    meta['name'] = req.name
    meta['updated_at'] = utcnow_iso()

    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=4)

    return meta

@router.post("/threads/{thread_id}/system_message")
async def add_system_message(thread_id: str, req: SystemMessage):
    t_dir = THREADS_DIR / thread_id
    msg_file = t_dir / "messages.json"
    if not msg_file.exists():
        raise HTTPException(404, "Thread not found")
        
    with open(msg_file, 'r', encoding='utf-8') as f:
        messages = json.load(f)
        
    new_msg = {
        "id": uuid.uuid4().hex[:8],
        "role": "system",
        "content": req.message,
        "timestamp": utcnow_iso()
    }
    messages.append(new_msg)

    with open(msg_file, 'w', encoding='utf-8') as f:
        json.dump(messages, f, indent=4)

    # Update updated_at
    meta_file = t_dir / "meta.json"
    with open(meta_file, 'r', encoding='utf-8') as f:
        meta = json.load(f)
    meta['updated_at'] = new_msg['timestamp']
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=4)
        
    return new_msg

@router.put("/threads/{thread_id}/participants")
async def update_participants(thread_id: str, participants: List[str]):
    t_dir = THREADS_DIR / thread_id
    meta_file = t_dir / "meta.json"
    if not meta_file.exists():
        raise HTTPException(404, "Thread not found")
        
    with open(meta_file, 'r', encoding='utf-8') as f:
        meta = json.load(f)
        
    meta['participants'] = participants
    meta['updated_at'] = utcnow_iso()

    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=4)

    return meta

@router.post("/threads/{thread_id}/generate")
async def generate_response(thread_id: str, req: GenerateRequest, request: Request):
    nexus = getattr(request.app.state, 'nexus', None)
    if not nexus:
        raise HTTPException(503, "System not initialized")
        
    pm = nexus.provider_manager
    t_dir = THREADS_DIR / thread_id
    
    # Load thread data
    msg_file = t_dir / "messages.json"
    if not msg_file.exists():
        raise HTTPException(404, "Thread not found")
        
    with open(msg_file, 'r', encoding='utf-8') as f:
        messages = json.load(f)
        
    # Load persona
    p_file = PEOPLE_DIR / f"{req.person_id}.json"
    if not p_file.exists():
        raise HTTPException(404, "Person not found")
        
    with open(p_file, 'r', encoding='utf-8') as f:
        person = json.load(f)
        
    # Build Prompt
    system_prompt = f"""You are {person['name']}, engaging in a conversational simulation.
Your background: {person['background']}
Your current internal traits (scale 1-10): {json.dumps(person['traits'])}
Your internal private memory: {person['memory']}

You must respond to the conversation with your next spoken line. 
Crucially, based on the conversation, your memory and traits may evolve.
You must output a strictly valid JSON object. Do not wrap in markdown or backticks, just raw JSON.

Format exactly like this:
{{
    "spoken_response": "Your actual words in the conversation",
    "updated_traits": {{"happiness": 6, "skepticism": 8, "...": "..."}},
    "memory_updates": "An updated summary of your internal private memory, capturing new important details from this conversation.",
    "trait_changes_tldr": "A short summary of why traits changed, e.g. 'Happiness +1 because of compliment'"
}}
"""

    # Build conversation context
    context = ""
    # Safe historical slicing
    history_to_use = messages
    if req.max_context and req.max_context > 0:
        if req.max_context < len(messages):
            history_to_use = messages[-req.max_context:]

    for m in history_to_use:
        role = m.get('role', '')
        if role == 'system':
            context += f"System Event: {m['content']}\n"
        else:
            context += f"{m.get('name', 'Unknown')}: {m['content']}\n"
            
    prompt = f"Recent conversation:\n{context}\n\nWhat do you say next {person['name']}? Reply in the JSON format requested."

    # Call LLM
    try:
        # Note: In Misaka-Cipher we call `call_with_failover` or similar depending on the manager
        response = await asyncio.to_thread(
            pm.call_with_failover,
            prompt=prompt,
            system_prompt=system_prompt,
            model=req.model_id,
            trace_id=uuid.uuid4().hex,
            source=CallSource.RESEARCH,
            json_mode=True # Hint if supported by pm
        )
        if not response.success:
            raise Exception(response.error)
            
        content = response.content.strip()
        # Clean json
        if content.startswith('```json'): content = content[7:]
        if content.startswith('```'): content = content[3:]
        if content.endswith('```'): content = content[:-3]
        content = content.strip()
        
        parsed = json.loads(content)
        
        # Extract components
        spoken = parsed.get("spoken_response", "")
        new_traits = parsed.get("updated_traits", person['traits'])
        new_memory = parsed.get("memory_updates", person['memory'])
        tldr = parsed.get("trait_changes_tldr", "")
        
        # Update Person
        person['traits'] = new_traits
        person['memory'] = new_memory
        person['message_count'] = person.get('message_count', 0) + 1
        with open(p_file, 'w', encoding='utf-8') as f:
            json.dump(person, f, indent=4)
            
        # Append Message
        msg_id = uuid.uuid4().hex[:8]
        new_msg = {
            "id": msg_id,
            "role": "person",
            "person_id": req.person_id,
            "name": person['name'],
            "content": spoken,
            "tldr": tldr,
            "timestamp": utcnow_iso()
        }
        messages.append(new_msg)
        with open(msg_file, 'w', encoding='utf-8') as f:
            json.dump(messages, f, indent=4)
            
        # Append Snapshot
        snap_file = t_dir / "snapshots.json"
        with open(snap_file, 'r', encoding='utf-8') as f:
            snaps = json.load(f)
            
        snaps.append({
            "message_id": msg_id,
            "person_id": req.person_id,
            "traits": new_traits,
            "timestamp": new_msg['timestamp']
        })
        with open(snap_file, 'w', encoding='utf-8') as f:
            json.dump(snaps, f, indent=4)
            
        # Update Meta
        meta_file = t_dir / "meta.json"
        with open(meta_file, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        meta['updated_at'] = new_msg['timestamp']
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=4)
            
        return {
            "message": new_msg,
            "updated_person": person
        }
        
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"Generate failed: {str(e)}\n{tb}")
        raise HTTPException(500, f"Generation failed: {str(e)}\nTraceback:\n{tb}")
