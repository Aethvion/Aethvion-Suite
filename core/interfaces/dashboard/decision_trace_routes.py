"""
Aethvion Suite - DecisionTrace Routes
Experimental feature: Organisational Decision Provenance Graph

Stores decisions as typed JSON entities locally.
Each decision captures: what was decided, what options were considered,
why it was chosen, what constraints existed, what was traded off,
who was involved, and how this decision links to others.

API prefix: /api/decision-trace
"""

import json
import uuid
import asyncio
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.utils import get_logger, utcnow_iso
from core.utils.paths import MODES

logger = get_logger("web.decision_trace_routes")
router = APIRouter(prefix="/api/decision-trace", tags=["decision-trace"])

# Data directory — stores one JSON file per decision
DECISIONS_DIR = MODES / "decision_trace"
DECISIONS_DIR.mkdir(parents=True, exist_ok=True)


# ── Pydantic models ────────────────────────────────────────────────────────────

class DecisionCreate(BaseModel):
    title: str
    context: str = ""
    options_considered: List[str] = []
    chosen_option: str = ""
    constraints: List[str] = []
    trade_offs: str = ""
    stakeholders: List[str] = []
    tags: List[str] = []
    links_to: List[str] = []          # IDs of related decisions


class DecisionUpdate(BaseModel):
    title: Optional[str] = None
    context: Optional[str] = None
    options_considered: Optional[List[str]] = None
    chosen_option: Optional[str] = None
    constraints: Optional[List[str]] = None
    trade_offs: Optional[str] = None
    stakeholders: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    links_to: Optional[List[str]] = None


class AskRequest(BaseModel):
    question: str
    model_id: str = "auto"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _decision_path(decision_id: str) -> Path:
    return DECISIONS_DIR / f"{decision_id}.json"


def _load_decision(decision_id: str) -> dict:
    path = _decision_path(decision_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Decision '{decision_id}' not found.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_decision(data: dict) -> None:
    path = _decision_path(data["id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _all_decisions() -> List[dict]:
    decisions = []
    for path in sorted(DECISIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(path, encoding="utf-8") as f:
                decisions.append(json.load(f))
        except Exception as exc:
            logger.warning("Failed to load decision file %s: %s", path, exc)
    return decisions


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/list")
async def list_decisions():
    """Return all decisions as a summary list (no full context body)."""
    decisions = _all_decisions()
    summary = []
    for d in decisions:
        summary.append({
            "id":               d.get("id"),
            "title":            d.get("title", "Untitled"),
            "chosen_option":    d.get("chosen_option", ""),
            "tags":             d.get("tags", []),
            "stakeholders":     d.get("stakeholders", []),
            "links_to":         d.get("links_to", []),
            "created_at":       d.get("created_at"),
            "updated_at":       d.get("updated_at"),
        })
    return {"decisions": summary, "total": len(summary)}


@router.post("/create")
async def create_decision(body: DecisionCreate):
    """Create a new decision record."""
    decision_id = uuid.uuid4().hex
    now = utcnow_iso()
    data = {
        "id":                 decision_id,
        "title":              body.title,
        "context":            body.context,
        "options_considered": body.options_considered,
        "chosen_option":      body.chosen_option,
        "constraints":        body.constraints,
        "trade_offs":         body.trade_offs,
        "stakeholders":       body.stakeholders,
        "tags":               body.tags,
        "links_to":           body.links_to,
        "created_at":         now,
        "updated_at":         now,
    }
    _save_decision(data)
    logger.info("Created decision %s: %s", decision_id, body.title)
    return {"id": decision_id, "decision": data}


@router.get("/{decision_id}")
async def get_decision(decision_id: str):
    """Return a single decision by ID."""
    return _load_decision(decision_id)


@router.put("/{decision_id}")
async def update_decision(decision_id: str, body: DecisionUpdate):
    """Update fields on an existing decision."""
    data = _load_decision(decision_id)
    update_fields = body.model_dump(exclude_unset=True)
    data.update(update_fields)
    data["updated_at"] = utcnow_iso()
    _save_decision(data)
    return {"id": decision_id, "decision": data}


@router.delete("/{decision_id}")
async def delete_decision(decision_id: str):
    """Delete a decision. Also removes this ID from any decision that links to it."""
    path = _decision_path(decision_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Decision '{decision_id}' not found.")
    path.unlink()

    # Clean up broken links in other decisions
    for d in _all_decisions():
        if decision_id in d.get("links_to", []):
            d["links_to"] = [lid for lid in d["links_to"] if lid != decision_id]
            d["updated_at"] = utcnow_iso()
            _save_decision(d)

    logger.info("Deleted decision %s", decision_id)
    return {"deleted": decision_id}


@router.get("/graph/all")
async def get_graph():
    """Return all decisions and their link relationships as a graph structure."""
    decisions = _all_decisions()
    nodes = []
    edges = []
    for d in decisions:
        nodes.append({
            "id":    d.get("id"),
            "title": d.get("title", "Untitled"),
            "tags":  d.get("tags", []),
            "chosen_option": d.get("chosen_option", ""),
        })
        for target in d.get("links_to", []):
            edges.append({"from": d.get("id"), "to": target})
    return {"nodes": nodes, "edges": edges}


@router.post("/{decision_id}/ask")
async def ask_about_decision(decision_id: str, body: AskRequest):
    """
    Stream an LLM answer about a decision.
    The model receives the full decision + all linked decisions as structured context.
    """
    decision = _load_decision(decision_id)

    # Build context: primary decision + all linked decisions
    all_decisions_map = {d["id"]: d for d in _all_decisions()}
    linked = [all_decisions_map[lid] for lid in decision.get("links_to", []) if lid in all_decisions_map]

    def _fmt_decision(d: dict) -> str:
        lines = [
            f"Decision: {d.get('title', 'Untitled')}",
            f"Context: {d.get('context', '—')}",
            f"Options Considered: {', '.join(d.get('options_considered', [])) or '—'}",
            f"Chosen: {d.get('chosen_option', '—')}",
            f"Constraints: {', '.join(d.get('constraints', [])) or '—'}",
            f"Trade-offs: {d.get('trade_offs', '—')}",
            f"Stakeholders: {', '.join(d.get('stakeholders', [])) or '—'}",
            f"Tags: {', '.join(d.get('tags', [])) or '—'}",
        ]
        return "\n".join(lines)

    context_block = "=== PRIMARY DECISION ===\n" + _fmt_decision(decision)
    if linked:
        context_block += "\n\n=== LINKED DECISIONS ===\n"
        context_block += "\n\n---\n".join(_fmt_decision(l) for l in linked)

    system_prompt = (
        "You are a knowledgeable advisor helping a team understand their past decisions. "
        "You have been given structured records of decisions made by the team. "
        "Answer the question based strictly on the decision context provided. "
        "If the answer cannot be determined from the context, say so clearly. "
        "Be concise but thorough."
    )

    full_prompt = (
        f"{system_prompt}\n\n"
        f"{context_block}\n\n"
        f"=== QUESTION ===\n{body.question}\n\n"
        f"Answer:"
    )

    async def event_generator():
        try:
            from core.providers.provider_manager import get_provider_manager
            from core.ai.call_contexts import CallSource

            pm = get_provider_manager()
            trace_id = f"dt-ask-{uuid.uuid4().hex[:8]}"

            # Run the blocking call in a thread to avoid blocking the event loop
            def _call():
                return pm.call_with_failover(
                    prompt=full_prompt,
                    trace_id=trace_id,
                    temperature=0.4,
                    model=body.model_id,
                    request_type="generation",
                    source=CallSource.RESEARCH,
                )

            response = await asyncio.to_thread(_call)

            if not response.success:
                yield f"data: {json.dumps({'error': response.error or 'LLM call failed'})}\n\n"
                return

            # Stream token by token if content is available
            text = response.content or ""
            chunk_size = 8
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i + chunk_size]
                yield f"data: {json.dumps({'token': chunk})}\n\n"
                await asyncio.sleep(0.01)

            yield f"data: {json.dumps({'done': True, 'model': response.model})}\n\n"

        except Exception as exc:
            logger.error("DecisionTrace ask error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
