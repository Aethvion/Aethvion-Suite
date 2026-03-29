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
    type: str  # "file" | "function" | "dir"
    path: str
    language: str = "python"
    size: int = 1

class Link(BaseModel):
    source: str
    target: str
    type: str  # "import" | "call" | "contains"

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
        self.function_defs: Dict[str, str] = {} # name -> func_id

    def scan(self, target_path: Optional[Path] = None):
        target = target_path or self.root
        self.nodes = {}
        self.links = []
        self.function_defs = {}
        
        logger.info(f"LinkMap: Scanning project at {target}")
        
        # 1. Create root directory node
        rel_root = str(target.relative_to(self.root)).replace("\\", "/")
        if rel_root == ".": rel_root = ""
        root_id = f"dir:{rel_root}"
        self.nodes[root_id] = Node(id=root_id, name=target.name or "root", type="dir", path=rel_root)

        # 2. Supported extensions
        extensions = [".py", ".js", ".ts", ".jsx", ".tsx"]
        files_found = 0
        
        # 3. First pass: Collect all files and directories to build the tree
        for dirpath, dirnames, filenames in os.walk(target):
            d_path = Path(dirpath)
            if any(part.startswith(".") or part in ["__pycache__", "node_modules", "venv", ".venv", "dist", "build"] for part in d_path.parts):
                continue
                
            rel_dir = str(d_path.relative_to(self.root)).replace("\\", "/")
            if rel_dir == ".": rel_dir = ""
            dir_id = f"dir:{rel_dir}"
            
            # Ensure directory node exists
            if dir_id not in self.nodes:
                self.nodes[dir_id] = Node(id=dir_id, name=d_path.name, type="dir", path=rel_dir)
                
            # Link to parent directory
            if d_path != target:
                parent_rel = str(d_path.parent.relative_to(self.root)).replace("\\", "/")
                if parent_rel == ".": parent_rel = ""
                parent_id = f"dir:{parent_rel}"
                if parent_id in self.nodes:
                    self.links.append(Link(source=parent_id, target=dir_id, type="contains"))

            for f in filenames:
                f_path = d_path / f
                if f_path.suffix.lower() in extensions:
                    rel_f = str(f_path.relative_to(self.root)).replace("\\", "/")
                    file_id = f"file:{rel_f}"
                    
                    # Create File Node
                    ext = f_path.suffix.lower()[1:]
                    self.nodes[file_id] = Node(
                        id=file_id, name=f, type="file", path=rel_f, language=ext
                    )
                    
                    # Link file to current directory
                    self.links.append(Link(source=dir_id, target=file_id, type="contains"))
                    files_found += 1

        # 4. Second pass: Deep analysis (Python symbols)
        for node_id, node in list(self.nodes.items()):
            if node.type == "file" and node.language == "python":
                full_path = self.root / node.path
                self._analyze_python_file(full_path)
            
        logger.info(f"LinkMap: Scan complete. Found {files_found} files, {len(self.nodes)} nodes, {len(self.links)} links.")
        return {"nodes": [n.dict() for n in self.nodes.values()], "links": [l.dict() for l in self.links]}

    def _analyze_python_file(self, file_path: Path):
        rel_path = str(file_path.relative_to(self.root)).replace("\\", "/")
        file_id = f"file:{rel_path}"
        
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)
            
            # Sub-pass 1: Discover all function definitions
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_id = f"func:{rel_path}:{node.name}"
                    self.nodes[func_id] = Node(
                        id=func_id, name=node.name, type="function", path=rel_path, language="python"
                    )
                    self.function_defs[node.name] = func_id
                    # Link file to function
                    self.links.append(Link(source=file_id, target=func_id, type="contains"))
                
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    self._handle_import(node, file_id)

            # Sub-pass 2: Discover calls
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    source_func_id = f"func:{rel_path}:{node.name}"
                    for subnode in ast.walk(node):
                        if isinstance(subnode, ast.Call):
                            self._handle_call(subnode, source_func_id)

        except Exception as e:
            logger.warning(f"Failed to analyze Python file {file_path}: {e}")

    def _analyze_generic_file(self, file_path: Path):
        # Already handled in the first pass
        pass

    def _handle_import(self, node, source_file_id: str):
        if isinstance(node, ast.Import):
            for alias in node.names:
                self._link_import(source_file_id, alias.name)
        elif isinstance(node, ast.ImportFrom):
            self._link_import(source_file_id, node.module or "")

    def _link_import(self, source_id: str, module_name: str):
        parts = module_name.split(".")
        potential_path = self.root / "/".join(parts)
        
        target_id = None
        if potential_path.with_suffix(".py").exists():
            rel = str(potential_path.with_suffix(".py").relative_to(self.root)).replace("\\", "/")
            target_id = f"file:{rel}"
        elif potential_path.is_dir() and (potential_path / "__init__.py").exists():
            rel = str((potential_path / "__init__.py").relative_to(self.root)).replace("\\", "/")
            target_id = f"file:{rel}"
            
        if target_id and target_id in self.nodes:
            self.links.append(Link(source=source_id, target=target_id, type="import"))

    def _handle_call(self, node: ast.Call, source_func_id: str):
        target_name = None
        if isinstance(node.func, ast.Name):
            target_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            target_name = node.func.attr
            
        if target_name and target_name in self.function_defs:
            target_id = self.function_defs[target_name]
            # Avoid self-calls and duplicates
            if target_id != source_func_id:
                # Check for existing link
                exists = any(l.source == source_func_id and l.target == target_id for l in self.links)
                if not exists:
                    self.links.append(Link(source=source_func_id, target=target_id, type="call"))

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
