"""
Misaka Cipher - Games Routes
AI-powered thinking games API.
"""

import re
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
            # Fallback: On the very last attempt, disable JSON mode in case the constraint is causing truncation
            use_json_mode = True
            if attempt == max_retries - 1:
                use_json_mode = False

            response = await loop.run_in_executor(
                None,
                lambda: pm.call_with_failover(
                    prompt=latest_prompt,
                    system_prompt=system_prompt,
                    trace_id=f"game-{session.session_id[:8]}",
                    temperature=0.7 if attempt == 0 else 0.85 if attempt == 1 else 1.0,
                    max_tokens=1024,
                    model=session.model,
                    json_mode=use_json_mode,   
                    source="game"
                )
            )

            raw = response.content.strip() if response.success else ""
            logger.info(f"[{session.session_id[:8]}] RAW AI CONTENT (Attempt {attempt+1}, JSON_MODE={use_json_mode}): {raw!r}")
            if not raw:
                last_error = "Empty response"
                continue

            # --- Extraction & Repair ---
            def repair_and_parse(text):
                text = text.strip()
                # If JSON mode was off, it might be wrapped in markdown
                if "```json" in text:
                    match = re.search(r'```json\s*(\{.*\})\s*```', text, re.DOTALL)
                    if match: text = match.group(1).strip()

                try: return json.loads(text)
                except: pass
                
                # Regex block extraction
                match = re.search(r'(\{.*\})', text, re.DOTALL)
                if match:
                    try: return json.loads(match.group(1))
                    except: text = match.group(1)

                repaired = text
                # Repair incomplete lists
                if repaired.count('[') > repaired.count(']'):
                    repaired = re.sub(r'\{\s*"rank":.*$', '', repaired).strip()
                    repaired = re.sub(r',\s*$', '', repaired)
                    repaired += ']'
                
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
                output = parsed.get("output")
                action = parsed.get("action")
                
                # Auto-infer action
                if not action:
                    if output is not None: action = "test_result"
                    elif "player_hand" in parsed: action = "dealt"
                    elif "rule" in parsed: action = "correct"
                    elif "hint" in parsed: action = "hint"
                    parsed["action"] = action

                # VALIDATION: Essential keys for Blackjack
                if session.game_type == "blackjack":
                    p_hand = parsed.get("player_hand")
                    a_hand = parsed.get("ai_hand")
                    if not p_hand or not isinstance(p_hand, list) or len(p_hand) == 0:
                        last_error = "Missing or empty player_hand"
                        continue
                    if not a_hand or not isinstance(a_hand, list) or len(a_hand) == 0:
                        last_error = "Missing or empty ai_hand"
                        continue

                # Success!
                logger.info(f"[{session.session_id[:8]}] AI Game Master response parsed successfully. Action: {action}")
                session.ai_context.append({"role": "user", "content": user_message})
                session.ai_context.append({"role": "assistant", "content": json.dumps(parsed)})
                return {"success": True, "parsed": parsed, "model": response.model or session.model}

            last_error = "Malformed or incomplete JSON structure"
        except Exception as e:
            last_error = str(e)
            logger.warning(f"[{session.session_id[:8]}] Attempt {attempt+1} failed: {last_error}")
            await asyncio.sleep(0.3)

    logger.error(f"[{session.session_id[:8]}] Final failure after {max_retries} attempts.")
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
    
    # Base response
    resp = {
        "success": True,
        "session_id": session.session_id,
        "model_used": result.get("model", req.model),
        "difficulty": req.difficulty
    }
    
    # Merge AI fields
    resp.update(parsed)
    
    # Update session status
    if parsed.get("completed"):
        session.completed = True
        session.result = parsed.get("result")
    
    # Save initial session state
    session.save_history()
    
    return resp


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
        session.save_history()

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
            session.history.append({"action": "guess", "guess": guess, "result": "correct"})
            session.completed = True
            session.result = "win" # Logic Quest guess is always a win if correct
            session.score = max(100 - (session.attempts * 8), 10)
            session.save_history()
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
            session.history.append({"action": "guess", "guess": guess, "result": "wrong"})
            session.save_history()
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
        session.save_history()
        return {
            "success": True,
            "action": "hint",
            "hint": parsed.get("hint", parsed.get("message", "The dealer looks confident...")),
            **parsed
        }

    # ── REVEAL ────────────────────────────────────────────────────
    elif action == "reveal":
        ai_msg = "I give up. Reveal the answer."
        result = await _call_ai(session, ai_msg, expected_action="reveal")

        if not result["success"]:
            return {"success": False, "error": result.get("error")}

        parsed = result["parsed"]
        session.completed = True
        session.save_history()
        return {
            "success": True,
            "action": "reveal",
            "rule": parsed.get("rule", "Rule revealed"),
            "message": parsed.get("message", "Game ended."),
            **parsed # Include any extra fields like final hands
        }

    # ── DRAW (Generic / Card Specific) ────────────────────────────
    elif action == "draw":
        ai_msg = "I want to draw a card."
        result = await _call_ai(session, ai_msg, expected_action="draw_result")
        if not result["success"]: return {"success": False, "error": result["error"]}
        
        parsed = result["parsed"]
        if parsed.get("completed"):
            session.completed = True
            session.result = parsed.get("result")
        session.save_history()
        return {"success": True, **parsed}

    # ── STAY (Generic / Card Specific) ────────────────────────────
    elif action == "stay":
        ai_msg = "I stay. Dealer's turn."
        result = await _call_ai(session, ai_msg, expected_action="stay_result")
        if not result["success"]: return {"success": False, "error": result["error"]}
        
        parsed = result["parsed"]
        if parsed.get("completed"):
            session.completed = True
            session.result = parsed.get("result")
        session.save_history()
        return {"success": True, **parsed}

    # ── CATCH-ALL FOR NEW GAMES ──────────────────────────────────
    else:
        # Just pass the action and data as a message to the AI
        ai_msg = f"ACTION: {action}, DATA: {json.dumps(data)}"
        result = await _call_ai(session, ai_msg)
        if not result["success"]: return {"success": False, "error": result["error"]}
        
        parsed = result["parsed"]
        if parsed.get("completed"):
            session.completed = True
            session.result = parsed.get("result")
        session.save_history()
        return {"success": True, **parsed}


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


@router.get("/stats")
async def get_game_stats():
    """Retrieve statistics and history for all games."""
    try:
        from pathlib import Path
        root = Path(__file__).parent.parent.parent.parent
        storage_dir = root / "data" / "memory" / "storage" / "games"
        
        stats = {
            "total_games": 0,
            "wins": 0,
            "losses": 0,
            "game_types": {}
        }
        recent_games = []

        if storage_dir.exists():
            for game_type_dir in storage_dir.iterdir():
                if game_type_dir.is_dir():
                    history_file = game_type_dir / "history.json"
                    if history_file.exists():
                        try:
                            with open(history_file, 'r', encoding='utf-8') as f:
                                history = json.load(f)
                            
                            type_stats = {"total": 0, "wins": 0, "losses": 0, "pushes": 0}
                            for entry in history:
                                if not entry.get("completed"): continue
                                
                                type_stats["total"] += 1
                                stats["total_games"] += 1
                                
                                res = entry.get("result")
                                if res == "win":
                                    type_stats["wins"] += 1
                                    stats["wins"] += 1
                                elif res == "loss":
                                    type_stats["losses"] += 1
                                    stats["losses"] += 1
                                elif res == "push":
                                    type_stats["pushes"] += 1
                                # Fallback if result is missing but it's completed (for legacy/logic-quest)
                                elif entry.get("game_type") == "logic-quest":
                                    type_stats["wins"] += 1
                                    stats["wins"] += 1

                                recent_games.append({
                                    "id": entry.get("session_id", "")[:8],
                                    "type": entry.get("game_type", ""),
                                    "result": res or "completed",
                                    "score": entry.get("score", 0),
                                    "date": entry.get("created_at") or entry.get("updated_at", "")
                                })
                            
                            stats["game_types"][game_type_dir.name] = type_stats
                        except:
                            continue

        # Sort recent games and take last 10
        recent_games.sort(key=lambda x: x["date"], reverse=True)
        recent_games = recent_games[:10]

        return {
            "success": True,
            "stats": stats,
            "recent": recent_games
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/stats/{game_type}")
async def clear_game_history(game_type: str):
    """Clear memory history for a specific game."""
    try:
        from pathlib import Path
        root = Path(__file__).parent.parent.parent.parent
        history_file = root / "data" / "memory" / "storage" / "games" / game_type / "history.json"
        
        if history_file.exists():
            history_file.unlink()
            return {"success": True, "message": f"History for {game_type} cleared."}
        return {"success": False, "error": "History file not found."}
    except Exception as e:
        return {"success": False, "error": str(e)}

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


# ── Word Search AI Generation ──────────────────────────────────────────────────

class WordSearchGenerateRequest(BaseModel):
    topic: str
    count: int = 15
    model: str = "auto"


@router.post("/word-search/generate")
async def generate_word_search(req: WordSearchGenerateRequest):
    """
    Generate a themed word list for Word Search using AI.
    Returns a list of uppercase words (4–15 letters) related to the given topic.
    """
    from core.providers import ProviderManager

    topic = req.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic cannot be empty.")

    count = max(8, min(req.count, 30))  # clamp between 8 and 30

    # Ask explicitly for {"words": [...]} so the key is always predictable.
    # json_mode is intentionally OFF — it forces providers to return an object
    # with a model-chosen key name, making reliable extraction harder.
    system_prompt = (
        "You are a word search puzzle generator. "
        'Respond with ONLY a JSON object in this exact format: {"words": ["WORD1", "WORD2", ...]}. '
        "Words must be uppercase, 4-15 letters, A-Z only (no spaces, hyphens, or numbers). "
        "No explanation, no markdown, no extra keys."
    )
    prompt = (
        f'Generate exactly {count} words for a word search puzzle with the theme: "{topic}". '
        f'Return ONLY: {{"words": ["EXAMPLE", "WORDS", "HERE"]}}'
    )

    pm = ProviderManager()
    loop = asyncio.get_event_loop()

    try:
        response = await loop.run_in_executor(
            None,
            lambda: pm.call_with_failover(
                prompt=prompt,
                system_prompt=system_prompt,
                trace_id="word-search-gen",
                temperature=0.8,
                max_tokens=2048,
                model=req.model,
                json_mode=False,
                source="game"
            )
        )

        if not response.success:
            raise HTTPException(status_code=502, detail="AI provider failed to respond.")

        raw = response.content.strip() if response.content else ""
        logger.info(f"[word-search-gen] Raw response for '{topic}': {raw!r}")

        if not raw:
            raise HTTPException(status_code=502, detail="AI returned an empty response.")

        # ── Step 1: strip markdown code fences if present ──
        fenced = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
        if fenced:
            raw = fenced.group(1).strip()

        # ── Step 2: try direct JSON parse ──
        words = None
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                words = parsed
            elif isinstance(parsed, dict):
                # Check "words" first, then scan all values for the first list
                if isinstance(parsed.get("words"), list):
                    words = parsed["words"]
                else:
                    for v in parsed.values():
                        if isinstance(v, list) and len(v) > 0:
                            words = v
                            break
        except Exception:
            pass

        # ── Step 3: rescue truncated JSON — extract all double-quoted uppercase words ──
        # Handles responses cut off mid-array: {"words": ["NARUTO", "BLEACH", "DRAGON...
        if words is None:
            quoted = re.findall(r'"([A-Z]{4,15})"', raw)
            if len(quoted) >= 5:
                words = quoted
                logger.info(f"[word-search-gen] Rescued {len(quoted)} words from truncated JSON")

        # ── Step 4: find any complete JSON array in the text ──
        if words is None:
            for m in re.finditer(r'\[[\s\S]*?\]', raw):
                try:
                    candidate = json.loads(m.group(0))
                    if isinstance(candidate, list) and len(candidate) > 0:
                        words = candidate
                        break
                except Exception:
                    continue

        # ── Step 4: last resort — extract bare uppercase words from the text ──
        # Handles responses like "Here are your words: PLANET, GALAXY, NEBULA, ..."
        if words is None:
            bare = re.findall(r'\b([A-Z]{4,15})\b', raw)
            if len(bare) >= 5:
                words = bare
                logger.info(f"[word-search-gen] Used bare-word fallback, found {len(bare)} words")

        if not words or not isinstance(words, list):
            snippet = raw[:300].replace('\n', ' ')
            raise HTTPException(
                status_code=502,
                detail=f"Could not parse word list from AI response. Raw: {snippet!r}"
            )

        # ── Step 5: sanitise ──
        seen = set()
        clean = []
        for w in words:
            w = re.sub(r'[^A-Z]', '', str(w).upper())
            if 4 <= len(w) <= 15 and w not in seen:
                seen.add(w)
                clean.append(w)

        if len(clean) < 5:
            snippet = raw[:200].replace('\n', ' ')
            raise HTTPException(
                status_code=502,
                detail=f"Only {len(clean)} valid words found. Raw: {snippet!r}"
            )

        logger.info(f"[word-search-gen] Generated {len(clean)} words for topic '{topic}'")
        return {
            "success": True,
            "words": clean,
            "topic": topic,
            "model_used": response.model or req.model
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Word search generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
