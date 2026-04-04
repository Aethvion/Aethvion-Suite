"""
Aethvion Suite - Utils Package
Utilities for tracing, logging, and validation
"""

from datetime import datetime, timezone as _tz


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO 8601 string with Z suffix.

    Format: 2026-04-04T14:30:45.123456Z
    Always UTC, always microsecond precision, always the 'Z' suffix.
    Use this everywhere a timestamp is stored so the format is consistent.
    """
    return datetime.now(_tz.utc).strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z'


from .trace_manager import (
    TraceManager,
    get_trace_manager,
    generate_trace_id,
    get_current_trace_id
)

from .logger import (
    AethvionLogger,
    get_logger
)

from .validators import (
    AethvionNamingValidator,
    InputValidator,
    validate_tool_name,
    suggest_tool_name
)

__all__ = [
    # Time
    'utcnow_iso',

    # Trace Management
    'TraceManager',
    'get_trace_manager',
    'generate_trace_id',
    'get_current_trace_id',

    # Logging
    'AethvionLogger',
    'get_logger',

    # Validation
    'AethvionNamingValidator',
    'InputValidator',
    'validate_tool_name',
    'suggest_tool_name',
]
