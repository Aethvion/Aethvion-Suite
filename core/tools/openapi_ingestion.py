"""
core/tools/openapi_ingestion.py
════════════════════════════════
Layer 3 — OpenAPI / Swagger Ingestion

Parses an OpenAPI 3.x or Swagger 2.x JSON/YAML spec and converts it into a
compact, agent-readable prompt fragment that describes the available endpoints.

The agent reads this fragment, then uses universal_api_link.send_http_request()
to call the correct endpoint without any hand-written Python bridge.

Usage
──────
    from core.tools.openapi_ingestion import load_openapi_spec, build_agent_context

    spec   = load_openapi_spec("/path/to/openapi.json")          # from file
    spec   = load_openapi_spec("https://petstore.swagger.io/v2/swagger.json")  # from URL
    context = build_agent_context(spec, base_url="https://api.mycompany.com")
    # Inject `context` into the agent's system prompt.

Dashboard API
─────────────
    POST /api/openapi/load    body: { "source": "<path or url>" }
    GET  /api/openapi/specs   → list of loaded specs (in-memory cache)
    GET  /api/openapi/<id>    → agent context string for a spec
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/openapi", tags=["openapi"])

# In-memory spec cache: id → {"meta": {...}, "context": str}
_SPEC_CACHE: Dict[str, Dict] = {}


# ── Public Python API ─────────────────────────────────────────────────────────

def load_openapi_spec(source: str) -> Dict:
    """
    Load an OpenAPI/Swagger spec from a local file path or a URL.

    Returns the parsed spec dict (raw).
    Raises ValueError on parse failure.
    """
    raw: Optional[str] = None

    if source.startswith("http://") or source.startswith("https://"):
        import urllib.request
        try:
            with urllib.request.urlopen(source, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
        except Exception as e:
            raise ValueError(f"Failed to fetch spec from {source}: {e}")
    else:
        path = Path(source)
        if not path.exists():
            raise ValueError(f"Spec file not found: {source}")
        raw = path.read_text(encoding="utf-8")

    return _parse_spec_text(raw, source)


def build_agent_context(
    spec: Dict,
    base_url: Optional[str] = None,
    max_endpoints: int = 80,
) -> str:
    """
    Convert a parsed OpenAPI spec into a compact prompt fragment.

    The fragment includes:
      - API title, version, and base URL
      - Each endpoint: METHOD /path — summary  (request/response hints)
      - Auth scheme hints

    Args:
        spec:           Parsed spec dict (from load_openapi_spec).
        base_url:       Override base URL (e.g. from user config).
        max_endpoints:  Truncate after this many endpoints to avoid token bloat.

    Returns:
        String ready to inject into an agent system prompt.
    """
    lines: List[str] = []
    title, version, resolved_base = _extract_meta(spec, base_url)

    lines.append(f"=== API: {title} (v{version}) ===")
    lines.append(f"Base URL: {resolved_base}")
    lines.append("")

    # Auth hints
    auth_hint = _extract_auth_hint(spec)
    if auth_hint:
        lines.append(f"Auth: {auth_hint}")
        lines.append("")

    # Endpoints
    paths = spec.get("paths", {})
    count = 0
    for path, path_item in sorted(paths.items()):
        if not isinstance(path_item, dict):
            continue
        for method in ["get", "post", "put", "patch", "delete", "head", "options"]:
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue

            summary = op.get("summary") or op.get("description") or ""
            summary = summary.strip().split("\n")[0][:120]  # first line, max 120 chars

            # Required query/body params summary
            params = _summarise_params(op, spec)

            line = f"  {method.upper():7} {path}"
            if summary:
                line += f"  — {summary}"
            if params:
                line += f"  [{params}]"
            lines.append(line)
            count += 1

            if count >= max_endpoints:
                remaining = sum(
                    1 for p, pi in paths.items() if isinstance(pi, dict)
                    for m in ["get", "post", "put", "patch", "delete"]
                    if isinstance(pi.get(m), dict)
                ) - max_endpoints
                if remaining > 0:
                    lines.append(f"  … and {remaining} more endpoints (increase max_endpoints to see all)")
                break
        else:
            continue
        break  # only break outer if inner hit limit

    lines.append("")
    lines.append(
        "To call these endpoints use send_http_request(url, method, headers, payload). "
        f"Prepend '{resolved_base}' to each path."
    )

    return "\n".join(lines)


# ── FastAPI routes ────────────────────────────────────────────────────────────

class LoadSpecRequest(BaseModel):
    source: str        # file path or URL
    base_url: Optional[str] = None
    label: Optional[str] = None


@router.post("/load")
async def load_spec(req: LoadSpecRequest):
    """Load an OpenAPI spec and store it in the in-memory cache."""
    try:
        spec    = load_openapi_spec(req.source)
        context = build_agent_context(spec, base_url=req.base_url)
        title, version, base = _extract_meta(spec, req.base_url)

        spec_id = hashlib.md5(req.source.encode()).hexdigest()[:10]
        _SPEC_CACHE[spec_id] = {
            "id":      spec_id,
            "source":  req.source,
            "label":   req.label or title,
            "title":   title,
            "version": version,
            "base_url": base,
            "endpoint_count": _count_endpoints(spec),
            "context": context,
        }
        logger.info(f"[openapi] Loaded spec '{title}' ({spec_id}) from {req.source}")
        return {
            "success":  True,
            "id":       spec_id,
            "title":    title,
            "version":  version,
            "base_url": base,
            "endpoint_count": _SPEC_CACHE[spec_id]["endpoint_count"],
            "context_preview": context[:500] + ("…" if len(context) > 500 else ""),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[openapi] Failed to load spec: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/specs")
async def list_specs():
    """Return metadata for all loaded specs."""
    return {
        "specs": [
            {k: v for k, v in s.items() if k != "context"}
            for s in _SPEC_CACHE.values()
        ]
    }


@router.get("/{spec_id}")
async def get_spec_context(spec_id: str):
    """Return the full agent-context string for a loaded spec."""
    if spec_id not in _SPEC_CACHE:
        raise HTTPException(status_code=404, detail=f"Spec '{spec_id}' not found.")
    return {"id": spec_id, "context": _SPEC_CACHE[spec_id]["context"]}


@router.delete("/{spec_id}")
async def delete_spec(spec_id: str):
    """Remove a spec from the cache."""
    if spec_id not in _SPEC_CACHE:
        raise HTTPException(status_code=404, detail=f"Spec '{spec_id}' not found.")
    del _SPEC_CACHE[spec_id]
    return {"success": True}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _parse_spec_text(raw: str, source: str) -> Dict:
    # Try JSON first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Try YAML
    try:
        import yaml  # pyyaml is a common dep; may not always be present
        return yaml.safe_load(raw)
    except ImportError:
        pass
    except Exception:
        pass
    raise ValueError(f"Could not parse spec as JSON or YAML: {source}")


def _extract_meta(spec: Dict, base_url_override: Optional[str] = None) -> Tuple[str, str, str]:
    info    = spec.get("info", {})
    title   = info.get("title", "Unknown API")
    version = info.get("version", "?")

    if base_url_override:
        base = base_url_override.rstrip("/")
    elif "servers" in spec:
        # OpenAPI 3.x
        servers = spec["servers"]
        base = servers[0].get("url", "") if servers else ""
    else:
        # Swagger 2.x
        scheme = (spec.get("schemes") or ["https"])[0]
        host   = spec.get("host", "")
        bp     = spec.get("basePath", "/")
        base   = f"{scheme}://{host}{bp}".rstrip("/") if host else ""

    return title, version, base


def _extract_auth_hint(spec: Dict) -> str:
    # OpenAPI 3.x
    components = spec.get("components", {})
    sec_schemes = components.get("securitySchemes", {})
    if not sec_schemes:
        # Swagger 2.x
        sec_schemes = spec.get("securityDefinitions", {})

    hints = []
    for name, scheme in sec_schemes.items():
        t = scheme.get("type", "")
        if t == "http":
            hints.append(f"{name}: HTTP {scheme.get('scheme','bearer')} (Authorization header)")
        elif t == "apiKey":
            hints.append(f"{name}: API Key in {scheme.get('in','header')} '{scheme.get('name','key')}'")
        elif t == "oauth2":
            hints.append(f"{name}: OAuth2")
        else:
            hints.append(f"{name}: {t}")
    return "; ".join(hints)


def _summarise_params(op: Dict, spec: Dict) -> str:
    required = []
    params = op.get("parameters", [])
    for p in params:
        if isinstance(p, dict) and p.get("required"):
            required.append(f"{p.get('in','?')}:{p.get('name','?')}")

    # Request body (OpenAPI 3.x)
    rb = op.get("requestBody", {})
    if rb.get("required"):
        content = rb.get("content", {})
        if "application/json" in content:
            required.append("body:json")
        elif content:
            required.append(f"body:{next(iter(content))}")

    return ", ".join(required[:6])  # cap at 6 to keep line short


def _count_endpoints(spec: Dict) -> int:
    count = 0
    for _, path_item in spec.get("paths", {}).items():
        if isinstance(path_item, dict):
            count += sum(1 for m in ["get","post","put","patch","delete","head"]
                         if isinstance(path_item.get(m), dict))
    return count
