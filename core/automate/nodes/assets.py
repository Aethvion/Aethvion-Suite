"""
core/automate/nodes/assets.py
Asset Library nodes.

    asset.save     store text, a file path or a data URI as a library asset
    asset.load     fetch an existing asset (by id) or import a file from disk
    asset.export   copy an asset into a folder — e.g. a game project's Assets directory
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ._utils import _to_str
from .models import fail, _tags


def asset_save(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    from core.assets import store, values  # noqa: PLC0415

    p    = node.get("properties", {})
    val  = inputs.get("in")
    name = _to_str(inputs.get("name") or p.get("name", "")).strip()
    tags = _tags(p.get("tags"))
    if val in (None, ""):
        return fail(ctx, node, "Nothing to save — the input is empty.", ("out", "id", "path", "url"))

    ref = values.as_asset_ref(val)
    if ref:
        # Already in the library: just apply the name / tags from this node.
        rec = store.get(ref["id"])
        if rec and (name or tags):
            rec = store.update(ref["id"], name=name or None, tags=sorted(set(rec.get("tags", [])) | set(tags)))
            ref = store.asset_ref(rec)
    else:
        source = ctx.asset_source(node)
        media  = values.read_media(val) if isinstance(val, (str, bytes, bytearray)) else None
        if media:
            data, _mime, ext = media
            rec = store.create_from_bytes(data, ext=ext, name=name or (Path(val).stem if isinstance(val, str) and not val.startswith("data:") else ""),
                                          source=source, tags=tags)
        else:
            is_struct = isinstance(val, (dict, list))
            ext = str(p.get("format", "") or "").strip().lstrip(".") or ("json" if is_struct else "txt")
            rec = store.create_text(_to_str(val), name=name, ext=ext, source=source, tags=tags)
        ref = store.asset_ref(rec)

    return {"out": ref, "id": ref["id"], "path": ref["path"], "url": ref["url"], "error": ""}


def asset_load(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    from core.assets import store, values  # noqa: PLC0415

    ports = ("out", "id", "path", "url", "kind", "text")
    p   = node.get("properties", {})
    key = _to_str(inputs.get("in") or p.get("asset", "")).strip()
    if not key:
        return fail(ctx, node, "No asset id or file path given.", ports)

    ref = values.as_asset_ref(key)
    if not ref:
        path = Path(key)
        if not path.is_file():
            return fail(ctx, node, f"'{key}' is neither a known asset id nor an existing file.", ports)
        rec = store.create_from_file(path, source={**ctx.asset_source(node), "imported_from": str(path)},
                                     tags=_tags(p.get("tags")))
        ref = store.asset_ref(rec)

    text = None
    if ref["kind"] in ("text", "json"):
        media = values.read_media(ref)
        text = media[0].decode("utf-8", errors="replace") if media else None
    return {"out": ref, "id": ref["id"], "path": ref["path"], "url": ref["url"],
            "kind": ref["kind"], "text": text, "error": ""}


def asset_export(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    from core.assets import store, values  # noqa: PLC0415

    ports = ("out", "path")
    p      = node.get("properties", {})
    val    = inputs.get("in")
    folder = _to_str(inputs.get("folder") or p.get("target_dir", "")).strip()
    fname  = _to_str(inputs.get("filename") or p.get("filename", "")).strip()
    if val in (None, ""):
        return fail(ctx, node, "Nothing to export — the input is empty.", ports)
    if not folder:
        raise ValueError("No target folder set — open the node's properties and choose one.")

    ref = values.as_asset_ref(val)
    if not ref:
        # Accept a plain file path / data URI by importing it first so the export is tracked.
        media = values.read_media(val)
        if not media:
            return fail(ctx, node, "Input is not an asset, file path or data URI.", ports)
        rec = store.create_from_bytes(media[0], ext=media[2], source=ctx.asset_source(node))
        ref = store.asset_ref(rec)

    try:
        dest = store.export(ref["id"], folder, fname, overwrite=p.get("overwrite", True) is not False)
    except OSError as exc:
        return fail(ctx, node, f"Export failed: {exc}", ports)
    store.update(ref["id"], meta={"exported_to": str(dest)})
    ctx._info(f"    Exported to {dest}")
    return {"out": ref, "path": str(dest), "error": ""}


def input_image(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Feed a picture you already have into a workflow.

    The Image property accepts a file path, an Asset Library id, or a data URI.  A file
    is imported into the library the first time and reused on later runs as long as it
    has not changed on disk, so re-running a workflow does not pile up copies.
    """
    from core.assets import store, values  # noqa: PLC0415

    ports = ("image", "out", "path", "width", "height")
    p   = node.get("properties", {})
    key = _to_str(inputs.get("in") or p.get("image", "")).strip().strip('"')
    if not key:
        raise ValueError("No image chosen — open the node's properties and pick an image file "
                         "(or paste an asset id).")

    ref = values.as_asset_ref(key)
    if not ref:
        if key.startswith("data:"):
            media = values.read_media(key)
            if not media:
                return fail(ctx, node, "The pasted image data could not be decoded.", ports)
            rec = store.create_from_bytes(media[0], ext=media[2], name=str(p.get("name", "") or "image"),
                                          source={**ctx.asset_source(node), "type": "image-input"})
        else:
            path = Path(key)
            if not path.is_file():
                return fail(ctx, node, f"Image file not found: {key}", ports)
            stat = path.stat()
            stamp = f"{stat.st_size}:{int(stat.st_mtime)}"
            rec = next((r for r in store.list_assets(kind="image", limit=100000)["assets"]
                        if (r.get("source") or {}).get("imported_from") == str(path)
                        and (r.get("meta") or {}).get("file_stamp") == stamp), None)
            if rec is None:
                rec = store.create_from_file(
                    path, source={"type": "image-input", "imported_from": str(path)},
                    meta={"file_stamp": stamp}, tags=_tags(p.get("tags")),
                )
        ref = store.asset_ref(rec)

    if ref["kind"] != "image":
        return fail(ctx, node, f"'{ref['name']}.{ref['ext']}' is a {ref['kind']} file, not an image.", ports)

    width = height = None
    try:
        from PIL import Image  # noqa: PLC0415
        with Image.open(ref["path"]) as im:
            width, height = im.size
    except Exception:  # noqa: BLE001 — size is a convenience; exotic formats may not open
        pass
    return {"image": ref, "out": ref, "path": ref["path"], "width": width, "height": height, "error": ""}
