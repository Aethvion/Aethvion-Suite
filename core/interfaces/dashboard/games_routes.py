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

    # Build conversation: system prompt + history + new message
    session.ai_context.append({"role": "user", "content": user_message})

    # Flatten to a single prompt (most providers support system + user turns via kwargs)
    system_prompt = session._build_system_prompt()
    history_text = ""
    for msg in session.ai_context[:-1]:   # all except the latest
        role = "User" if msg["role"] == "user" else "AI"
        history_text += f"{role}: {msg['content']}\n"

    full_prompt = (
        f"{system_prompt}\n\n"
        f"== CONVERSATION HISTORY ==\n{history_text}\n"
        f"== LATEST USER MESSAGE ==\n{user_message}"
    )

    try:
        pm = ProviderManager()
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: pm.call_with_failover(
                prompt=full_prompt,
                trace_id=f"game-{session.session_id[:8]}",
                temperature=0.8,
                max_tokens=400,
                model=session.model,
                source="game"
            )
        )

        raw = response.content.strip() if response.success else ""

        # Strip optional markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)
        session.ai_context.append({"role": "assistant", "content": raw})
        return {"success": True, "parsed": parsed, "model": response.model or session.model}

    except json.JSONDecodeError as e:
        logger.warning(f"Game AI returned non-JSON: {raw!r} — {e}")
        # Try to salvage a text response
        session.ai_context.append({"role": "assistant", "content": raw})
        return {"success": False, "error": "AI returned malformed JSON", "raw": raw}
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
