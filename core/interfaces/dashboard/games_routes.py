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

async def _call_ai(session: AIGameSession, user_message: str, expected_action: Optional[str] = None) -> Dict[str, Any]:
    """
    Send messages to the AI with 3-retry logic and strict validation.
    """
    from core.providers import ProviderManager

    if len(session.ai_context) > 15:
        session.ai_context = session.ai_context[-15:]

    system_prompt = session._build_system_prompt()
    history_text = ""
    for msg in session.ai_context:
        role = "User" if msg["role"] == "user" else "AI"
        history_text += f"{role}: {msg['content']}\n"

    latest_prompt = (
        f"== HISTORY ==\n{history_text}\n"
        f"== NEW INPUT ==\n{user_message}"
    )

    pm = ProviderManager()
    loop = asyncio.get_event_loop()
    
    max_retries = 3
    last_error = "Unknown error"

    for attempt in range(max_retries):
        try:
            response = await loop.run_in_executor(
                None,
                lambda: pm.call_with_failover(
                    prompt=latest_prompt,
                    system_prompt=system_prompt,
                    trace_id=f"game-{session.session_id[:8]}",
                    temperature=0.1 if attempt == 0 else 0.4 if attempt == 1 else 0.8,
                    max_tokens=600,
                    model=session.model,
                    json_mode=True,   
                    source="game"
                )
            )

            raw = response.content.strip() if response.success else ""
            if not raw:
                last_error = "Empty response"
                continue

            # --- Extraction & Repair ---
            def repair_and_parse(text):
                text = text.strip()
                try: return json.loads(text)
                except: pass
                import re
                match = re.search(r'(\{.*\})', text, re.DOTALL)
                if match:
                    try: return json.loads(match.group(1))
                    except: text = match.group(1)
                repaired = text
                repaired = re.sub(r',\s*$', '', repaired) 
                repaired = re.sub(r',\s*\}', '}', repaired)
                if repaired.count('"') % 2 != 0: repaired += '"'
                open_braces = repaired.count('{') - repaired.count('}')
                if open_braces > 0: repaired += '}' * open_braces
                try: return json.loads(repaired)
                except:
                    if ',' in repaired:
                        last_comma = repaired.rfind(',')
                        try: return json.loads(repaired[:last_comma] + '}')
                        except: pass
                return None

            parsed = repair_and_parse(raw)

            if parsed and isinstance(parsed, dict):
                # Normalize keys and action
                output = parsed.get("output")
                action = parsed.get("action")
                
                if not action:
                    if output is not None: action = "test_result"
                    elif "rule" in parsed: action = "correct"
                    elif "hint" in parsed: action = "hint"
                    parsed["action"] = action

                # STRIKE 1: Explicit check for "?" or empty output for test results
                if expected_action == "test" and (not output or str(output).strip() == "?"):
                    last_error = f"AI returned invalid/empty output: '{output}'"
                    logger.warning(f"[{session.session_id[:8]}] Retry {attempt+1}: {last_error}")
                    continue

                # STRIKE 2: If we expected an action and got nothing relevant
                if expected_action == "test" and action != "test_result":
                    last_error = f"AI returned unexpected action: {action}"
                    continue

                # Success! Persist to context
                session.ai_context.append({"role": "user", "content": user_message})
                session.ai_context.append({"role": "assistant", "content": json.dumps(parsed)})
                return {"success": True, "parsed": parsed, "model": response.model or session.model}

            last_error = "Malformed JSON"
        except Exception as e:
            last_error = str(e)
            logger.warning(f"[{session.session_id[:8]}] Attempt {attempt+1} failed: {last_error}")
            await asyncio.sleep(0.3)

    logger.error(f"[{session.session_id[:8]}] Final failure after {max_retries} attempts. Last RAW: {raw!r}")
    return {"success": False, "error": f"AI Game Master Error: {last_error}"}


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/new")
async def create_game(req: NewGameRequest):
    """Start a new AI-driven game session."""
    manager = get_ai_game_manager()
    session = manager.create_session(req.game_type, req.difficulty, req.model)

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
        
        ai_msg = f"Test input: {input_val}"
        result = await _call_ai(session, ai_msg, expected_action="test")

        if not result["success"]:
            return {"success": False, "error": result.get("error"), "history": session.history}

        session.attempts += 1
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
        
        ai_msg = f"I think the secret rule is: {guess}"
        result = await _call_ai(session, ai_msg, expected_action="guess")

        if not result["success"]:
            return {"success": False, "error": result.get("error"), "history": session.history}

        session.attempts += 1
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
        result = await _call_ai(session, ai_msg, expected_action="hint")

        if not result["success"]:
            return {"success": False, "error": result.get("error")}

        parsed = result["parsed"]
        return {
            "success": True,
            "action": "hint",
            "hint": parsed.get("hint", "The pattern is subtle..."),
        }

    # ── REVEAL ────────────────────────────────────────────────────
    elif action == "reveal":
        ai_msg = "I give up. Reveal the answer."
        result = await _call_ai(session, ai_msg, expected_action="reveal")

        if not result["success"]:
            return {"success": False, "error": result.get("error")}

        parsed = result["parsed"]
        session.completed = True
        return {
            "success": True,
            "action": "reveal",
            "rule": parsed.get("rule", "Rule revealed"),
            "message": parsed.get("message", "Game ended.")
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
