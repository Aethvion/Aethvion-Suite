"""
core/automate/nodes/_utils.py
══════════════════════════════
Shared utilities for all node implementations.
Imported by every category file — keep this lean.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from core.providers import get_provider_manager as _get_pm  # noqa: PLC0415


# Timestamp

def _now() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


# Value coercion

def _to_str(val: Any) -> str:
    """Coerce any value to a string, serialising dicts/lists as JSON."""
    if isinstance(val, str):
        return val
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


# Safe expression evaluator

def _safe_eval(expr: str, local_vars: dict) -> Any:
    """Evaluate a simple expression in a restricted namespace (no builtins)."""
    safe_builtins = {
        "len": len, "str": str, "int": int, "float": float,
        "bool": bool, "list": list, "dict": dict,
        "True": True, "False": False,
    }
    return eval(expr, {"__builtins__": safe_builtins}, local_vars)  # noqa: S307