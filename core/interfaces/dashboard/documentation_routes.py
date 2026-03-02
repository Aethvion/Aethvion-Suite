from fastapi import APIRouter, HTTPException
from pathlib import Path
import os
from typing import Dict, List, Any

router = APIRouter(prefix="/api/documentation", tags=["Documentation"])

PROJECT_ROOT = Path("c:/Aethvion/Misaka-Cipher")
EXCLUDE_DIRS = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', '.gemini', 'data'}

@router.get("")
async def get_documentation():
    """Scan the repository for Markdown files and group them by folder."""
    try:
        docs_grouped = {}
        
        for root, dirs, files in os.walk(PROJECT_ROOT):
            # Modifying dirs in-place to skip excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            
            md_files = [f for f in files if f.lower().endswith('.md')]
            if not md_files:
                continue
                
            rel_root = os.path.relpath(root, PROJECT_ROOT)
            if rel_root == ".":
                display_folder = "Root"
            else:
                display_folder = rel_root.replace("\\", "/")
                
            if display_folder not in docs_grouped:
                docs_grouped[display_folder] = []
                
            for filename in md_files:
                file_path = Path(root) / filename
                try:
                    content = file_path.read_text(encoding="utf-8")
                    docs_grouped[display_folder].append({
                        "name": filename,
                        "path": os.path.relpath(file_path, PROJECT_ROOT).replace("\\", "/"),
                        "content": content
                    })
                except Exception as e:
                    # Skip files that can't be read
                    continue
                    
        return {"docs": docs_grouped}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to scan documentation: {str(e)}")
