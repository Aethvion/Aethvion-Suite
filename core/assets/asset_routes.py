"""
core/assets/asset_routes.py
REST API for the Asset Library (prefix /api/assets).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import store

router = APIRouter(prefix="/api/assets", tags=["assets"])

_MAX_UPLOAD = 512 * 1024 * 1024  # 512 MB


def _public(rec: dict) -> dict:
    out = dict(rec)
    out["url"] = f"/api/assets/{rec['id']}/file"
    return out


@router.get("")
async def list_assets(kind: str = "", tag: str = "", project: str = "", q: str = "",
                      run_id: str = "", workflow_id: str = "", limit: int = 60, offset: int = 0):
    res = store.list_assets(kind=kind, tag=tag, project=project, query=q, run_id=run_id,
                            workflow_id=workflow_id, limit=min(max(limit, 1), 500), offset=max(offset, 0))
    return {"assets": [_public(r) for r in res["assets"]], "total": res["total"]}


@router.get("/summary")
async def summary():
    """Counts per kind + all tags in use — drives the filter bar."""
    recs = store.list_assets(limit=10_000_000)["assets"]
    kinds: dict[str, int] = {}
    tags: dict[str, int] = {}
    size = 0
    for r in recs:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        size += int(r.get("size_bytes") or 0)
        for t in r.get("tags", []):
            tags[t] = tags.get(t, 0) + 1
    return {"total": len(recs), "size_bytes": size, "kinds": kinds, "tags": tags}


@router.get("/{asset_id}")
async def get_asset(asset_id: str):
    rec = store.get(asset_id)
    if not rec:
        raise HTTPException(404, "Asset not found")
    lin = store.lineage(asset_id)
    return {
        "asset": _public(rec),
        "ancestors":   [_public(r) for r in lin["ancestors"]],
        "descendants": [_public(r) for r in lin["descendants"]],
    }


@router.get("/{asset_id}/file")
async def get_asset_file(asset_id: str, download: bool = False):
    rec = store.get(asset_id)
    if not rec or not Path(rec["path"]).is_file():
        raise HTTPException(404, "Asset file not found")
    filename = f"{rec['name']}.{rec['ext']}" if download else None
    return FileResponse(rec["path"], media_type=rec["mime"], filename=filename)


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    tags: Optional[list[str]] = None
    project: Optional[str] = None


@router.patch("/{asset_id}")
async def update_asset(asset_id: str, body: AssetUpdate):
    rec = store.update(asset_id, name=body.name, tags=body.tags, project=body.project)
    if not rec:
        raise HTTPException(404, "Asset not found")
    return {"asset": _public(rec)}


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str):
    if not store.delete(asset_id):
        raise HTTPException(404, "Asset not found")
    return {"ok": True}


class ExportBody(BaseModel):
    target_dir: str
    filename: str = ""
    overwrite: bool = True


@router.post("/{asset_id}/export")
async def export_asset(asset_id: str, body: ExportBody):
    if not body.target_dir.strip():
        raise HTTPException(400, "target_dir is required")
    try:
        dest = store.export(asset_id, body.target_dir, body.filename, body.overwrite)
    except KeyError:
        raise HTTPException(404, "Asset not found")
    except OSError as exc:
        raise HTTPException(400, f"Export failed: {exc}")
    return {"ok": True, "path": str(dest)}


@router.post("/upload")
async def upload_asset(file: UploadFile = File(...), tags: str = Form(""), project: str = Form("")):
    data = await file.read()
    if len(data) > _MAX_UPLOAD:
        raise HTTPException(413, "File too large")
    fname = Path(file.filename or "upload.bin")
    rec = store.create_from_bytes(
        data, ext=fname.suffix.lstrip(".") or "bin", name=fname.stem,
        source={"type": "upload"}, project=project,
        tags=[t for t in tags.split(",") if t.strip()],
    )
    return {"asset": _public(rec)}
