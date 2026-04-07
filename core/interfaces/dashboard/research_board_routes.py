"""
Aethvion Suite - Research Board of Directors API
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import uuid
import asyncio
from datetime import datetime

from core.utils import get_logger, utcnow_iso
from core.utils.paths import HISTORY_ADVANCED
from core.ai.call_contexts import CallSource

logger = get_logger("web.research_board_routes")

router = APIRouter(prefix="/api/board", tags=["board"])

DIRECTORS_DIR = HISTORY_ADVANCED / "directors"
SESSIONS_DIR = HISTORY_ADVANCED / "board_sessions"

# Ensure dirs exist
DIRECTORS_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

class BoardStartRequest(BaseModel):
    topic: str
    round_count: int = 3
    model_id: str = "auto"
    participants: Optional[List[str]] = None

class SynthesisRequest(BaseModel):
    thread_id: str
    model_id: str = "auto"

class BoardGenerateRequest(BaseModel):
    person_id: str
    model_id: str
    max_context: int = 20

DEFAULT_DIRECTORS = [
    {
        "id": "director_ops",
        "name": "Strategic Operations Director",
        "type": "director",
        "gender": "Non-binary",
        "background": "An expert in scaling startups and optimizing unit economics. They focus on long-term sustainability, market expansion, and operational efficiency. They prioritize data-driven decisions and clear paths to profitability.",
        "traits": {"Scaling": 9, "Efficiency": 10, "Risk_Assessment": 8, "Sustainability": 7},
        "memory": "Expert in operational infrastructure and market entry."
    },
    {
        "id": "director_cx",
        "name": "Customer Experience Lead",
        "type": "director",
        "gender": "Female",
        "background": "A specialist in user retention, community building, and brand trust. They believe that long-term success comes from providing genuine value and maintaining a transparent relationship with the audience.",
        "traits": {"Retention": 10, "Empathy": 9, "Community-Value": 10, "Transparency": 8},
        "memory": "Expert in user psychology and community health."
    },
    {
        "id": "director_arch",
        "name": "Lead Technical Architect",
        "type": "director",
        "gender": "Male",
        "background": "A veteran systems architect focused on technical stability, security, and reducing technical debt. They advocate for realistic development timelines and robust, maintainable infrastructure.",
        "traits": {"Stability": 10, "Security": 9, "Feasibility": 10, "Long-term-Debt": 9},
        "memory": "Expert in distributed systems and technical lifecycle management."
    },
    {
        "id": "director_growth",
        "name": "Market Strategy & Growth",
        "type": "director",
        "gender": "Fluid",
        "background": "A marketing and growth specialist focused on brand positioning, acquisition channels, and viral loops. They look for unique angles to reach the target audience and build a compelling brand narrative.",
        "traits": {"Growth": 10, "Positioning": 9, "Creativity": 8, "Market-Fit": 10},
        "memory": "Expert in brand storytelling and acquisition strategy."
    }
]

def ensure_default_directors():
    """Ensure the 4 default board members exist in the directors directory."""
    for d_cfg in DEFAULT_DIRECTORS:
        p_file = DIRECTORS_DIR / f"{d_cfg['id']}.json"
        if not p_file.exists():
            data = d_cfg.copy()
            data.pop('id')
            data['original_traits'] = data['traits'].copy()
            data['original_memory'] = data['memory']
            data['message_count'] = 0
            with open(p_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            logger.info(f"Initialized default director: {d_cfg['name']}")

@router.get("/directors")
async def get_directors():
    ensure_default_directors()
    directors = []
    for f in DIRECTORS_DIR.glob("*.json"):
        try:
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)
                data['id'] = f.stem
                directors.append(data)
        except Exception as e:
            logger.error(f"Failed to read director {f}: {e}")
    return directors

@router.post("/start")
async def start_board(req: BoardStartRequest):
    ensure_default_directors()
    active_pids = req.participants if req.participants and len(req.participants) > 0 else [d['id'] for d in DEFAULT_DIRECTORS]
    
    sid = f"board-{uuid.uuid4().hex[:8]}"
    s_dir = SESSIONS_DIR / sid
    s_dir.mkdir(parents=True, exist_ok=True)
    
    meta = {
        "name": f"Board: {req.topic[:30]}...",
        "topic": req.topic,
        "participants": active_pids,
        "round_count": req.round_count,
        "is_board": True,
        "created_at": utcnow_iso(),
        "updated_at": utcnow_iso()
    }
    with open(s_dir / "meta.json", "w", encoding='utf-8') as f:
        json.dump(meta, f, indent=4)
    with open(s_dir / "messages.json", "w", encoding='utf-8') as f:
        json.dump([], f)
    with open(s_dir / "snapshots.json", "w", encoding='utf-8') as f:
        json.dump([], f)
        
    people = []
    for pid in active_pids:
        p_file = DIRECTORS_DIR / f"{pid}.json"
        if p_file.exists():
            with open(p_file, 'r', encoding='utf-8') as f:
                p = json.load(f)
                p['id'] = pid
                people.append(p)
            
    return {"thread": {"id": sid, **meta}, "personas": people}

@router.post("/sessions/{session_id}/generate")
async def generate_board_response(session_id: str, req: BoardGenerateRequest, request: Request):
    nexus = getattr(request.app.state, 'nexus', None)
    if not nexus: raise HTTPException(503, "System not initialized")
    
    s_dir = SESSIONS_DIR / session_id
    if not s_dir.exists(): raise HTTPException(404, "Session not found")
    
    # Load persona
    p_file = DIRECTORS_DIR / f"{req.person_id}.json"
    if not p_file.exists(): raise HTTPException(404, "Director not found")
    with open(p_file, 'r', encoding='utf-8') as f:
        person = json.load(f)
        
    # Load messages
    msg_file = s_dir / "messages.json"
    with open(msg_file, 'r', encoding='utf-8') as f:
        messages = json.load(f)
        
    # Specialized Professional Board prompt
    system_prompt = f"""You are {person['name']}, a senior consultant on the Board of Directors.
Your expertise: {person['background']}
Your current focus areas (scale 1-10): {json.dumps(person['traits'])}
Your internal professional context: {person['memory']}

You are participating in a strategic consult for the CEO. Your goal is to provide realistic, professional, and useful advice from your specific area of expertise.
Avoid extreme caricatures or roleplay jargon. Be concise, direct, and helpful.

Output a strictly valid JSON object:
{{
    "spoken_response": "Your professional contribution or question for the board/CEO",
    "updated_traits": {json.dumps(person['traits'])},
    "memory_updates": "Briefly update your context with new core facts from the debate.",
    "trait_changes_tldr": "Why is your focus shifting?"
}}
"""

    context = ""
    history = messages[-req.max_context:] if len(messages) > req.max_context else messages
    for m in history:
        context += f"[{m.get('name', 'System')}]: {m['content']}\n"
        
    prompt = f"Global Topic: {session_id}\n\nRecent Transcript:\n{context}\n\n{person['name']}, what is your official stance or reply?"

    try:
        pm = nexus.provider_manager
        response = await asyncio.to_thread(
            pm.call_with_failover,
            prompt=prompt,
            system_prompt=system_prompt,
            model=req.model_id,
            trace_id=uuid.uuid4().hex,
            source=CallSource.RESEARCH,
            json_mode=True
        )
        if not response.success: raise Exception(response.error)
        
        content = response.content.strip()
        if content.startswith('```json'): content = content[7:]
        if content.startswith('```'): content = content[3:]
        if content.endswith('```'): content = content[:-3]
        parsed = json.loads(content.strip())
        
        # Save updates
        spoken = parsed.get("spoken_response", "")
        person['traits'] = parsed.get("updated_traits", person['traits'])
        person['memory'] = parsed.get("memory_updates", person['memory'])
        person['message_count'] = person.get('message_count', 0) + 1
        with open(p_file, 'w', encoding='utf-8') as f:
            json.dump(person, f, indent=4)
            
        msg_id = uuid.uuid4().hex[:8]
        new_msg = {
            "id": msg_id,
            "role": "person",
            "person_id": req.person_id,
            "name": person['name'],
            "content": spoken,
            "timestamp": utcnow_iso()
        }
        messages.append(new_msg)
        with open(msg_file, 'w', encoding='utf-8') as f:
            json.dump(messages, f, indent=4)

        return {"message": new_msg, "updated_person": person}
    except Exception as e:
        logger.error(f"Board generate failed: {e}")
        raise HTTPException(500, str(e))

@router.post("/synthesize")
async def synthesize_board(req: SynthesisRequest, request: Request):
    nexus = getattr(request.app.state, 'nexus', None)
    if not nexus: raise HTTPException(503, "System not initialized")
    
    s_dir = SESSIONS_DIR / req.thread_id
    if not s_dir.exists(): raise HTTPException(404, "Session not found")
    
    with open(s_dir / "messages.json", 'r', encoding='utf-8') as f:
        messages = json.load(f)
    with open(s_dir / "meta.json", 'r', encoding='utf-8') as f:
        meta = json.load(f)
        
    transcript = f"Topic: {meta['topic']}\n\n"
    for m in messages:
        if m['role'] == 'person':
            transcript += f"[{m['name']}]: {m['content']}\n\n"
            
    system_prompt = """You are the 'Synthesis Secretary' for a Board of Directors debate. 
Provide a professional, structured markdown recommendation to the CEO based on the transcript.
1. Core conflict points.
2. Compelling arguments.
3. Final synthesize recommendation.
4. Action items."""
    
    prompt = f"Synthesize debate:\n\n{transcript}"
    
    try:
        pm = nexus.provider_manager
        response = await asyncio.to_thread(
            pm.call_with_failover,
            prompt=prompt,
            system_prompt=system_prompt,
            model=req.model_id,
            trace_id=uuid.uuid4().hex,
            source=CallSource.RESEARCH
        )
        if not response.success: raise Exception(response.error)
        
        new_msg = {
            "id": uuid.uuid4().hex[:8],
            "role": "system",
            "content": f"### FINAL BOARD RECOMMENDATION\n\n{response.content}",
            "is_synthesis": True,
            "timestamp": utcnow_iso()
        }
        messages.append(new_msg)
        with open(s_dir / "messages.json", 'w', encoding='utf-8') as f:
            json.dump(messages, f, indent=4)
            
        return {"synthesis": response.content}
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        raise HTTPException(500, str(e))
