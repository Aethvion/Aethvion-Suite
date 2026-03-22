"""
Aethvion Suite - Are You Smarter Than AI? Routes
Gameshow-format trivia: a Game Master LLM generates questions,
human and AI players answer, and the GM judges and awards points.
"""

import re
import uuid
import json
import random
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.utils import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/smarter-than-ai", tags=["smarter-than-ai"])


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class Player:
    id: str
    name: str
    type: str          # "human" | "ai"
    model: Optional[str]
    score: int = 0
    answers: List[str] = field(default_factory=list)


@dataclass
class Round:
    round_number: int
    question: str = ""
    category: str = ""
    points: int = 100
    correct_answer: str = ""
    explanation: str = ""
    hint: str = ""
    answers: Dict[str, str] = field(default_factory=dict)       # player_id -> answer
    judgements: Dict[str, bool] = field(default_factory=dict)   # player_id -> correct?
    state: str = "pending"  # "pending" | "question" | "answering" | "judged"


@dataclass
class SmarterThanAIShow:
    show_id: str
    game_master_model: str
    players: List[Player]
    categories: List[str]
    total_rounds: int
    time_limit_seconds: int
    rounds: List[Round] = field(default_factory=list)
    current_round_index: int = -1
    state: str = "lobby"  # "lobby" | "playing" | "finished"


# ── In-memory show store ───────────────────────────────────────────────────────

_shows: Dict[str, SmarterThanAIShow] = {}


# ── Request models ─────────────────────────────────────────────────────────────

class PlayerConfig(BaseModel):
    name: str
    type: str           # "human" | "ai"
    model: Optional[str] = None


class CreateShowRequest(BaseModel):
    game_master_model: str = "auto"
    players: List[PlayerConfig]
    categories: List[str] = ["General Knowledge", "Science", "History", "Pop Culture", "Technology"]
    total_rounds: int = 5
    time_limit_seconds: int = 30


class ShowIdRequest(BaseModel):
    show_id: str


class AnswerRequest(BaseModel):
    show_id: str
    player_id: str
    answer: str


# ── LLM helper ────────────────────────────────────────────────────────────────

def _parse_json_response(raw: str) -> Optional[Dict]:
    """Robust JSON extraction from LLM output."""
    if not raw:
        return None

    text = raw.strip()

    # Strip markdown fences
    fenced = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if fenced:
        text = fenced.group(1).strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r'(\{[\s\S]*\})', text)
    if match:
        candidate = match.group(1)
        # Attempt repair
        try:
            return json.loads(candidate)
        except Exception:
            repaired = candidate
            repaired = re.sub(r',\s*\}', '}', repaired)
            repaired = re.sub(r',\s*\]', ']', repaired)
            open_b = repaired.count('{') - repaired.count('}')
            if open_b > 0:
                repaired += '}' * open_b
            try:
                return json.loads(repaired)
            except Exception:
                pass

    return None


async def _llm_call(model: str, prompt: str, trace_id: str) -> Optional[str]:
    """Thin wrapper around ProviderManager.call_with_failover using asyncio.to_thread."""
    from core.providers import ProviderManager
    pm = ProviderManager()
    try:
        response = await asyncio.to_thread(
            pm.call_with_failover,
            prompt=prompt,
            trace_id=trace_id,
            temperature=0.7,
            max_tokens=512,
            model=model,
            source="game"
        )
        if response and response.success:
            return response.content
        logger.warning(f"[STA] LLM call failed for trace {trace_id}: {getattr(response, 'error', 'unknown')}")
        return None
    except Exception as e:
        logger.error(f"[STA] LLM exception for trace {trace_id}: {e}")
        return None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/show")
async def create_show(req: CreateShowRequest):
    """Create a new show and return its initial state."""
    if len(req.players) < 1:
        raise HTTPException(status_code=400, detail="At least one player is required.")
    if req.total_rounds < 1 or req.total_rounds > 20:
        raise HTTPException(status_code=400, detail="total_rounds must be between 1 and 20.")

    show_id = str(uuid.uuid4())
    players = [
        Player(
            id=str(uuid.uuid4()),
            name=p.name,
            type=p.type,
            model=p.model
        )
        for p in req.players
    ]

    show = SmarterThanAIShow(
        show_id=show_id,
        game_master_model=req.game_master_model,
        players=players,
        categories=req.categories,
        total_rounds=req.total_rounds,
        time_limit_seconds=req.time_limit_seconds,
    )
    _shows[show_id] = show
    logger.info(f"[STA] Show created: {show_id} with {len(players)} players, {req.total_rounds} rounds.")
    return {"success": True, "show_id": show_id, "state": _show_state(show)}


@router.post("/round/start")
async def start_round(req: ShowIdRequest):
    """Game Master generates a question for the next round."""
    show = _get_show(req.show_id)

    if show.state == "finished":
        raise HTTPException(status_code=400, detail="Show is already finished.")

    # Advance round index
    show.current_round_index += 1
    round_num = show.current_round_index + 1

    if round_num > show.total_rounds:
        show.state = "finished"
        return {"success": True, "finished": True, "state": _show_state(show)}

    show.state = "playing"

    # Pick a category — shuffle order so it feels less mechanical
    if not hasattr(show, '_category_order'):
        show._category_order = random.sample(show.categories, len(show.categories))
    cat_idx = show.current_round_index % len(show._category_order)
    chosen_category = show._category_order[cat_idx]

    # Collect already-asked questions so the LLM can avoid them
    asked_so_far = [r.question for r in show.rounds[:-1] if r.question]
    avoid_block = ""
    if asked_so_far:
        listed = "\n".join(f"  - {q}" for q in asked_so_far)
        avoid_block = (
            f"\n\nIMPORTANT: These questions have already been asked this game — "
            f"do NOT repeat or closely resemble any of them:\n{listed}"
        )

    prompt = (
        f"You are the host of 'Are You Smarter Than AI?' — a competitive trivia gameshow.\n"
        f"Generate a unique, interesting trivia question for round {round_num} of {show.total_rounds}.\n"
        f"Category: {chosen_category}.\n"
        f"The question must be DIFFERENT from any question you have generated before.{avoid_block}\n\n"
        "Return ONLY valid JSON with no additional text:\n"
        '{"question": "...", "category": "...", "correct_answer": "...", "points": 100, "hint": "one short hint without giving away the answer"}'
    )

    raw = await _llm_call(
        model=show.game_master_model,
        prompt=prompt,
        trace_id=f"sta-{show.show_id[:8]}-gm-q{round_num}"
    )

    parsed = _parse_json_response(raw) if raw else None

    if not parsed or not parsed.get("question"):
        # Diverse fallback pool — pick one not already used
        fallback_pool = [
            {"question": "What is the largest planet in our solar system?",      "correct_answer": "Jupiter",          "hint": "It has a famous storm called the Great Red Spot."},
            {"question": "Who painted the Mona Lisa?",                           "correct_answer": "Leonardo da Vinci", "hint": "He was also a famous inventor and scientist."},
            {"question": "In what year did the Berlin Wall fall?",                "correct_answer": "1989",             "hint": "It happened in the late 1980s."},
            {"question": "What element has the chemical symbol 'Au'?",           "correct_answer": "Gold",             "hint": "It comes from the Latin word 'Aurum'."},
            {"question": "How many sides does a dodecagon have?",                 "correct_answer": "12",               "hint": "The prefix 'dodeca' means twelve."},
            {"question": "Which country invented the printing press?",           "correct_answer": "Germany",          "hint": "Johannes Gutenberg is credited with its invention."},
            {"question": "What is the speed of light in km/s (approximate)?",   "correct_answer": "300,000 km/s",     "hint": "It takes about 8 minutes to travel from the Sun to Earth."},
            {"question": "Who wrote 'Pride and Prejudice'?",                     "correct_answer": "Jane Austen",      "hint": "She was an English novelist of the early 19th century."},
            {"question": "What is the smallest country in the world by area?",   "correct_answer": "Vatican City",     "hint": "It is located within Rome, Italy."},
            {"question": "What gas do plants absorb during photosynthesis?",     "correct_answer": "Carbon dioxide",   "hint": "Humans exhale it."},
            {"question": "Which programming language was created by Guido van Rossum?", "correct_answer": "Python",   "hint": "Named after a British comedy group."},
            {"question": "What is the longest river in the world?",              "correct_answer": "The Nile",         "hint": "It flows through Egypt."},
            {"question": "In chess, which piece can only move diagonally?",      "correct_answer": "Bishop",           "hint": "Each player starts with two of them."},
            {"question": "What is the hardest natural substance on Earth?",      "correct_answer": "Diamond",          "hint": "It scores 10 on the Mohs hardness scale."},
            {"question": "How many bones are in the adult human body?",          "correct_answer": "206",              "hint": "Babies are born with around 270."},
        ]
        used_questions = {r.question for r in show.rounds}
        unused = [f for f in fallback_pool if f["question"] not in used_questions]
        chosen = random.choice(unused if unused else fallback_pool)
        parsed = {
            "question": chosen["question"],
            "category": chosen_category,
            "correct_answer": chosen["correct_answer"],
            "points": 100,
            "hint": chosen["hint"],
        }
        logger.warning(f"[STA] GM question generation failed, using fallback for round {round_num}.")

    new_round = Round(
        round_number=round_num,
        question=parsed.get("question", ""),
        category=parsed.get("category", chosen_category),
        points=int(parsed.get("points", 100)),
        correct_answer=parsed.get("correct_answer", ""),
        hint=parsed.get("hint", ""),
        state="answering"
    )
    show.rounds.append(new_round)

    logger.info(f"[STA] Round {round_num} started: {new_round.question[:60]}...")
    return {"success": True, "round": _round_state(new_round), "state": _show_state(show)}


@router.post("/round/answer")
async def submit_answer(req: AnswerRequest):
    """Submit a single player's answer for the current round."""
    show = _get_show(req.show_id)
    current_round = _current_round(show)

    if current_round.state not in ("answering",):
        raise HTTPException(status_code=400, detail="Round is not in answering state.")

    # Verify player exists
    player = next((p for p in show.players if p.id == req.player_id), None)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found.")

    current_round.answers[req.player_id] = req.answer
    logger.info(f"[STA] Player '{player.name}' answered round {current_round.round_number}.")

    return {"success": True, "round": _round_state(current_round), "state": _show_state(show)}


@router.post("/round/ai-answers")
async def ai_answers(req: ShowIdRequest):
    """Auto-answer for all AI players concurrently."""
    show = _get_show(req.show_id)
    current_round = _current_round(show)

    if current_round.state not in ("answering",):
        raise HTTPException(status_code=400, detail="Round is not in answering state.")

    ai_players = [p for p in show.players if p.type == "ai"]
    if not ai_players:
        return {"success": True, "round": _round_state(current_round), "state": _show_state(show)}

    async def answer_for_player(player: Player):
        prompt = (
            "You are a contestant on a trivia gameshow called 'Are You Smarter Than AI?'. "
            f"Answer this question concisely and accurately: {current_round.question} "
            "Return ONLY valid JSON: {\"answer\": \"your answer here\"}"
        )
        raw = await _llm_call(
            model=player.model or "auto",
            prompt=prompt,
            trace_id=f"sta-{show.show_id[:8]}-ai-{player.id[:6]}"
        )
        parsed = _parse_json_response(raw) if raw else None
        answer = parsed.get("answer", "I don't know.") if parsed else "I don't know."
        current_round.answers[player.id] = answer
        logger.info(f"[STA] AI player '{player.name}' answered: {answer[:60]}")

    await asyncio.gather(*[answer_for_player(p) for p in ai_players])

    return {"success": True, "round": _round_state(current_round), "state": _show_state(show)}


@router.post("/round/judge")
async def judge_round(req: ShowIdRequest):
    """Game Master judges all answers and updates scores."""
    show = _get_show(req.show_id)
    current_round = _current_round(show)

    if current_round.state not in ("answering",):
        raise HTTPException(status_code=400, detail="Round is not ready to judge.")

    if not current_round.answers:
        raise HTTPException(status_code=400, detail="No answers have been submitted.")

    # Build judging context
    answers_text = "\n".join(
        f"- Player ID {pid}: \"{ans}\""
        for pid, ans in current_round.answers.items()
    )

    judge_prompt = (
        f"You are the judge for 'Are You Smarter Than AI?' trivia gameshow.\n"
        f"Question: {current_round.question}\n"
        f"Correct answer: {current_round.correct_answer}\n\n"
        f"Player answers:\n{answers_text}\n\n"
        "Judge each answer LENIENTLY. Mark an answer as CORRECT if it conveys the same meaning as the correct answer, including:\n"
        "  - Articles or prefixes: 'The Bishop' = 'Bishop', 'A diamond' = 'Diamond'\n"
        "  - Singular/plural: 'bishops' = 'bishop'\n"
        "  - Common abbreviations or alternate spellings\n"
        "  - Reasonable paraphrases with the same core meaning\n"
        "  - Numbers written as words: 'twelve' = '12'\n"
        "Only mark an answer as WRONG if it is clearly and unambiguously incorrect or empty.\n\n"
        "Return ONLY valid JSON:\n"
        '{"judgements": [{"player_id": "...", "is_correct": true, "points": 100}], "explanation": "brief explanation of the correct answer"}'
    )

    raw = await _llm_call(
        model=show.game_master_model,
        prompt=judge_prompt,
        trace_id=f"sta-{show.show_id[:8]}-judge-r{current_round.round_number}"
    )

    parsed = _parse_json_response(raw) if raw else None

    # Fallback: lenient string match (strips articles, punctuation, normalises whitespace)
    if not parsed or "judgements" not in parsed:
        logger.warning(f"[STA] GM judging failed, falling back to fuzzy match.")

        def _normalise(s: str) -> str:
            s = s.strip().lower()
            # Strip leading articles
            for article in ("the ", "a ", "an "):
                if s.startswith(article):
                    s = s[len(article):]
            # Remove punctuation and collapse spaces
            s = re.sub(r"[^\w\s]", "", s)
            s = re.sub(r"\s+", " ", s).strip()
            return s

        correct_norm = _normalise(current_round.correct_answer)
        judgements = []
        for pid, ans in current_round.answers.items():
            is_correct = _normalise(ans) == correct_norm
            judgements.append({"player_id": pid, "is_correct": is_correct, "points": current_round.points})
        parsed = {"judgements": judgements, "explanation": f"Correct answer: {current_round.correct_answer}"}

    # Apply judgements
    explanation = parsed.get("explanation", "")
    current_round.explanation = explanation

    for j in parsed.get("judgements", []):
        pid = j.get("player_id")
        is_correct = bool(j.get("is_correct", False))
        pts = int(j.get("points", current_round.points if is_correct else 0))

        current_round.judgements[pid] = is_correct

        if is_correct:
            player = next((p for p in show.players if p.id == pid), None)
            if player:
                player.score += pts
                logger.info(f"[STA] Player '{player.name}' earned {pts} pts. Total: {player.score}")

    current_round.state = "judged"

    # Check if show is over
    if current_round.round_number >= show.total_rounds:
        show.state = "finished"

    return {
        "success": True,
        "explanation": explanation,
        "correct_answer": current_round.correct_answer,
        "judgements": parsed.get("judgements", []),
        "round": _round_state(current_round),
        "state": _show_state(show)
    }


@router.get("/show/{show_id}")
async def get_show(show_id: str):
    """Get the current state of a show."""
    show = _get_show(show_id)
    current_round = show.rounds[show.current_round_index] if show.current_round_index >= 0 and show.rounds else None
    return {
        "success": True,
        "state": _show_state(show),
        "current_round": _round_state(current_round) if current_round else None
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_show(show_id: str) -> SmarterThanAIShow:
    show = _shows.get(show_id)
    if not show:
        raise HTTPException(status_code=404, detail="Show not found.")
    return show


def _current_round(show: SmarterThanAIShow) -> Round:
    if show.current_round_index < 0 or show.current_round_index >= len(show.rounds):
        raise HTTPException(status_code=400, detail="No active round.")
    return show.rounds[show.current_round_index]


def _player_state(p: Player) -> Dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "type": p.type,
        "model": p.model,
        "score": p.score
    }


def _round_state(r: Round) -> Dict[str, Any]:
    return {
        "round_number": r.round_number,
        "question": r.question,
        "category": r.category,
        "points": r.points,
        "hint": r.hint,
        "correct_answer": r.correct_answer if r.state == "judged" else "",
        "explanation": r.explanation,
        "answers": r.answers,
        "judgements": r.judgements,
        "state": r.state
    }


def _show_state(show: SmarterThanAIShow) -> Dict[str, Any]:
    return {
        "show_id": show.show_id,
        "game_master_model": show.game_master_model,
        "players": [_player_state(p) for p in show.players],
        "total_rounds": show.total_rounds,
        "current_round_index": show.current_round_index,
        "time_limit_seconds": show.time_limit_seconds,
        "state": show.state
    }
