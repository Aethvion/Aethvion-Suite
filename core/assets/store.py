"""
core/assets/store.py
Asset Library — permanent, typed storage for everything a model produces.

Layout (under data/assets/):
    files/YYYY-MM/<asset_id>.<ext>     the file itself
    meta/<asset_id>.json               one metadata record per asset

An asset record:
    id          "ast_<12 hex>"
    kind        text | image | mesh | audio | video | json | file
    name        human-readable name
    ext, mime, path, size_bytes, created_at
    source      where it came from: {type, workflow_id, workflow_name, run_id,
                node_id, node_label, endpoint, capability}
    parents     ids of the assets this one was derived from (lineage)
    tags        free-form labels
    project     optional project id (Studio, phase 3)
    meta        free-form details (prompt, seed, stats…)

Values that travel along workflow wires are *asset refs* — small dicts produced by
``asset_ref()``.  See core/assets/values.py for the helpers that turn any wire
value (ref, id, file path, data URI) back into bytes or a local path.
"""
from __future__ import annotations

import mimetypes
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from core.utils import atomic_json_write, load_json, utcnow_iso
from core.utils.paths import DATA

ASSETS_ROOT = DATA / "assets"
_FILES_DIR  = ASSETS_ROOT / "files"
_META_DIR   = ASSETS_ROOT / "meta"

KINDS = ("text", "image", "mesh", "audio", "video", "json", "file")

_EXT_KIND: dict[str, str] = {
    # images
    "png": "image", "jpg": "image", "jpeg": "image", "webp": "image", "gif": "image",
    "bmp": "image", "tga": "image", "tif": "image", "tiff": "image", "exr": "image",
    # meshes
    "glb": "mesh", "gltf": "mesh", "obj": "mesh", "fbx": "mesh", "stl": "mesh",
    "ply": "mesh", "usdz": "mesh", "usd": "mesh", "blend": "mesh", "3mf": "mesh",
    # audio
    "wav": "audio", "mp3": "audio", "ogg": "audio", "flac": "audio", "m4a": "audio",
    # video
    "mp4": "video", "webm": "video", "mov": "video", "mkv": "video",
    # text / data
    "txt": "text", "md": "text", "json": "json", "csv": "text", "yaml": "text", "yml": "text",
}

_EXTRA_MIME: dict[str, str] = {
    "glb": "model/gltf-binary", "gltf": "model/gltf+json", "obj": "model/obj",
    "fbx": "application/octet-stream", "stl": "model/stl", "ply": "application/octet-stream",
    "usdz": "model/vnd.usdz+zip", "webp": "image/webp", "md": "text/markdown",
    "exr": "image/x-exr", "tga": "image/x-tga",
}

_lock = threading.RLock()
_cache: dict[str, dict] | None = None      # id -> record; loaded lazily, kept in sync


# Kind / mime helpers

def kind_for_ext(ext: str) -> str:
    return _EXT_KIND.get(ext.lower().lstrip("."), "file")


def mime_for_ext(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    if ext in _EXTRA_MIME:
        return _EXTRA_MIME[ext]
    return mimetypes.guess_type(f"x.{ext}")[0] or "application/octet-stream"


def ext_for_mime(mime: str, default: str = "bin") -> str:
    mime = (mime or "").split(";")[0].strip().lower()
    for ext, m in _EXTRA_MIME.items():
        if m == mime and mime != "application/octet-stream":
            return ext
    guess = mimetypes.guess_extension(mime) if mime else None
    if guess:
        return {"jpe": "jpg", "jpeg": "jpg"}.get(guess.lstrip("."), guess.lstrip("."))
    return default


# Internal index

def _load_all() -> dict[str, dict]:
    global _cache
    with _lock:
        if _cache is None:
            _cache = {}
            if _META_DIR.exists():
                for p in _META_DIR.glob("*.json"):
                    rec = load_json(p, default=None)
                    if isinstance(rec, dict) and rec.get("id"):
                        _cache[rec["id"]] = rec
        return _cache


def _save(rec: dict) -> None:
    _META_DIR.mkdir(parents=True, exist_ok=True)
    atomic_json_write(_META_DIR / f"{rec['id']}.json", rec)
    with _lock:
        _load_all()[rec["id"]] = rec


def _new_id() -> str:
    return f"ast_{uuid.uuid4().hex[:12]}"


def _safe_name(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in " -_." else "_" for c in (name or "")).strip()
    return keep[:80] or "asset"


# Public API — create

def create_from_bytes(
    data: bytes,
    *,
    ext: str,
    kind: Optional[str] = None,
    name: str = "",
    source: Optional[dict] = None,
    parents: Optional[Iterable[str]] = None,
    tags: Optional[Iterable[str]] = None,
    meta: Optional[dict] = None,
    project: str = "",
) -> dict:
    """Store *data* as a new asset and return its record."""
    ext  = (ext or "bin").lower().lstrip(".")
    kind = kind if kind in KINDS else kind_for_ext(ext)
    aid  = _new_id()

    folder = _FILES_DIR / datetime.now().strftime("%Y-%m")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{aid}.{ext}"
    path.write_bytes(data)

    rec = {
        "id":         aid,
        "kind":       kind,
        "name":       _safe_name(name) if name else f"{kind}-{aid[-6:]}",
        "ext":        ext,
        "mime":       mime_for_ext(ext),
        "path":       str(path),
        "size_bytes": len(data),
        "created_at": utcnow_iso(),
        "source":     dict(source or {}),
        "parents":    [p for p in (parents or []) if p],
        "tags":       sorted({str(t).strip() for t in (tags or []) if str(t).strip()}),
        "project":    project or "",
        "meta":       dict(meta or {}),
    }
    _save(rec)
    return rec


def create_from_file(path: str | Path, **kwargs: Any) -> dict:
    """Copy an existing file into the library and return the new asset record."""
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"File not found: {src}")
    kwargs.setdefault("name", src.stem)
    kwargs.setdefault("ext", src.suffix.lstrip(".") or "bin")
    return create_from_bytes(src.read_bytes(), **kwargs)


def create_text(text: str, *, name: str = "", ext: str = "txt", **kwargs: Any) -> dict:
    return create_from_bytes(text.encode("utf-8"), ext=ext, name=name, **kwargs)


# Public API — read

def get(asset_id: str) -> Optional[dict]:
    return _load_all().get(asset_id)


def list_assets(
    *,
    kind: str = "",
    tag: str = "",
    project: str = "",
    query: str = "",
    run_id: str = "",
    workflow_id: str = "",
    limit: int = 60,
    offset: int = 0,
) -> dict:
    """Return {"assets": [...], "total": n}, newest first."""
    q = query.strip().lower()
    items = []
    for rec in _load_all().values():
        if kind and rec.get("kind") != kind:
            continue
        if tag and tag not in rec.get("tags", []):
            continue
        if project and rec.get("project") != project:
            continue
        src = rec.get("source") or {}
        if run_id and src.get("run_id") != run_id:
            continue
        if workflow_id and src.get("workflow_id") != workflow_id:
            continue
        if q:
            hay = " ".join([
                rec.get("name", ""), " ".join(rec.get("tags", [])),
                str(src.get("endpoint", "")), str(src.get("workflow_name", "")),
                str((rec.get("meta") or {}).get("prompt", "")),
            ]).lower()
            if q not in hay:
                continue
        items.append(rec)
    items.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    total = len(items)
    return {"assets": items[offset: offset + max(1, limit)], "total": total}


def lineage(asset_id: str) -> dict:
    """Return the ancestors and descendants of an asset (each a flat list of records)."""
    allrecs = _load_all()
    ancestors: list[dict] = []
    seen: set[str] = {asset_id}
    queue = list((allrecs.get(asset_id) or {}).get("parents", []))
    while queue:
        pid = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        rec = allrecs.get(pid)
        if rec:
            ancestors.append(rec)
            queue.extend(rec.get("parents", []))

    descendants: list[dict] = []
    seen_d: set[str] = {asset_id}
    frontier = {asset_id}
    while frontier:
        nxt: set[str] = set()
        for rec in allrecs.values():
            if rec["id"] in seen_d:
                continue
            if frontier & set(rec.get("parents", [])):
                descendants.append(rec)
                seen_d.add(rec["id"])
                nxt.add(rec["id"])
        frontier = nxt
    descendants.sort(key=lambda r: r.get("created_at", ""))
    return {"ancestors": ancestors, "descendants": descendants}


# Public API — update / delete

def update(asset_id: str, *, name: Optional[str] = None, tags: Optional[Iterable[str]] = None,
           project: Optional[str] = None, meta: Optional[dict] = None) -> Optional[dict]:
    with _lock:
        rec = get(asset_id)
        if not rec:
            return None
        rec = dict(rec)
        if name is not None:
            rec["name"] = _safe_name(name)
        if tags is not None:
            rec["tags"] = sorted({str(t).strip() for t in tags if str(t).strip()})
        if project is not None:
            rec["project"] = project
        if meta:
            rec["meta"] = {**(rec.get("meta") or {}), **meta}
        _save(rec)
        return rec


def delete(asset_id: str) -> bool:
    with _lock:
        rec = get(asset_id)
        if not rec:
            return False
        try:
            Path(rec["path"]).unlink(missing_ok=True)
        except OSError:
            pass
        (_META_DIR / f"{asset_id}.json").unlink(missing_ok=True)
        _load_all().pop(asset_id, None)
        return True


def export(asset_id: str, target_dir: str | Path, filename: str = "", overwrite: bool = True) -> Path:
    """Copy an asset's file into *target_dir* (e.g. a game project's Assets folder)."""
    rec = get(asset_id)
    if not rec:
        raise KeyError(f"Unknown asset: {asset_id}")
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    fname = filename.strip() or f"{rec['name']}.{rec['ext']}"
    if "." not in Path(fname).name:
        fname = f"{fname}.{rec['ext']}"
    dest = target / Path(fname).name
    if dest.exists() and not overwrite:
        stem, suffix, i = dest.stem, dest.suffix, 1
        while dest.exists():
            dest = target / f"{stem}_{i}{suffix}"
            i += 1
    shutil.copyfile(rec["path"], dest)
    return dest


# Wire value

def asset_ref(rec: dict) -> dict:
    """The compact value that flows between workflow nodes for an asset."""
    return {
        "__asset__": True,
        "id":   rec["id"],
        "kind": rec["kind"],
        "name": rec["name"],
        "ext":  rec["ext"],
        "mime": rec["mime"],
        "path": rec["path"],
        "url":  f"/api/assets/{rec['id']}/file",
    }
