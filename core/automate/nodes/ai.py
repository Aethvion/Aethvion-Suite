"""
core/automate/nodes/ai.py
══════════════════════════
Handler functions for all ai.* node types.

Both ai.google and ai.any share the same execution logic — they differ only in
which model options the UI shows. The executor routes both to ai_model().
"""
from __future__ import annotations

import uuid
from typing import Any

from ._utils import _to_str, _get_pm


def ai_model(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Shared handler for ai.google and ai.any."""
    p = node.get("properties", {})

    def _inp(port: str, prop_key: str, default: str = "") -> str:
        """Port value takes priority; falls back to node property."""
        wired = _to_str(inputs.get(port, "")).strip()
        return wired if wired else str(p.get(prop_key, default)).strip()

    model_id      = _inp("model",         "model")
    system_prompt = _inp("system_prompt", "system_prompt", "") or None
    prefix        = _inp("prompt_prefix", "prompt_prefix")
    suffix        = _inp("prompt_suffix", "prompt_suffix")
    in_val        = _to_str(inputs.get("in", ""))

    # Temperature: wired port overrides property
    _temp_raw = inputs.get("temperature")
    try:
        temperature = float(_temp_raw) if _temp_raw not in (None, "") else float(p.get("temperature", 0.7))
    except (ValueError, TypeError):
        temperature = float(p.get("temperature", 0.7))

    if not model_id:
        raise ValueError("No model selected — open node properties and pick a model.")

    parts  = [x for x in [prefix, in_val, suffix] if x]
    prompt = "\n\n".join(parts) if parts else "(no input)"

    pm   = _get_pm()
    resp = pm.call_with_failover(
        prompt=prompt,
        trace_id=f"automate-exec-{uuid.uuid4().hex[:8]}",
        system_prompt=system_prompt,
        temperature=temperature,
        model=model_id,
        request_type="generation",
        source="automate-execution",
    )

    if not resp.success:
        return {"out": "", "error": resp.error or "AI call failed"}
    return {"out": resp.content, "error": ""}
