"""
Aethvion Suite — Ollama Routes
Manage models in a locally-running Ollama instance.
"""

import asyncio
import json
import os
import threading
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from core.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/ollama", tags=["ollama"])

# Override via OLLAMA_URL environment variable for non-default Ollama installations.
_DEFAULT = os.environ.get("OLLAMA_URL", "http://localhost:11434")


def _url(path: str, base: str = _DEFAULT) -> str:
    return base.rstrip("/") + path


# ── Status & model list ───────────────────────────────────────────────────────

@router.get("/status")
async def ollama_status():
    """Check if Ollama is reachable and return available models."""
    import requests
    try:
        r = requests.get(_url("/api/tags"), timeout=3)
        if r.ok:
            models = [m["name"] for m in r.json().get("models", [])]
            return {"running": True, "models": models}
    except Exception:
        pass
    return {"running": False, "models": []}


@router.get("/models")
async def ollama_models():
    """Return full model details from Ollama."""
    import requests
    try:
        r = requests.get(_url("/api/tags"), timeout=5)
        r.raise_for_status()
        return {"models": r.json().get("models", [])}
    except Exception as exc:
        raise HTTPException(503, f"Ollama not reachable: {exc}")


# ── Pull a model (SSE streaming) ──────────────────────────────────────────────

@router.post("/pull")
async def ollama_pull(request: Request):
    """Pull an Ollama model and stream progress as SSE."""
    import requests as _req

    data       = await request.json()
    model_name = (data.get("model") or "").strip()
    if not model_name:
        raise HTTPException(400, "model name required")

    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    def _worker():
        try:
            with _req.post(
                _url("/api/pull"),
                json={"name": model_name, "stream": True},
                stream=True,
                timeout=3600,
            ) as r:
                r.raise_for_status()
                for raw in r.iter_lines():
                    if not raw:
                        continue
                    msg      = json.loads(raw)
                    total    = msg.get("total",     0)
                    done_b   = msg.get("completed", 0)
                    status   = msg.get("status",    "")
                    pct      = round(done_b / total * 100, 1) if total > 0 else 0
                    loop.call_soon_threadsafe(q.put_nowait, {
                        "status": status, "pct": pct,
                        "total": total, "completed": done_b,
                    })
                    if status == "success":
                        loop.call_soon_threadsafe(q.put_nowait,
                                                  {"done": True, "success": True})
                        return
            # If stream ends without "success" status, treat as done
            loop.call_soon_threadsafe(q.put_nowait, {"done": True, "success": True})
        except Exception as exc:
            loop.call_soon_threadsafe(q.put_nowait,
                                      {"done": True, "success": False, "error": str(exc)})

    threading.Thread(target=_worker, daemon=True).start()

    async def _generate():
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=30.0)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'heartbeat': True})}\n\n"
                continue
            yield f"data: {json.dumps(msg)}\n\n"
            if msg.get("done"):
                break

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Delete a model ────────────────────────────────────────────────────────────

@router.delete("/model")
async def ollama_delete_model(request: Request):
    import requests as _req
    data = await request.json()
    name = (data.get("model") or "").strip()
    if not name:
        raise HTTPException(400, "model name required")
    try:
        r = _req.delete(_url("/api/delete"), json={"name": name}, timeout=30)
        r.raise_for_status()
        return {"success": True}
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ── Register / unregister in Aethvion registry ────────────────────────────────

@router.post("/register")
async def ollama_register(request: Request):
    """Add an Ollama model to the Aethvion model registry."""
    from core.interfaces.dashboard.registry_routes import _load_registry, _save_registry

    data = await request.json()
    name = (data.get("model") or "").strip()
    if not name:
        raise HTTPException(400, "model name required")

    registry  = _load_registry()
    providers = registry.setdefault("providers", {})
    ollama_p  = providers.setdefault("ollama", {
        "name": "Ollama", "active": True, "models": {}
    })
    ollama_p["models"][name] = {
        "input_cost_per_1m_tokens":  0,
        "output_cost_per_1m_tokens": 0,
        "capabilities": ["CHAT"],
        "description": f"Ollama model: {name}",
    }
    _save_registry(registry)

    if hasattr(request.app.state, "aether"):
        request.app.state.aether.reload_config()

    return {"success": True, "model": name}


@router.delete("/unregister")
async def ollama_unregister(request: Request):
    """Remove an Ollama model from the Aethvion registry."""
    from core.interfaces.dashboard.registry_routes import _load_registry, _save_registry

    data = await request.json()
    name = (data.get("model") or "").strip()

    registry = _load_registry()
    ollama_models = (registry
                     .get("providers", {})
                     .get("ollama", {})
                     .get("models", {}))
    ollama_models.pop(name, None)
    _save_registry(registry)

    if hasattr(request.app.state, "aether"):
        request.app.state.aether.reload_config()

    return {"success": True}
