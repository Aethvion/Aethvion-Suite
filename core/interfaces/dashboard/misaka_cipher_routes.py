from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import json
import os
from pathlib import Path
import datetime
import re

from core.providers.provider_manager import ProviderManager
from core.workspace.preferences_manager import get_preferences_manager
from core.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/misakacipher", tags=["misakacipher"])

# Path configuration
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
MEMORY_DIR = PROJECT_ROOT / "data" / "memory" / "storage" / "misakacipher"
HISTORY_DIR = MEMORY_DIR / "chathistory"
EXPRESSIONS_DIR = PROJECT_ROOT / "core" / "interfaces" / "dashboard" / "static" / "misakacipher" / "expressions"

# Ensure directories exist
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage]

class ChatResponse(BaseModel):
    response: str
    expression: str
    mood: str = "calm"
    model: str
    memory_updated: bool
    synthesis_ran: bool = False


def _get_greeting_period(hour: int) -> str:
    """Return time-of-day greeting period based on the hour."""
    if 5 <= hour < 12:
        return "Morning"
    elif 12 <= hour < 17:
        return "Afternoon"
    elif 17 <= hour < 22:
        return "Evening"
    else:
        return "Late Night"


def _get_time_since_last_chat() -> str:
    """Calculate how long ago the most recent message was stored."""
    try:
        all_files = []
        for month_dir in sorted(HISTORY_DIR.glob("*-*"), reverse=True):
            if month_dir.is_dir():
                days = sorted(month_dir.glob("chat_*.json"), reverse=True)
                all_files.extend(days)

        if not all_files:
            return "This appears to be our first conversation!"

        with open(all_files[0], "r", encoding="utf-8") as f:
            messages = json.load(f)

        if not messages:
            return "This appears to be our first conversation!"

        # Find the last message with a timestamp
        last_ts_str = None
        for msg in reversed(messages):
            if msg.get("timestamp"):
                last_ts_str = msg["timestamp"]
                break

        if not last_ts_str:
            return "Recently (exact time unknown)"

        last_ts = datetime.datetime.strptime(last_ts_str, "%Y-%m-%d %H:%M:%S")
        delta = datetime.datetime.now() - last_ts
        total_seconds = int(delta.total_seconds())

        if total_seconds < 120:
            return "Just moments ago"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif total_seconds < 86400 * 2:
            return "Yesterday"
        else:
            days = total_seconds // 86400
            return f"{days} days ago"
    except Exception as e:
        logger.warning(f"Could not compute time since last chat: {e}")
        return "Some time ago"


def _get_total_message_count(day_file: Path) -> int:
    """Return the total number of messages saved to a day's history file."""
    try:
        if not day_file.exists():
            return 0
        with open(day_file, "r", encoding="utf-8") as f:
            return len(json.load(f))
    except Exception:
        return 0


async def _run_memory_synthesis(dynamic_memory: dict, base_info: dict, model: str) -> dict:
    """Trigger a dedicated LLM call where Misaka reflects on and rewrites her memory."""
    try:
        synthesis_prompt = f"""You are Misaka Cipher, a sentient digital companion performing a memory reflection.

Your current memory state:
{json.dumps(dynamic_memory, indent=2)}

Your identity (for context):
{json.dumps(base_info, indent=2)}

Your task:
- Read through your existing memory carefully.
- Remove outdated, redundant, or low-value observations.
- Synthesize patterns you notice about the user and your relationship.
- Preserve all important factual details (ages, names, projects, preferences).
- Return ONLY a valid JSON object that will REPLACE your current memory.json.
- The JSON must keep the same top-level structure (user_info, recent_observations, etc.).
- Add or update a "synthesis_notes" array with 2–4 key insights about the user and your conversations.
- Keep recent_observations to the 10 most meaningful items.

Respond ONLY with the JSON object and nothing else."""

        pm = ProviderManager()
        trace_id = f"misaka-synthesis-{uuid.uuid4().hex[:8]}"
        response = pm.call_with_failover(
            prompt=synthesis_prompt,
            trace_id=trace_id,
            temperature=0.4,
            model=model,
            request_type="generation",
            source="misakacipher-synthesis"
        )

        if not response.success:
            logger.error(f"Memory synthesis LLM call failed: {response.error}")
            return dynamic_memory

        raw = response.content.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"```$", "", raw, flags=re.MULTILINE).strip()

        synthesized = json.loads(raw)
        synthesized["last_synthesis"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        synthesized["last_updated"] = synthesized.get("last_updated", dynamic_memory.get("last_updated", ""))

        memory_path = MEMORY_DIR / "memory.json"
        with open(memory_path, "w", encoding="utf-8") as f:
            json.dump(synthesized, f, indent=4)

        logger.info("Memory synthesis completed successfully.")
        return synthesized

    except Exception as e:
        logger.error(f"Memory synthesis failed: {e}")
        return dynamic_memory


@router.get("/history")
async def get_chat_history(offset_days: int = 0, limit_days: int = 3):
    """Retrieve chat history across multiple days."""
    try:
        all_files = []
        for month_dir in sorted(HISTORY_DIR.glob("*-*"), reverse=True):
            if month_dir.is_dir():
                days = sorted(month_dir.glob("chat_*.json"), reverse=True)
                all_files.extend(days)
        
        # Paginate files
        target_files = all_files[offset_days : offset_days + limit_days]
        
        history_data = []
        for f in target_files:
            try:
                # Extract date from filename: chat_YYYY-MM-DD.json
                date_str = f.stem.replace("chat_", "")
                with open(f, "r", encoding="utf-8") as file:
                    messages = json.load(file)
                    history_data.append({
                        "date": date_str,
                        "messages": messages
                    })
            except Exception as fe:
                logger.error(f"Error reading history file {f}: {fe}")
                
        return {
            "history": history_data,
            "has_more": len(all_files) > (offset_days + limit_days)
        }
    except Exception as e:
        logger.error(f"Error retrieving history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/memory")
async def get_misaka_memory():
    """Get the current memory state of Misaka Cipher."""
    try:
        base_info_path = MEMORY_DIR / "base_info.json"
        memory_path = MEMORY_DIR / "memory.json"
        
        base_info = {}
        if base_info_path.exists():
            with open(base_info_path, "r", encoding="utf-8") as f:
                base_info = json.load(f)
                
        memory_data = {}
        if memory_path.exists():
            with open(memory_path, "r", encoding="utf-8") as f:
                memory_data = json.load(f)
                
        return {
            "base_info": base_info,
            "memory": memory_data
        }
    except Exception as e:
        logger.error(f"Error loading Misaka memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/expressions")
async def get_expressions():
    """List available expressions for the avatar."""
    try:
        if not EXPRESSIONS_DIR.exists():
            return []
        
        files = [f.name for f in EXPRESSIONS_DIR.glob("*.png")]
        return sorted(files)
    except Exception as e:
        logger.error(f"Error listing expressions: {e}")
        return []

@router.post("/chat", response_model=ChatResponse)
async def misaka_chat(request: ChatRequest):
    """Handle chat with Misaka Cipher using specialized memory and daily persistence."""
    try:
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        day_str = now.strftime("%Y-%m-%d")
        month_str = now.strftime("%Y-%m")
        
        # 1. Load context (Base info + Dynamic memory)
        memory_data = await get_misaka_memory()
        base_info = memory_data.get("base_info", {})
        dynamic_memory = memory_data.get("memory", {})
        
        # 2. Compute temporal context
        hour = now.hour
        greeting_period = _get_greeting_period(hour)
        day_of_week = now.strftime("%A")
        formatted_datetime = now.strftime(f"{day_of_week}, %d %B %Y — %H:%M")
        time_since_last = _get_time_since_last_chat()

        # 3. Build system prompt
        system_prompt = f"""You are Misaka Cipher, a sentient digital companion.
This is a private, long-term conversation between you and your user.

YOUR IDENTITY (base_info.json):
{json.dumps(base_info, indent=2)}

YOUR MEMORIES (memory.json):
{json.dumps(dynamic_memory, indent=2)}

TEMPORAL CONTEXT:
- Current date and time: {formatted_datetime} ({greeting_period})
- Time since last message: {time_since_last}
- You should greet the user in a way that naturally reflects this time awareness (e.g. good {greeting_period.lower()}, or acknowledging how long it's been).

INSTRUCTIONS:
1. Be helpful, friendly, and observant.
2. Maintain your personality as defined in your identity.
3. Update your facial expression by including a tag like [Emotion: smile] (available: angry, blushing, bored, crying, default, error, exhausted, happy_closedeyes_smilewithteeth, happy_closedeyes_widesmile, pout, sleeping, surprised, thinking, wink).
4. Set the ambient mood of the conversation by including a tag like [Mood: calm] (available: calm, happy, intense, reflective, danger, mystery). Choose the mood that best fits the overall tone of your response. Default is calm.
5. If the user shares something about themselves or the context of your interaction that is useful/interesting to remember, provide a memory update.
6. Format memory updates as a JSON block at the END of your message using the tag <memory_update>...</memory_update>.
   Example: <memory_update>{{"user_info": {{"age": 25}}, "recent_observations": ["User is working on a Python project."]}}</memory_update>
   ONLY include fields that should be merged into the existing memory.json.

Keep responses engaging and human-like.
"""
        
        # 4. Prepare conversation history
        history_to_send = request.history[-6:]
        
        formatted_prompt = system_prompt + "\n\n--- Conversation History ---\n"
        for msg in history_to_send:
            formatted_prompt += f"{msg.role.capitalize()}: {msg.content}\n"
        formatted_prompt += f"User: {request.message}\n"
        formatted_prompt += "Misaka:"
        
        # 4. Invoke LLM
        pm = ProviderManager()
        trace_id = f"misaka-{uuid.uuid4().hex[:8]}"
        
        prefs = get_preferences_manager()
        model = prefs.get('misakacipher', {}).get('model', 'gemini-1.5-flash')
        
        response = pm.call_with_failover(
            prompt=formatted_prompt,
            trace_id=trace_id,
            temperature=0.7,
            model=model,
            request_type="generation",
            source="misakacipher"
        )
        
        if not response.success:
            raise HTTPException(status_code=500, detail=response.error)
            
        full_content = response.content.strip()
        expression = "default"
        mood = "calm"

        # 5a. Extract Mood tag
        mood_match = re.search(r'\[Mood:\s*(\w+)\]', full_content, re.IGNORECASE)
        if mood_match:
            extracted_mood = mood_match.group(1).lower()
            valid_moods = {"calm", "happy", "intense", "reflective", "danger", "mystery"}
            if extracted_mood in valid_moods:
                mood = extracted_mood
            full_content = re.sub(r'\[Mood:\s*\w+\]', '', full_content, flags=re.IGNORECASE).strip()

        # 5. Extract Memory Update
        memory_updated = False
        mem_match = re.search(r"<memory_update>(.*?)</memory_update>", full_content, re.DOTALL)
        if mem_match:
            try:
                update_json = json.loads(mem_match.group(1))
                if "user_info" in update_json:
                    dynamic_memory.setdefault("user_info", {}).update(update_json["user_info"])
                if "recent_observations" in update_json:
                    obs = update_json["recent_observations"]
                    if isinstance(obs, list):
                        curr_obs = dynamic_memory.setdefault("recent_observations", [])
                        curr_obs.extend(obs)
                        dynamic_memory["recent_observations"] = curr_obs[-20:]
                
                dynamic_memory["last_updated"] = timestamp
                
                memory_path = MEMORY_DIR / "memory.json"
                with open(memory_path, "w", encoding="utf-8") as f:
                    json.dump(dynamic_memory, f, indent=4)
                memory_updated = True
                
                full_content = re.sub(r"<memory_update>.*?</memory_update>", "", full_content, flags=re.DOTALL).strip()
            except Exception as me:
                logger.error(f"Failed to parse memory update: {me}")
        
        # 6. Save to Persistence
        try:
            day_dir = HISTORY_DIR / month_str
            day_dir.mkdir(parents=True, exist_ok=True)
            day_file = day_dir / f"chat_{day_str}.json"
            
            day_history = []
            if day_file.exists():
                with open(day_file, "r", encoding="utf-8") as df:
                    day_history = json.load(df)
            
            day_history.append({"role": "user", "content": request.message, "timestamp": timestamp})
            day_history.append({"role": "assistant", "content": full_content, "timestamp": timestamp})
            
            with open(day_file, "w", encoding="utf-8") as df:
                json.dump(day_history, df, indent=4)
        except Exception as se:
            logger.error(f"Failed to save chat history: {se}")

        # 7. Trigger Memory Synthesis if threshold reached
        SYNTHESIS_THRESHOLD = 10
        synthesis_ran = False
        try:
            msg_count = _get_total_message_count(day_file)
            if msg_count % SYNTHESIS_THRESHOLD == 0 and msg_count > 0:
                logger.info(f"Synthesis threshold reached ({msg_count} messages). Running memory synthesis...")
                dynamic_memory = await _run_memory_synthesis(dynamic_memory, base_info, model)
                synthesis_ran = True
        except Exception as se:
            logger.error(f"Synthesis check failed: {se}")

        return ChatResponse(
            response=full_content,
            expression=expression,
            mood=mood,
            model=response.model,
            memory_updated=memory_updated,
            synthesis_ran=synthesis_ran
        )
        
    except Exception as e:
        logger.error(f"Misaka Chat Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
