import os
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(MODULE_DIR, "..", ".."))
for p in (MODULE_DIR, PROJECT_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from apps.audio.audio_core import audio_session

# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Aethvion Audio Editor", version="1.0.0")
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

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def get_status():
    has_file = audio_session.current is not None
    return JSONResponse({
        "status": "running",
        "has_file": has_file,
        "filename": audio_session.filename if has_file else None,
    })

# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@app.post("/api/audio/upload")
async def upload_audio(file: UploadFile = File(...)):
    """Upload an audio file and load it into the session."""
    data = await file.read()
    try:
        info = audio_session.load(data, file.filename)
        waveform = audio_session.get_waveform()
        return JSONResponse({"success": True, "info": info, "waveform": waveform})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

# ---------------------------------------------------------------------------
# Info & Waveform
# ---------------------------------------------------------------------------

@app.get("/api/audio/info")
async def get_info():
    if audio_session.current is None:
        return JSONResponse({"error": "No file loaded"}, status_code=404)
    return JSONResponse(audio_session._get_info())

@app.get("/api/audio/waveform")
async def get_waveform(points: int = 2000):
    if audio_session.current is None:
        return JSONResponse({"error": "No file loaded"}, status_code=404)
    return JSONResponse({"waveform": audio_session.get_waveform(points)})

# ---------------------------------------------------------------------------
# Preview (stream current audio as WAV)
# ---------------------------------------------------------------------------

@app.get("/api/audio/preview")
async def preview_audio():
    if audio_session.current is None:
        raise HTTPException(status_code=404, detail="No file loaded")
    data = audio_session.get_audio_bytes("wav")
    return Response(
        content=data,
        media_type="audio/wav",
        headers={"Content-Disposition": 'inline; filename="preview.wav"'},
    )

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@app.get("/api/audio/export")
async def export_audio(format: str = "wav"):
    if audio_session.current is None:
        raise HTTPException(status_code=404, detail="No file loaded")
    fmt = format.lower()
    if fmt not in ("wav", "mp3", "ogg"):
        raise HTTPException(status_code=400, detail="Unsupported format")
    try:
        data = audio_session.get_audio_bytes(fmt)
        stem = Path(audio_session.filename).stem or "export"
        mime = {"wav": "audio/wav", "mp3": "audio/mpeg", "ogg": "audio/ogg"}.get(fmt, "audio/wav")
        return Response(
            content=data,
            media_type=mime,
            headers={"Content-Disposition": f'attachment; filename="{stem}_edited.{fmt}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

class OperationRequest(BaseModel):
    op: str
    params: Optional[dict] = {}

@app.post("/api/audio/operation")
async def apply_operation(req: OperationRequest):
    """Apply an audio editing operation."""
    if audio_session.current is None:
        return JSONResponse({"success": False, "error": "No file loaded"}, status_code=400)

    op = req.op
    p = req.params or {}

    try:
        if op == "trim":
            info = audio_session.trim(p.get("start_ms", 0), p.get("end_ms", len(audio_session.current)))
        elif op == "fade_in":
            info = audio_session.fade_in(p.get("duration_ms", 1000))
        elif op == "fade_out":
            info = audio_session.fade_out(p.get("duration_ms", 1000))
        elif op == "normalize":
            info = audio_session.do_normalize()
        elif op == "reverse":
            info = audio_session.reverse()
        elif op == "volume":
            info = audio_session.change_volume(p.get("db", 0))
        elif op == "speed":
            info = audio_session.change_speed(p.get("rate", 1.0))
        elif op == "silence":
            info = audio_session.silence_region(p.get("start_ms", 0), p.get("end_ms", 0))
        elif op == "crop_silence":
            info = audio_session.crop_silence(p.get("threshold_db", -50.0))
        elif op == "stereo_to_mono":
            info = audio_session.stereo_to_mono()
        elif op == "mono_to_stereo":
            info = audio_session.mono_to_stereo()
        elif op == "resample":
            info = audio_session.resample(p.get("sample_rate", 44100))
        else:
            return JSONResponse({"success": False, "error": f"Unknown operation: {op}"}, status_code=400)

        waveform = audio_session.get_waveform()
        return JSONResponse({"success": True, "info": info, "waveform": waveform})

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

# ---------------------------------------------------------------------------
# Undo / Reset
# ---------------------------------------------------------------------------

@app.post("/api/audio/undo")
async def undo():
    if audio_session.current is None:
        return JSONResponse({"success": False, "error": "No file loaded"}, status_code=400)
    info = audio_session.undo()
    if info is None:
        return JSONResponse({"success": False, "error": "Nothing to undo"})
    waveform = audio_session.get_waveform()
    return JSONResponse({"success": True, "info": info, "waveform": waveform})

@app.post("/api/audio/reset")
async def reset():
    if audio_session.original is None:
        return JSONResponse({"success": False, "error": "No file loaded"}, status_code=400)
    info = audio_session.reset()
    waveform = audio_session.get_waveform()
    return JSONResponse({"success": True, "info": info, "waveform": waveform})

# ---------------------------------------------------------------------------
# Front-end
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    idx = VIEWER_DIR / "index.html"
    return idx.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

def launch():
    from core.utils.port_manager import PortManager
    base_port = int(os.getenv("AUDIO_PORT", "8083"))
    port = PortManager.bind_port("Aethvion Audio", base_port)
    print(f"🔊 Aethvion Audio Editor → http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    launch()
