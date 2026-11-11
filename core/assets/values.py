"""
core/assets/values.py
Turn any value that can arrive on a workflow wire into something usable.

A "media value" may be:
    • an asset ref dict            {"__asset__": True, "id": ..., "path": ...}
    • a JSON string of an asset ref (after passing through a text-only node)
    • an asset id                  "ast_1a2b3c4d5e6f"
    • a local file path
    • a data URI                   "data:image/png;base64,...."
    • raw bytes
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Optional

from . import store


def is_asset_ref(val: Any) -> bool:
    return isinstance(val, dict) and val.get("__asset__") is True and bool(val.get("id"))


def as_asset_ref(val: Any) -> Optional[dict]:
    """Return an asset ref if *val* identifies a stored asset, else None."""
    if is_asset_ref(val):
        return val
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("ast_") and len(s) <= 20:
            rec = store.get(s)
            return store.asset_ref(rec) if rec else None
        if s.startswith("{") and '"__asset__"' in s:
            try:
                obj = json.loads(s)
            except ValueError:
                return None
            return obj if is_asset_ref(obj) else None
    return None


def asset_id_of(val: Any) -> str:
    ref = as_asset_ref(val)
    return ref["id"] if ref else ""


def read_media(val: Any) -> Optional[tuple[bytes, str, str]]:
    """Return (bytes, mime, ext) for a media value, or None if it can't be resolved."""
    if val is None or val == "":
        return None
    if isinstance(val, (bytes, bytearray)):
        return bytes(val), "application/octet-stream", "bin"

    ref = as_asset_ref(val)
    if ref:
        p = Path(ref["path"])
        if p.is_file():
            return p.read_bytes(), ref.get("mime") or store.mime_for_ext(p.suffix), p.suffix.lstrip(".")
        return None

    if isinstance(val, dict):
        # tolerate {"path": ...} / {"url": "data:..."} shaped dicts
        val = val.get("path") or val.get("image") or val.get("url") or ""

    if isinstance(val, str):
        s = val.strip()
        if s.startswith("data:") and "," in s:
            header, b64 = s.split(",", 1)
            mime = header[5:].split(";")[0] or "application/octet-stream"
            try:
                return base64.b64decode(b64), mime, store.ext_for_mime(mime)
            except ValueError:
                return None
        p = Path(s)
        try:
            if p.is_file():
                ext = p.suffix.lstrip(".").lower()
                return p.read_bytes(), store.mime_for_ext(ext), ext
        except OSError:
            return None
    return None


def local_path(val: Any) -> str:
    """Best-effort local file path for a media value ('' if there is none)."""
    ref = as_asset_ref(val)
    if ref:
        return ref.get("path", "")
    if isinstance(val, str):
        s = val.strip()
        try:
            if s and not s.startswith("data:") and Path(s).is_file():
                return s
        except OSError:
            return ""
    return ""


def to_base64(val: Any) -> str:
    media = read_media(val)
    return base64.b64encode(media[0]).decode() if media else ""


def to_data_uri(val: Any) -> str:
    media = read_media(val)
    if not media:
        return ""
    data, mime, _ = media
    return f"data:{mime};base64," + base64.b64encode(data).decode()
