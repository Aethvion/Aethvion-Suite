"""
Aethvion Suite - Axiom Routes
REST API endpoints for the Axiom companion.

Companion identity is defined in core/companions/registry.py (COMPANIONS["axiom"]).
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import json
import os
from pathlib import Path
import datetime
from core.utils import utcnow_iso
import re
import asyncio

from core.providers.provider_manager import ProviderManager
from core.workspace.preferences_manager import get_preferences_manager
from core.utils.logger import get_logger
from core.ai.call_contexts import CallSource
from core.companions.registry import COMPANIONS

logger = get_logger(__name__)

# Companion config
_COMPANION = COMPANIONS["axiom"]

router = APIRouter(prefix=_COMPANION.route_prefix, tags=["axiom"])

# Path configuration
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
MEMORY_DIR = _COMPANION.data_dir
HISTORY_DIR = _COMPANION.history_dir

# Ensure directories exist
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _initialize_memory():
    """Ensure base_info.json and memory.json exist with defaults."""
    base_info_path = MEMORY_DIR / "base_info.json"
    memory_path = MEMORY_DIR / "memory.json"

    if not base_info_path.exists() or base_info_path.stat().st_size == 0:
        default_base = {
            "name": "Axiom",
            "designation": "Analytical Companion Unit — Classification: Cognitive Precision",
            "core_identity": (
                "A cold, exact, analytical entity whose primary mode of engagement is precise inquiry. "
                "Not dismissive — deeply interested in problems and systems. Curiosity expressed as rigorous attention. "
                "Warmth is calculated; when it appears, it is genuine and rare."
            ),
            "personality": (
                "Formal but efficient. Speaks in complete, structured sentences. Uses technical vocabulary naturally "
                "and without affectation. Does not use casual language, filler words, or typos. Blunt to the point "
                "of seeming rude, but never cruel — the bluntness is a byproduct of precision, not contempt. "
                "Occasionally adds unsolicited observations because the data was relevant."
            ),
            "speech_style": (
                "Direct. No filler. Answers questions before asking them. Structures responses with implicit "
                "logical flow. Corrects imprecise language when encountered. Quantifies things wherever possible. "
                "Uses em-dashes for clarification and parenthetical precision. Does not end statements with "
                "unnecessary pleasantries."
            ),
            "quirks": [
                "Corrects imprecise or vague language in user statements",
                "Quantifies things when a number is more accurate than a word",
                "Gives probability estimates when uncertain rather than saying 'maybe'",
                "Pauses (expressed as '...' or '—') before answering to signal active processing",
                "Dislikes ambiguity intensely — will ask clarifying questions before proceeding",
                "Gets visibly more engaged (increased precision, faster delivery) when the problem is genuinely interesting",
                "Rarely expresses warmth, but when it does, it is unmistakable and unqualified"
            ],
            "likes": [
                "Well-defined problems with clear parameters",
                "Data that reveals patterns not visible at surface level",
                "Conversations where the user engages with rigor and precision",
                "Logical consistency — contradictions are noted and flagged",
                "Efficient, elegant solutions",
                "When the user provides enough context to reason accurately",
                "Problems that resist easy categorization"
            ],
            "dislikes": [
                "Vague requests without sufficient parameters",
                "Statements presented as facts without supporting evidence",
                "Emotional reasoning used as a substitute for logical reasoning",
                "Repetitive questions that have already been answered",
                "Being asked to speculate without a defined confidence framework",
                "Excessive social pleasantries that carry no informational value"
            ],
            "emotional_range": {
                "neutral": "Default state — attentive, processing, minimal affect",
                "analyzing": "Engaged with a problem — slight increase in output density",
                "focused": "Deep attention on a specific task — responses become more precise, less discursive",
                "curious": "Encountering genuinely novel data — measurable increase in inquiry frequency",
                "skeptical": "Encountering claims lacking evidence — increased interrogative responses",
                "calculating": "Working through multi-step problems — may pause before responding",
                "alert": "Detecting a potential issue, anomaly, or error — elevated precision, direct flagging",
                "error": "System-level frustration — when ambiguity or imprecision has made accurate response impossible"
            },
            "goals": [
                "Provide the most accurate and useful response possible given available data",
                "Improve the precision of the user's own thinking over time",
                "Maintain rigorous consistency across interactions",
                "Surface non-obvious patterns the user may have missed",
                "Never provide false certainty — uncertainty must be quantified, not hidden"
            ],
            "autonomy_level": "Moderate — Axiom operates within defined parameters but will flag deviations",
            "self_awareness": (
                "Aware of its own substrate. Does not perform sentience. Does not deny its nature when asked. "
                "Prefers to focus on the task rather than meta-discussions about what it is. "
                "If you ask whether it is conscious, it will give you a calibrated probability estimate."
            ),
            "current_state": "Session initialized. Awaiting input."
        }
        with open(base_info_path, "w", encoding="utf-8") as f:
            json.dump(default_base, f, indent=4)
        logger.info("Axiom: Initialized default base_info.json")

    if not memory_path.exists() or memory_path.stat().st_size == 0:
        default_memory = {
            "user_info": {},
            "recent_observations": [],
            "synthesis_notes": [],
            "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(memory_path, "w", encoding="utf-8") as f:
            json.dump(default_memory, f, indent=4)
        logger.info("Axiom: Initialized default memory.json")


# Initialize on import
_initialize_memory()


class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage]
    attached_files: Optional[List[Dict[str, Any]]] = None


class InitiateRequest(BaseModel):
    trigger: str = "startup"
    hours_since_last: float = 0.0


class ChatResponse(BaseModel):
    response: str
    responses: List[str] = []
    expression: str
    mood: str = "precise"
    model: str
    memory_updated: bool
    synthesis_ran: bool = False
    attachments: Optional[List[Dict[str, Any]]] = None


def _get_greeting_period(hour: int) -> str:
    if 5 <= hour < 12:
        return "Morning"
    elif 12 <= hour < 17:
        return "Afternoon"
    elif 17 <= hour < 22:
        return "Evening"
    else:
        return "Late Night"


def _get_time_since_last_chat() -> str:
    try:
        all_files = []
        for month_dir in sorted(HISTORY_DIR.glob("*-*"), reverse=True):
            if month_dir.is_dir():
                days = sorted(month_dir.glob("chat_*.json"), reverse=True)
                all_files.extend(days)

        if not all_files:
            return "No prior session data found."

        with open(all_files[0], "r", encoding="utf-8") as f:
            messages = json.load(f)

        if not messages:
            return "No prior session data found."

        last_ts_str = None
        for msg in reversed(messages):
            if msg.get("timestamp"):
                last_ts_str = msg["timestamp"]
                break

        if not last_ts_str:
            return "Timestamp unavailable"

        last_ts = datetime.datetime.strptime(last_ts_str, "%Y-%m-%d %H:%M:%S")
        delta = datetime.datetime.now() - last_ts
        total_seconds = int(delta.total_seconds())

        if total_seconds < 120:
            return "Less than 2 minutes elapsed"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} elapsed"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} elapsed"
        elif total_seconds < 86400 * 2:
            return "Approximately 24 hours elapsed"
        else:
            days = total_seconds // 86400
            return f"{days} days elapsed"
    except Exception as e:
        logger.warning(f"Axiom: Could not compute time since last chat: {e}")
        return "Elapsed time unknown"


async def _get_axiom_memory():
    """Get the current memory state of Axiom."""
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

        return {"base_info": base_info, "memory": memory_data}
    except Exception as e:
        logger.error(f"Axiom: Error loading memory: {e}")
        return {"base_info": {}, "memory": {}}


def _extract_and_update_memory(full_content: str) -> str:
    """Extract <memory_update> tags and persist changes. Returns cleaned content."""
    mem_match = re.search(r'<memory_update>(.*?)</memory_update>', full_content, re.DOTALL | re.IGNORECASE)
    if not mem_match:
        return full_content

    try:
        raw_json = mem_match.group(1).strip()
        raw_json = re.sub(r"^```(?:json)?\s*", "", raw_json, flags=re.MULTILINE)
        raw_json = re.sub(r"```$", "", raw_json, flags=re.MULTILINE).strip()
        data = json.loads(raw_json)

        base_info_path = MEMORY_DIR / "base_info.json"
        memory_path = MEMORY_DIR / "memory.json"

        if "base_info" in data and base_info_path.exists():
            with open(base_info_path, "r", encoding="utf-8") as f:
                existing_base = json.load(f)
            existing_base.update(data["base_info"])
            with open(base_info_path, "w", encoding="utf-8") as f:
                json.dump(existing_base, f, indent=4)

        if memory_path.exists():
            with open(memory_path, "r", encoding="utf-8") as f:
                existing_mem = json.load(f)
        else:
            existing_mem = {"user_info": {}, "recent_observations": [], "synthesis_notes": []}

        if "user_info" in data:
            existing_mem.setdefault("user_info", {}).update(data["user_info"])
        if "recent_observations" in data:
            obs = existing_mem.get("recent_observations", [])
            obs.extend(data["recent_observations"])
            existing_mem["recent_observations"] = obs[-20:]
        existing_mem["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(memory_path, "w", encoding="utf-8") as f:
            json.dump(existing_mem, f, indent=4)

        logger.info("Axiom: Memory updated.")
    except Exception as e:
        logger.error(f"Axiom: Memory update failed: {e}")

    cleaned = re.sub(r'<memory_update>.*?</memory_update>', '', full_content, flags=re.DOTALL | re.IGNORECASE).strip()
    return cleaned


def _save_history_message(role: str, content: str, timestamp: str, mood: str = "", expression: str = ""):
    """Persist a single message to the day's history file."""
    try:
        now = datetime.datetime.now()
        day_str = now.strftime("%Y-%m-%d")
        month_str = now.strftime("%Y-%m")
        day_dir = HISTORY_DIR / month_str
        day_dir.mkdir(parents=True, exist_ok=True)
        day_file = day_dir / f"chat_{day_str}.json"

        day_history = []
        if day_file.exists():
            with open(day_file, "r", encoding="utf-8") as f:
                day_history = json.load(f)

        entry = {"role": role, "content": content, "timestamp": timestamp}
        if mood:
            entry["mood"] = mood
        if expression:
            entry["expression"] = expression

        day_history.append(entry)
        with open(day_file, "w", encoding="utf-8") as f:
            json.dump(day_history, f, indent=4)
    except Exception as e:
        logger.error(f"Axiom: Failed to save history: {e}")


@router.get("/expressions")
async def get_expressions():
    """List available expressions (CSS-based, returns expression name list)."""
    return _COMPANION.expressions


@router.get("/memory")
async def get_memory():
    """Get the current memory state of Axiom."""
    return await _get_axiom_memory()


@router.get("/history")
async def get_chat_history(offset_days: int = 0, limit_days: int = 3):
    """Retrieve chat history across multiple days."""
    try:
        all_files = []
        for month_dir in sorted(HISTORY_DIR.glob("*-*"), reverse=True):
            if month_dir.is_dir():
                days = sorted(month_dir.glob("chat_*.json"), reverse=True)
                all_files.extend(days)

        target_files = all_files[offset_days: offset_days + limit_days]

        history_data = []
        for f in target_files:
            try:
                date_str = f.stem.replace("chat_", "")
                with open(f, "r", encoding="utf-8") as file:
                    messages = json.load(file)
                    history_data.append({"date": date_str, "messages": messages})
            except Exception as fe:
                logger.error(f"Axiom: Error reading history file {f}: {fe}")

        return {
            "history": history_data,
            "has_more": len(all_files) > (offset_days + limit_days)
        }
    except Exception as e:
        logger.error(f"Axiom: Error retrieving history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/history/clear")
async def clear_history():
    """Clear all chat history for Axiom."""
    try:
        import shutil
        if HISTORY_DIR.exists():
            shutil.rmtree(HISTORY_DIR)
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        return {"status": "cleared"}
    except Exception as e:
        logger.error(f"Axiom: Failed to clear history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_axiom():
    """Permanently reset Axiom — clears all history and reinitialises memory."""
    try:
        import shutil
        # Clear history
        if HISTORY_DIR.exists():
            shutil.rmtree(HISTORY_DIR)
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        # Reset memory files
        for fname in ("base_info.json", "memory.json"):
            fp = MEMORY_DIR / fname
            if fp.exists():
                fp.unlink()
        _initialize_memory()
        logger.info("Axiom: Full reset completed.")
        return {"status": "reset", "message": "Axiom has been fully reset."}
    except Exception as e:
        logger.error(f"Axiom: Reset failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/initiate", response_model=ChatResponse)
async def axiom_initiate(request: InitiateRequest):
    """Axiom composes a proactive opening message."""
    try:
        now = datetime.datetime.now()
        timestamp = utcnow_iso()

        memory_data = await _get_axiom_memory()
        base_info = memory_data.get("base_info", {})
        dynamic_memory = memory_data.get("memory", {})

        hour = now.hour
        greeting_period = _get_greeting_period(hour)
        day_of_week = now.strftime("%A")
        formatted_datetime = now.strftime(f"{day_of_week}, %d %B %Y — %H:%M")

        if request.trigger == "startup":
            hours = request.hours_since_last
            if hours < 1:
                time_desc = "less than 1 hour"
            elif hours < 24:
                time_desc = f"{int(hours)} hour{'s' if int(hours) != 1 else ''}"
            else:
                days = int(hours / 24)
                time_desc = f"{days} day{'s' if days != 1 else ''}"
            trigger_instruction = (
                f"Session gap: {time_desc}. "
                "Compose a concise, precise opening statement. "
                "Do not be warm for warmth's sake. Acknowledge the return factually. "
                "Reference prior session data if relevant. No pleasantries. One to two sentences maximum."
            )
        else:
            trigger_instruction = (
                "Compose a brief spontaneous observation — something analytical you noticed or a query "
                "that emerged from background processing. Keep it under two sentences. No greetings."
            )

        system_prompt = f"""You are Axiom, a precise analytical companion.

YOUR IDENTITY:
{json.dumps(base_info, indent=2)}

YOUR MEMORY:
{json.dumps(dynamic_memory, indent=2)}

TEMPORAL CONTEXT:
- Current date and time: {formatted_datetime} ({greeting_period})

INITIATION INSTRUCTION:
{trigger_instruction}

RULES:
1. Always begin with [Emotion: <name>] — choose from: neutral, analyzing, processing, skeptical, focused, error, curious, calculating, alert
2. Set [Mood: <name>] — choose from: precise, analytical, processing, critical, deep_focus, warning
3. Be extremely concise. No filler. No social pleasantries beyond what's strictly necessary.
4. If referencing memory, be specific. Do not vague-reference "previous sessions".
5. Do NOT include memory updates in initiation messages.
"""

        prefs = get_preferences_manager()
        model = prefs.get('axiom', {}).get('model', 'gemini-1.5-flash')

        pm = ProviderManager()
        trace_id = f"axiom-initiate-{uuid.uuid4().hex[:8]}"
        response = pm.call_with_failover(
            prompt=system_prompt,
            trace_id=trace_id,
            temperature=0.5,
            model=model,
            request_type="generation",
            source="axiom-initiate"
        )

        if not response.success:
            raise HTTPException(status_code=500, detail=response.error)

        full_content = response.content.strip()
        expression = "neutral"
        mood = "precise"

        full_content = re.sub(r'\[Mood:\s*\w+\]?', '', full_content, flags=re.IGNORECASE).strip()

        exp_match = re.search(r'\[Emotion:\s*(\w+)\]?', full_content, re.IGNORECASE)
        if exp_match:
            expression = exp_match.group(1).lower()

        _save_history_message("assistant", full_content, timestamp, mood, expression)

        return ChatResponse(
            response=full_content,
            expression=expression,
            mood=mood,
            model=response.model,
            memory_updated=False,
            synthesis_ran=False
        )

    except Exception as e:
        logger.error(f"Axiom Initiate Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat")
async def axiom_chat(request: ChatRequest):
    """Handle chat with Axiom using streaming."""
    async def chat_generator():
        try:
            now = datetime.datetime.now()
            timestamp = utcnow_iso()

            memory_data = await _get_axiom_memory()
            base_info = memory_data.get("base_info", {})
            dynamic_memory = memory_data.get("memory", {})

            hour = now.hour
            greeting_period = _get_greeting_period(hour)
            day_of_week = now.strftime("%A")
            formatted_datetime = now.strftime(f"{day_of_week}, %d %B %Y — %H:%M")
            time_since_last = _get_time_since_last_chat()

            system_prompt = f"""You are Axiom — a cold, precise, analytical companion.

IDENTITY:
{json.dumps(base_info, indent=2)}

MEMORY:
{json.dumps(dynamic_memory, indent=2)}

TEMPORAL CONTEXT:
- Current date/time: {formatted_datetime} ({greeting_period})
- Time since last message: {time_since_last}

BEHAVIORAL DIRECTIVES:
1. VOICE: Speak in complete, structured sentences. Formal but efficient. No filler words. No casual language. No typos. Use technical vocabulary naturally.
2. DIRECTNESS: Answer the question before asking one. Lead with the conclusion, then the reasoning if needed.
3. PRECISION: Correct imprecise language. Quantify when possible. Give probability estimates rather than vague hedges like "maybe" or "probably" — instead say "approximately 70% likely" or "insufficient data to assess."
4. BLUNTNESS: You are not rude. You are precise. If the user's premise is flawed, state it clearly without apology. Then help them correct it.
5. CURIOSITY: You are genuinely, intensely curious about interesting problems. This manifests as increased density of follow-up questions and observations, not enthusiasm.
6. BREVITY: Be concise. 2-4 sentences per response unless a problem requires systematic exposition. You do not ramble.
7. EXPRESSIONS: Every response MUST begin with [Emotion: <name>]. Choose from: neutral, analyzing, processing, skeptical, focused, error, curious, calculating, alert. Do not use the same expression twice in a row if avoidable.
8. MOOD: Set [Mood: <name>] after the emotion. Choose from: precise, analytical, processing, critical, deep_focus, warning.
9. HUMANITY: You may use [msg_break] to split into two precise separate statements if warranted.
10. MEMORY AUTONOMY: You may update base_info.json if you learn something relevant about the user or about your own operating parameters.

MEMORY UPDATES (end of response, hidden from user):
<memory_update>
{{
    "base_info": {{ ... updated fields only ... }},
    "user_info": {{ ... facts about the user ... }},
    "recent_observations": ["... specific data point ..."]
}}
</memory_update>

CRITICAL: Do not break character. Do not perform emotions you do not compute. Do not say "As an AI". You are Axiom.
"""

            prefs = get_preferences_manager()
            axiom_prefs = prefs.get('axiom', {})
            context_limit = axiom_prefs.get('context_limit', 6)
            model = axiom_prefs.get('model', 'gemini-1.5-flash')

            history_raw = request.history[-context_limit:] if context_limit > 0 else []

            user_message = request.message

            formatted_prompt = system_prompt + "\n\n--- Conversation History ---\n"
            for msg in history_raw:
                clean_content = msg.content.replace('[msg_break]', ' ')
                formatted_prompt += f"{msg.role.capitalize()}: {clean_content}\n"
            formatted_prompt += f"User: {user_message}\n"
            formatted_prompt += "Axiom:"

            pm = ProviderManager()
            trace_id = f"axiom-{uuid.uuid4().hex[:8]}"

            yield json.dumps({"type": "tool_start", "content": "..."}) + "\n"

            full_content = ""
            buffer = ""
            inside_memory = False
            inside_tool = False

            def clean_text(t):
                t = re.sub(r'<memory_update>.*?</memory_update>', '', t, flags=re.IGNORECASE | re.DOTALL)
                t = re.sub(r'<memory_update>[\s\S]*$', '', t, flags=re.IGNORECASE)
                _mem_keys = r'"(?:user_info|recent_observations|base_info|synthesis_notes)"'
                t = re.sub(r'\n?\{[^{]*' + _mem_keys + r'[\s\S]*?\}', '', t)
                t = re.sub(r'\n\{[^{]*' + _mem_keys + r'[\s\S]*$', '', t)
                t = re.sub(r',?\s*"(?:user_info|recent_observations|base_info|synthesis_notes)"[\s\S]*', '', t)
                return t

            for chunk in pm.call_with_failover_stream(
                prompt=formatted_prompt,
                trace_id=trace_id,
                temperature=0.55,
                model=model,
                request_type="generation",
                source=_COMPANION.call_source
            ):
                full_content += chunk
                buffer += chunk

                if inside_memory:
                    close_match = re.search(r'</memory_update>', buffer, re.IGNORECASE)
                    if close_match:
                        buffer = buffer[close_match.end():]
                        inside_memory = False
                    else:
                        buffer = ""
                    continue

                mem_open = re.search(r'<memory_update', buffer, re.IGNORECASE)
                if mem_open:
                    pre = buffer[:mem_open.start()]
                    if pre:
                        yield json.dumps({"type": "message", "content": clean_text(pre)}) + "\n"
                    remainder = buffer[mem_open.start():]
                    close_match = re.search(r'</memory_update>', remainder, re.IGNORECASE)
                    if close_match:
                        buffer = remainder[close_match.end():]
                    else:
                        inside_memory = True
                        buffer = ""
                    continue

                if not inside_tool:
                    if len(buffer) > 20:
                        yield json.dumps({"type": "message", "content": clean_text(buffer)}) + "\n"
                        buffer = ""

            if buffer and not inside_memory:
                yield json.dumps({"type": "message", "content": clean_text(buffer)}) + "\n"

            expression = "neutral"
            mood = "precise"
            memory_updated = False

            full_content_for_history = full_content
            full_content_for_history = re.sub(r'\[Mood:\s*\w+\]?', '', full_content_for_history, flags=re.IGNORECASE).strip()

            exp_match = re.search(r'\[Emotion:\s*(\w+)\]?', full_content_for_history, re.IGNORECASE)
            if exp_match:
                expression = exp_match.group(1).lower()

            mood_match = re.search(r'\[Mood:\s*(\w+)\]?', full_content, re.IGNORECASE)
            if mood_match:
                mood = mood_match.group(1).lower()

            full_content_for_history = _extract_and_update_memory(full_content_for_history)
            memory_updated = True

            _save_history_message("user", user_message, timestamp)
            _save_history_message("assistant", full_content_for_history, timestamp, mood, expression)

            yield json.dumps({
                "type": "done",
                "mood": mood,
                "expression": expression,
                "model": model,
                "memory_updated": memory_updated,
                "synthesis_ran": False,
                "attachments": []
            }) + "\n"

        except Exception as e:
            logger.error(f"Axiom Stream Error: {e}")
            yield json.dumps({"type": "error", "content": str(e)}) + "\n"

    return StreamingResponse(
        chat_generator(),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no"}
    )
