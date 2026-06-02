"""
core/automate/nodes/ai.py
Handler functions for all ai.* node types.

Both ai.google and ai.any share the same execution logic — they differ only in
which model options the UI shows. The executor routes both to ai_model().
"""
from __future__ import annotations

import json
import re
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


# Shared helpers

def _simple_ai_call(model_id: str, system_prompt: str, prompt: str,
                    temperature: float = 0.3) -> "any":
    """Minimal AI call used by the focused nodes (summarize, classify, extract)."""
    pm = _get_pm()
    return pm.call_with_failover(
        prompt=prompt,
        trace_id=f"automate-exec-{uuid.uuid4().hex[:8]}",
        system_prompt=system_prompt or None,
        temperature=temperature,
        model=model_id,
        request_type="generation",
        source="automate-execution",
    )


def _extract_json_from_response(text: str) -> dict:
    """
    Pull the first valid JSON object out of an AI response.
    Handles cases where the model adds prose around the JSON.
    """
    # Fast path — response is already clean JSON
    try:
        result = json.loads(text.strip())
        if isinstance(result, dict):
            return result
    except Exception:
        pass

    # Walk the string counting braces to find the outermost {...} block
    start = text.find("{")
    if start == -1:
        return {}
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    result = json.loads(text[start : i + 1])
                    if isinstance(result, dict):
                        return result
                except Exception:
                    break
    return {}


# Focused AI nodes

def ai_summarize(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p        = node.get("properties", {})
    model_id = _to_str(inputs.get("model") or p.get("model", "")).strip()
    if not model_id:
        raise ValueError("ai.summarize: No model selected")

    text     = _to_str(inputs.get("in", ""))
    style    = str(p.get("style", "paragraph"))
    length   = _to_str(inputs.get("length") or p.get("length", "medium"))
    language = str(p.get("language", "")).strip()

    style_map = {
        "paragraph": "Write a clear, concise summary in flowing prose.",
        "bullets":   "Write a bullet-point list summary (use - for each bullet).",
        "headline":  "Write a one-sentence headline followed by a 2-sentence description.",
        "tldr":      "Write a single TL;DR sentence (one line only).",
    }
    length_map = {
        "short":  "Keep the summary to 1–2 sentences.",
        "medium": "Keep the summary to roughly one paragraph.",
        "long":   "Write a thorough summary with multiple paragraphs covering all key points.",
    }

    lang_note = f" Write the summary in {language}." if language else ""
    system = (
        f"You are a professional text summarizer.{lang_note} "
        f"{style_map.get(style, '')} "
        f"{length_map.get(length, '')}"
    ).strip()

    resp = _simple_ai_call(model_id, system, text, temperature=0.3)
    if not resp.success:
        return {"out": "", "error": resp.error or "AI call failed"}
    return {"out": resp.content, "error": ""}


def ai_classify(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p        = node.get("properties", {})
    model_id = _to_str(inputs.get("model") or p.get("model", "")).strip()
    if not model_id:
        raise ValueError("ai.classify: No model selected")

    text       = _to_str(inputs.get("in", ""))
    raw_labels = _to_str(inputs.get("labels") or p.get("labels", ""))
    labels     = [lb.strip() for lb in raw_labels.split(",") if lb.strip()]
    context    = str(p.get("context", "")).strip()

    if not labels:
        return {"label": "", "reasoning": "", "all": "{}", "error": "No categories configured"}

    system = (
        f"You are a text classifier. Classify the given text into exactly one of "
        f"the following categories: {', '.join(labels)}.\n"
        + (f"Context: {context}\n" if context else "")
        + "Respond with ONLY a JSON object in this exact format: "
        '{"label": "<chosen label>", "reasoning": "<one sentence why>"}'
    )

    resp = _simple_ai_call(model_id, system, text, temperature=0.1)
    if not resp.success:
        return {"label": "", "reasoning": "", "all": "{}", "error": resp.error or "AI call failed"}

    parsed    = _extract_json_from_response(resp.content)
    label     = str(parsed.get("label", "")).strip()
    reasoning = str(parsed.get("reasoning", "")).strip()

    # Validate — if AI hallucinated a label not in the list, fall back gracefully
    if label not in labels:
        # Try case-insensitive match
        lower_map = {lb.lower(): lb for lb in labels}
        label = lower_map.get(label.lower(), label or "unknown")

    result = {"label": label, "reasoning": reasoning}
    return {
        "label":     label,
        "reasoning": reasoning,
        "all":       json.dumps(result, ensure_ascii=False),
        "error":     "",
    }


def ai_extract_data(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p        = node.get("properties", {})
    model_id = _to_str(inputs.get("model") or p.get("model", "")).strip()
    if not model_id:
        raise ValueError("ai.extract_data: No model selected")

    text       = _to_str(inputs.get("in", ""))
    fields_raw = _to_str(inputs.get("schema") or p.get("fields", ""))
    context    = str(p.get("context", "")).strip()
    missing    = str(p.get("missing_value", ""))

    # Parse "field_name: description" lines
    field_defs: dict[str, str] = {}
    for line in fields_raw.strip().splitlines():
        if ":" in line:
            key, desc = line.split(":", 1)
            key = key.strip()
            if key:
                field_defs[key] = desc.strip()

    if not field_defs:
        return {"out": "{}", "error": "No fields configured"}

    schema_desc = "\n".join(f'- "{k}": {v}' for k, v in field_defs.items())
    system = (
        f"You are a data extraction assistant."
        + (f" Context: {context}" if context else "")
        + f"\nExtract the following fields from the provided text and return ONLY a valid JSON object:\n"
        + schema_desc
        + f"\nIf a field cannot be found, use {repr(missing)} as its value."
        + "\nReturn ONLY the JSON object, no explanation or extra text."
    )

    resp = _simple_ai_call(model_id, system, text, temperature=0.1)
    if not resp.success:
        return {"out": "{}", "error": resp.error or "AI call failed"}

    parsed = _extract_json_from_response(resp.content)
    if not parsed:
        # AI returned something but we couldn't parse it — return raw with error
        return {"out": resp.content, "error": "Could not parse JSON from AI response"}

    # Fill in missing fields with the configured missing value
    for key in field_defs:
        if key not in parsed:
            parsed[key] = missing

    return {"out": json.dumps(parsed, ensure_ascii=False), "error": ""}
