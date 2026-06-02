"""
core/automate/nodes/logic.py
Handler functions for all logic.* node types.
"""
from __future__ import annotations

import json
import time
from typing import Any

from ._utils import _to_str, _safe_eval


def logic_if(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p         = node.get("properties", {})
    in_val    = inputs.get("in", "")
    condition = str(p.get("condition", "")).strip()
    try:
        result = bool(_safe_eval(condition, {"value": in_val, "input": in_val}))
    except Exception:
        result = bool(in_val)
    return {
        "true":  in_val if result     else None,
        "false": in_val if not result else None,
    }


def logic_delay(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p  = node.get("properties", {})
    ms = float(p.get("duration", 1000))
    time.sleep(min(ms / 1000.0, 10.0))   # cap at 10 s to prevent runaway waits
    return {"trigger": inputs.get("in", "")}


def logic_loop(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    items = inputs.get("in", [])
    if not isinstance(items, list):
        try:
            items = json.loads(_to_str(items))
        except Exception:
            items = [items]
    first = items[0] if items else None
    return {"item": first, "done": items}


def logic_try_catch(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p          = node.get("properties", {})
    in_val     = inputs.get("in", "")
    error_val  = str(inputs.get("error_in", "") or "").strip()
    filter_str = str(p.get("error_contains", "")).strip()

    is_error = bool(error_val)
    if filter_str and is_error:
        is_error = filter_str.lower() in error_val.lower()

    if is_error:
        return {"try": None, "catch": error_val, "always": error_val}
    return {"try": in_val, "catch": None, "always": in_val}


def logic_switch(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p      = node.get("properties", {})
    in_val = inputs.get("in", "")

    # Optionally extract a sub-field from the input before comparing
    key = str(p.get("switch_on", "")).strip()
    if key:
        try:
            obj = json.loads(_to_str(in_val)) if isinstance(in_val, str) else in_val
            compare_val = str(obj.get(key, ""))
        except Exception:
            compare_val = _to_str(in_val)
    else:
        compare_val = _to_str(in_val)

    num     = max(1, min(4, int(p.get("num_cases", 2))))
    result  = {f"case_{i}": None for i in range(1, 5)}
    result["default"] = None
    matched = False

    for i in range(1, num + 1):
        if not matched and compare_val == str(p.get(f"case_{i}", "")):
            result[f"case_{i}"] = in_val
            matched = True

    if not matched:
        result["default"] = in_val

    return result


def logic_repeat(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p      = node.get("properties", {})
    in_val = inputs.get("in", "")
    try:
        count = max(1, min(500, int(p.get("count", 1))))
    except (ValueError, TypeError):
        count = 1
    items = [in_val] * count
    return {"out": items, "count": count}


def logic_merge(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p    = node.get("properties", {})
    mode = str(p.get("mode", "first"))

    if mode == "all":
        collected = {
            port: inputs[port]
            for port in ("a", "b", "c", "d")
            if inputs.get(port) is not None
        }
        return {"out": collected, "source": "all"}

    # "first" mode — pass through the first non-null branch in order a→b→c→d
    for port in ("a", "b", "c", "d"):
        val = inputs.get(port)
        if val is not None:
            return {"out": val, "source": port}

    return {"out": None, "source": ""}
