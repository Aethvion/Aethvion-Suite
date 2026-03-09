"""
Misaka Cipher - Games Routes
AI-powered thinking games API.
"""

import uuid
import json
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from .games_logic import get_ai_game_manager, AIGameSession
from core.utils import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/games", tags=["games"])


# ── Request models ─────────────────────────────────────────────────────────────

class NewGameRequest(BaseModel):
    game_type: str
    difficulty: str = "easy"
    model: str = "auto"       # model ID or "auto"

class GameActionRequest(BaseModel):
    session_id: str
    action: str               # "test" | "guess" | "hint"
    data: Dict[str, Any]


# ── Helper: call any model via ProviderManager ──────────────────────────────────

async def _call_ai(session: AIGameSession, user_message: str) -> Dict[str, Any]:
    """
    Send the current conversation plus a new user message to the AI and return
    the parsed JSON response from the game master.
    """
    from core.providers import ProviderManager

    # Manage context length to avoid token bloat (at most last 15 messages)
    if len(session.ai_context) > 15:
        session.ai_context = session.ai_context[-15:]

    system_prompt = session._build_system_prompt()
    history_text = ""
    for msg in session.ai_context[:-1]:
        role = "User" if msg["role"] == "user" else "AI"
        history_text += f"{role}: {msg['content']}\n"

    latest_prompt = (
        f"== HISTORY ==\n{history_text}\n"
        f"== NEW INPUT ==\n{user_message}"
    )

    try:
        pm = ProviderManager()
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: pm.call_with_failover(
                prompt=latest_prompt,
                system_prompt=system_prompt,
                trace_id=f"game-{session.session_id[:8]}",
                temperature=0.1,  
                max_tokens=600,   # 600 is plenty for one JSON object
                model=session.model,
                json_mode=True,   
                source="game"
            )
        )

        raw = response.content.strip() if response.success else ""
        if not raw:
            return {"success": False, "error": "AI returned empty response"}

        # --- High-Resilience JSON Repair ---
        def repair_and_parse(text):
            text = text.strip()
            # 1. Direct try
            try:
                return json.loads(text)
            except:
                pass
            
            # 2. Extract block
            import re
            match = re.search(r'(\{.*\})', text, re.DOTALL)
            if match:
                try: return json.loads(match.group(1))
                except: text = match.group(1)

            # 3. Truncated Repair Logic
            repaired = text
            # Handle trailing comma inside object
            repaired = re.sub(r',\s*$', '', repaired) 
            repaired = re.sub(r',\s*\}', '}', repaired)

            # Close open quotes
            if repaired.count('"') % 2 != 0:
                repaired += '"'
            
            # Balance braces
            open_braces = repaired.count('{') - repaired.count('}')
            if open_braces > 0:
                repaired += '}' * open_braces
            
            # Final attempt
            try:
                return json.loads(repaired)
            except:
                # One last try: remove partial final key-value
                if ',' in repaired:
                    last_comma = repaired.rfind(',')
                    try:
                        return json.loads(repaired[:last_comma] + '}')
                    except:
                        pass
            return None

        parsed = repair_and_parse(raw)

        if parsed and isinstance(parsed, dict):
            # Action inference
            if "action" not in parsed:
                if "output" in parsed: parsed["action"] = "test_result"
                elif "hint" in parsed: parsed["action"] = "hint"
            
            session.ai_context.append({"role": "assistant", "content": json.dumps(parsed)})
            return {"success": True, "parsed": parsed, "model": response.model or session.model}

        logger.error(f"Game AI extraction failed. Raw content: {raw!r}")
        return {"success": False, "error": "AI response structure invalid", "raw": raw}

    except Exception as e:
        logger.error(f"Game AI call failed: {e}")
        return {"success": False, "error": str(e)}


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/new")
async def create_game(req: NewGameRequest):
    """Start a new AI-driven game session."""
    manager = get_ai_game_manager()
    session = manager.create_session(req.game_type, req.difficulty, req.model)

    # Ask AI to initialize the game
    opening = session.get_opening_message()
    result = await _call_ai(session, opening["content"])

    if not result["success"]:
        return {
            "success": False,
            "error": result.get("error", "AI failed to start game"),
            "session_id": session.session_id,
            "hint": "",
            "max_attempts": 10,
            "history": [],
            "model_used": req.model
        }

    parsed = result["parsed"]
    max_attempts = parsed.get("max_attempts", 10 if req.difficulty == "easy" else 6 if req.difficulty == "medium" else 4)

    return {
        "success": True,
        "session_id": session.session_id,
        "hint": parsed.get("hint", ""),
        "max_attempts": max_attempts,
        "history": [],
        "model_used": result.get("model", req.model),
        "difficulty": req.difficulty
    }


@router.post("/action")
async def game_action(req: GameActionRequest):
    """Process a game action (test/guess/hint) through the AI."""
    manager = get_ai_game_manager()
    session = manager.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Game session not found.")

    if session.completed:
        return {"success": False, "error": "Game is already over. Start a new game."}

    action = req.action
    data = req.data

    # ── TEST ──────────────────────────────────────────────────────
    if action == "test":
        input_val = str(data.get("input", ""))
        session.attempts += 1

        ai_msg = f"Test input: {input_val}"
        result = await _call_ai(session, ai_msg)

        if not result["success"]:
            return {"success": False, "error": result.get("error"), "history": session.history}

        parsed = result["parsed"]
        output = parsed.get("output", "?")
        comment = parsed.get("comment", "")

        session.history.append({"input": input_val, "output": output})

        return {
            "success": True,
            "action": "test_result",
            "output": output,
            "comment": comment,
            "attempts": session.attempts,
            "history": session.history,
        }

    # ── GUESS ─────────────────────────────────────────────────────
    elif action == "guess":
        guess = str(data.get("guess", ""))
        session.attempts += 1

        ai_msg = f"I think the secret rule is: {guess}"
        result = await _call_ai(session, ai_msg)

        if not result["success"]:
            return {"success": False, "error": result.get("error"), "history": session.history}

        parsed = result["parsed"]
        action_type = parsed.get("action", "wrong")

        if action_type == "correct":
            session.completed = True
            session.score = max(100 - (session.attempts * 8), 10)
            return {
                "success": True,
                "action": "correct",
                "correct": True,
                "rule": parsed.get("rule", guess),
                "message": parsed.get("message", "Correct!"),
                "score": session.score,
                "attempts": session.attempts,
                "history": session.history,
            }
        else:
            return {
                "success": True,
                "action": "wrong",
                "correct": False,
                "message": parsed.get("message", "Not quite. Keep testing."),
                "attempts": session.attempts,
                "history": session.history,
            }

    # ── HINT ──────────────────────────────────────────────────────
    elif action == "hint":
        ai_msg = "Give me a hint please."
        result = await _call_ai(session, ai_msg)

        if not result["success"]:
            return {"success": False, "error": result.get("error")}

        parsed = result["parsed"]
        return {
            "success": True,
            "action": "hint",
            "hint": parsed.get("hint", "The pattern is subtle..."),
        }

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """Get the current state of a game session."""
    manager = get_ai_game_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Game session not found.")

    return {
        "success": True,
        "session_id": session_id,
        "history": session.history,
        "attempts": session.attempts,
        "completed": session.completed,
        "score": session.score,
    }


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a game session."""
    manager = get_ai_game_manager()
    manager.delete_session(session_id)
    return {"success": True}


@router.get("/models")
async def get_available_models():
    """Return list of available models for game selection."""
    try:
        from core.providers import ProviderManager
        pm = ProviderManager()
        models = [{"id": mid, "provider": info.get("provider", ""), "description": info.get("description", "")}
                  for mid, info in pm.model_descriptor_map.items()
                  if "chat" in info.get("capabilities", [])]
        return {"success": True, "models": [{"id": "auto", "provider": "auto", "description": "Auto-select best model"}] + models}
    except Exception as e:
        return {"success": False, "error": str(e), "models": [{"id": "auto", "provider": "auto", "description": "Auto"}]}
