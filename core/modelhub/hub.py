"""
core/modelhub/hub.py
The single entry point for running a model of any kind.

    from core.modelhub import hub
    result = hub.invoke("3d:trellis-2", "mesh.generate", image=concept_ref, prompt="a rusty sword")
    result.ok, result.text, result.assets, result.error

Every file an endpoint produces is stored in the Asset Library with lineage (which
endpoint, which capability, which input assets, and — when called from a workflow —
which workflow / run / node).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from core.assets import store, values
from core.utils.logger import get_logger

from . import registry
from .adapters import ADAPTERS, EndpointError, InvokeRequest
from .capabilities import CAPABILITIES, output_kind

logger = get_logger(__name__)


@dataclass
class InvokeResult:
    ok: bool
    endpoint: str = ""
    capability: str = ""
    text: str = ""
    assets: list[dict] = field(default_factory=list)   # asset records
    data: Any = None
    error: str = ""
    duration_ms: float = 0.0

    @property
    def refs(self) -> list[dict]:
        return [store.asset_ref(a) for a in self.assets]

    def to_dict(self) -> dict:
        return {
            "ok": self.ok, "endpoint": self.endpoint, "capability": self.capability,
            "text": self.text, "assets": self.refs, "error": self.error,
            "duration_ms": self.duration_ms,
        }


def invoke(
    endpoint_id: str,
    capability: str = "",
    *,
    prompt: str = "",
    system_prompt: str = "",
    negative_prompt: str = "",
    image: Any = None,
    mesh: Any = None,
    audio: Any = None,
    params: Optional[dict] = None,
    source: Optional[dict] = None,
    name: str = "",
    tags: Optional[list[str]] = None,
    project: str = "",
    cancel: Optional[Callable[[], bool]] = None,
    log: Optional[Callable[[str], None]] = None,
) -> InvokeResult:
    """Run *endpoint_id* and return its output.  Never raises for endpoint failures."""
    t0 = time.perf_counter()

    def _fail(msg: str) -> InvokeResult:
        return InvokeResult(ok=False, endpoint=endpoint_id, capability=capability, error=msg,
                            duration_ms=round((time.perf_counter() - t0) * 1000, 1))

    if not endpoint_id:
        return _fail("No model endpoint selected.")
    endpoint = registry.resolve(endpoint_id, capability)
    if not endpoint:
        return _fail(f"Unknown model endpoint '{endpoint_id}'. Open Model Hub to see what is available.")
    if not capability:
        capability = endpoint["capabilities"][0]
    if capability not in CAPABILITIES:
        return _fail(f"Unknown capability '{capability}'.")
    if capability not in endpoint["capabilities"] and "custom" not in endpoint["capabilities"]:
        return _fail(f"'{endpoint['name']}' does not support {capability} "
                     f"(it supports: {', '.join(endpoint['capabilities'])}).")
    if not endpoint.get("available", True):
        return _fail(f"'{endpoint['name']}' is not available: {endpoint.get('reason') or 'unknown reason'}")

    adapter = ADAPTERS.get(endpoint["adapter"])
    if not adapter:
        return _fail(f"No adapter for endpoint type '{endpoint['adapter']}'.")

    req = InvokeRequest(
        capability=capability, prompt=prompt or "", system_prompt=system_prompt or "",
        negative_prompt=negative_prompt or "", image=image, mesh=mesh, audio=audio,
        params=dict(params or {}), cancel=cancel, log=log,
    )

    try:
        raw = adapter(endpoint, req)
    except EndpointError as exc:
        return _fail(str(exc))
    except Exception as exc:  # noqa: BLE001 — an endpoint bug must not take the workflow down
        logger.exception("modelhub: endpoint %s crashed", endpoint["id"])
        return _fail(f"{type(exc).__name__}: {exc}")

    parents = [pid for pid in (values.asset_id_of(image), values.asset_id_of(mesh), values.asset_id_of(audio)) if pid]
    src = {"type": "modelhub", **(source or {}), "endpoint": endpoint["id"], "capability": capability}
    out_kind = (endpoint.get("definition") or {}).get("output", {}).get("kind") or output_kind(capability)

    assets: list[dict] = []
    for i, f in enumerate(raw.files):
        kind = f.kind or (out_kind if store.kind_for_ext(f.ext) == "file" else store.kind_for_ext(f.ext))
        base = name or f.name or _name_from_prompt(prompt, kind)
        assets.append(store.create_from_bytes(
            f.data, ext=f.ext, kind=kind,
            name=base if len(raw.files) == 1 else f"{base}_{i + 1}",
            source=src, parents=parents, tags=tags, project=project,
            meta={k: v for k, v in {
                "prompt": prompt[:2000] if prompt else "",
                "negative_prompt": negative_prompt[:500] if negative_prompt else "",
                "params": {k: v for k, v in req.params.items() if isinstance(v, (str, int, float, bool))},
                "model": raw.model,
            }.items() if v},
        ))

    return InvokeResult(
        ok=True, endpoint=endpoint["id"], capability=capability, text=raw.text, assets=assets,
        data=raw.data, duration_ms=round((time.perf_counter() - t0) * 1000, 1),
    )


def _name_from_prompt(prompt: str, kind: str) -> str:
    words = "".join(c if c.isalnum() or c == " " else " " for c in (prompt or "")).split()
    return ("_".join(words[:6]).lower()[:48] or kind) if words else kind
