"""
core/tools/webhook_link.py
═══════════════════════════
Layer 4 — Webhook / n8n Hand-off

Sends a structured JSON payload to an automation platform (n8n, Make, Zapier,
or any webhook receiver) so that Aethvion agents can trigger complex cross-platform
workflows without native integrations.

Strategy
─────────
  Aethvion → webhook_link → n8n / Make / Zapier → Stripe / Jira / Slack / …

The agent decides WHAT to do; the automation platform handles the actual
multi-step API calls to third-party services.

Usage
──────
    from core.tools.webhook_link import trigger_webhook, register_webhook

    # Register a named webhook (persisted in data/config/webhooks.json)
    register_webhook("refund_customer", url="https://n8n.mycompany.com/webhook/abc123",
                     description="Refund a customer in Stripe via n8n")

    # Trigger by name
    result = await trigger_webhook("refund_customer",
                                   payload={"action": "refund", "customer": "John", "amount": 49.99})

    # Or trigger by URL directly (no registration needed)
    result = await trigger_webhook(url="https://hooks.zapier.com/hooks/catch/123/abc",
                                   payload={"event": "user_signup", "email": "user@example.com"})

Dashboard API
─────────────
    GET  /api/webhooks              → list registered webhooks
    POST /api/webhooks/register     → register a new webhook
    POST /api/webhooks/trigger/{id} → fire a registered webhook
    POST /api/webhooks/trigger      → fire by URL (body: {url, payload, ...})
    DELETE /api/webhooks/{id}       → remove a webhook
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

_ROOT           = Path(__file__).parent.parent.parent
_WEBHOOKS_FILE  = _ROOT / "data" / "config" / "webhooks.json"
_DEFAULT_TIMEOUT = int(os.getenv("AETHVION_WEBHOOK_TIMEOUT", "30"))


# ── Schemas ───────────────────────────────────────────────────────────────────

class WebhookResult:
    def __init__(self, *, success: bool, status_code: int, body: Any,
                 webhook_id: str = "", url: str = "", error: Optional[str] = None):
        self.success     = success
        self.status_code = status_code
        self.body        = body
        self.webhook_id  = webhook_id
        self.url         = url
        self.error       = error
        self.timestamp   = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> Dict:
        return {
            "success":     self.success,
            "status_code": self.status_code,
            "body":        self.body,
            "webhook_id":  self.webhook_id,
            "url":         self.url,
            "error":       self.error,
            "timestamp":   self.timestamp,
        }


class RegisterRequest(BaseModel):
    name: str
    url: str
    description: str = ""
    secret_header: Optional[str] = None     # e.g. "X-Webhook-Secret"
    secret_value: Optional[str] = None      # value for the secret header
    method: str = "POST"
    extra_headers: Optional[Dict[str, str]] = None


class TriggerByUrlRequest(BaseModel):
    url: str
    payload: Optional[Dict[str, Any]] = None
    method: str = "POST"
    headers: Optional[Dict[str, str]] = None
    timeout: int = _DEFAULT_TIMEOUT


class TriggerByIdRequest(BaseModel):
    payload: Optional[Dict[str, Any]] = None
    extra_payload: Optional[Dict[str, Any]] = None  # merged into payload
    timeout: int = _DEFAULT_TIMEOUT


# ── Persistence helpers ───────────────────────────────────────────────────────

def _load_webhooks() -> Dict[str, Dict]:
    if not _WEBHOOKS_FILE.exists():
        return {}
    try:
        return json.loads(_WEBHOOKS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_webhooks(data: Dict[str, Dict]) -> None:
    _WEBHOOKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _WEBHOOKS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Public Python API ─────────────────────────────────────────────────────────

def register_webhook(
    name: str,
    url: str,
    description: str = "",
    secret_header: Optional[str] = None,
    secret_value: Optional[str] = None,
    method: str = "POST",
    extra_headers: Optional[Dict[str, str]] = None,
) -> str:
    """Register a named webhook. Returns the generated webhook ID."""
    webhooks = _load_webhooks()
    wh_id = str(uuid.uuid4())[:8]
    webhooks[wh_id] = {
        "id":             wh_id,
        "name":           name,
        "url":            url,
        "description":    description,
        "method":         method.upper(),
        "secret_header":  secret_header,
        "secret_value":   secret_value,
        "extra_headers":  extra_headers or {},
        "created_at":     datetime.utcnow().isoformat() + "Z",
        "trigger_count":  0,
        "last_triggered": None,
    }
    _save_webhooks(webhooks)
    logger.info(f"[webhook_link] Registered webhook '{name}' → {url} (id: {wh_id})")
    return wh_id


def trigger_webhook(
    webhook_id: Optional[str] = None,
    url: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    method: str = "POST",
    timeout: int = _DEFAULT_TIMEOUT,
) -> WebhookResult:
    """
    Fire a webhook by registered ID or direct URL.

    At least one of `webhook_id` or `url` must be provided.
    If both are provided, `webhook_id` takes precedence.
    """
    import urllib.request, urllib.error

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    resolved_url = url or ""
    resolved_id  = webhook_id or "adhoc"

    if webhook_id:
        webhooks = _load_webhooks()
        entry    = webhooks.get(webhook_id)
        if not entry:
            return WebhookResult(success=False, status_code=0, body=None,
                                  webhook_id=webhook_id, error=f"Webhook '{webhook_id}' not found.")
        resolved_url = entry["url"]
        method       = entry.get("method", "POST")
        if entry.get("secret_header") and entry.get("secret_value"):
            headers[entry["secret_header"]] = entry["secret_value"]
        headers.update(entry.get("extra_headers") or {})

        # Update stats
        entry["trigger_count"]  = entry.get("trigger_count", 0) + 1
        entry["last_triggered"] = datetime.utcnow().isoformat() + "Z"
        webhooks[webhook_id] = entry
        _save_webhooks(webhooks)

    if extra_headers:
        headers.update(extra_headers)

    if not resolved_url:
        return WebhookResult(success=False, status_code=0, body=None,
                              webhook_id=resolved_id, error="No URL provided.")

    body_bytes = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    logger.info(f"[webhook_link] Firing {method} → {resolved_url} "
                f"(payload keys: {list((payload or {}).keys())})")

    try:
        req = urllib.request.Request(
            resolved_url,
            data=body_bytes,
            headers=headers,
            method=method,
        )
        with urllib.request.urlopen(req, timeout=min(timeout, 120)) as resp:
            status = resp.status
            resp_body = resp.read()
        try:
            body = json.loads(resp_body.decode("utf-8"))
        except Exception:
            body = resp_body.decode("utf-8", errors="replace")

        return WebhookResult(
            success=200 <= status < 300,
            status_code=status,
            body=body,
            webhook_id=resolved_id,
            url=resolved_url,
        )

    except urllib.error.HTTPError as e:
        body_raw = e.read() or b""
        try:
            body = json.loads(body_raw.decode("utf-8"))
        except Exception:
            body = body_raw.decode("utf-8", errors="replace")
        return WebhookResult(success=False, status_code=e.code, body=body,
                              webhook_id=resolved_id, url=resolved_url,
                              error=f"HTTP {e.code}: {e.reason}")

    except urllib.error.URLError as e:
        return WebhookResult(success=False, status_code=0, body=None,
                              webhook_id=resolved_id, url=resolved_url,
                              error=f"Connection error: {e.reason}")

    except Exception as e:
        return WebhookResult(success=False, status_code=0, body=None,
                              webhook_id=resolved_id, url=resolved_url, error=str(e))


# ── FastAPI routes ────────────────────────────────────────────────────────────

@router.get("")
async def list_webhooks():
    """Return all registered webhooks (secrets are masked)."""
    webhooks = _load_webhooks()
    safe = []
    for wh in webhooks.values():
        entry = dict(wh)
        if entry.get("secret_value"):
            entry["secret_value"] = "***"
        safe.append(entry)
    return {"webhooks": safe}


@router.post("/register")
async def register_webhook_endpoint(req: RegisterRequest):
    """Register a new named webhook."""
    wh_id = register_webhook(
        name=req.name,
        url=req.url,
        description=req.description,
        secret_header=req.secret_header,
        secret_value=req.secret_value,
        method=req.method,
        extra_headers=req.extra_headers,
    )
    return {"success": True, "id": wh_id, "name": req.name}


@router.post("/trigger")
async def trigger_by_url(req: TriggerByUrlRequest):
    """Fire a webhook by URL (no registration required)."""
    result = trigger_webhook(
        url=req.url,
        payload=req.payload,
        extra_headers=req.headers,
        method=req.method,
        timeout=req.timeout,
    )
    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "Webhook failed")
    return result.to_dict()


@router.post("/trigger/{webhook_id}")
async def trigger_by_id(webhook_id: str, req: TriggerByIdRequest):
    """Fire a registered webhook by its ID."""
    payload = dict(req.payload or {})
    if req.extra_payload:
        payload.update(req.extra_payload)

    result = trigger_webhook(
        webhook_id=webhook_id,
        payload=payload,
        timeout=req.timeout,
    )
    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "Webhook failed")
    return result.to_dict()


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str):
    """Remove a registered webhook."""
    webhooks = _load_webhooks()
    if webhook_id not in webhooks:
        raise HTTPException(status_code=404, detail=f"Webhook '{webhook_id}' not found.")
    name = webhooks[webhook_id].get("name", webhook_id)
    del webhooks[webhook_id]
    _save_webhooks(webhooks)
    return {"success": True, "message": f"Webhook '{name}' deleted."}
