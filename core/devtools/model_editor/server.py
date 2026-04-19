"""
core/devtools/model_editor/server.py
------------------------------------
Internal devtool for editing model defaults via a web interface.
Run with: python -m core.devtools.model_editor.server
"""

import json
import os
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pathlib import Path
from typing import Dict, Any, List

# Setup paths (now 4 levels deep from root)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
MODEL_DEFAULTS_DIR = PROJECT_ROOT / "core" / "config" / "model_defaults"
SUGGESTED_DIR = MODEL_DEFAULTS_DIR / "suggested"
DEFAULTS_JSON = MODEL_DEFAULTS_DIR / "defaults.json"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Aethvion Model Defaults Editor")

# Routes
@app.get("/api/providers")
async def list_providers():
    """List all provider files in the suggested directory."""
    providers = []
    for file in SUGGESTED_DIR.glob("*.json"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                p_id = file.stem
                if p_id in data:
                    providers.append({
                        "id": p_id,
                        "name": data[p_id].get("name", p_id.title()),
                        "file": str(file.relative_to(PROJECT_ROOT))
                    })
        except Exception:
            continue
    return sorted(providers, key=lambda x: x["name"])

@app.get("/api/provider/{provider_id}")
async def get_provider_models(provider_id: str):
    """Get the full content of a provider's suggested models file."""
    file_path = SUGGESTED_DIR / f"{provider_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Provider file not found")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

@app.post("/api/provider/{provider_id}")
async def save_provider_models(provider_id: str, data: Dict[str, Any]):
    """Save the updated suggested models for a provider."""
    file_path = SUGGESTED_DIR / f"{provider_id}.json"
    
    # Ensure structure is { provider_id: { ... } }
    if provider_id not in data:
        # If they sent the inner object directly, wrap it
        data = { provider_id: data }
        
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/defaults")
async def get_defaults():
    """Get the content of defaults.json."""
    if not DEFAULTS_JSON.exists():
        return {}
    with open(DEFAULTS_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)

@app.post("/api/defaults")
async def save_defaults(data: Dict[str, List[str]]):
    """Save the updated defaults.json."""
    try:
        with open(DEFAULTS_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def serve_ui():
    """Serve the main UI page."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("UI not found. Please create core/devtools/static/index.html")
    return FileResponse(index_path)

# Serve other static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    print("\n" + "="*50)
    print("  Aethvion Model Defaults Editor - DEVTOOL")
    print("  URL: http://localhost:8001")
    print("="*50 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8001)
