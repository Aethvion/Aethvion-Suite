"""
Aethvion Suite - Arena Routes
API endpoints for the Arena Mode (model comparison battles)
"""

import json
import uuid
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import time

from core.utils import get_logger, atomic_json_write
from core.utils.paths import APP_ARENA, HISTORY_AI_CONV
from core.ai.call_contexts import CallSource

logger = get_logger(__name__)

router = APIRouter(prefix="/api/arena", tags=["arena"])

ARENA_SYSTEM_PROMPT = (
    "You are an AI model participating in a blind benchmark evaluation. "
    "Multiple AI models are answering the same prompt simultaneously and will be judged on "
    "accuracy, clarity, helpfulness, and completeness. "
    "Answer the user's prompt directly and to the best of your ability. "
    "Do not introduce yourself, do not adopt any persona, and do not mention this evaluation context."
)
LEADERBOARD_FILE = APP_ARENA / "leaderboard.json"
AICONV_DIR = HISTORY_AI_CONV


class ArenaBattleRequest(BaseModel):
    """Arena battle request."""
    prompt: str
    model_ids: List[str]
    evaluator_model_id: Optional[str] = None


def _load_leaderboard() -> Dict[str, Any]:
    """Load leaderboard from disk."""
    try:
        if LEADERBOARD_FILE.exists():
            with open(LEADERBOARD_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load leaderboard: {e}")
    return {"models": {}}


def _save_leaderboard(data: Dict[str, Any]) -> None:
    """Save leaderboard to disk."""
    atomic_json_write(LEADERBOARD_FILE, data)


async def _call_model(provider_manager, prompt: str, model_id: str, trace_id: str):
    """Call a single model and return result dict with timing."""
    start_time = time.time()
    try:
        response = await asyncio.to_thread(
            provider_manager.call_with_failover,
            prompt=prompt,
            trace_id=trace_id,
            model=model_id,
            source=CallSource.ARENA,
            system_prompt=ARENA_SYSTEM_PROMPT
        )
        end_time = time.time()
        return {
            "model_id": model_id,
            "response": response.content if response.success else f"Error: {response.error}",
            "provider": response.provider,
            "success": response.success,
            "score": None,
            "time_ms": int((end_time - start_time) * 1000)
        }
    except Exception as e:
        end_time = time.time()
        logger.error(f"Arena call failed for {model_id}: {e}")
        return {
            "model_id": model_id,
            "response": f"Error: {str(e)}",
            "provider": "unknown",
            "success": False,
            "score": None,
            "time_ms": int((end_time - start_time) * 1000)
        }


async def _evaluate_responses(provider_manager, prompt: str, responses: List[Dict], evaluator_model_id: str, trace_id: str) -> List[Dict]:
    """Use evaluator model to score all responses."""
    # Build evaluation prompt
    eval_prompt = f"""You are an AI response evaluator. Score each response to the following prompt on a scale of 1-10.

ORIGINAL PROMPT: {prompt}

"""
    for i, r in enumerate(responses):
        if r["success"]:
            eval_prompt += f"--- RESPONSE {i+1} (Model: {r['model_id']}) ---\n{r['response']}\n\n"

    eval_prompt += """Score each response from 1-10 based on accuracy, helpfulness, clarity, and completeness.
Respond ONLY with a JSON array of objects like: [{"model_id": "...", "score": N, "reasoning": "Quick logic on why this score was given"}]
No other text. Just the JSON array."""

    try:
        eval_response = await asyncio.to_thread(
            provider_manager.call_with_failover,
            prompt=eval_prompt,
            trace_id=f"{trace_id}_eval",
            model=evaluator_model_id,
            source=CallSource.ARENA
        )

        if eval_response.success:
            # Parse scores and reasoning from response
            content = eval_response.content.strip()
            # Try to extract JSON from response
            start = content.find('[')
            end = content.rfind(']') + 1
            if start >= 0 and end > start:
                scores = json.loads(content[start:end])
                score_map = {s["model_id"]: s for s in scores}
                for r in responses:
                    if r["model_id"] in score_map:
                        eval_data = score_map[r["model_id"]]
                        r["score"] = eval_data.get("score")
                        r["reasoning"] = eval_data.get("reasoning")
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")

    return responses


@router.post("/battle_stream")
async def arena_battle_stream(request: ArenaBattleRequest, req: Request):
    """Run an arena battle and stream results back via Server-Sent Events as models finish."""
    if len(request.model_ids) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 models for a battle")

    nexus = getattr(req.app.state, 'nexus', None)
    if not nexus:
        raise HTTPException(status_code=503, detail="System not initialized")
    provider_manager = nexus.provider_manager

    trace_id = f"ARENA_{uuid.uuid4().hex[:8]}"

    async def event_generator():
        # Yield initial state
        yield f"data: {json.dumps({'type': 'start', 'trace_id': trace_id, 'prompt': request.prompt})}\n\n"
        
        # Start all tasks
        tasks = [
            asyncio.create_task(_call_model(provider_manager, request.prompt, model_id, trace_id))
            for model_id in request.model_ids
        ]
        
        responses = []
        leaderboard = _load_leaderboard()
        models_data = leaderboard.get("models", {})
        
        # Stream results as they complete using as_completed
        for completed_task in asyncio.as_completed(tasks):
            try:
                result = await completed_task
                responses.append(result)
                
                # Update battles count for this model early
                mid = result["model_id"]
                if mid not in models_data:
                    models_data[mid] = {"wins": 0, "battles": 0, "failures": 0, "total_time_ms": 0, "scores_total": 0, "scores_count": 0}
                # Ensure legacy entries have new fields
                for field in ("failures", "total_time_ms", "scores_total", "scores_count"):
                    models_data[mid].setdefault(field, 0)
                models_data[mid]["battles"] += 1
                models_data[mid]["total_time_ms"] += result.get("time_ms", 0) or 0
                if not result["success"]:
                    models_data[mid]["failures"] += 1
                
                # Yield this specific result
                yield f"data: {json.dumps({'type': 'result', 'data': result})}\n\n"
            except Exception as e:
                logger.error(f"Error yielding task result: {e}")
                
        # Save updated battles counts
        leaderboard["models"] = models_data
        _save_leaderboard(leaderboard)
        
        # Yield final complete state with updated leaderboard
        yield f"data: {json.dumps({'type': 'complete', 'responses': responses, 'leaderboard': models_data})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class ArenaEvaluateRequest(BaseModel):
    """Request to evaluate an already completed battle."""
    prompt: str
    responses: List[Dict[str, Any]]
    evaluator_model_id: str
    trace_id: str

@router.post("/evaluate_battle")
async def evaluate_battle(request: ArenaEvaluateRequest, req: Request):
    """Evaluate an existing set of arena responses."""
    try:
        nexus = getattr(req.app.state, 'nexus', None)
        if not nexus:
            raise HTTPException(status_code=503, detail="System not initialized")
        provider_manager = nexus.provider_manager

        responses = await _evaluate_responses(
            provider_manager, request.prompt, request.responses,
            request.evaluator_model_id, request.trace_id
        )

        # Determine winner
        winner_id = None
        scored = [r for r in responses if r.get("score") is not None and r.get("success")]
        if scored:
            winner = max(scored, key=lambda r: r["score"])
            winner_id = winner["model_id"]

        # Update wins in leaderboard
        leaderboard = _load_leaderboard()
        models_data = leaderboard.get("models", {})

        # Update scores and wins in leaderboard
        for r in responses:
            mid = r["model_id"]
            if mid not in models_data:
                models_data[mid] = {"wins": 0, "battles": 0, "failures": 0, "total_time_ms": 0, "scores_total": 0, "scores_count": 0}
            for field in ("failures", "total_time_ms", "scores_total", "scores_count"):
                models_data[mid].setdefault(field, 0)
            if r.get("score") is not None and r.get("success"):
                models_data[mid]["scores_total"] += r["score"]
                models_data[mid]["scores_count"] += 1

        if winner_id:
            if winner_id not in models_data:
                models_data[winner_id] = {"wins": 0, "battles": 0, "failures": 0, "total_time_ms": 0, "scores_total": 0, "scores_count": 0}
            models_data[winner_id]["wins"] += 1

        leaderboard["models"] = models_data
        _save_leaderboard(leaderboard)

        return {
            "responses": list(responses),
            "winner_id": winner_id,
            "leaderboard": models_data
        }

    except Exception as e:
        logger.error(f"Arena evaluation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leaderboard")
async def get_leaderboard():
    """Get the arena leaderboard."""
    return _load_leaderboard()


@router.delete("/leaderboard")
async def clear_leaderboard():
    """Clear the arena leaderboard."""
    _save_leaderboard({"models": {}})
    return {"status": "success", "message": "Leaderboard cleared"}


class DeclareWinnerRequest(BaseModel):
    """Request to manually declare a winner."""
    winner_model_id: str
    participant_model_ids: List[str]


@router.post("/declare_winner")
async def declare_winner(request: DeclareWinnerRequest):
    """Manually declare a winner when no evaluator was used."""
    try:
        leaderboard = _load_leaderboard()
        models_data = leaderboard.get("models", {})

        # Only update wins here — battles were already counted in battle_stream
        for mid in request.participant_model_ids:
            if mid not in models_data:
                models_data[mid] = {"wins": 0, "battles": 0, "failures": 0, "total_time_ms": 0, "scores_total": 0, "scores_count": 0}
            for field in ("failures", "total_time_ms", "scores_total", "scores_count"):
                models_data[mid].setdefault(field, 0)
        if request.winner_model_id in models_data:
            models_data[request.winner_model_id]["wins"] += 1

        leaderboard["models"] = models_data
        _save_leaderboard(leaderboard)

        return {
            "status": "success", 
            "winner_id": request.winner_model_id,
            "leaderboard": models_data
        }

    except Exception as e:
        logger.error(f"Failed to declare winner: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class AIConvTurnRequest(BaseModel):
    """Request for a single turn in AI Conversation."""
    model_id: str
    system_prompt: Optional[str] = None
    messages: List[Dict[str, str]] # History of the conversation including current prompt


class AIConvSaveRequest(BaseModel):
    """Request to save a conversation snapshot."""
    id: Optional[str] = None
    name: str
    topic: str
    participants: List[Dict[str, Any]]
    messageHistory: List[Dict[str, Any]]
    stats: Optional[Dict[str, Any]] = None


class AIConvRenameRequest(BaseModel):
    name: str


@router.post("/aiconv/generate")
async def aiconv_generate(request: AIConvTurnRequest, req: Request):
    """Generate a single turn for AI Conversations."""
    try:
        nexus = getattr(req.app.state, 'nexus', None)
        if not nexus:
            raise HTTPException(status_code=503, detail="System not initialized")
        provider_manager = nexus.provider_manager

        trace_id = f"AICONV_{uuid.uuid4().hex[:8]}"
        
        # Since call_with_failover usually takes a single string prompt, we construct it:
        full_prompt = ""
        if request.system_prompt:
            full_prompt += f"{request.system_prompt}\n\n"
            
        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            name = msg.get("name")
            
            if name:
                full_prompt += f"[{name}]: {content}\n\n"
            else:
                full_prompt += f"[{role.capitalize()}]: {content}\n\n"

        response = await asyncio.to_thread(
            provider_manager.call_with_failover,
            prompt=full_prompt,
            trace_id=trace_id,
            model=request.model_id,
            source=CallSource.AICONV
        )
        
        return {
            "model_id": request.model_id,
            "response": response.content if response.success else f"Error: {response.error}",
            "provider": response.provider,
            "success": response.success,
            "usage": response.metadata.get("usage", {}) if response.metadata else {}
        }

    except Exception as e:
        logger.error(f"AI Conv generate error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── AI Conversation History ────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get("/aiconv/conversations")
async def list_aiconv_conversations():
    """List all saved AI conversations, newest first."""
    AICONV_DIR.mkdir(parents=True, exist_ok=True)
    convs = []
    for f in sorted(AICONV_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            convs.append({
                "id":                data["id"],
                "name":              data.get("name", "Untitled"),
                "topic":             data.get("topic", ""),
                "created":           data.get("created", ""),
                "updated":           data.get("updated", ""),
                "message_count":     len([m for m in data.get("messageHistory", []) if m.get("role") != "system"]),
                "participant_count": len(data.get("participants", []))
            })
        except Exception:
            pass
    return {"conversations": convs}


@router.post("/aiconv/conversations")
async def save_aiconv_conversation(req: AIConvSaveRequest):
    """Create or update a saved AI conversation."""
    AICONV_DIR.mkdir(parents=True, exist_ok=True)
    conv_id = req.id or uuid.uuid4().hex[:8]
    now = _now_iso()
    path = AICONV_DIR / f"{conv_id}.json"

    created = now
    if path.exists():
        try:
            created = json.loads(path.read_text(encoding="utf-8")).get("created", now)
        except Exception:
            pass

    data = {
        "id":             conv_id,
        "name":           req.name,
        "topic":          req.topic,
        "created":        created,
        "updated":        now,
        "participants":   req.participants,
        "messageHistory": req.messageHistory,
        "stats":          req.stats or {}
    }
    atomic_json_write(path, data)
    return {"id": conv_id, "updated": now}


@router.get("/aiconv/conversations/{conv_id}")
async def get_aiconv_conversation(conv_id: str):
    """Load a saved AI conversation by ID."""
    path = AICONV_DIR / f"{conv_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Conversation not found")
    return json.loads(path.read_text(encoding="utf-8"))


@router.delete("/aiconv/conversations/{conv_id}")
async def delete_aiconv_conversation(conv_id: str):
    """Delete a saved AI conversation."""
    path = AICONV_DIR / f"{conv_id}.json"
    if path.exists():
        path.unlink()
    return {"status": "ok"}


@router.put("/aiconv/conversations/{conv_id}/name")
async def rename_aiconv_conversation(conv_id: str, req: AIConvRenameRequest):
    """Rename a saved AI conversation."""
    path = AICONV_DIR / f"{conv_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Conversation not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["name"] = req.name
    data["updated"] = _now_iso()
    atomic_json_write(path, data)
    return {"status": "ok"}
