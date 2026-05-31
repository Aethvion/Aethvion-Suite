"""
core/interfaces/dashboard/routes/workspace_routes.py
══════════════════════════════════════════════════════
API routes for workspace file management and exploration.
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import os
import subprocess
import sys
import mimetypes
from core.utils import get_logger

from core.utils.paths import WS_OUTPUTS, WS_MEDIA, WS_UPLOADS

logger = get_logger(__name__)
router = APIRouter(prefix="/api/workspace", tags=["workspace"])

# Global cache for workspace files to avoid redundant disk scans
FILES_CACHE = {}

class SemanticSearchRequest(BaseModel):
    query: str
    limit: int = 10
    domain: Optional[str] = None

class ExplorerOpenRequest(BaseModel):
    path: str

def _get_subdir_for_category(category: str) -> str:
    """Helper to map categories to subdirectories."""
    if category in ['files', 'output']:
        return str(WS_OUTPUTS)
    elif category == 'screenshots':
        return str(WS_MEDIA / "screenshots")
    elif category == 'camera':
        return str(WS_MEDIA / "webcam")
    elif category == 'uploads':
        return str(WS_UPLOADS)
    return str(WS_OUTPUTS)

@router.get("/files")
async def list_workspace_files(category: str = 'output', refresh: bool = False):
    """List files recursively based on category with optional caching."""
    global FILES_CACHE
    try:
        from core.workspace.workspace_manager import WorkspaceManager
        project_root = Path(__file__).parent.parent.parent.parent.parent
        
        # Check cache if not refreshing
        if not refresh and FILES_CACHE:
            all_data = FILES_CACHE.get('data')
            if all_data:
                sub_dir = _get_subdir_for_category(category)
                filtered_files = [
                    f for f in all_data.get('files', []) 
                    if f['path'].startswith(sub_dir) or f['path'].startswith(sub_dir.replace('/', '\\'))
                ]
                
                total_files = sum(1 for f in filtered_files if not f.get('is_dir'))
                stats = {}
                for f in filtered_files:
                    if not f.get('is_dir'):
                        ext = f.get('file_type', 'txt')
                        stats[ext] = stats.get(ext, 0) + 1
                
                stats_percentages = {}
                if total_files > 0:
                    for ext, count in stats.items():
                        stats_percentages[ext] = round((count / total_files) * 100, 1)
                        
                return {
                    "count": len(filtered_files),
                    "files": filtered_files,
                    "stats": stats_percentages,
                    "cached": True
                }

        manager = WorkspaceManager(workspace_root=project_root, create_dirs=False)
        all_data = manager.list_outputs()
        
        FILES_CACHE = {
            'timestamp': datetime.now().timestamp(),
            'data': all_data
        }
        
        sub_dir = _get_subdir_for_category(category)
        filtered_files = [
            f for f in all_data.get('files', []) 
            if f['path'].startswith(sub_dir) or f['path'].startswith(sub_dir.replace('/', '\\'))
        ]
        
        total_files = sum(1 for f in filtered_files if not f.get('is_dir'))
        stats = {}
        for f in filtered_files:
            if not f.get('is_dir'):
                ext = f.get('file_type', 'txt')
                stats[ext] = stats.get(ext, 0) + 1
        
        stats_percentages = {}
        if total_files > 0:
            for ext, count in stats.items():
                stats_percentages[ext] = round((count / total_files) * 100, 1)
                
        return {
            "count": len(filtered_files),
            "files": filtered_files,
            "stats": stats_percentages,
            "cached": False
        }
        
    except Exception as e:
        logger.error(f"Workspace file listing error for category {category}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/files/search")
async def search_workspace_files(req: SemanticSearchRequest):
    """Semantically search workspace files."""
    try:
        from core.memory.file_vector_store import get_file_vector_store
        from core.workspace import get_workspace_manager
        
        store = get_file_vector_store()
        workspace = get_workspace_manager()
        
        if store.collection.count() == 0:
            logger.info("Semantic index is empty, performing initial index...")
            all_files_data = workspace.list_outputs()
            all_files = all_files_data.get('files', [])
            for f in all_files:
                if not f.get('is_dir'):
                    path = workspace.workspace_root / f['path']
                    if path.exists():
                        try:
                            content = path.read_text(encoding='utf-8', errors='ignore')
                            store.index_file(f['path'], content, {"domain": f['domain']})
                        except Exception as e:
                            logger.debug(f"File index error for {f['path']!r}: {e}")
                            continue
        
        results = store.search(req.query, limit=req.limit, domain=req.domain)
        
        all_metadata_data = workspace.list_outputs()
        all_metadata = all_metadata_data.get('files', [])
        meta_map = {f['path']: f for f in all_metadata}
        
        enriched_results = []
        for r in results:
            path = r['path']
            if path in meta_map:
                enriched_results.append({
                    **meta_map[path],
                    "relevance": round(1.0 - (r['score'] / 2.0), 3),
                    "excerpt": r['excerpt']
                })
        
        return {"results": enriched_results, "count": len(enriched_results)}
    except Exception as e:
        logger.error(f"Semantic file search error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/files/reindex")
async def reindex_workspace_files():
    """Manually trigger a full re-index of workspace files."""
    try:
        from core.memory.file_vector_store import get_file_vector_store
        from core.workspace import get_workspace_manager
        
        store = get_file_vector_store()
        workspace = get_workspace_manager()
        
        store.client.delete_collection("workspace_files")
        store.collection = store.client.create_collection("workspace_files")
        
        all_files_data = workspace.list_outputs()
        all_files = all_files_data.get('files', [])
        indexed_count = 0
        for f in all_files:
            if not f.get('is_dir'):
                path = workspace.workspace_root / f['path']
                if path.exists():
                    try:
                        content = path.read_text(encoding='utf-8', errors='ignore')
                        if store.index_file(f['path'], content, {"domain": f['domain']}):
                            indexed_count += 1
                    except Exception as e:
                        logger.debug(f"File reindex error for {f['path']!r}: {e}")
                        continue
        
        return {"status": "success", "indexed_count": indexed_count}
    except Exception as e:
        logger.error(f"Re-indexing error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/explorer/open")
async def open_in_explorer(req: ExplorerOpenRequest):
    """Open a file or folder in the system's external explorer."""
    try:
        project_root = Path(__file__).parent.parent.parent.parent.parent
        target_path = project_root / req.path
        if not target_path.exists():
            raise HTTPException(status_code=404, detail=f"Path not found: {req.path}")
            
        target_str = str(target_path.resolve())
        
        if os.name == 'nt':
            if target_path.is_file():
                subprocess.Popen(f'explorer /select,"{target_str}"')
            else:
                os.startfile(target_str)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', '-R', target_str] if target_path.is_file() else ['open', target_str])
        else:
            subprocess.Popen(['xdg-open', target_str if target_path.is_dir() else str(target_path.parent)])
            
        return {"status": "success", "opened": req.path}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        logger.error(f"Explorer open error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files/{domain}/{filename}")
async def download_workspace_file(domain: str, filename: str):
    """Download workspace file."""
    try:
        from core.workspace import get_workspace_manager
        workspace = get_workspace_manager()
        file_path = workspace.get_output_path(domain, filename)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {domain}/{filename}")
        return FileResponse(path=str(file_path), filename=filename, media_type="application/octet-stream")
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        logger.error(f"File download error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files/serve")
async def serve_workspace_file(path: str):
    """Serve a workspace file directly (useful for image previews)."""
    try:
        project_root = Path(__file__).parent.parent.parent.parent.parent
        file_path = project_root / path
        
        try:
            resolved_path = file_path.resolve()
            project_resolved = project_root.resolve()
            if not str(resolved_path).startswith(str(project_resolved)):
                raise HTTPException(status_code=403, detail="Access denied")
        except (Exception, ValueError):
            raise HTTPException(status_code=403, detail="Invalid path")

        if not resolved_path.exists() or not resolved_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
            
        return FileResponse(path=str(resolved_path))
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        logger.error(f"File serve error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files/content")
async def get_workspace_file_content(path: str):
    """Serve the content of a file from the workspace data directory."""
    try:
        requested_path = Path(path).resolve()
        project_root = Path(__file__).parent.parent.parent.parent.parent.resolve()
        data_parent = (project_root / "data").resolve()
        
        if not str(requested_path).startswith(str(data_parent)):
            logger.warning(f"Unauthorized path access attempt: {path}")
            raise HTTPException(status_code=403, detail="Unauthorized: Path outside of workspace data.")

        if not requested_path.exists() or not requested_path.is_file():
            logger.warning(f"File not found: {path}")
            raise HTTPException(status_code=404, detail="File not found.")

        mime_type, _ = mimetypes.guess_type(str(requested_path))
        if not mime_type:
            mime_type = "application/octet-stream"

        return FileResponse(str(requested_path), media_type=mime_type)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving file content: {e}")
        raise HTTPException(status_code=500, detail=str(e))
