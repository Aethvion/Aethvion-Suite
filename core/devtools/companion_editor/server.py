"""
core/devtools/companion_editor/server.py
────────────────────────────────────────
Aethvion Dev Tool — Companion Editor

Standalone FastAPI server that mounts the existing companion_creator_routes
router but redirects both _CUSTOM_DIR and _CORE_CONFIG_DIR to
core/companions/configs/ so that:

  • All companions in configs/ appear as editable (no "built-in" lock)
  • Saves go directly back to configs/ — the shipped defaults
  • simple_companion.json is treated as just another companion file

Run with:
    python -m core.devtools.companion_editor.server
or via:
    Launch_CompanionEditor.bat

Port: 8003
"""
from __future__ import annotations

import sys
from pathlib import Path

# Project root on sys.path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Patch companion_creator_routes BEFORE importing its router
# Both _CUSTOM_DIR (user-created) and _CORE_CONFIG_DIR (built-ins) are pointed
# at the same configs/ directory so every companion is fully editable.
CONFIGS_DIR = PROJECT_ROOT / "core" / "companions" / "configs"
CONFIGS_DIR.mkdir(parents=True, exist_ok=True)

import core.companions.companion_creator_routes as _cr  # noqa: E402

# Redirect both dirs → same folder; companion_creator_routes reads/writes _CUSTOM_DIR
_cr._CUSTOM_DIR      = CONFIGS_DIR
_cr._CORE_CONFIG_DIR = CONFIGS_DIR

# Also point the utils.paths.COMPANIONS constant that _CUSTOM_DIR was initialised from
# (the mkdir call at module import already ran, so we just need the variable reassigned)
# No side-effects from this — it's only used for mkdir at module-load time.

# FastAPI app
import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.responses import HTMLResponse, FileResponse  # noqa: E402

STATIC_DIR  = Path(__file__).parent / "static"
DASH_STATIC = PROJECT_ROOT / "core" / "interfaces" / "dashboard" / "static"

app = FastAPI(title="Aethvion Dev — Companion Editor", docs_url=None, redoc_url=None)

# Mount the patched companion creator router
app.include_router(_cr.router)

# Serve our own index page
@app.get("/", response_class=HTMLResponse)
async def root():
    idx = STATIC_DIR / "index.html"
    return FileResponse(str(idx))

# Serve dashboard static assets (CSS, JS …)
app.mount("/static", StaticFiles(directory=str(DASH_STATIC)), name="static")

# Entry point
if __name__ == "__main__":
    port = 8003
    print("\n" + "=" * 58)
    print("  Aethvion Dev Tool — Companion Editor")
    print(f"  URL  : http://localhost:{port}")
    print(f"  Dir  : {CONFIGS_DIR}")
    print("  Saves go directly to core/companions/configs/")
    print("=" * 58 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=port)
