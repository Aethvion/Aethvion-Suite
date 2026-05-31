"""
Aethvion Suite - Utils Package
Utilities for tracing, logging, and validation
"""

from datetime import datetime, timezone as _tz
import json as _json
import os as _os
import tempfile as _tempfile
from pathlib import Path as _Path
from typing import Union as _Union


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO 8601 string with Z suffix.

    Format: 2026-04-04T14:30:45.123456Z
    Always UTC, always microsecond precision, always the 'Z' suffix.
    Use this everywhere a timestamp is stored so the format is consistent.
    """
    return datetime.now(_tz.utc).strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z'


def atomic_json_write(
    path: _Union[str, "_Path"],
    data: _Union[dict, list],
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> None:
    """Write *data* as JSON to *path* atomically.

    Writes to a temporary file in the same directory, then renames it into
    place.  This prevents a partial / corrupt file being left on disk if the
    process is killed mid-write.  ``os.replace()`` is atomic on POSIX and
    near-atomic on Windows (uses MoveFileEx MOVEFILE_REPLACE_EXISTING).

    Args:
        path: Destination file path (``str`` or ``Path``).
        data: JSON-serialisable ``dict`` or ``list``.
        indent: JSON indent level (default 2).
        ensure_ascii: Passed through to ``json.dump`` (default False → keep
            Unicode characters as-is).

    Raises:
        Whatever ``json.dump`` or ``os.replace`` raises on genuine failure.
    """
    path = _Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = _tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with _os.fdopen(fd, "w", encoding="utf-8") as f:
            _json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
        _os.replace(tmp_path, str(path))
    except Exception:
        try:
            _os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_json(
    path: _Union[str, "_Path"],
    default=None,
) -> _Union[dict, list, None]:
    """Load JSON from *path*, returning *default* on missing file or parse error.

    Args:
        path:    File to read.
        default: Value returned when the file is absent or unreadable.
                 Pass ``{}`` for dicts, ``[]`` for lists.
    """
    path = _Path(path)
    if not path.exists():
        return default
    try:
        return _json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        import logging as _std_logging
        _std_logging.getLogger(__name__).warning("Failed to load %s: %s", path, exc)
        return default


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

    # I/O helpers
    'atomic_json_write',
    'load_json',

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
