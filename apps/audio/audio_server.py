import os
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from core.utils import fastapi_utils
from pydantic import BaseModel
from typing import Optional, List

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(MODULE_DIR, "..", ".."))
for p in (MODULE_DIR, PROJECT_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from apps.audio.audio_core import session

# App

app = FastAPI(title="Aethvion Audio Editor", version="2.0.0")
fastapi_utils.add_dev_cache_control(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
VIEWER_DIR = BASE_DIR / "viewer"
app.mount("/viewer", StaticFiles(directory=str(VIEWER_DIR)), name="viewer")

# Status & Session

@app.get("/api/status")
async def get_status():
    return JSONResponse({"status": "running", "track_count": len(session._tracks)})


@app.get("/api/session")
async def get_session():
    return JSONResponse(session.to_dict())


class WorkspaceUpdate(BaseModel):
    workspace_ms: float


@app.post("/api/session/workspace")
async def set_workspace(body: WorkspaceUpdate):
    session.set_workspace(body.workspace_ms)
    return JSONResponse({"workspace_ms": session.workspace_ms})

# Track CRUD

@app.post("/api/tracks/upload")
async def upload_track(
    file: UploadFile = File(...),
    start_ms: Optional[float] = Form(None),
    name: Optional[str] = Form(None),
):
    data = await file.read()
    try:
        track = session.add_track(data, file.filename, start_ms=start_ms)
        if name:
            track.name = name
        return JSONResponse({
            "success": True,
            "track": track.to_dict(),
            "session": session.to_dict(),
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)


@app.delete("/api/tracks/{track_id}")
async def remove_track(track_id: str):
    if not session.remove_track(track_id):
        raise HTTPException(404, "Track not found")
    return JSONResponse({"success": True, "session": session.to_dict()})


class TrackPatch(BaseModel):
    name: Optional[str] = None
    muted: Optional[bool] = None
    start_ms: Optional[float] = None


@app.patch("/api/tracks/{track_id}")
async def patch_track(track_id: str, body: TrackPatch):
    track = session.get_track(track_id)
    if not track:
        raise HTTPException(404, "Track not found")
    if body.name is not None:
        track.name = body.name
    if body.muted is not None:
        track.muted = body.muted
    if body.start_ms is not None:
        track.start_ms = max(0.0, body.start_ms)
        session._auto_expand()
    return JSONResponse({"success": True, "track": track.to_dict(), "session": session.to_dict()})


class ReorderTracks(BaseModel):
    order: List[str]


@app.post("/api/tracks/reorder")
async def reorder_tracks(body: ReorderTracks):
    session.reorder_tracks(body.order)
    return JSONResponse({"success": True, "session": session.to_dict()})

# Per-track preview

@app.get("/api/tracks/{track_id}/preview")
async def track_preview(track_id: str):
    track = session.get_track(track_id)
    if not track:
        raise HTTPException(404, "Track not found")
    import io as _io
    buf = _io.BytesIO()
    track.get_rendered().export(buf, format="wav")
    return Response(
        content=buf.getvalue(),
        media_type="audio/wav",
        headers={"Content-Disposition": f'inline; filename="{track.name}.wav"'},
    )

# Effects (non-destructive, per-track)

class EffectAdd(BaseModel):
    op: str
    params: Optional[dict] = {}


@app.post("/api/tracks/{track_id}/effects")
async def add_effect(track_id: str, body: EffectAdd):
    track = session.get_track(track_id)
    if not track:
        raise HTTPException(404, "Track not found")
    fx = track.add_effect(body.op, body.params or {})
    return JSONResponse({"success": True, "effect": fx, "track": track.to_dict()})


class EffectPatch(BaseModel):
    enabled: Optional[bool] = None
    params: Optional[dict] = None


@app.patch("/api/tracks/{track_id}/effects/{effect_id}")
async def patch_effect(track_id: str, effect_id: str, body: EffectPatch):
    track = session.get_track(track_id)
    if not track:
        raise HTTPException(404, "Track not found")
    fx = track.get_effect(effect_id)
    if not fx:
        raise HTTPException(404, "Effect not found")
    if body.enabled is not None:
        fx["enabled"] = body.enabled
    if body.params is not None:
        fx["params"].update(body.params)
    return JSONResponse({"success": True, "effect": fx, "track": track.to_dict()})


@app.delete("/api/tracks/{track_id}/effects/{effect_id}")
async def remove_effect(track_id: str, effect_id: str):
    track = session.get_track(track_id)
    if not track:
        raise HTTPException(404, "Track not found")
    if not track.remove_effect(effect_id):
        raise HTTPException(404, "Effect not found")
    return JSONResponse({"success": True, "track": track.to_dict()})


class ReorderEffects(BaseModel):
    order: List[str]


@app.post("/api/tracks/{track_id}/effects/reorder")
async def reorder_effects(track_id: str, body: ReorderEffects):
    track = session.get_track(track_id)
    if not track:
        raise HTTPException(404, "Track not found")
    track.reorder_effects(body.order)
    return JSONResponse({"success": True, "track": track.to_dict()})

# Mix preview & export

@app.get("/api/preview")
async def mix_preview():
    if not session._tracks:
        raise HTTPException(400, "No tracks loaded")
    try:
        data = session.get_mix_bytes("wav")
        return Response(
            content=data,
            media_type="audio/wav",
            headers={"Content-Disposition": 'inline; filename="mix.wav"'},
        )
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/export")
async def mix_export(format: str = "wav"):
    if not session._tracks:
        raise HTTPException(400, "No tracks loaded")
    fmt = format.lower()
    if fmt not in ("wav", "mp3", "ogg"):
        raise HTTPException(400, "Unsupported format")
    try:
        data = session.get_mix_bytes(fmt)
        mime = {"wav": "audio/wav", "mp3": "audio/mpeg", "ogg": "audio/ogg"}[fmt]
        return Response(
            content=data,
            media_type=mime,
            headers={"Content-Disposition": f'attachment; filename="mix.{fmt}"'},
        )
    except Exception as e:
        raise HTTPException(500, str(e))

# Front-end

@app.get("/", response_class=HTMLResponse)
async def index():
    return (VIEWER_DIR / "index.html").read_text(encoding="utf-8")

# Launch

def launch():
    from core.utils.port_manager import PortManager
    base_port = int(os.getenv("AUDIO_PORT", "8085"))
    port = PortManager.bind_port("Aethvion Audio", base_port)
    print(f"🔊 Aethvion Audio Editor → http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    launch()
