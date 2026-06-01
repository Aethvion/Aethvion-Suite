"""
Aethvion Suite - External API
OpenAI-compatible API layer for external integrations.
External apps call Aethvion just like the OpenAI API — pass a model ID + messages,
Aethvion handles all routing, failover, and provider management.
"""
import json
import secrets
import time
import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.utils import get_logger, utcnow_iso, atomic_json_write
from core.utils.paths import EXT_API_DIR, EXT_API_KEYS, EXT_API_CONFIG
from core.ai.call_contexts import CallSource

logger = get_logger(__name__)

# ── OpenAI-compatible router (/v1) ────────────────────────────────────────────
router = APIRouter(prefix="/v1", tags=["external-api"])

# ── Management router (/api/external-api) ─────────────────────────────────────
mgmt_router = APIRouter(prefix="/api/external-api", tags=["external-api-mgmt"])


# ── Config & key helpers ──────────────────────────────────────────────────────

def _load_config() -> dict:
    # require_auth defaults to True — new installs are secure out of the box.
    # Users must explicitly disable auth via the UI/config if they want open access.
    defaults = {"enabled": True, "require_auth": True}
    if not EXT_API_CONFIG.exists():
        return defaults
    try:
        return {**defaults, **json.loads(EXT_API_CONFIG.read_text())}
    except Exception:
        return defaults


def _save_config(cfg: dict):
    atomic_json_write(EXT_API_CONFIG, cfg)


def _load_keys() -> dict:
    if not EXT_API_KEYS.exists():
        return {}
    try:
        return json.loads(EXT_API_KEYS.read_text())
    except Exception:
        return {}


def _save_keys(keys: dict):
    atomic_json_write(EXT_API_KEYS, keys)


def _check_auth(authorization: Optional[str]):
    cfg = _load_config()
    if not cfg.get("enabled", True):
        raise HTTPException(status_code=503, detail="Aethvion External API is disabled")
    if not cfg.get("require_auth", False):
        return None  # open access
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required (Bearer <key>)")
    token = authorization.removeprefix("Bearer ").strip()
    keys = _load_keys()
    for key_id, kd in keys.items():
        if kd.get("key") == token and kd.get("enabled", True):
            kd["last_used"] = utcnow_iso()
            kd["request_count"] = kd.get("request_count", 0) + 1
            _save_keys(keys)
            return key_id
    raise HTTPException(status_code=401, detail="Invalid or revoked API key")


# ── Pydantic models ───────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False


# ── GET /v1/models ────────────────────────────────────────────────────────────

@router.get("/models")
async def list_models(authorization: Optional[str] = Header(None)):
    """List all models available in the Aethvion registry."""
    _check_auth(authorization)
    try:
        from core.utils.paths import MODEL_REGISTRY
        registry = json.loads(MODEL_REGISTRY.read_text()) if MODEL_REGISTRY.exists() else {}
        models = []
        for provider_name, provider_data in (registry.get("providers") or {}).items():
            for model_id in (provider_data.get("models") or {}):
                models.append({
                    "id": model_id,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": f"aethvion/{provider_name}",
                })
        return {"object": "list", "data": models}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── POST /v1/chat/completions ─────────────────────────────────────────────────

@router.post("/chat/completions")
async def chat_completions(
    req: ChatCompletionRequest,
    authorization: Optional[str] = Header(None),
):
    """
    OpenAI-compatible chat completions. Aethvion routes to the best available
    provider for the requested model with automatic failover.
    """
    _check_auth(authorization)

    # Build prompt from messages list
    system_parts = [m.content for m in req.messages if m.role == "system"]
    conv_parts   = [
        f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}"
        for m in req.messages if m.role in ("user", "assistant")
    ]
    system_str = "\n".join(system_parts)
    history    = "\n".join(conv_parts)
    prompt     = f"{system_str}\n\n{history}\nAssistant:".strip() if system_str else f"{history}\nAssistant:"

    if req.stream:
        return StreamingResponse(
            _stream_chunks(req, prompt, system_str or None),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Non-streaming
    try:
        from core.providers.provider_manager import get_provider_manager
        pm = get_provider_manager()
        resp = pm.call_with_failover(
            prompt=prompt,
            trace_id=f"extapi-{uuid.uuid4().hex[:8]}",
            temperature=req.temperature or 0.7,
            max_tokens=req.max_tokens,
            model=req.model,
            request_type="generation",
            source=CallSource.EXTERNAL_API,
        )
        if not resp.success:
            raise HTTPException(status_code=500, detail=resp.error or "Provider call failed")

        cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        return {
            "id": cid,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": resp.content},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(resp.content.split()),
                "total_tokens": len(prompt.split()) + len(resp.content.split()),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _stream_chunks(req: ChatCompletionRequest, prompt: str, system_prompt: Optional[str]):
    cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    try:
        from core.providers.provider_manager import get_provider_manager
        pm = get_provider_manager()
        for chunk in pm.call_with_failover_stream(
            prompt=prompt,
            trace_id=f"extapi-s-{uuid.uuid4().hex[:8]}",
            system_prompt=system_prompt,
            temperature=req.temperature or 0.7,
            max_tokens=req.max_tokens,
            model=req.model,
            source=CallSource.EXTERNAL_API,
        ):
            data = json.dumps({
                "id": cid, "object": "chat.completion.chunk",
                "created": int(time.time()), "model": req.model,
                "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}],
            })
            yield f"data: {data}\n\n"

        done = json.dumps({
            "id": cid, "object": "chat.completion.chunk",
            "created": int(time.time()), "model": req.model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        })
        yield f"data: {done}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': {'message': str(e), 'type': 'server_error'}})}\n\n"


# ── Management endpoints ──────────────────────────────────────────────────────

@mgmt_router.get("/config")
async def get_ext_config():
    return _load_config()


@mgmt_router.post("/config")
async def update_ext_config(request: Request):
    body = await request.json()
    cfg = _load_config()
    for k in ("enabled", "require_auth"):
        if k in body:
            cfg[k] = body[k]
    _save_config(cfg)
    return cfg


@mgmt_router.get("/keys")
async def list_api_keys():
    keys = _load_keys()
    safe = []
    for kid, kd in keys.items():
        safe.append({
            "id": kid,
            "name": kd.get("name", "Unnamed"),
            "key_preview": kd.get("key", "")[:14] + "…",
            "created_at": kd.get("created_at"),
            "last_used": kd.get("last_used"),
            "request_count": kd.get("request_count", 0),
            "enabled": kd.get("enabled", True),
        })
    return {"keys": safe}


@mgmt_router.post("/keys")
async def create_api_key(request: Request):
    body = await request.json()
    name = (body.get("name") or "API Key").strip()[:64]
    keys = _load_keys()
    kid  = uuid.uuid4().hex[:12]
    raw  = f"aeth-{secrets.token_urlsafe(32)}"
    keys[kid] = {
        "id": kid, "name": name, "key": raw,
        "created_at": utcnow_iso(),
        "last_used": None, "request_count": 0, "enabled": True,
    }
    _save_keys(keys)
    # Return full key ONCE — after this it's preview-only
    return {"id": kid, "name": name, "key": raw, "created_at": keys[kid]["created_at"]}


@mgmt_router.delete("/keys/{key_id}")
async def delete_api_key(key_id: str):
    keys = _load_keys()
    if key_id not in keys:
        raise HTTPException(status_code=404, detail="Key not found")
    del keys[key_id]
    _save_keys(keys)
    return {"success": True}
