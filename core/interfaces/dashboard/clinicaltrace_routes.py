from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid
import time
import asyncio
from fastapi.responses import StreamingResponse

# Assume providers is used for the "Ask" streaming
from core.models.providers import generate_streaming_response

clinicaltrace_router = APIRouter(prefix="/api/dashboard/clinicaltrace", tags=["ClinicalTrace"])

# ── Mock Data Storage ────────────────────────────────────────────────────────
_nodes = [
    {"id": "int_sema", "title": "Semaglutide 1.0mg", "type": "Intervention", "group": "intervention"},
    {"id": "pop_t2d", "title": "T2D Patients (HbA1c > 7.0%)", "type": "Population", "group": "population"},
    {"id": "pop_ckd", "title": "T2D + Chronic Kidney Disease", "type": "Population", "group": "population"},
    
    {"id": "trial_sustain", "title": "SUSTAIN-6 Trial (RCT)", "type": "Trial", "group": "trial"},
    {"id": "trial_flow", "title": "FLOW Trial (RCT)", "type": "Trial", "group": "trial"},
    {"id": "trial_obs", "title": "RetroObservational-2024", "type": "Trial", "group": "trial"},
    
    {"id": "out_hba1c", "title": "HbA1c Reduction (-1.2%)", "type": "Outcome", "group": "outcome"},
    {"id": "out_weight", "title": "Weight Loss (-4.5kg)", "type": "Outcome", "group": "outcome"},
    {"id": "out_renal_good", "title": "Renal Event Risk (-24%)", "type": "Outcome", "group": "outcome"},
    {"id": "out_renal_bad", "title": "Renal Event Risk (+5% NS)", "type": "Outcome", "group": "outcome"}
]

_edges = [
    # SUSTAIN-6
    {"id": "e1", "from": "trial_sustain", "to": "int_sema", "label": "tests"},
    {"id": "e2", "from": "trial_sustain", "to": "pop_t2d", "label": "enrolls"},
    {"id": "e3", "from": "trial_sustain", "to": "out_hba1c", "label": "produces"},
    {"id": "e4", "from": "trial_sustain", "to": "out_weight", "label": "produces"},
    
    # FLOW
    {"id": "e5", "from": "trial_flow", "to": "int_sema", "label": "tests"},
    {"id": "e6", "from": "trial_flow", "to": "pop_ckd", "label": "enrolls"},
    {"id": "e7", "from": "trial_flow", "to": "out_renal_good", "label": "produces"},
    
    # Observational
    {"id": "e8", "from": "trial_obs", "to": "int_sema", "label": "tests"},
    {"id": "e9", "from": "trial_obs", "to": "pop_ckd", "label": "enrolls"},
    {"id": "e10", "from": "trial_obs", "to": "out_renal_bad", "label": "produces"},
]

_contradictions = [
    {"id": "c1", "from_trial": "trial_obs", "to_trial": "trial_flow", "topic": "Renal Event Risk", "severity": "high"}
]

# ── API Models ───────────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str
    model_id: str = "auto"

# ── Routes ───────────────────────────────────────────────────────────────────

@clinicaltrace_router.get("/graph")
def get_graph():
    """Returns the full clinical evidence graph including nodes, edges, and contradictions."""
    return {
        "nodes": _nodes,
        "edges": _edges,
        "contradictions": _contradictions
    }

@clinicaltrace_router.post("/{node_id}/ask")
async def ask_node(node_id: str, req: AskRequest):
    """
    Stream an AI response answering a question about a specific node.
    It builds a context block by traversing the graph upstream/downstream.
    """
    # Find the target node
    target_node = next((n for n in _nodes if n["id"] == node_id), None)
    if not target_node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Build transitive dependency context
    # Find upstream dependencies
    upstream_edges = [e for e in _edges if e["to"] == node_id]
    downstream_edges = [e for e in _edges if e["from"] == node_id]
    
    # Check for contradictions involving this node (if it's a trial)
    contradictions = [c for c in _contradictions if c["from_trial"] == node_id or c["to_trial"] == node_id]

    context_lines = [
        f"TARGET NODE: {target_node['title']} ({target_node['type']})",
        ""
    ]
    
    if upstream_edges:
        context_lines.append("INCOMING EDGES (Linked to this node):")
        for e in upstream_edges:
            n = next((n for n in _nodes if n["id"] == e["from"]), {})
            context_lines.append(f"  - {n.get('title', 'Unknown')} [{e['label']}]")
            
    if downstream_edges:
        context_lines.append("OUTGOING EDGES (This node links to):")
        for e in downstream_edges:
            n = next((n for n in _nodes if n["id"] == e["to"]), {})
            context_lines.append(f"  - [{e['label']}] {n.get('title', 'Unknown')}")

    if contradictions:
        context_lines.append("CONTRADICTIONS:")
        for c in contradictions:
            other_id = c["to_trial"] if c["from_trial"] == node_id else c["from_trial"]
            n = next((n for n in _nodes if n["id"] == other_id), {})
            context_lines.append(f"  - Contradicts {n.get('title', 'Unknown')} on topic: {c['topic']} (Severity: {c['severity']})")

    context_str = "\n".join(context_lines)

    prompt = f"""You are ClinicalTrace, an AI Medical Evidence Analyst.
Use the following graph context to answer the user's question. The context shows relationships (1-hop) for the target node in the clinical evidence graph.

<graph_context>
{context_str}
</graph_context>

User Question: {req.question}

Provide a concise, analytical response focusing on evidence quality, population specifics, and contradictions.
"""

    async def _stream():
        try:
            for chunk in generate_streaming_response(prompt, model=req.model_id if req.model_id != "auto" else None):
                yield f"data: {chunk}\n\n"
        except Exception as e:
            yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
