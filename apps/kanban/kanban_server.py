"""
Aethvion Kanban — FastAPI Server
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Optional

# Ensure both the project root and this app's directory are importable
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent.parent))            # project root for core.*

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from core.utils import fastapi_utils

app = FastAPI(title="Aethvion Kanban", version="1.0.0")
fastapi_utils.add_dev_cache_control(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VIEWER_DIR = Path(__file__).parent / "viewer"
app.mount("/viewer", StaticFiles(directory=str(VIEWER_DIR), html=True), name="viewer")

DATA_DIR = Path("data/kanban")
DATA_DIR.mkdir(parents=True, exist_ok=True)
KANBAN_FILE = DATA_DIR / "board.json"

# Models

class Task(BaseModel):
    id: str
    title: str
    description: Optional[str] = ""
    priority: str = "medium"  # low, medium, high
    tags: List[str] = []

class Column(BaseModel):
    id: str
    title: str
    tasks: List[Task] = []

class Board(BaseModel):
    columns: List[Column]

# Persistence

def load_board() -> Board:
    if not KANBAN_FILE.exists():
        # Default board
        return Board(columns=[
            Column(id="todo", title="To Do", tasks=[]),
            Column(id="in-progress", title="In Progress", tasks=[]),
            Column(id="done", title="Done", tasks=[])
        ])
    
    try:
        with open(KANBAN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return Board(**data)
    except Exception as e:
        print(f"[ERROR] Failed to load board: {e}")
        return Board(columns=[])

def save_board(board: Board):
    with open(KANBAN_FILE, "w", encoding="utf-8") as f:
        json.dump(board.dict(), f, indent=2, ensure_ascii=False)

# API

@app.get("/")
async def root():
    return RedirectResponse(url="/viewer/index.html")

@app.get("/api/board")
async def get_board():
    return load_board()

@app.post("/api/board")
async def update_board(board: Board):
    save_board(board)
    return {"status": "saved"}

@app.get("/api/health")
async def api_health():
    return {"status": "ok", "module": "kanban"}

# Entry point

def launch():
    import uvicorn
    import os
    from core.utils.port_manager import PortManager
    base_port = int(os.getenv("KANBAN_PORT", "8090"))
    port = PortManager.bind_port("Aethvion Kanban", base_port)
    print(f"  Aethvion Kanban  →  http://localhost:{port}")
    try:
        from core.utils.browser import open_app_window
        open_app_window(f"http://localhost:{port}", delay=1.5)
    except Exception:
        pass
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    launch()
