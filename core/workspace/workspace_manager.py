"""
Misaka Cipher - Workspace Manager
Manages user-facing output files in outputfiles
"""

from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import shutil
import json

from core.utils import get_logger

logger = get_logger(__name__)


@dataclass
class FileInfo:
    """Information about an output file."""
    path: str
    filename: str
    domain: str
    size_bytes: int
    created_at: str
    trace_id: Optional[str] = None
    file_type: str = ""
    is_dir: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            'path': self.path.replace('\\', '/'),
            'filename': self.filename,
            'domain': self.domain,
            'size_bytes': self.size_bytes,
            'created_at': self.created_at,
            'trace_id': self.trace_id,
            'file_type': self.file_type,
            'is_dir': self.is_dir
        }
    

class WorkspaceManager:
    """
    Workspace Manager - Output file organization for user deliverables.
    
    Manages user-facing output files in outputfiles with automatic domain
    organization. Does NOT manage AI code/tools (those stay in their normal locations).
    
    Scope:
    - Manages: User deliverables (reports, PDFs, CSVs, analysis results)
    - Does NOT manage: Tools (tools/generated/), agent code, system files
    """
    
    ALLOWED_DOMAINS = ['Finance', 'System', 'Data', 'Code', 'Audio', 'General']
    
    def __init__(self, workspace_root: Optional[Path] = None, create_dirs: bool = True):
        """
        Initialize Workspace Manager.
        """
        self.project_root = Path(__file__).parent.parent.parent
        
        if workspace_root is None:
            workspace_root = self.project_root / "data" / "outputfiles"
        
        self.workspace_root = Path(workspace_root)
        
        # Create workspace and domain subdirectories if requested
        if create_dirs:
            self._initialize_workspace()
        
        logger.info(f"Workspace Manager initialized (root: {self.workspace_root})")
    
    def _initialize_workspace(self):
        """Create workspace directory structure."""
        # Create root
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        
        # Create domain subdirectories
        for domain in self.ALLOWED_DOMAINS:
            domain_path = self.workspace_root / domain
            domain_path.mkdir(exist_ok=True)
            logger.debug(f"Initialized domain directory: {domain}")
    
    def get_output_path(self, domain: str, filename: str) -> Path:
        """
        Get suggested output path for a file.
        
        Args:
            domain: Domain category (Finance, System, Data, etc.)
            filename: Desired filename
            
        Returns:
            Full path in outputfiles/{domain}/{filename}
        """
        # Normalize domain
        if domain not in self.ALLOWED_DOMAINS:
            logger.warning(f"Unknown domain '{domain}', using 'General'")
            domain = 'General'
        
        # Ensure domain directory exists
        domain_path = self.workspace_root / domain
        domain_path.mkdir(parents=True, exist_ok=True)
        
        return domain_path / filename
    
    def save_output(
        self, 
        domain: str, 
        filename: str, 
        content: bytes,
        trace_id: Optional[str] = None
    ) -> Path:
        """
        Save output file to workspace.
        
        Args:
            domain: Domain category
            filename: Filename
            content: File content (bytes)
            trace_id: Optional Trace_ID for tracking
            
        Returns:
            Path to saved file
        """
        output_path = self.get_output_path(domain, filename)
        
        # Write file
        output_path.write_bytes(content)
        
        logger.info(f"Saved output: {output_path} (domain: {domain}, trace: {trace_id})")
        
        # Log to Knowledge Graph if trace_id provided
        if trace_id:
            self.log_output_to_graph(output_path, trace_id, {'domain': domain})
        
        return output_path
    
    def list_outputs(self) -> Dict[str, Any]:
        """
        List output files and folders recursively in outputfiles.
        Returns a dict containing count, files list, and stats breakdown.
        Saves a cache to files.json.
        """
        outputs = []
        stats = {}
        total_files = 0
        
        # Deep recursive scan
        try:
            for file_path in self.workspace_root.rglob('*'):
                # Exclude files.json
                if file_path.name == 'files.json':
                    continue
                    
                relative_path = file_path.relative_to(self.workspace_root)
                domain = relative_path.parts[0] if len(relative_path.parts) > 0 else 'General'
                
                try:
                    stat = file_path.stat()
                    is_dir = file_path.is_dir()
                    
                    file_type = ""
                    if not is_dir:
                        file_type = file_path.suffix.lstrip('.') if file_path.suffix else 'txt'
                        total_files += 1
                        stats[file_type] = stats.get(file_type, 0) + 1
                    
                    file_info = FileInfo(
                        path=str(relative_path),
                        filename=file_path.name,
                        domain=domain,
                        size_bytes=stat.st_size if not is_dir else 0,
                        created_at=datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        file_type=file_type,
                        is_dir=is_dir
                    )
                    
                    outputs.append(file_info)
                except Exception as e:
                    logger.error(f"Error reading file {file_path}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error traversing workspace: {str(e)}")
            
        # Calculate percentages
        stats_percentages = {}
        if total_files > 0:
            for ext, count in stats.items():
                stats_percentages[ext] = round((count / total_files) * 100, 1)
        
        # Ensure outputs are sorted by creation_time descending
        outputs.sort(key=lambda f: f.created_at, reverse=True)
        
        result_dict = {
            "count": len(outputs),
            "files": [output.to_dict() for output in outputs],
            "stats": stats_percentages
        }
        
        # Save cache
        # Always try to save in data/ folder
        cache_dir = self.project_root / "data"
        if not cache_dir.exists():
            cache_dir.mkdir(parents=True, exist_ok=True)
            
        cache_path = cache_dir / "files.json"
        
        # Cleanup old root-level files.json if it exists
        old_root_cache = self.project_root / "files.json"
        if old_root_cache.exists():
            try:
                old_root_cache.unlink()
                logger.info("Removed old files.json from project root")
            except Exception:
                pass

        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(result_dict, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save files.json cache to {cache_path}: {e}")
            
        return result_dict
    
    def get_output_info(self, file_path: Path) -> Optional[FileInfo]:
        """
        Get information about a specific output file.
        
        Args:
            file_path: Path to file (can be relative to workspace_root)
            
        Returns:
            FileInfo or None if file doesn't exist
        """
        # Convert to absolute path if relative
        if not file_path.is_absolute():
            file_path = self.workspace_root / file_path
        
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return None
        
        try:
            stat = file_path.stat()
            
            # Determine domain from path
            relative_path = file_path.relative_to(self.workspace_root)
            domain = relative_path.parts[0] if len(relative_path.parts) > 1 else 'General'
            
            return FileInfo(
                path=str(relative_path),
                filename=file_path.name,
                domain=domain,
                size_bytes=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_ctime).isoformat(),
                file_type=file_path.suffix.lstrip('.')
            )
        except Exception as e:
            logger.error(f"Error getting file info {file_path}: {str(e)}")
            return None
    
    def log_output_to_graph(
        self, 
        file_path: Path, 
        trace_id: str,
        metadata: Optional[Dict] = None
    ):
        """
        Log output file to Knowledge Graph.
        
        Args:
            file_path: Path to output file
            trace_id: Trace_ID that created this file
            metadata: Optional additional metadata
        """
        try:
            from core.memory import get_knowledge_graph
            
            graph = get_knowledge_graph()
            
            # Get file info
            file_info = self.get_output_info(file_path)
            if not file_info:
                logger.warning(f"Cannot log non-existent file: {file_path}")
                return
            
            # Prepare metadata
            file_metadata = metadata or {}
            file_metadata.update({
                'size_bytes': file_info.size_bytes,
                'file_type': file_info.file_type,
                'created_at': file_info.created_at
            })
            
            # Add file node to graph
            graph.add_file_node(
                file_path=file_info.path,
                domain=file_info.domain,
                trace_id=trace_id,
                metadata=file_metadata
            )
            
            logger.info(f"Logged output to Knowledge Graph: {file_info.path}")
            
        except Exception as e:
            logger.error(f"Failed to log output to Knowledge Graph: {str(e)}")
    
    def delete_output(self, file_path: Path) -> bool:
        """
        Delete an output file.
        
        Args:
            file_path: Path to file (can be relative to workspace_root)
            
        Returns:
            True if deleted successfully
        """
        # Convert to absolute path if relative
        if not file_path.is_absolute():
            file_path = self.workspace_root / file_path
        
        try:
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted output: {file_path}")
                return True
            else:
                logger.warning(f"Cannot delete non-existent file: {file_path}")
                return False
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {str(e)}")
            return False


# Global singleton instance
_workspace_manager = None


def get_workspace_manager(workspace_root: Optional[Path] = None, create_dirs: bool = True) -> WorkspaceManager:
    """Get the global WorkspaceManager instance."""
    global _workspace_manager
    if _workspace_manager is None:
        _workspace_manager = WorkspaceManager(workspace_root, create_dirs=create_dirs)
    return _workspace_manager
