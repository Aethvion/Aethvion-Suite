"""
core/tools/universal_api_link.py
═════════════════════════════════
Layer 2 — Universal REST API Bridge

Provides a generic HTTP tool that lets any AI agent interact with external
SaaS APIs (Jira, Stripe, Slack, GitHub, etc.) without bespoke Python bridges.

Claude/GPT/Qwen models already know the API structure for most major SaaS
products from training. You just provide the user's API key and the agent
constructs the correct request.

Usage (from agent/tool-call context):
──────────────────────────────────────
    from core.tools.universal_api_link import send_http_request

    # Simple GET
    result = await send_http_request(
        url="https://api.github.com/repos/owner/repo/issues",
        method="GET",
        headers={"Authorization": "Bearer ghp_xxx", "Accept": "application/vnd.github.v3+json"},
    )

    # POST with JSON body
    result = await send_http_request(
        url="https://slack.com/api/chat.postMessage",
        method="POST",
        headers={"Authorization": "Bearer xoxb-xxx"},
        payload={"channel": "#general", "text": "Hello from Aethvion"},
    )

Security
────────
- No credentials are stored here — callers must supply auth headers each call.
- Private-network requests (127.x, 10.x, 192.168.x, ::1) are allowed to
  support self-hosted enterprise software.  Set AETHVION_BLOCK_PRIVATE_HOSTS=1
  to disallow them.
- Request body size is capped at 1 MB by default.
- Timeout is capped at 120 s.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from core.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_BODY_BYTES     = int(os.getenv("AETHVION_API_MAX_BODY",  str(1 * 1024 * 1024)))  # 1 MB
_DEFAULT_TIMEOUT    = int(os.getenv("AETHVION_API_TIMEOUT",   "30"))
_MAX_TIMEOUT        = int(os.getenv("AETHVION_API_MAX_TIMEOUT", "120"))
_BLOCK_PRIVATE      = os.getenv("AETHVION_BLOCK_PRIVATE_HOSTS", "").lower() in ("1", "true", "yes")


# ── Result type ───────────────────────────────────────────────────────────────

class ApiResponse:
    """Structured result from a universal API call."""

    def __init__(
        self,
        *,
        success: bool,
        status_code: int,
        body: Any,
        headers: Dict[str, str],
        error: Optional[str] = None,
        url: str = "",
        method: str = "",
    ):
        self.success     = success
        self.status_code = status_code
        self.body        = body        # parsed JSON or raw text
        self.headers     = headers
        self.error       = error
        self.url         = url
        self.method      = method

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success":     self.success,
            "status_code": self.status_code,
            "body":        self.body,
            "headers":     self.headers,
            "error":       self.error,
            "url":         self.url,
            "method":      self.method,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ApiResponse {self.method} {self.url} → {self.status_code}>"


# ── Main function ─────────────────────────────────────────────────────────────

def send_http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    payload: Optional[Any] = None,
    params: Optional[Dict[str, str]] = None,
    timeout: int = _DEFAULT_TIMEOUT,
    content_type: str = "application/json",
) -> ApiResponse:
    """
    Send an HTTP request to any external API.

    Args:
        url:          Full URL (https://api.example.com/v1/resource).
        method:       HTTP verb — GET, POST, PUT, PATCH, DELETE, HEAD.
        headers:      Dict of request headers.  Auth tokens go here.
        payload:      Request body.  Dicts are JSON-serialised automatically.
                      Pass a string to send raw body.
        params:       URL query parameters (appended to url).
        timeout:      Request timeout in seconds (capped at 120).
        content_type: Content-Type header value (default: application/json).

    Returns:
        ApiResponse with .success, .status_code, .body, .headers, .error.
    """
    method  = method.upper().strip()
    timeout = min(int(timeout), _MAX_TIMEOUT)
    headers = dict(headers or {})

    # Append query string
    if params:
        encoded = urllib.parse.urlencode(params)
        sep     = "&" if "?" in url else "?"
        url     = f"{url}{sep}{encoded}"

    # Serialise body
    body_bytes: Optional[bytes] = None
    if payload is not None:
        if isinstance(payload, (dict, list)):
            body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers.setdefault("Content-Type", content_type)
        elif isinstance(payload, str):
            body_bytes = payload.encode("utf-8")
            headers.setdefault("Content-Type", content_type)
        elif isinstance(payload, bytes):
            body_bytes = payload

        if body_bytes and len(body_bytes) > _MAX_BODY_BYTES:
            return ApiResponse(
                success=False, status_code=0, body=None, headers={},
                error=f"Request body exceeds {_MAX_BODY_BYTES} bytes limit.", url=url, method=method,
            )

    # Private host guard
    if _BLOCK_PRIVATE:
        parsed = urllib.parse.urlparse(url)
        host   = parsed.hostname or ""
        if _is_private_host(host):
            return ApiResponse(
                success=False, status_code=0, body=None, headers={},
                error=f"Private host '{host}' is blocked by AETHVION_BLOCK_PRIVATE_HOSTS policy.",
                url=url, method=method,
            )

    logger.debug(f"[universal_api_link] {method} {url}")

    try:
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers=headers,
            method=method,
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status      = resp.status
            resp_bytes  = resp.read()
            resp_headers = dict(resp.headers)

        body = _parse_body(resp_bytes, resp_headers.get("Content-Type", ""))
        return ApiResponse(
            success=200 <= status < 300,
            status_code=status,
            body=body,
            headers=resp_headers,
            url=url,
            method=method,
        )

    except urllib.error.HTTPError as e:
        resp_bytes = e.read() or b""
        body       = _parse_body(resp_bytes, e.headers.get("Content-Type", "") if e.headers else "")
        logger.warning(f"[universal_api_link] HTTP {e.code} from {url}: {body}")
        return ApiResponse(
            success=False,
            status_code=e.code,
            body=body,
            headers=dict(e.headers) if e.headers else {},
            error=f"HTTP {e.code}: {e.reason}",
            url=url, method=method,
        )

    except urllib.error.URLError as e:
        logger.error(f"[universal_api_link] URLError for {url}: {e.reason}")
        return ApiResponse(
            success=False, status_code=0, body=None, headers={},
            error=f"Connection error: {e.reason}", url=url, method=method,
        )

    except Exception as e:
        logger.error(f"[universal_api_link] Unexpected error for {url}: {e}")
        return ApiResponse(
            success=False, status_code=0, body=None, headers={},
            error=str(e), url=url, method=method,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_body(data: bytes, content_type: str) -> Any:
    """Try to parse response as JSON; fall back to UTF-8 string."""
    if not data:
        return None
    if "json" in content_type.lower():
        try:
            return json.loads(data.decode("utf-8"))
        except Exception:
            pass
    try:
        return data.decode("utf-8")
    except Exception:
        return data.hex()


def _is_private_host(host: str) -> bool:
    import ipaddress
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback
    except ValueError:
        return host in ("localhost", "localhost.localdomain")
