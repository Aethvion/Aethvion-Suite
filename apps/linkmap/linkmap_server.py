import os
import sys
import json
import ast
import uuid
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import tkinter as tk
from tkinter import filedialog

# ---------------------------------------------------------------------------
# Bootstrap workspace root & imports
# ---------------------------------------------------------------------------
WORKSPACE_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(WORKSPACE_ROOT))
from core.utils.port_manager import PortManager
from core.utils import get_logger, fastapi_utils

logger = get_logger("AethvionLinkMap")

# ---------------------------------------------------------------------------
# App Configuration
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Aethvion LinkMap — 3D Context Visualization",
    description="Interactive visualization of project dependencies and function calls",
    version="1.0.0",
)
fastapi_utils.add_dev_cache_control(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).parent
DATA_DIR = WORKSPACE_ROOT / "data" / "apps" / "linkmap"
VIEWER_DIR = APP_DIR / "viewer"

for d in [DATA_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ScanRequest(BaseModel):
    path: Optional[str] = None
    force: bool = False

class Node(BaseModel):
    id: str
    name: str
    type: str  # "file" | "function"
    path: str
    language: str = "python"
    size: int = 1

class Link(BaseModel):
    source: str
    target: str
    type: str  # "import" | "call"

class MapData(BaseModel):
    nodes: List[Node]
    links: List[Link]

# ---------------------------------------------------------------------------
# AST Analysis
# ---------------------------------------------------------------------------
class ProjectAnalyzer:
    def __init__(self, root: Path):
        self.root = root
        self.nodes: Dict[str, Node] = {}
        self.links: List[Link] = []
        self.visited_files: Set[str] = set()

    def scan(self, target_path: Optional[Path] = None):
        target = target_path or self.root
        self.nodes = {}
        self.links = []
        
        logger.info(f"LinkMap: Scanning project at {target}")
        
        # Supported extensions
        extensions = [".py", ".js", ".ts", ".jsx", ".tsx"]
        files_found = 0
        
        # Analyze files
        for ext in extensions:
            for f_path in target.rglob(f"*{ext}"):
                if any(part.startswith(".") or part in ["__pycache__", "node_modules", "venv", ".venv", "dist", "build"] for part in f_path.parts):
                    continue
                files_found += 1
                if ext == ".py":
                    self._analyze_python_file(f_path)
                else:
                    self._analyze_generic_file(f_path)
            
        logger.info(f"LinkMap: Scan complete. Found {files_found} files, {len(self.nodes)} nodes, {len(self.links)} links.")
        return {"nodes": [n.dict() for n in self.nodes.values()], "links": [l.dict() for l in self.links]}

    def _analyze_python_file(self, file_path: Path):
        rel_path = str(file_path.relative_to(self.root)).replace("\\", "/")
        file_id = f"file:{rel_path}"
        
        if file_id in self.nodes:
            return
            
        self.nodes[file_id] = Node(
            id=file_id,
            name=file_path.name,
            type="file",
            path=rel_path,
            language="python"
        )
        
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                # Imports
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    self._handle_import(node, file_id)
                
                # Functions
                elif isinstance(node, ast.FunctionDef):
                    func_id = f"func:{rel_path}:{node.name}"
                    self.nodes[func_id] = Node(
                        id=func_id,
                        name=node.name,
                        type="function",
                        path=rel_path,
                        language="python"
                    )
                    # Link file to its functions
                    self.links.append(Link(source=file_id, target=func_id, type="contains"))

        except Exception as e:
            logger.warning(f"Failed to analyze Python file {file_path}: {e}")

    def _analyze_generic_file(self, file_path: Path):
        """Simple node creation for non-python files."""
        rel_path = str(file_path.relative_to(self.root)).replace("\\", "/")
        file_id = f"file:{rel_path}"
        
        if file_id in self.nodes:
            return
            
        ext = file_path.suffix.lower()[1:]
        self.nodes[file_id] = Node(
            id=file_id,
            name=file_path.name,
            type="file",
            path=rel_path,
            language=ext
        )

    def _handle_import(self, node, source_file_id: str):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target_module = alias.name
                self._link_import(source_file_id, target_module)
        elif isinstance(node, ast.ImportFrom):
            target_module = node.module or ""
            self._link_import(source_file_id, target_module)

    def _link_import(self, source_id: str, module_name: str):
        # Heuristic: try to find if it's a local module
        parts = module_name.split(".")
        potential_path = self.root / "/".join(parts)
        
        target_id = None
        if potential_path.with_suffix(".py").exists():
            rel = str(potential_path.with_suffix(".py").relative_to(self.root)).replace("\\", "/")
            target_id = f"file:{rel}"
        elif potential_path.is_dir() and (potential_path / "__init__.py").exists():
            rel = str((potential_path / "__init__.py").relative_to(self.root)).replace("\\", "/")
            target_id = f"file:{rel}"
            
        if target_id:
            self.links.append(Link(source=source_id, target=target_id, type="import"))

    def _handle_call(self, node: ast.Call, source_func_id: str, rel_path: str):
        # Basic call analysis (very simplified)
        target_name = None
        if isinstance(node.func, ast.Name):
            target_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            target_name = node.func.attr
            
        if target_name:
            # We don't know exactly WHICH function it calls if it's from another file
            # But we can link to functions in the SAME file
            local_func_id = f"func:{rel_path}:{target_name}"
            # self.links.append(Link(source=source_func_id, target=local_func_id, type="call"))
            pass

# ---------------------------------------------------------------------------
# Global State
# ---------------------------------------------------------------------------
analyzer = ProjectAnalyzer(WORKSPACE_ROOT)
current_map: dict = {"nodes": [], "links": []}

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = VIEWER_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Aethvion LinkMap</h1><p>Viewer not found.</p>", status_code=404)

if VIEWER_DIR.exists():
    app.mount("/js", StaticFiles(directory=str(VIEWER_DIR / "js")), name="js")
    app.mount("/css", StaticFiles(directory=str(VIEWER_DIR / "css")), name="css")

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.post("/api/fs/browse")
async def browse_folder():
    """Open a native folder picker."""
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(parent=root, title="Select Project Folder")
        root.destroy()
        if folder:
            return {"path": folder.replace("\\", "/")}
        return {"path": None}
    except Exception as e:
        logger.error(f"Browse failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/file/read")
async def read_file(path: str):
    """Read file content."""
    # Ensure path is absolute or relative to WORKSPACE_ROOT
    target = Path(path)
    if not target.is_absolute():
        target = WORKSPACE_ROOT / target
        
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
        
    try:
        content = target.read_text(encoding="utf-8", errors="ignore")
        return {"content": content, "path": str(target)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scan")
async def scan_project(req: ScanRequest = ScanRequest()):
    global current_map
    target_path = Path(req.path) if req.path else WORKSPACE_ROOT
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Path not found")
        
    logger.info(f"Scanning project at {target_path}...")
    # Update analyzer root if a new path is provided
    analyzer.root = target_path
    current_map = analyzer.scan(target_path)
    
    # Save to disk
    save_path = DATA_DIR / "map.json"
    save_path.write_text(json.dumps(current_map, indent=2), encoding="utf-8")
    
    return current_map

@app.get("/api/map")
async def get_map():
    global current_map
    if not current_map["nodes"]:
        save_path = DATA_DIR / "map.json"
        if save_path.exists():
            current_map = json.loads(save_path.read_text(encoding="utf-8"))
    return current_map

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
def launch():
    base_port = int(os.getenv("LINKMAP_PORT", "8089"))
    port = PortManager.bind_port("Aethvion LinkMap", base_port)
    logger.info(f"Aethvion LinkMap → http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    launch()
