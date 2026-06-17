"""
Aethvion Suite - LexMap Routes
Experimental feature: Legal Entity Intelligence Graph

Stores legal artifacts (Statutes, Cases, Regulations) as typed JSON entities locally.
Provides endpoints for CRUD operations, graph traversal, and an AI Ask endpoint
which queries the legal graph with deterministic context.

API prefix: /api/lexmap
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

logger = get_logger("web.lexmap_routes")
router = APIRouter(prefix="/api/lexmap", tags=["lexmap"])

# Data directory — stores one JSON file per legal artifact
LEXMAP_DIR = MODES / "lexmap"
LEXMAP_DIR.mkdir(parents=True, exist_ok=True)


# ── Pydantic models ────────────────────────────────────────────────────────────

class Link(BaseModel):
    to_id: str
    edge_type: str  # e.g., "overrules", "affirms", "modifies", "exempts", "interpreted_by"


class ArtifactCreate(BaseModel):
    title: str
    artifact_type: str  # e.g., "Statute", "Case", "Regulation"
    jurisdiction: str = ""
    content: str = ""
    tags: List[str] = []
    links: List[Link] = []


class ArtifactUpdate(BaseModel):
    title: Optional[str] = None
    artifact_type: Optional[str] = None
    jurisdiction: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    links: Optional[List[Link]] = None


class AskRequest(BaseModel):
    question: str
    model_id: str = "auto"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _artifact_path(artifact_id: str) -> Path:
    return LEXMAP_DIR / f"{artifact_id}.json"


def _load_artifact(artifact_id: str) -> dict:
    path = _artifact_path(artifact_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' not found.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_artifact(data: dict) -> None:
    path = _artifact_path(data["id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _all_artifacts() -> List[dict]:
    artifacts = []
    for path in sorted(LEXMAP_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(path, encoding="utf-8") as f:
                artifacts.append(json.load(f))
        except Exception as exc:
            logger.warning("Failed to load lexmap file %s: %s", path, exc)
    return artifacts


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/list")
async def list_artifacts():
    """Return all legal artifacts as a summary list."""
    artifacts = _all_artifacts()
    summary = []
    for a in artifacts:
        summary.append({
            "id":            a.get("id"),
            "title":         a.get("title", "Untitled"),
            "artifact_type": a.get("artifact_type", "Unknown"),
            "jurisdiction":  a.get("jurisdiction", ""),
            "tags":          a.get("tags", []),
            "links":         a.get("links", []),
            "created_at":    a.get("created_at"),
            "updated_at":    a.get("updated_at"),
        })
    return {"artifacts": summary, "total": len(summary)}


@router.post("/create")
async def create_artifact(body: ArtifactCreate):
    """Create a new legal artifact."""
    artifact_id = uuid.uuid4().hex
    now = utcnow_iso()
    
    # Dump links explicitly to dicts
    links_data = [link.model_dump() for link in body.links]
    
    data = {
        "id":            artifact_id,
        "title":         body.title,
        "artifact_type": body.artifact_type,
        "jurisdiction":  body.jurisdiction,
        "content":       body.content,
        "tags":          body.tags,
        "links":         links_data,
        "created_at":    now,
        "updated_at":    now,
    }
    _save_artifact(data)
    logger.info("Created LexMap artifact %s: %s", artifact_id, body.title)
    return {"id": artifact_id, "artifact": data}


@router.get("/{artifact_id}")
async def get_artifact(artifact_id: str):
    """Return a single artifact by ID."""
    return _load_artifact(artifact_id)


@router.put("/{artifact_id}")
async def update_artifact(artifact_id: str, body: ArtifactUpdate):
    """Update fields on an existing artifact."""
    data = _load_artifact(artifact_id)
    update_fields = body.model_dump(exclude_unset=True)
    
    # Handle links conversion if present
    if "links" in update_fields:
        update_fields["links"] = [l if isinstance(l, dict) else l.model_dump() for l in update_fields["links"]]
        
    data.update(update_fields)
    data["updated_at"] = utcnow_iso()
    _save_artifact(data)
    return {"id": artifact_id, "artifact": data}


@router.delete("/{artifact_id}")
async def delete_artifact(artifact_id: str):
    """Delete an artifact. Also removes this ID from any artifact that links to it."""
    path = _artifact_path(artifact_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' not found.")
    path.unlink()

    # Clean up broken links in other artifacts
    for a in _all_artifacts():
        original_links = a.get("links", [])
        new_links = [link for link in original_links if link.get("to_id") != artifact_id]
        if len(new_links) != len(original_links):
            a["links"] = new_links
            a["updated_at"] = utcnow_iso()
            _save_artifact(a)

    logger.info("Deleted LexMap artifact %s", artifact_id)
    return {"deleted": artifact_id}


@router.get("/graph/all")
async def get_graph():
    """Return all artifacts and their typed relationships as a graph structure."""
    artifacts = _all_artifacts()
    nodes = []
    edges = []
    for a in artifacts:
        nodes.append({
            "id":            a.get("id"),
            "title":         a.get("title", "Untitled"),
            "artifact_type": a.get("artifact_type", "Unknown"),
            "tags":          a.get("tags", []),
        })
        for link in a.get("links", []):
            edges.append({
                "from": a.get("id"), 
                "to": link.get("to_id"),
                "label": link.get("edge_type", "")
            })
            
    # Also find implicit reverse edges (e.g., if A overrules B, B is overruled_by A)
    # The UI graph might want these, but sending explicit edges is usually enough.
    
    return {"nodes": nodes, "edges": edges}


@router.post("/{artifact_id}/ask")
async def ask_about_artifact(artifact_id: str, body: AskRequest):
    """
    Stream an LLM answer about an artifact.
    The model receives the primary artifact + all connected artifacts as structured context.
    """
    artifact = _load_artifact(artifact_id)

    # Build context: primary artifact + all linked artifacts (both directions)
    all_artifacts = _all_artifacts()
    all_artifacts_map = {a["id"]: a for a in all_artifacts}
    
    # Find artifacts linked FROM this one
    forward_links = [l for l in artifact.get("links", []) if l.get("to_id") in all_artifacts_map]
    
    # Find artifacts linked TO this one
    reverse_links = []
    for a in all_artifacts:
        for l in a.get("links", []):
            if l.get("to_id") == artifact_id:
                reverse_links.append({"from_id": a["id"], "edge_type": l.get("edge_type"), "artifact": a})

    def _fmt_artifact(a: dict) -> str:
        lines = [
            f"Type: {a.get('artifact_type', 'Unknown')}",
            f"Title: {a.get('title', 'Untitled')}",
            f"Jurisdiction: {a.get('jurisdiction', '—')}",
            f"Tags: {', '.join(a.get('tags', [])) or '—'}",
            f"Content:\n{a.get('content', '—')}"
        ]
        return "\n".join(lines)

    context_block = "=== PRIMARY LEGAL ARTIFACT ===\n" + _fmt_artifact(artifact)
    
    if forward_links or reverse_links:
        context_block += "\n\n=== RELATED ARTIFACTS IN PRECEDENT GRAPH ===\n"
        
        for link in forward_links:
            target = all_artifacts_map[link["to_id"]]
            context_block += f"\n---\nRelationship: Primary Artifact {link.get('edge_type', 'links to').upper()} this artifact:\n"
            context_block += _fmt_artifact(target)
            
        for link in reverse_links:
            source = link["artifact"]
            context_block += f"\n---\nRelationship: This artifact {link.get('edge_type', 'links to').upper()} the Primary Artifact:\n"
            context_block += _fmt_artifact(source)

    system_prompt = (
        "You are LexMap AI, an expert legal assistant. "
        "You have been provided with a structured graph of legal artifacts (statutes, cases, regulations). "
        "Your job is to answer the user's question based strictly on the provided legal graph context. "
        "Pay special attention to the relationships between artifacts (e.g., 'overrules', 'interprets'). "
        "Do not invent legal precedent outside the provided context. Be precise and cite the titles of the artifacts provided."
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
            trace_id = f"lexmap-ask-{uuid.uuid4().hex[:8]}"

            def _call():
                return pm.call_with_failover(
                    prompt=full_prompt,
                    trace_id=trace_id,
                    temperature=0.3,
                    model=body.model_id,
                    request_type="generation",
                    source=CallSource.RESEARCH,
                )

            response = await asyncio.to_thread(_call)

            if not response.success:
                yield f"data: {json.dumps({'error': response.error or 'LLM call failed'})}\n\n"
                return

            text = response.content or ""
            chunk_size = 8
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i + chunk_size]
                yield f"data: {json.dumps({'token': chunk})}\n\n"
                await asyncio.sleep(0.01)

            yield f"data: {json.dumps({'done': True, 'model': response.model})}\n\n"

        except Exception as exc:
            logger.error("LexMap ask error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
