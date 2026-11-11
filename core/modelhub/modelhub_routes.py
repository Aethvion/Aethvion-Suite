"""
core/modelhub/modelhub_routes.py
REST API for the Model Hub (prefix /api/modelhub).
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import registry
from .capabilities import CAPABILITIES

router = APIRouter(prefix="/api/modelhub", tags=["modelhub"])


@router.get("/capabilities")
async def get_capabilities():
    return {"capabilities": [{"id": k, **v} for k, v in CAPABILITIES.items()]}


@router.get("/endpoints")
async def get_endpoints(capability: str = "", available_only: bool = False):
    eps = await asyncio.to_thread(registry.list_endpoints, capability, not available_only, True)
    return {"endpoints": eps}


@router.get("/models")
async def get_models(capability: str = ""):
    """Same data shaped for Automate's `model_select` property ({id, label, description})."""
    eps = await asyncio.to_thread(registry.list_endpoints, capability)
    models = []
    for e in eps:
        label = f"{e['name']}  ({e['group']})"
        if not e["available"]:
            label += " — unavailable"
        models.append({"id": e["id"], "label": label,
                       "description": e["reason"] or e["description"],
                       "available": e["available"], "capabilities": e["capabilities"]})
    return {"models": models}


@router.get("/templates")
async def get_templates():
    return {"templates": registry.list_templates()}


class EndpointBody(BaseModel):
    definition: dict[str, Any]


@router.post("/endpoints/validate")
async def validate_endpoint(body: EndpointBody):
    errs = registry.validate_definition(body.definition)
    return {"ok": not errs, "errors": errs}


@router.put("/endpoints")
async def save_endpoint(body: EndpointBody):
    try:
        saved = registry.save_custom(body.definition)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "definition": saved}


@router.delete("/endpoints/{endpoint_id}")
async def delete_endpoint(endpoint_id: str):
    if not registry.delete_custom(endpoint_id):
        raise HTTPException(404, "Custom endpoint not found")
    return {"ok": True}


class InvokeBody(BaseModel):
    endpoint: str
    capability: str = ""
    prompt: str = ""
    system_prompt: str = ""
    negative_prompt: str = ""
    image: Optional[Any] = None     # asset id, asset ref, path or data URI
    mesh: Optional[Any] = None
    audio: Optional[Any] = None
    params: dict[str, Any] = {}
    name: str = ""
    tags: list[str] = []


@router.post("/invoke")
async def invoke_endpoint(body: InvokeBody):
    """Run one endpoint directly — used by the Model Hub 'Test' button and by other tools."""
    from . import hub  # noqa: PLC0415

    result = await asyncio.to_thread(
        hub.invoke, body.endpoint, body.capability,
        prompt=body.prompt, system_prompt=body.system_prompt, negative_prompt=body.negative_prompt,
        image=body.image, mesh=body.mesh, audio=body.audio, params=body.params,
        source={"type": "modelhub-test"}, name=body.name, tags=body.tags,
    )
    return result.to_dict()
