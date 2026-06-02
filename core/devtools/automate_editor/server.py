"""
core/devtools/automate_editor/server.py
────────────────────────────────────────
Aethvion Dev Tool — Automate Workflow Editor

Standalone FastAPI server that mounts the existing automate_routes router
but redirects both _EXAMPLES_DIR and _DATA_DIR to core/automate/config/ so
that every workflow saved here IS the shipped default — no copy-paste needed.

Run with:
    python -m core.devtools.automate_editor.server
or via:
    Launch_AutomateEditor.bat

Port: 8002
"""
from __future__ import annotations

import sys
from pathlib import Path

# Project root on sys.path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Patch automate_routes BEFORE importing its router
# Both the "examples" directory and the user "data" directory are redirected to
# core/automate/config/ so saves go directly into the shipped defaults.
CONFIG_DIR = PROJECT_ROOT / "core" / "automate" / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

import core.automate.automate_routes as _ar  # noqa: E402

_ar._EXAMPLES_DIR = CONFIG_DIR   # /api/automate/examples/* reads from here
_ar._DATA_DIR     = CONFIG_DIR   # /api/automate/workflows/* reads/writes here

# FastAPI app
import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.responses import HTMLResponse, FileResponse  # noqa: E402

STATIC_DIR   = Path(__file__).parent / "static"
DASH_STATIC  = PROJECT_ROOT / "core" / "interfaces" / "dashboard" / "static"
PARTIALS_DIR = DASH_STATIC / "partials"

app = FastAPI(title="Aethvion Dev — Automate Editor", docs_url=None, redoc_url=None)

# Mount the live automate router (already patched above)
app.include_router(_ar.router)

# Serve our own index page
@app.get("/", response_class=HTMLResponse)
async def root():
    idx = STATIC_DIR / "index.html"
    return FileResponse(str(idx))

# Serve dashboard static assets (CSS, JS, fonts …)
app.mount("/static", StaticFiles(directory=str(DASH_STATIC)), name="static")

# Entry point
if __name__ == "__main__":
    port = 8002
    print("\n" + "=" * 58)
    print("  Aethvion Dev Tool — Automate Workflow Editor")
    print(f"  URL  : http://localhost:{port}")
    print(f"  Dir  : {CONFIG_DIR}")
    print("  Saves go directly to core/automate/config/")
    print("=" * 58 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=port)