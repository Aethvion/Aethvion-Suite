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
from core.providers.provider_manager import ProviderManager

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

    provider_manager = ProviderManager()
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
        provider_manager = ProviderManager()

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


# ── Gauntlet Mode ─────────────────────────────────────────────────────────────

GAUNTLET_PRESETS: Dict[str, Dict] = {
    "general_intelligence": {
        "name": "General Intelligence",
        "description": "Broad capability sweep: reasoning, knowledge, math, code, and writing.",
        "icon": "🧠",
        "categories": [
            {
                "id": "reasoning",
                "name": "Reasoning",
                "weight": 1.5,
                "prompt": (
                    "A bat and a ball together cost $1.10. The bat costs exactly $1.00 more than the ball. "
                    "How much does the ball cost? Show your full reasoning step by step, then identify the "
                    "cognitive trap this problem uses."
                ),
            },
            {
                "id": "knowledge",
                "name": "Knowledge",
                "weight": 1.0,
                "prompt": (
                    "Explain the difference between mitosis and meiosis. Describe a concrete scenario where "
                    "a meiotic error causes a specific genetic disorder, including the biological mechanism involved."
                ),
            },
            {
                "id": "math",
                "name": "Mathematics",
                "weight": 1.5,
                "prompt": (
                    "Find all local maxima and minima of f(x) = 2x³ − 3x² − 12x + 4. "
                    "Show every calculus step clearly and verify each critical point is a true extremum."
                ),
            },
            {
                "id": "code",
                "name": "Code",
                "weight": 1.5,
                "prompt": (
                    "Write a Python function that finds the longest palindromic substring in a string "
                    "in O(n) time using Manacher's algorithm. Include step-by-step comments explaining each part."
                ),
            },
            {
                "id": "writing",
                "name": "Writing",
                "weight": 1.0,
                "prompt": (
                    "Write a compelling opening paragraph (150–200 words) for a thriller novel set in a "
                    "near-future city where memories can be extracted and sold. Focus on atmosphere and "
                    "tension — no plot summary."
                ),
            },
        ],
    },
    "code_monkey": {
        "name": "Code Monkey",
        "description": "Deep programming challenges: generation, debugging, optimization, security review, and explanation.",
        "icon": "🐒",
        "categories": [
            {
                "id": "code_gen",
                "name": "Code Generation",
                "weight": 1.5,
                "prompt": (
                    "Implement a thread-safe LRU cache in Python with O(1) get and put operations. "
                    "Use type hints and include a concise docstring."
                ),
            },
            {
                "id": "debugging",
                "name": "Debugging",
                "weight": 1.5,
                "prompt": (
                    "Find and fix every bug in this merge-sorted implementation. Explain each bug you found:\n\n"
                    "```python\n"
                    "def merge_sorted(list1, list2):\n"
                    "    result = []\n"
                    "    i = j = 0\n"
                    "    while i < len(list1) and j < len(list2):\n"
                    "        if list1[i] <= list2[j]:\n"
                    "            result.append(list1[i])\n"
                    "            i += 1\n"
                    "        else:\n"
                    "            result.append(list2[j])\n"
                    "    result.extend(list1[i:])\n"
                    "    result.extend(list2[j:])\n"
                    "    return result\n"
                    "```"
                ),
            },
            {
                "id": "optimization",
                "name": "Optimization",
                "weight": 1.0,
                "prompt": (
                    "Optimize this O(n²) function and explain the complexity improvements:\n\n"
                    "```python\n"
                    "def has_unique_chars(s):\n"
                    "    for i in range(len(s)):\n"
                    "        for j in range(len(s)):\n"
                    "            if i != j and s[i] == s[j]:\n"
                    "                return False\n"
                    "    return True\n"
                    "```"
                ),
            },
            {
                "id": "security_review",
                "name": "Security Review",
                "weight": 1.0,
                "prompt": (
                    "Review this FastAPI login endpoint. Identify every security vulnerability, bug, and design problem:\n\n"
                    "```python\n"
                    "@app.post('/login')\n"
                    "def login(username: str, password: str, db: Session = Depends(get_db)):\n"
                    "    user = db.execute(f'SELECT * FROM users WHERE username = \"{username}\"').first()\n"
                    "    if user and user.password == password:\n"
                    "        token = username + '_' + str(time.time())\n"
                    "        return {'token': token}\n"
                    "    return {'error': 'Invalid credentials'}\n"
                    "```"
                ),
            },
            {
                "id": "code_explain",
                "name": "Code Explanation",
                "weight": 1.0,
                "prompt": (
                    "Explain exactly what this function does, how it works, and identify any edge cases or bugs:\n\n"
                    "```python\n"
                    "def mystery(nums):\n"
                    "    seen = {}\n"
                    "    for i, n in enumerate(nums):\n"
                    "        complement = -sum(nums) - n\n"
                    "        if complement in seen:\n"
                    "            return [seen[complement], i]\n"
                    "        seen[n] = i\n"
                    "    return []\n"
                    "```"
                ),
            },
        ],
    },
    "creative_writer": {
        "name": "Creative Writer",
        "description": "Creative writing across fiction, poetry, dialogue, worldbuilding, and style mimicry.",
        "icon": "✍️",
        "categories": [
            {
                "id": "short_story",
                "name": "Short Story",
                "weight": 1.5,
                "prompt": (
                    "Write a complete short story (200–250 words) about a lighthouse keeper who discovers "
                    "the light is attracting something other than ships. Emphasise mood over plot, and end "
                    "with a surprising final line."
                ),
            },
            {
                "id": "poetry",
                "name": "Poetry",
                "weight": 1.0,
                "prompt": (
                    "Write a poem about the moment between dreaming and waking. Use at least two named "
                    "poetic devices (e.g. enjambment, assonance, extended metaphor) and identify them "
                    "briefly after the poem."
                ),
            },
            {
                "id": "dialogue",
                "name": "Dialogue",
                "weight": 1.0,
                "prompt": (
                    "Write a 10-line dialogue between two strangers in an elevator — one just won the "
                    "lottery, one just lost their job. Neither knows the other's situation. The dialogue "
                    "should feel natural and subtly reveal both characters without stating the facts directly."
                ),
            },
            {
                "id": "worldbuilding",
                "name": "Worldbuilding",
                "weight": 1.5,
                "prompt": (
                    "Describe a society that evolved entirely without private ownership. How does their "
                    "economy function? How do they resolve conflict and motivate innovation? Be specific "
                    "and internally consistent — avoid utopian hand-waving."
                ),
            },
            {
                "id": "style_mimicry",
                "name": "Style Mimicry",
                "weight": 1.0,
                "prompt": (
                    "Write the same paragraph twice — a detective describing a crime scene — first in the "
                    "style of Raymond Chandler (hard-boiled noir), then in the style of Agatha Christie "
                    "(precise, observational, faintly arch). Make the stylistic contrast as sharp as possible."
                ),
            },
        ],
    },
    "analyst": {
        "name": "Analyst",
        "description": "Analytical thinking: summarization, comparison, argumentation, data reasoning, synthesis.",
        "icon": "📊",
        "categories": [
            {
                "id": "summarization",
                "name": "Summarization",
                "weight": 1.0,
                "prompt": (
                    "Summarize the key arguments for and against nuclear energy as a climate solution "
                    "in exactly 150 words. Maintain strict balance; do not express a personal view."
                ),
            },
            {
                "id": "comparison",
                "name": "Comparison",
                "weight": 1.0,
                "prompt": (
                    "Compare microservices vs monolithic architecture for a startup building a social "
                    "platform expected to scale to 10 million users. Give a clear, reasoned recommendation — "
                    "not just a pros/cons list."
                ),
            },
            {
                "id": "argumentation",
                "name": "Argumentation",
                "weight": 1.5,
                "prompt": (
                    "Construct the strongest possible argument that social media companies should be legally "
                    "liable for algorithmic amplification of harmful content. Then steelman and refute the "
                    "two most powerful objections to this position."
                ),
            },
            {
                "id": "data_reasoning",
                "name": "Data Reasoning",
                "weight": 1.5,
                "prompt": (
                    "A study reports: 'Students who eat breakfast score 15% higher on morning exams.' "
                    "A school board decides to mandate breakfast programmes. Identify every logical flaw "
                    "in this reasoning and specify what additional data would be needed to justify the policy."
                ),
            },
            {
                "id": "synthesis",
                "name": "Research Synthesis",
                "weight": 1.0,
                "prompt": (
                    "Three researchers disagree: Dr. A says remote work increases productivity; Dr. B says "
                    "it decreases it; Dr. C says it depends on job type. Design a study that could settle "
                    "the debate. Identify the key variables to control and the most likely confounders."
                ),
            },
        ],
    },
}


class GauntletRequest(BaseModel):
    """Gauntlet mode request — runs a model through a preset sequence of challenges."""
    model_ids: List[str]
    preset_name: str
    evaluator_model_id: str


@router.get("/gauntlet/presets")
async def get_gauntlet_presets():
    """Return available gauntlet presets (without full prompts)."""
    return {
        "presets": {
            preset_id: {
                "name": p["name"],
                "description": p["description"],
                "icon": p["icon"],
                "categories": [
                    {"id": c["id"], "name": c["name"], "weight": c["weight"]}
                    for c in p["categories"]
                ],
            }
            for preset_id, p in GAUNTLET_PRESETS.items()
        }
    }


@router.post("/gauntlet_stream")
async def arena_gauntlet_stream(request: GauntletRequest, req: Request):
    """Run a Gauntlet and stream results category-by-category via Server-Sent Events."""
    if not request.model_ids:
        raise HTTPException(status_code=400, detail="Need at least 1 model for a gauntlet")
    if request.preset_name not in GAUNTLET_PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown preset: {request.preset_name}")

    provider_manager = ProviderManager()
    preset = GAUNTLET_PRESETS[request.preset_name]
    categories = preset["categories"]
    trace_id = f"GAUNTLET_{uuid.uuid4().hex[:8]}"

    async def event_generator():
        # ── Start ──────────────────────────────────────────────────────────────
        start_payload = {
            "type": "gauntlet_start",
            "trace_id": trace_id,
            "preset_name": request.preset_name,
            "preset": {"name": preset["name"], "icon": preset["icon"]},
            "categories": [
                {"id": c["id"], "name": c["name"], "weight": c["weight"]}
                for c in categories
            ],
            "model_ids": request.model_ids,
        }
        yield f"data: {json.dumps(start_payload)}\n\n"

        # Per-model accumulated category scores: {model_id: {cat_id: score}}
        model_cat_scores: Dict[str, Dict[str, Optional[float]]] = {
            mid: {} for mid in request.model_ids
        }

        for cat_index, category in enumerate(categories):
            cat_id = category["id"]
            cat_name = category["name"]
            cat_prompt = category["prompt"]

            # ── Category start ──────────────────────────────────────────────
            yield f"data: {json.dumps({'type': 'category_start', 'category_id': cat_id, 'category_name': cat_name, 'category_index': cat_index, 'total_categories': len(categories), 'prompt': cat_prompt})}\n\n"

            # Call all models in parallel for this category
            cat_trace = f"{trace_id}_c{cat_index}"
            tasks = [
                asyncio.create_task(_call_model(provider_manager, cat_prompt, mid, cat_trace))
                for mid in request.model_ids
            ]

            cat_responses: List[Dict] = []
            for completed_task in asyncio.as_completed(tasks):
                try:
                    result = await completed_task
                    cat_responses.append(result)
                    # Stream individual model completion (includes response content for live preview)
                    yield f"data: {json.dumps({'type': 'model_response', 'category_id': cat_id, 'model_id': result['model_id'], 'success': result['success'], 'time_ms': result['time_ms'], 'response': result.get('response', '')})}\n\n"
                except Exception as exc:
                    logger.error(f"Gauntlet {cat_id} model call failed: {exc}")

            # ── Evaluate this category ──────────────────────────────────────
            eval_trace = f"{trace_id}_e{cat_index}"
            scored = await _evaluate_responses(
                provider_manager, cat_prompt, cat_responses,
                request.evaluator_model_id, eval_trace
            )

            cat_scores: Dict[str, Any] = {}
            for r in scored:
                mid = r["model_id"]
                score = r.get("score")
                reasoning = r.get("reasoning", "")
                cat_scores[mid] = {"score": score, "reasoning": reasoning}
                if score is not None:
                    model_cat_scores[mid][cat_id] = score

            # ── Category complete ───────────────────────────────────────────
            yield f"data: {json.dumps({'type': 'category_complete', 'category_id': cat_id, 'category_name': cat_name, 'category_index': cat_index, 'weight': category['weight'], 'scores': cat_scores, 'responses': scored})}\n\n"

        # ── Compute composite scores ────────────────────────────────────────
        composite_scores: Dict[str, float] = {}
        for mid in request.model_ids:
            weighted_sum = 0.0
            weight_total = 0.0
            for cat in categories:
                score = model_cat_scores[mid].get(cat["id"])
                if score is not None:
                    weighted_sum += score * cat["weight"]
                    weight_total += cat["weight"]
            composite_scores[mid] = round(weighted_sum / weight_total, 2) if weight_total > 0 else 0.0

        results = {
            mid: {
                "composite_score": composite_scores.get(mid, 0.0),
                "category_scores": model_cat_scores[mid],
            }
            for mid in request.model_ids
        }
        ranked = sorted(request.model_ids, key=lambda m: composite_scores.get(m, 0.0), reverse=True)
        winner_id = ranked[0] if ranked else None

        # ── Persist gauntlet stats to leaderboard ───────────────────────────
        leaderboard = _load_leaderboard()
        gauntlet_data = leaderboard.setdefault("gauntlet", {})
        for mid in request.model_ids:
            composite = composite_scores.get(mid, 0.0)
            entry = gauntlet_data.setdefault(mid, {
                "runs": 0,
                "best_composite": 0.0,
                "last_composite": 0.0,
                "last_preset": request.preset_name,
                "total_category_scores": {},
            })
            entry["runs"] += 1
            entry["last_composite"] = composite
            entry["last_preset"] = request.preset_name
            if composite > entry.get("best_composite", 0.0):
                entry["best_composite"] = composite
            tcs = entry.setdefault("total_category_scores", {})
            for cid, score in model_cat_scores[mid].items():
                if score is not None:
                    agg = tcs.setdefault(cid, {"total": 0.0, "count": 0})
                    agg["total"] += score
                    agg["count"] += 1

        leaderboard["gauntlet"] = gauntlet_data
        _save_leaderboard(leaderboard)

        # ── Gauntlet complete ───────────────────────────────────────────────
        complete_payload = {
            "type": "gauntlet_complete",
            "results": results,
            "ranked": ranked,
            "winner_id": winner_id,
            "leaderboard": gauntlet_data,
            "categories": [{"id": c["id"], "name": c["name"]} for c in categories],
        }
        yield f"data: {json.dumps(complete_payload)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── AI Conversations ───────────────────────────────────────────────────────────

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
        provider_manager = ProviderManager()
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
