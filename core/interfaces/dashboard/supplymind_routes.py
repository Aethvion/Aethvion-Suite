from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid
import time
import asyncio
import json
from fastapi.responses import StreamingResponse

from core.utils import get_logger

logger = get_logger("web.supplymind_routes")
supplymind_router = APIRouter(prefix="/api/dashboard/supplymind", tags=["SupplyMind"])

# ── Mock Data Storage ────────────────────────────────────────────────────────
_nodes = [
    {"id": "prod_ev", "title": "EV Battery Pack X1", "type": "Product", "group": "finished_good"},
    {"id": "comp_cells", "title": "Lithium Ion Cells", "type": "Product", "group": "component"},
    {"id": "comp_bms", "title": "BMS Controller Board", "type": "Product", "group": "component"},
    {"id": "comp_cooling", "title": "Thermal Management Sys", "type": "Product", "group": "component"},
    {"id": "raw_lithium", "title": "Raw Lithium", "type": "Product", "group": "raw_material"},
    {"id": "raw_cobalt", "title": "Raw Cobalt", "type": "Product", "group": "raw_material"},
    {"id": "fac_shanghai", "title": "Shanghai Gigafactory (CellCorp)", "type": "Facility", "group": "facility"},
    {"id": "fac_taiwan", "title": "Taiwan Fab 2 (MicroChip)", "type": "Facility", "group": "facility"},
    {"id": "fac_germany", "title": "Munich Plant (ThermoDynamics)", "type": "Facility", "group": "facility"},
    {"id": "fac_aus", "title": "Perth Mine (AusMines)", "type": "Facility", "group": "facility"},
    {"id": "fac_congo", "title": "DRC Mine (CobaltCorp)", "type": "Facility", "group": "facility"}
]

_edges = [
    # BOM Hierarchy (upstream from finished good)
    {"id": "e1", "from": "comp_cells", "to": "prod_ev", "label": "used_in", "lead_time_days": 14},
    {"id": "e2", "from": "comp_bms", "to": "prod_ev", "label": "used_in", "lead_time_days": 7},
    {"id": "e3", "from": "comp_cooling", "to": "prod_ev", "label": "used_in", "lead_time_days": 10},
    {"id": "e4", "from": "raw_lithium", "to": "comp_cells", "label": "refined_for", "lead_time_days": 30},
    {"id": "e5", "from": "raw_cobalt", "to": "comp_cells", "label": "refined_for", "lead_time_days": 45},
    
    # Sourcing from facilities
    {"id": "e6", "from": "fac_shanghai", "to": "comp_cells", "label": "manufactures"},
    {"id": "e7", "from": "fac_taiwan", "to": "comp_bms", "label": "manufactures"},
    {"id": "e8", "from": "fac_germany", "to": "comp_cooling", "label": "manufactures"},
    {"id": "e9", "from": "fac_aus", "to": "raw_lithium", "label": "extracts"},
    {"id": "e10", "from": "fac_congo", "to": "raw_cobalt", "label": "extracts"},
]

_risk_events = [
    {"id": "risk_1", "title": "Taiwan Semiconductor Fab Fire", "target_id": "fac_taiwan", "severity": "critical"},
    {"id": "risk_2", "title": "Port Closure (Shanghai)", "target_id": "fac_shanghai", "severity": "high"},
    {"id": "risk_3", "title": "Cobalt Export Ban", "target_id": "fac_congo", "severity": "critical"}
]

# ── API Models ───────────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str
    model_id: str = "auto"

# ── Routes ───────────────────────────────────────────────────────────────────

@supplymind_router.get("/graph")
def get_graph():
    """Returns the full supply chain graph including nodes, edges, and active risk events."""
    return {
        "nodes": _nodes,
        "edges": _edges,
        "risks": _risk_events
    }

@supplymind_router.post("/{node_id}/ask")
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
    # Find upstream dependencies (what feeds this node)
    upstream_edges = [e for e in _edges if e["to"] == node_id]
    downstream_edges = [e for e in _edges if e["from"] == node_id]
    
    # Check for direct risks
    risks = [r for r in _risk_events if r["target_id"] == node_id]

    context_lines = [
        f"TARGET NODE: {target_node['title']} ({target_node['type']})",
        ""
    ]
    
    if upstream_edges:
        context_lines.append("UPSTREAM DEPENDENCIES (Supplies this node):")
        for e in upstream_edges:
            n = next((n for n in _nodes if n["id"] == e["from"]), {})
            lead_time = f" ({e['lead_time_days']} days)" if "lead_time_days" in e else ""
            context_lines.append(f"  - {n.get('title', 'Unknown')} [{e['label']}]{lead_time}")
            
    if downstream_edges:
        context_lines.append("DOWNSTREAM DEPENDENCIES (Depends on this node):")
        for e in downstream_edges:
            n = next((n for n in _nodes if n["id"] == e["to"]), {})
            context_lines.append(f"  - {n.get('title', 'Unknown')} [{e['label']}]")

    if risks:
        context_lines.append("ACTIVE RISKS:")
        for r in risks:
            context_lines.append(f"  - {r['severity'].upper()}: {r['title']}")

    context_str = "\n".join(context_lines)

    prompt = f"""You are SupplyMind, an AI Supply Chain Analyst.
Use the following graph context to answer the user's question. The context shows direct relationships (1-hop) for the target node in the supply chain graph.

<graph_context>
{context_str}
</graph_context>

User Question: {req.question}

Provide a concise, analytical response focusing on risk propagation, substitution options, and lead times.
"""

    async def _stream():
        try:
            from core.providers.provider_manager import get_provider_manager
            from core.ai.call_contexts import CallSource

            pm = get_provider_manager()
            trace_id = f"supplymind-ask-{uuid.uuid4().hex[:8]}"

            def _call():
                return pm.call_with_failover(
                    prompt=prompt,
                    trace_id=trace_id,
                    temperature=0.3,
                    model=req.model_id if req.model_id != "auto" else None,
                    request_type="generation",
                    source=CallSource.RESEARCH,
                )

            response = await asyncio.to_thread(_call)
            if not response.success:
                yield f"data: {json.dumps({'error': response.error or 'LLM call failed'})}\n\n"
                return

            text = response.content or ""
            for i in range(0, len(text), 8):
                yield f"data: {json.dumps({'token': text[i:i + 8]})}\n\n"
                await asyncio.sleep(0.01)
            yield f"data: {json.dumps({'done': True, 'model': response.model})}\n\n"
        except Exception as exc:
            logger.error("SupplyMind ask error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
